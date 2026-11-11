"""One isolated Drive/PDF operation. JSON stdin/stdout, no candidate logging."""

from dataclasses import asdict
import sys

from pydantic import ValidationError

from app.schemas.assessments import WorkerRequest, SourceFile, Discovered, Failed, Ready, Excluded
from app.services.drive import discover_pdf_files
from app.services.intake import screen_drive_file
from app.services.mandatory_gate import GateRequirement, GATE_VERSION
from app.services.processing_errors import ResumeProcessingError
from app.services.screening import ReadyForAnalysis, ExcludedResume


MAX_MESSAGE_BYTES = 4 * 1024 * 1024


def execute(request: WorkerRequest):
    snapshot = request.snapshot
    if snapshot.gate_version != GATE_VERSION:
        return Failed(code="unsupported_snapshot", message="This worker does not support the assessment's saved gate version.")
    if request.action == "discover":
        try:
            entries = discover_pdf_files(snapshot.folder_id, max_files=snapshot.max_files)
            files = [SourceFile.model_validate(entry) for entry in entries]
            if not files:
                return Failed(code="no_pdfs", message="No PDFs were found directly inside the job folder.")
            files.sort(key=lambda entry: (entry.name.casefold(), entry.id))
            if len({entry.id for entry in files}) != len(files):
                return Failed(code="invalid_file_list", message="Drive returned duplicate files; retry the assessment.")
            return Discovered(files=files)
        except ResumeProcessingError as exc:
            return Failed(code=exc.code, message=exc.message)
        except Exception:
            return Failed(code="discovery_failed", message="Could not read the job folder. Check folder sharing and retry.")
    if request.file is None:
        return Failed(code="invalid_worker_request", message="No queued PDF was supplied.")
    outcome = screen_drive_file(
        request.file.id, folder_id=snapshot.folder_id, expected_version=request.file.version,
        requirements=tuple(GateRequirement(s.skill, s.mandatory, tuple(s.aliases)) for s in snapshot.skills),
        limits=snapshot.pdf_limits,
    )
    if isinstance(outcome, ReadyForAnalysis):
        return Ready(document=asdict(outcome.document))
    if isinstance(outcome, ExcludedResume):
        return Excluded(missing_skills=list(outcome.missing_skills))
    return Failed(code=outcome.code, message=outcome.message)


def main():
    try:
        payload = sys.stdin.buffer.read(MAX_MESSAGE_BYTES + 1)
        if len(payload) > MAX_MESSAGE_BYTES:
            raise ValueError("Request exceeds protocol limit")
        request = WorkerRequest.model_validate_json(payload)
        result = execute(request)
    except (ValidationError, ValueError):
        result = Failed(code="unsupported_snapshot", message="The saved assessment input is invalid or unsupported.")
    except Exception:
        result = Failed(code="worker_error", message="This file could not be processed safely.")
    encoded = result.model_dump_json().encode("utf-8")
    if len(encoded) > MAX_MESSAGE_BYTES:
        encoded = Failed(code="result_too_large", message="Extracted document exceeds the result-size limit.").model_dump_json().encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
