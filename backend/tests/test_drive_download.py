import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httplib2
from googleapiclient.errors import HttpError

from app.services.drive import download_pdf_file, list_pdf_files
from app.services.processing_errors import ResumeProcessingError


def metadata(**overrides):
    return {"id": "resume_id", "mimeType": "application/pdf", "size": "12",
            "version": "3", "parents": ["job_folder"], "trashed": False, **overrides}


class DriveDownloadTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.files = self.service.files.return_value
        self.files.get.return_value.execute.side_effect = [metadata(), metadata()]
        self.http = Mock()
        self.http.request.return_value = (httplib2.Response({"status": "200", "content-length": "12"}), b"%PDF-content")
        self.files.get_media.return_value = SimpleNamespace(
            uri="https://example.test/media", headers={}, http=self.http,
        )
        self.factory = patch("app.services.drive._get_drive_service", return_value=self.service)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def assert_failure(self, code, **kwargs):
        with self.assertRaises(ResumeProcessingError) as raised:
            download_pdf_file("resume_id", folder_id="job_folder", **kwargs)
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_real_downloader_reads_without_writing_drive(self):
        self.assertEqual(download_pdf_file("resume_id", folder_id="job_folder", expected_version="3"), b"%PDF-content")
        self.files.get_media.assert_called_once_with(fileId="resume_id", supportsAllDrives=True)
        self.assertEqual(self.files.get.call_count, 2)
        self.files.update.assert_not_called()
        self.files.delete.assert_not_called()

    def test_changed_snapshot_version_rejected_before_download(self):
        self.assert_failure("file_changed", expected_version="2")
        self.files.get_media.assert_not_called()

    def test_change_during_download_is_failure(self):
        self.files.get.return_value.execute.side_effect = [metadata(), metadata(version="4")]
        self.assert_failure("file_changed")

    def test_missing_version_is_not_silently_accepted(self):
        self.files.get.return_value.execute.side_effect = [metadata(version=None)]
        self.assert_failure("file_version_unavailable")
        self.files.get_media.assert_not_called()

    def test_metadata_size_limit_before_download(self):
        self.assert_failure("file_too_large", max_bytes=10)
        self.files.get_media.assert_not_called()

    def test_actual_bytes_enforce_limit_when_size_missing(self):
        self.files.get.return_value.execute.side_effect = [metadata(size="0"), metadata(size="0")]
        self.assert_failure("file_too_large", max_bytes=10)

    def test_pdf_must_belong_to_folder_and_not_be_trashed(self):
        for info in (metadata(parents=["other_folder"]), metadata(trashed=True), metadata(parents=[])):
            self.files.get.return_value.execute.side_effect = [info]
            self.assert_failure("file_not_in_folder")
        self.files.get_media.assert_not_called()

    def test_file_moved_during_download_is_failure(self):
        self.files.get.return_value.execute.side_effect = [metadata(), metadata(parents=["other_folder"])]
        self.assert_failure("file_not_in_folder")

    def test_non_pdf_rejected(self):
        self.files.get.return_value.execute.side_effect = [metadata(mimeType="text/plain")]
        self.assert_failure("unsupported_file")

    def test_http_errors_are_safe_failure_codes(self):
        for status, code in ((403, "file_access_denied"), (404, "file_not_found"), (500, "download_failed")):
            self.files.get.return_value.execute.side_effect = HttpError(
                httplib2.Response({"status": str(status)}), b"private credential information",
            )
            error = self.assert_failure(code)
            self.assertNotIn("private", error.message)

    def test_credential_errors_do_not_expose_paths(self):
        self.service.files.side_effect = FileNotFoundError("C:/private/credential.json")
        error = self.assert_failure("download_failed")
        self.assertNotIn("private", error.message)

    def test_invalid_ids_or_limits_are_configuration_errors(self):
        for kwargs in ({"file_id": "bad'id", "folder_id": "job_folder"},
                       {"file_id": "resume_id", "folder_id": "bad'id"},
                       {"file_id": "resume_id", "folder_id": "job_folder", "max_bytes": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                download_pdf_file(**kwargs)
        with self.assertRaises(ValueError):
            list_pdf_files("bad'id")

    def test_real_downloader_follows_multiple_chunks(self):
        self.http.request.side_effect = [
            (httplib2.Response({"status": "206", "content-range": "bytes 0-5/12"}), b"%PDF-c"),
            (httplib2.Response({"status": "206", "content-range": "bytes 6-11/12"}), b"ontent"),
        ]
        self.assertEqual(download_pdf_file("resume_id", folder_id="job_folder"), b"%PDF-content")
        self.assertEqual(self.http.request.call_count, 2)
