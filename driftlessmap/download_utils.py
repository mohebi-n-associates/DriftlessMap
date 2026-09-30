"""Atomic and verifiable HTTP downloads used by atlas dialogs."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse

import requests


MANIFEST_NAME = "download_manifest.json"


class DownloadCancelled(Exception):
    pass


def _manifest_path(destination):
    return Path(destination).parent / MANIFEST_NAME


def read_download_manifest(folder):
    path = Path(folder) / MANIFEST_NAME
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record_download(destination, url, sha256, size):
    """Remember what was downloaded so later downloads can be compared."""
    destination = Path(destination)
    manifest = read_download_manifest(destination.parent)
    manifest[destination.name] = {"url": url, "sha256": sha256, "size_bytes": size}
    path = _manifest_path(destination)
    with tempfile.NamedTemporaryFile(
        "w",
        dir=str(path.parent),
        prefix=".{}-".format(path.name),
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    ) as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)
        temporary = stream.name
    os.replace(temporary, str(path))


def _content_length(response):
    """Return the transferred byte count to expect, or ``None`` if unknown."""
    encoding = (response.headers.get("Content-Encoding") or "identity").lower()
    if encoding not in ("", "identity"):
        # ``iter_content`` decodes transfer compression, so the decoded size
        # cannot be compared with the compressed Content-Length.
        return None
    value = response.headers.get("Content-Length")
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


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
    record_manifest=True,
):
    """Download ``url`` atomically, validating status, length, and checksum.

    With ``record_manifest`` the URL, size and SHA-256 are kept in the
    folder's ``download_manifest.json``. A later download of the same file
    whose bytes differ from the recorded ones fails, so an atlas folder never
    silently mixes files from different upstream releases.
    """
    if urlparse(url).scheme.lower() != "https":
        raise ValueError("Atlas downloads require HTTPS.")

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    response = None
    try:
        response = request_get(
            url,
            stream=True,
            timeout=timeout,
            headers={"Accept-Encoding": "identity"},
        )
        response.raise_for_status()
        hops = [getattr(hop, "url", "") for hop in getattr(response, "history", [])]
        hops.append(getattr(response, "url", url))
        if any(urlparse(hop).scheme.lower() != "https" for hop in hops if hop):
            raise ValueError("Atlas download redirected through an insecure URL.")

        expected_size = _content_length(response)
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
        if record_manifest:
            previous = read_download_manifest(destination.parent).get(destination.name)
            if (
                isinstance(previous, dict)
                and previous.get("url") == url
                and previous.get("sha256")
                and previous["sha256"] != actual_sha256
            ):
                raise IOError(
                    "{} differs from the copy downloaded into this folder "
                    "before, so the upstream file has changed. Use a new "
                    "folder for the new release.".format(destination.name)
                )

        os.replace(str(temporary_path), str(destination))
        temporary_path = None
        if record_manifest:
            _record_download(destination, url, actual_sha256, received)
        if progress is not None:
            progress(100)
        return actual_sha256
    finally:
        if response is not None and hasattr(response, "close"):
            response.close()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def thread_is_running(thread):
    """Return whether a ``QThread`` runs, treating a deleted thread as stopped."""
    if thread is None:
        return False
    try:
        return thread.isRunning()
    except RuntimeError:
        # The C++ object was already released through ``deleteLater``.
        return False
