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

import numpy as np

from .persistence import ArchiveAttachment


REFERENCE_SCHEMA_VERSION = 1
_REFERENCE_CACHE = {}
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


def _relative_hint(path, project_path):
    if project_path is None:
        return None
    try:
        return os.path.relpath(str(path), str(Path(project_path).resolve().parent))
    except (OSError, ValueError):
        return None


def _file_record(path, relative_path):
    stat = path.stat()
    return {
        "path": relative_path,
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "sha256": sha256_file(path),
    }


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


def describe_path(path, project_path=None, included_names=None):
    """Describe a file or directory using relocatable hints and SHA-256 data."""
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
    cache_key = ("directory", str(root), signature)
    records = _REFERENCE_CACHE.get(cache_key)
    if records is None:
        records = [
            _file_record(item, item.relative_to(root).as_posix()) for item in files
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
    )
    if not reference.get("files"):
        raise ValueError("Atlas folder contains no recognized identity files.")
    return reference


def candidate_paths(reference, project_path=None):
    """Return unique relocation candidates, preferring the project-relative hint."""
    candidates = []
    relative = reference.get("relative_path") if reference else None
    if relative and project_path is not None:
        candidates.append((Path(project_path).resolve().parent / relative).resolve())
    absolute = reference.get("absolute_path") if reference else None
    if absolute:
        candidates.append(Path(absolute).expanduser().resolve())
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


def resolve_reference(reference, project_path=None):
    for candidate in candidate_paths(reference, project_path):
        matches, _ = verify_reference(candidate, reference)
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
        paths = [(root.name, root)]
    else:
        recorded = reference.get("files", [])
        paths = [(record["path"], root / record["path"]) for record in recorded]
    return {
        "schema_version": 1,
        "kind": reference["kind"],
        "name": root.name,
        "files": [
            {
                "path": relative,
                "data": ArchiveAttachment(
                    source_path=item, display_name=relative
                ),
            }
            for relative, item in paths
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

    for record in payload.get("files", []):
        relative = _safe_relative_path(record["path"])
        output = (base / relative).resolve()
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
    return str(root)
