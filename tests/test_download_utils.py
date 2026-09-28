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



class DownloadHardeningTests(unittest.TestCase):
    def fetch(self, folder, response, name="atlas.nii.gz", **kwargs):
        destination = Path(folder) / name
        download_utils.download_file(
            "https://example.test/file",
            destination,
            request_get=lambda *args, **kw: response,
            **kwargs,
        )
        return destination

    def test_transfer_encoded_bodies_skip_the_compressed_length_check(self):
        response = FakeResponse([b"decoded atlas bytes"], declared_size=7)
        response.headers["Content-Encoding"] = "gzip"
        with tempfile.TemporaryDirectory() as folder:
            destination = self.fetch(folder, response)
            self.assertEqual(destination.read_bytes(), b"decoded atlas bytes")

    def test_non_numeric_length_is_ignored(self):
        response = FakeResponse([b"bytes"])
        response.headers["Content-Length"] = "unknown"
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(self.fetch(folder, response).is_file())

    def test_insecure_redirect_hops_are_rejected(self):
        response = FakeResponse([b"bytes"])
        hop = FakeResponse([])
        hop.url = "http://example.test/insecure"
        response.history = [hop]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "insecure"):
                self.fetch(folder, response)

    def test_manifest_records_downloads_and_catches_changed_upstream_files(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fetch(folder, FakeResponse([b"release one"]))
            manifest = download_utils.read_download_manifest(folder)
            self.assertEqual(
                manifest["atlas.nii.gz"]["sha256"],
                hashlib.sha256(b"release one").hexdigest(),
            )
            self.fetch(folder, FakeResponse([b"release one"]))
            with self.assertRaisesRegex(IOError, "upstream file has changed"):
                self.fetch(folder, FakeResponse([b"release two"]))
            self.assertEqual(
                (Path(folder) / "atlas.nii.gz").read_bytes(), b"release one"
            )

if __name__ == "__main__":
    unittest.main()
