"""Reproducible references and portable source payloads.

The project archive deliberately does not copy a processed volume atlas.  This
module records enough information to find and verify linked inputs instead of
silently accepting whatever happens to exist at an old absolute path.
"""

from datetime import datetime, timezone
import copy
import hashlib
import json
import os
from pathlib import Path
import pickle
import struct

import numpy as np

from .persistence import ArchiveAttachment, read_inert_pickle


REFERENCE_SCHEMA_VERSION = 1
_REFERENCE_CACHE: dict = {}
ATLAS_IDENTITY_FILES = (
    "atlas_axis_info.pkl",
    "atlas_labels.pkl",
    "atlas_pre_made.pkl",
    "segment_pre_made.pkl",
    "atlas_meshdata.pkl",
    "atlas_small_meshdata.pkl",
    "contour_pre_made.pkl",
    "sagital_contour_pre_made.pkl",
    "coronal_contour_pre_made.pkl",
    "horizontal_contour_pre_made.pkl",
)
# The files that are the atlas: its axes, regions, template and annotation.
# The others (meshes, region outlines) are drawn from these for display, and
# differ between computers that processed the same atlas, so results never
# depend on them and they are not checked.
ATLAS_CONTENT_FILES = (
    "atlas_axis_info.pkl",
    "atlas_labels.pkl",
    "atlas_pre_made.pkl",
    "segment_pre_made.pkl",
)
# Every pickle protocol a processed atlas may have been written with: 5 now,
# 4 before DriftlessMap 1.4.35, older ones by HERBS.
ATLAS_PICKLE_PROTOCOLS = (5, 4, 3, 2)
CONTENT_DIGEST_PREFIX = b"driftlessmap-atlas-content-1\n"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(file_path, chunk_size=8 * 1024 * 1024):
    digest = hashlib.sha256()
    with open(file_path, "rb") as stream:
        while True:
            chunk = stream.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class _HashingReader:
    """Hashes a file's bytes while a pickle is read from it, in one pass."""

    def __init__(self, stream):
        self._stream = stream
        self._digest = hashlib.sha256()

    def read(self, size=-1):
        data = self._stream.read(size)
        self._digest.update(data)
        return data

    def readline(self):
        data = self._stream.readline()
        self._digest.update(data)
        return data

    def readinto(self, buffer):
        count = self._stream.readinto(buffer)
        if count:
            self._digest.update(memoryview(buffer).cast("B")[:count])
        return count

    def hexdigest(self, chunk_size=8 * 1024 * 1024):
        # Whatever follows the pickle belongs to the file's checksum too.
        while self.read(chunk_size):
            pass
        return self._digest.hexdigest()


class _TooLong(Exception):
    pass


class _HashingWriter:
    """Hashes what is written and gives up once it exceeds ``limit`` bytes."""

    def __init__(self, limit):
        self._digest = hashlib.sha256()
        self._limit = limit
        self.count = 0

    def write(self, data):
        size = memoryview(data).nbytes
        self.count += size
        if self.count > self._limit:
            raise _TooLong()
        self._digest.update(data)
        return size

    def hexdigest(self):
        return self._digest.hexdigest()


def _update_content(digest, value):
    """Feed ``value`` to ``digest`` in a form no encoding or platform changes."""
    if value is None:
        digest.update(b"N")
    elif isinstance(value, (bool, np.bool_)):
        digest.update(b"T" if value else b"F")
    elif isinstance(value, (int, np.integer)):
        digest.update(b"I%d;" % int(value))
    elif isinstance(value, (float, np.floating)):
        digest.update(b"D" + struct.pack("<d", float(value)))
    elif isinstance(value, (complex, np.complexfloating)):
        value = complex(value)
        digest.update(b"C" + struct.pack("<dd", value.real, value.imag))
    elif isinstance(value, str):
        data = value.encode("utf-8", "surrogatepass")
        digest.update(b"S%d;" % len(data))
        digest.update(data)
    elif isinstance(value, (bytes, bytearray)):
        digest.update(b"B%d;" % len(value))
        digest.update(value)
    elif isinstance(value, np.ndarray):
        shape = ",".join(str(int(side)) for side in value.shape).encode("ascii")
        kind = value.dtype.kind
        if kind in "biufc":
            data = np.ascontiguousarray(value, dtype=value.dtype.newbyteorder("<"))
            digest.update(b"A%s%d;%s;" % (kind.encode("ascii"), data.dtype.itemsize, shape))
            digest.update(data)
        elif kind in "OSU":
            # Text and mixed arrays: by their values, whatever the item width.
            digest.update(b"E%s;" % shape)
            for item in value.ravel().tolist():
                _update_content(digest, item)
        else:
            raise TypeError("Unsupported array type {}.".format(value.dtype))
    elif isinstance(value, (list, tuple)):
        digest.update(b"L%d;" % len(value))
        for item in value:
            _update_content(digest, item)
    elif isinstance(value, dict):
        entries = sorted(
            ((_content_bytes(key), item) for key, item in value.items()),
            key=lambda entry: entry[0],
        )
        digest.update(b"M%d;" % len(entries))
        for key, item in entries:
            digest.update(key)
            _update_content(digest, item)
    elif isinstance(value, (set, frozenset)):
        digest.update(b"Z%d;" % len(value))
        for item in sorted(_content_bytes(member) for member in value):
            digest.update(item)
    else:
        raise TypeError("Unsupported value type {}.".format(type(value).__name__))


def _content_bytes(value):
    digest = hashlib.sha256()
    _update_content(digest, value)
    return digest.digest()


def content_digest(value):
    """SHA-256 of what a cache file holds, whatever encoding it was saved in.

    Arrays count by type, shape and little-endian values; sequences by their
    items in order (a list and a tuple are the same); dictionaries and sets
    by their entries in any order. Raises ``TypeError`` for other values.
    """
    digest = hashlib.sha256(CONTENT_DIGEST_PREFIX)
    _update_content(digest, value)
    return digest.hexdigest()


def hash_file_and_content(file_path):
    """Return a cache file's ``(sha256, content digest)``, read once.

    The content digest is None when the file is not an inert pickle of
    supported values; its checksum is still given.
    """
    try:
        with open(file_path, "rb") as stream:
            reader = _HashingReader(stream)
            value = read_inert_pickle(reader)
            byte_hash = reader.hexdigest()
    except OSError:
        raise
    except Exception:
        return sha256_file(file_path), None
    try:
        return byte_hash, content_digest(value)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return byte_hash, None


def _relative_hint(path, project_path):
    if project_path is None:
        return None
    try:
        return os.path.relpath(str(path), str(Path(project_path).resolve().parent))
    except (OSError, ValueError):
        return None


def _file_record(path, relative_path, with_content=False):
    stat = path.stat()
    record = {
        "path": relative_path,
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }
    if with_content:
        record["sha256"], content = hash_file_and_content(path)
        if content is not None:
            record["content_sha256"] = content
    else:
        record["sha256"] = sha256_file(path)
    return record


def _directory_files(path, included_names=None):
    if included_names is None:
        return sorted(
            item for item in path.rglob("*") if item.is_file() and not item.is_symlink()
        )
    return [
        path / name
        for name in included_names
        if (path / name).is_file() and not (path / name).is_symlink()
    ]


def _safe_relative_path(value):
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("Reference contains an unsafe relative path.")
    return relative


def path_stat_signature(path, included_names=None):
    """Capture cheap mutation evidence at the moment an input is loaded."""
    root = Path(path).expanduser().resolve()
    if root.is_file():
        stat = root.stat()
        return (
            "file",
            int(stat.st_size),
            int(stat.st_mtime_ns),
            int(stat.st_ctime_ns),
        )
    if root.is_dir():
        return (
            "directory",
            tuple(
                (
                    item.relative_to(root).as_posix(),
                    int(item.stat().st_size),
                    int(item.stat().st_mtime_ns),
                    int(item.stat().st_ctime_ns),
                )
                for item in _directory_files(root, included_names)
            ),
        )
    raise FileNotFoundError(str(root))


def describe_path(path, project_path=None, included_names=None, content_names=()):
    """Describe a file or directory using relocatable hints and SHA-256 data.

    Files of a directory named in ``content_names`` also get a
    ``content_sha256`` (:func:`content_digest`).
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(str(root))

    reference = {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "kind": "directory" if root.is_dir() else "file",
        "name": root.name,
        "absolute_path": str(root),
        "relative_path": _relative_hint(root, project_path),
    }
    if root.is_file():
        stat = root.stat()
        cache_key = (
            "file",
            str(root),
            int(stat.st_size),
            int(stat.st_mtime_ns),
            int(stat.st_ctime_ns),
        )
        record = _REFERENCE_CACHE.get(cache_key)
        if record is None:
            record = _file_record(root, root.name)
            _REFERENCE_CACHE[cache_key] = copy.deepcopy(record)
        reference.update(
            {
                "size_bytes": record["size_bytes"],
                "mtime_ns": record["mtime_ns"],
                "sha256": record["sha256"],
            }
        )
        return reference

    files = _directory_files(root, included_names)
    signature = tuple(
        (
            item.relative_to(root).as_posix(),
            int(item.stat().st_size),
            int(item.stat().st_mtime_ns),
            int(item.stat().st_ctime_ns),
        )
        for item in files
    )
    cache_key = ("directory", str(root), signature, tuple(content_names))
    records = _REFERENCE_CACHE.get(cache_key)
    if records is None:
        records = [
            _file_record(
                item,
                item.relative_to(root).as_posix(),
                with_content=item.relative_to(root).as_posix() in content_names,
            )
            for item in files
        ]
        _REFERENCE_CACHE[cache_key] = copy.deepcopy(records)
    else:
        records = copy.deepcopy(records)
    identity = [
        (record["path"], record["size_bytes"], record["sha256"])
        for record in records
    ]
    reference["files"] = records
    reference["size_bytes"] = sum(record["size_bytes"] for record in records)
    reference["sha256"] = hashlib.sha256(
        json.dumps(identity, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return reference


def describe_atlas_path(path, project_path=None):
    reference = describe_path(
        path,
        project_path=project_path,
        included_names=ATLAS_IDENTITY_FILES,
        content_names=ATLAS_CONTENT_FILES,
    )
    if not reference.get("files"):
        raise ValueError("Atlas folder contains no recognized identity files.")
    return reference


def candidate_paths(reference, project_path=None, extra=()):
    """Return unique relocation candidates, preferring the project-relative hint.

    ``extra`` are further places to look (an atlas already in use on this
    computer), tried after the recorded ones.
    """
    candidates = []
    relative = reference.get("relative_path") if reference else None
    if relative and project_path is not None:
        candidates.append((Path(project_path).resolve().parent / relative).resolve())
    absolute = reference.get("absolute_path") if reference else None
    if absolute:
        candidates.append(Path(absolute).expanduser().resolve())
    for place in extra:
        if place:
            candidates.append(Path(place).expanduser().resolve())
    unique = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def verify_reference(path, reference):
    """Verify a candidate against a saved reference without trusting timestamps."""
    candidate = Path(path).expanduser().resolve()
    if not candidate.exists():
        return False, "path does not exist"
    expected_kind = reference.get("kind")
    if expected_kind == "file":
        if not candidate.is_file():
            return False, "expected a file"
        if candidate.stat().st_size != reference.get("size_bytes"):
            return False, "file size differs"
        if sha256_file(candidate) != reference.get("sha256"):
            return False, "file checksum differs"
        return True, None
    if expected_kind != "directory" or not candidate.is_dir():
        return False, "expected a directory"

    records = reference.get("files", [])
    if not records:
        return False, "reference contains no files"
    recorded_names = {str(record.get("path")) for record in records}
    is_atlas = recorded_names <= set(ATLAS_IDENTITY_FILES) and bool(
        recorded_names & set(ATLAS_CONTENT_FILES)
    )
    if is_atlas:
        # Content files that appeared since the reference was recorded change
        # the atlas too, so they must not be ignored.
        for name in ATLAS_CONTENT_FILES:
            if name not in recorded_names and (candidate / name).is_file():
                return False, "unexpected {}".format(name)
    elif recorded_names <= set(ATLAS_IDENTITY_FILES):
        for name in ATLAS_IDENTITY_FILES:
            if name not in recorded_names and (candidate / name).is_file():
                return False, "unexpected {}".format(name)
    if reference.get("sha256") is not None:
        identity = [
            (record["path"], record["size_bytes"], record["sha256"])
            for record in records
        ]
        aggregate = hashlib.sha256(
            json.dumps(identity, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        if aggregate != reference["sha256"]:
            return False, "reference file list does not match its checksum"
    if is_atlas:
        return _verify_atlas(candidate, records)
    for record in records:
        try:
            relative = _safe_relative_path(record["path"])
        except ValueError as exc:
            return False, str(exc)
        item = (candidate / relative).resolve()
        if candidate not in item.parents:
            return False, "reference path escapes its directory"
        if not item.is_file():
            return False, "missing {}".format(record["path"])
        if item.stat().st_size != record["size_bytes"]:
            return False, "size differs for {}".format(record["path"])
        if sha256_file(item) != record["sha256"]:
            return False, "checksum differs for {}".format(record["path"])
    return True, None


def _plausible_size(found, recorded):
    """Whether two sizes can be one content in different encodings."""
    return abs(found - recorded) <= max(65536, max(found, recorded) // 100)


def _matches_another_encoding(item, record):
    """Whether ``item`` holds what ``record`` describes, pickled differently.

    For references without a content digest (saved before 2.9.4): the file is
    written again with each pickle protocol an atlas may have used and must
    then have the recorded size and SHA-256 exactly.
    """
    try:
        with open(item, "rb") as stream:
            value = read_inert_pickle(stream, normalize=False)
    except OSError:
        raise
    except Exception:
        return False
    for protocol in ATLAS_PICKLE_PROTOCOLS:
        writer = _HashingWriter(record["size_bytes"])
        try:
            pickle.dump(value, writer, protocol=protocol)
        except Exception:
            continue
        if writer.count == record["size_bytes"] and writer.hexdigest() == record["sha256"]:
            return True
    return False


def _same_atlas_file(item, record):
    if item.stat().st_size == record["size_bytes"] and sha256_file(item) == record["sha256"]:
        return True
    expected = record.get("content_sha256")
    if expected:
        return hash_file_and_content(item)[1] == expected
    return _matches_another_encoding(item, record)


def _verify_atlas(candidate, records):
    """Verify an atlas folder by the data in its content files.

    The same atlas processed on another computer, or by another DriftlessMap
    version, has other bytes (pickle protocol) and other display caches, so
    those do not decide; the axes, regions, template and annotation must be
    identical.
    """
    content = [
        record for record in records if str(record.get("path")) in ATLAS_CONTENT_FILES
    ]
    # The cheap checks on every file first: a different atlas is refused
    # before any large file is read.
    items = {}
    for record in content:
        item = (candidate / record["path"]).resolve()
        if candidate not in item.parents:
            return False, "reference path escapes its directory"
        if not item.is_file():
            return False, "missing {}".format(record["path"])
        if not _plausible_size(item.stat().st_size, record["size_bytes"]):
            return False, "size differs for {}".format(record["path"])
        items[record["path"]] = item
    for record in sorted(content, key=lambda record: record["size_bytes"]):
        if not _same_atlas_file(items[record["path"]], record):
            return False, "atlas data differs in {}".format(record["path"])
    return True, None


def resolve_reference(reference, project_path=None, extra=()):
    for candidate in candidate_paths(reference, project_path, extra):
        try:
            matches, _ = verify_reference(candidate, reference)
        except OSError:
            matches = False
        if matches:
            return str(candidate), None
    return None, "No recorded path contains the expected input data."


def references_match(first, second):
    """Compare content identity while ignoring machine-specific path hints."""
    if not first or not second or first.get("kind") != second.get("kind"):
        return False
    return (
        first.get("size_bytes") == second.get("size_bytes")
        and first.get("sha256") == second.get("sha256")
    )


def pack_path(path, reference=None):
    """Create streaming attachment records for a portable project."""
    root = Path(path).expanduser().resolve()
    if reference is None:
        reference = describe_path(root)
    if root.is_file():
        paths = [(root.name, root, reference.get("sha256"))]
    else:
        recorded = reference.get("files", [])
        paths = [
            (record["path"], root / record["path"], record.get("sha256"))
            for record in recorded
        ]
    return {
        "schema_version": 1,
        "kind": reference["kind"],
        "name": root.name,
        "files": [
            {
                "path": relative,
                "data": ArchiveAttachment(
                    source_path=item,
                    display_name=relative,
                    expected_sha256=expected_sha256,
                ),
            }
            for relative, item, expected_sha256 in paths
        ],
    }


def unpack_path(payload, destination):
    """Extract a portable payload below a caller-owned temporary directory."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    payload_name = _safe_relative_path(payload["name"])
    if len(payload_name.parts) != 1 or payload_name.name in ("", "."):
        raise ValueError("Portable source has an unsafe root name.")
    root = destination / payload_name
    if payload["kind"] == "directory":
        root.mkdir(parents=True, exist_ok=True)
        base = root
    else:
        base = destination

    written = []
    for record in payload.get("files", []):
        relative = _safe_relative_path(record["path"])
        output = (base / relative).resolve()
        written.append(output)
        if destination not in output.parents:
            raise ValueError("Portable source escapes its extraction directory.")
        output.parent.mkdir(parents=True, exist_ok=True)
        data = record["data"]
        if isinstance(data, ArchiveAttachment):
            data.extract_to(output)
        else:
            # Compatibility with early development builds that stored bytes as
            # inert NumPy arrays before streaming attachments were introduced.
            output.write_bytes(np.asarray(data, dtype=np.uint8).tobytes())
    if payload["kind"] == "file":
        # A file payload's bytes live at its record path, which need not
        # equal the payload name.
        if len(written) != 1:
            raise ValueError("A portable file source must contain exactly one file.")
        return str(written[0])
    return str(root)
