"""Killable child-process boundary around native parsing and network calls."""

import asyncio
from concurrent.futures import Future
from contextlib import suppress
import os
from pathlib import Path
import sys

from pydantic import TypeAdapter, ValidationError

from app.schemas.assessments import WorkerRequest, WorkerResult, Failed
from app.core.config import settings


MAX_MESSAGE_BYTES = 4 * 1024 * 1024
BACKEND_DIR = Path(__file__).resolve().parents[2]
result_adapter = TypeAdapter(WorkerResult)


async def run_isolated(request: WorkerRequest) -> WorkerResult:
    # Windows selector loops cannot create subprocess transports. A dedicated
    # Proactor loop keeps this working without changing the server's loop policy.
    if sys.platform == "win32" and isinstance(asyncio.get_running_loop(), asyncio.SelectorEventLoop):
        return await _run_on_windows_proactor(request)
    return await _run_on_current_loop(request)


async def _run_on_windows_proactor(request):
    ready = Future()

    def run():
        try:
            with asyncio.Runner(loop_factory=asyncio.ProactorEventLoop) as runner:
                async def operation():
                    ready.set_result((asyncio.get_running_loop(), asyncio.current_task()))
                    return await _run_on_current_loop(request)
                return runner.run(operation())
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            raise

    task = asyncio.create_task(asyncio.to_thread(run))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        loop, operation = await asyncio.wrap_future(ready)
        with suppress(RuntimeError):  # The operation may have just closed its loop.
            loop.call_soon_threadsafe(operation.cancel)
        with suppress(asyncio.CancelledError):
            await task  # Wait until the child is killed before releasing the DB lease.
        raise


async def _run_on_current_loop(request: WorkerRequest) -> WorkerResult:
    process = None
    try:
        payload = request.model_dump_json().encode("utf-8")
        if len(payload) > MAX_MESSAGE_BYTES:
            return Failed(code="request_too_large", message="Assessment configuration exceeds the worker input limit.")
        environment = os.environ.copy()
        # Pydantic's .env loading does not populate os.environ. Resolve the key
        # relative to the parent so --app-dir launches retain folder-check access.
        if settings.google_service_account_file:
            environment["GOOGLE_SERVICE_ACCOUNT_FILE"] = str(Path(settings.google_service_account_file).expanduser().resolve())
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "app.services.intake_child", cwd=str(BACKEND_DIR),
            env=environment,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def exchange():
            process.stdin.write(payload)
            await process.stdin.drain()
            process.stdin.close()
            chunks = []
            size = 0
            while chunk := await process.stdout.read(64 * 1024):
                size += len(chunk)
                if size > MAX_MESSAGE_BYTES:
                    raise ValueError("Worker output exceeds protocol limit")
                chunks.append(chunk)
            if await process.wait() != 0:
                raise ValueError("Worker did not exit successfully")
            return result_adapter.validate_json(b"".join(chunks))

        return await asyncio.wait_for(exchange(), timeout=request.snapshot.file_timeout_seconds)
    except TimeoutError:
        return Failed(code="processing_timeout", message="Processing exceeded the per-file time limit.")
    except (OSError, ValueError, ValidationError):
        return Failed(code="worker_error", message="The isolated worker could not complete this operation.")
    finally:
        # Also runs on task cancellation. No child survives a clean shutdown.
        if process is not None:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            await process.wait()
