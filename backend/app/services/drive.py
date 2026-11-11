"""Google Drive service — folder validation and file listing via service account."""

from dataclasses import dataclass

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


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
