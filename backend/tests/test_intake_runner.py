import asyncio
import sys
import unittest
from unittest.mock import patch

from app.schemas.assessments import WorkerRequest
from app.services.intake_runner import run_isolated, MAX_MESSAGE_BYTES
from queue_helpers import snapshot


class IsolatedWorkerTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows selector-loop compatibility")
    async def test_windows_selector_loop_can_run_isolated_worker(self):
        def run_with_selector():
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                return runner.run(run_isolated(WorkerRequest(action="discover", snapshot=snapshot())))
        with patch("app.services.intake_runner.settings.google_service_account_file", "does-not-exist-for-lucid-test.json"):
            result = await asyncio.to_thread(run_with_selector)
        self.assertEqual(result.code, "discovery_failed")

    @unittest.skipUnless(sys.platform == "win32", "Windows selector-loop compatibility")
    async def test_windows_selector_cancellation_still_reaps_child(self):
        def run_with_selector():
            with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
                runner.run(self.run_stub("import time; time.sleep(30)", cancel=True))
        await asyncio.to_thread(run_with_selector)

    async def test_real_child_returns_safe_discovery_failure_without_credentials(self):
        with patch("app.services.intake_runner.settings.google_service_account_file", "does-not-exist-for-lucid-test.json"):
            result = await run_isolated(WorkerRequest(action="discover", snapshot=snapshot()))
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.code, "discovery_failed")
        self.assertNotIn("does-not-exist", result.message)

    async def run_stub(self, code, *, timeout=2, cancel=False):
        original_spawn = asyncio.create_subprocess_exec
        created = []
        spawned = asyncio.Event()

        async def spawn(*args, **kwargs):
            process = await original_spawn(sys.executable, "-c", code, **kwargs)
            created.append(process)
            spawned.set()
            return process

        request = WorkerRequest(action="discover", snapshot=snapshot().model_copy(update={"file_timeout_seconds": timeout}))
        with patch("app.services.intake_runner.asyncio.create_subprocess_exec", side_effect=spawn):
            if cancel:
                task = asyncio.create_task(run_isolated(request))
                await spawned.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                result = None
            else:
                result = await run_isolated(request)
        self.assertIsNotNone(created[0].returncode, "Child process must be reaped")
        return result

    async def test_hard_timeout_kills_and_reaps_hung_child(self):
        result = await self.run_stub("import time; time.sleep(30)", timeout=1)
        self.assertEqual(result.code, "processing_timeout")

    async def test_cancellation_kills_and_reaps_child(self):
        await self.run_stub("import time; time.sleep(30)", cancel=True)

    async def test_invalid_json_is_processing_failure(self):
        result = await self.run_stub("print('not json')")
        self.assertEqual(result.code, "worker_error")

    async def test_excessive_output_kills_child(self):
        result = await self.run_stub(f"import sys; sys.stdout.buffer.write(b'x' * {MAX_MESSAGE_BYTES + 1}); sys.stdout.flush()")
        self.assertEqual(result.code, "worker_error")

    async def test_valid_protocol_result_is_read(self):
        result = await self.run_stub("print('{\"status\":\"failed\",\"code\":\"no_pdfs\",\"message\":\"No PDFs.\"}')")
        self.assertEqual(result.code, "no_pdfs")
