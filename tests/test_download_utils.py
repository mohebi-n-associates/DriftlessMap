import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "download_utils.py"
SPEC = importlib.util.spec_from_file_location("download_utils", MODULE_PATH)
download_utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download_utils)


class FakeResponse:
    def __init__(self, chunks, *, declared_size=None, error=None):
        self.chunks = chunks
        self.headers = {}
        if declared_size is not None:
            self.headers["Content-Length"] = str(declared_size)
        self.error = error
        self.url = "https://example.test/file"
        self.closed = False

    def raise_for_status(self):
        if self.error is not None:
            raise self.error

    def iter_content(self, chunk_size):
        yield from self.chunks

    def close(self):
        self.closed = True


class DownloadTests(unittest.TestCase):
    def test_success_is_atomic_and_reports_verified_progress(self):
        payload = b"atlas-data"
        response = FakeResponse([payload[:5], payload[5:]], declared_size=len(payload))
        progress = []
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "atlas.nrrd"
            digest = download_utils.download_file(
                "https://example.test/file",
                destination,
                progress=progress.append,
                expected_sha256=hashlib.sha256(payload).hexdigest(),
                request_get=lambda *args, **kwargs: response,
            )
            self.assertEqual(destination.read_bytes(), payload)
            self.assertFalse(list(Path(folder).glob("*.part")))

        self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
        self.assertEqual(progress[-1], 100)
        self.assertTrue(response.closed)

    def test_incomplete_download_does_not_replace_existing_file(self):
        response = FakeResponse([b"short"], declared_size=20)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "atlas.nrrd"
            destination.write_bytes(b"known-good")
            with self.assertRaises(IOError):
                download_utils.download_file(
                    "https://example.test/file",
                    destination,
                    request_get=lambda *args, **kwargs: response,
                )
            self.assertEqual(destination.read_bytes(), b"known-good")

    def test_plain_http_is_rejected_before_request(self):
        with self.assertRaises(ValueError):
            download_utils.download_file(
                "http://example.test/file", "unused", request_get=lambda: None
            )


if __name__ == "__main__":
    unittest.main()
