"""Google Drive service — folder validation and file listing via service account."""

from dataclasses import dataclass
from io import BytesIO
import re

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.core.config import settings
from app.services.processing_errors import ResumeProcessingError

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _validate_drive_id(value: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise ValueError("Invalid Google Drive ID")


@dataclass
class FolderInfo:
    """Result of a successful folder access check."""
    folder_id: str
    name: str
    pdf_count: int


@dataclass
class FolderError:
    """Result of a failed folder access check."""
    message: str
    code: str  # "not_found", "no_access", "not_shared", "invalid", "error"


def _get_drive_service():
    """Build an authenticated Drive API service using the service account."""
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def get_service_account_email() -> str:
    """Return the service account email for display in the UI."""
    credentials = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=SCOPES
    )
    return credentials.service_account_email


def check_folder_access(folder_id: str) -> FolderInfo | FolderError:
    """
    Verify that the service account can access the folder and count PDFs.

    Returns FolderInfo on success, FolderError on failure.
    """
    try:
        service = _get_drive_service()

        # 1. Check folder exists and is accessible
        try:
            folder = service.files().get(
                fileId=folder_id,
                fields="id,name,mimeType",
                supportsAllDrives=True,
            ).execute()
        except HttpError as e:
            if e.resp.status == 404:
                return FolderError(
                    message="Folder not found. Check the link and ensure "
                            "the folder is shared with the service account.",
                    code="not_found",
                )
            if e.resp.status == 403:
                return FolderError(
                    message="Access denied. Share the folder with the "
                            "service account email as Viewer.",
                    code="no_access",
                )
            raise

        # Verify it's actually a folder
        if folder.get("mimeType") != "application/vnd.google-apps.folder":
            return FolderError(
                message="The link points to a file, not a folder.",
                code="invalid",
            )

        # 2. Count PDFs directly inside the folder (no subfolders)
        pdf_count = 0
        page_token = None
        query = (
            f"'{folder_id}' in parents "
            f"and mimeType='application/pdf' "
            f"and trashed=false"
        )

        while True:
            response = service.files().list(
                q=query,
                fields="nextPageToken,files(id)",
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageToken=page_token,
            ).execute()

            pdf_count += len(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return FolderInfo(
            folder_id=folder_id,
            name=folder["name"],
            pdf_count=pdf_count,
        )

    except FileNotFoundError:
        return FolderError(
            message="Service account key file not found. "
                    "Contact the administrator.",
            code="error",
        )
    except Exception as e:
        return FolderError(
            message=f"Unexpected error checking folder access: {e}",
            code="error",
        )


def list_pdf_files(folder_id: str) -> list[dict]:
    """
    List all non-trashed PDF files in the folder.

    Returns a list of dicts with keys: id, name, size, modifiedTime.
    Follows pagination until the full list is obtained.
    """
    _validate_drive_id(folder_id)
    service = _get_drive_service()
    files = []
    page_token = None
    query = (
        f"'{folder_id}' in parents "
        f"and mimeType='application/pdf' "
        f"and trashed=false"
    )

    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken,files(id,name,size,modifiedTime,version)",
            pageSize=1000,
            orderBy="name",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageToken=page_token,
        ).execute()

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


class _LimitedBuffer(BytesIO):
    """Enforce the byte limit even when Drive metadata is absent or stale."""

    def __init__(self, max_bytes: int):
        super().__init__()
        self.max_bytes = max_bytes

    def write(self, data: bytes) -> int:
        if self.tell() + len(data) > self.max_bytes:
            raise ResumeProcessingError("file_too_large", "PDF exceeds the configured file-size limit.")
        return super().write(data)


def download_pdf_file(
    file_id: str,
    *,
    folder_id: str,
    max_bytes: int = 10 * 1024 * 1024,
    expected_version: str | None = None,
) -> bytes:
    """Read a PDF directly inside the job folder, without modifying Drive.

    Check the version before/after reading to avoid silently screening a file
    changed since queue discovery. Ownership of the job/folder must already
    have been verified by the caller; this service is not an API endpoint.
    """
    _validate_drive_id(file_id)
    _validate_drive_id(folder_id)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    try:
        service = _get_drive_service()
        files = service.files()

        def metadata():
            return files.get(
                fileId=file_id,
                fields="id,mimeType,size,version,parents,trashed",
                supportsAllDrives=True,
            ).execute()

        def validate(info):
            if info.get("trashed") or folder_id not in info.get("parents", []):
                raise ResumeProcessingError("file_not_in_folder", "The PDF is no longer in the job's folder.")
            if info.get("mimeType") != "application/pdf":
                raise ResumeProcessingError("unsupported_file", "Only PDF files can be screened.")
            if int(info.get("size", 0)) > max_bytes:
                raise ResumeProcessingError("file_too_large", "PDF exceeds the configured file-size limit.")

        before = metadata()
        validate(before)
        version = before.get("version")
        if not isinstance(version, str) or not version:
            raise ResumeProcessingError("file_version_unavailable", "The PDF's version could not be verified.")
        if expected_version is not None and version != expected_version:
            raise ResumeProcessingError("file_changed", "The PDF changed after it was added to the assessment.")

        with _LimitedBuffer(max_bytes) as buffer:
            request = files.get_media(fileId=file_id, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(buffer, request, chunksize=min(max_bytes, 256 * 1024))
            done = False
            while not done:
                _, done = downloader.next_chunk(num_retries=2)
            after = metadata()
            validate(after)
            if after.get("version") != version:
                raise ResumeProcessingError("file_changed", "The PDF changed while it was being downloaded.")
            return buffer.getvalue()
    except ResumeProcessingError:
        raise
    except HttpError as exc:
        if exc.resp.status == 404:
            code, message = "file_not_found", "The PDF was removed or is no longer accessible."
        elif exc.resp.status == 403:
            code, message = "file_access_denied", "The service account cannot download this PDF."
        else:
            code, message = "download_failed", "Google Drive could not provide this PDF."
        raise ResumeProcessingError(code, message) from exc
    except Exception as exc:
        # Never return credential paths, HTTP bodies, or candidate data.
        raise ResumeProcessingError("download_failed", "The PDF could not be downloaded.") from exc
