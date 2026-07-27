"""Atomic and verifiable HTTP downloads used by atlas dialogs."""

import hashlib
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

import requests


class DownloadCancelled(Exception):
    pass


def download_file(
    url,
    destination,
    *,
    progress=None,
    cancelled=None,
    expected_sha256=None,
    timeout=(15, 60),
    chunk_size=1024 * 1024,
    request_get=requests.get,
):
    """Download ``url`` atomically, validating status, length, and checksum."""
    if urlparse(url).scheme.lower() != "https":
        raise ValueError("Atlas downloads require HTTPS.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    response = None
    try:
        response = request_get(url, stream=True, timeout=timeout)
        response.raise_for_status()
        final_url = getattr(response, "url", url)
        if urlparse(final_url).scheme.lower() != "https":
            raise ValueError("Atlas download redirected to an insecure URL.")

        content_length = response.headers.get("Content-Length")
        expected_size = int(content_length) if content_length else None
        digest = hashlib.sha256()
        received = 0
        with tempfile.NamedTemporaryFile(
            dir=str(destination.parent),
            prefix=".{}-".format(destination.name),
            suffix=".part",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            for chunk in response.iter_content(chunk_size=chunk_size):
                if cancelled is not None and cancelled():
                    raise DownloadCancelled("Download cancelled.")
                if not chunk:
                    continue
                stream.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress is not None and expected_size:
                    progress(min(99, int(received / expected_size * 100)))

        if received == 0:
            raise IOError("Server returned an empty file.")
        if expected_size is not None and received != expected_size:
            raise IOError(
                "Incomplete download: expected {} bytes, received {}.".format(
                    expected_size, received
                )
            )
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            raise IOError("Downloaded file failed SHA-256 verification.")

        os.replace(str(temporary_path), str(destination))
        temporary_path = None
        if progress is not None:
            progress(100)
        return actual_sha256
    finally:
        if response is not None and hasattr(response, "close"):
            response.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
