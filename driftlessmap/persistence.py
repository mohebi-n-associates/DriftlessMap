"""Versioned, non-executable persistence for DriftlessMap user data."""

import io
import importlib
import json
import os
from pathlib import Path
import pickle
import shutil
import tempfile
import zipfile
from contextlib import contextmanager

import numpy as np


FORMAT_NAME = "DriftlessMap"
LEGACY_FORMAT_NAMES = frozenset({"HERBS"})
SUPPORTED_FORMAT_NAMES = LEGACY_FORMAT_NAMES | {FORMAT_NAME}
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024 * 1024

REQUIRED_KEYS = {
    "layer": {"layer_link", "data", "color", "thumbnail"},
    "object": {"type", "data", "name"},
    "probe_settings": {"probe_settings", "planning"},
    "project": {
        "atlas_path",
        "img_path",
        "current_atlas",
        "num_windows",
        "probe_settings",
        "np_onside",
        "processing_slice",
        "processing_img",
        "overlay_img",
        "atlas_control",
        "img_ctrl_data",
        "setting_data",
        "tool_data",
        "layer_data",
        "working_img_data",
        "working_atlas_data",
        "object_data",
    },
    "slice": {"data", "cut", "width", "height", "distance", "Bregma", "ready"},
    "triangulation": {
        "atlas_corner_points",
        "atlas_side_lines",
        "atlas_tri_data",
        "atlas_tri_inside_data",
        "atlas_tri_onside_data",
        "atlas_display",
    },
}


class ArchiveAttachment:
    """A file streamed into, or lazily read from, a DriftlessMap archive."""

    def __init__(
        self,
        *,
        source_path=None,
        archive_path=None,
        member_name=None,
        display_name=None,
    ):
        self.source_path = None if source_path is None else str(source_path)
        self.archive_path = None if archive_path is None else str(archive_path)
        self.member_name = member_name
        self.display_name = display_name
        if self.source_path is None and (
            self.archive_path is None or self.member_name is None
        ):
            raise ValueError("Attachment needs a source file or archive member.")

    @contextmanager
    def open(self):
        if self.source_path is not None:
            with open(self.source_path, "rb") as stream:
                yield stream
            return
        with zipfile.ZipFile(self.archive_path, "r") as archive:
            with archive.open(self.member_name, "r") as stream:
                yield stream

    def extract_to(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.open() as source, destination.open("wb") as output:
            shutil.copyfileobj(source, output, length=8 * 1024 * 1024)


def _numpy_pickle_globals():
    """Return inert NumPy constructors used by supported pickle versions."""
    safe_globals = {
        ("numpy", "dtype"): np.dtype,
        ("numpy", "ndarray"): np.ndarray,
        ("numpy.core.multiarray", "_reconstruct"): np.core.multiarray._reconstruct,
        ("numpy.core.multiarray", "scalar"): np.core.multiarray.scalar,
        ("numpy._core.multiarray", "_reconstruct"): np.core.multiarray._reconstruct,
        ("numpy._core.multiarray", "scalar"): np.core.multiarray.scalar,
    }
    frombuffer = None
    for module_name in ("numpy._core.numeric", "numpy.core.numeric"):
        try:
            numeric_module = importlib.import_module(module_name)
            frombuffer = numeric_module._frombuffer
            break
        except (AttributeError, ImportError):
            continue
    if frombuffer is not None:
        for module_name in ("numpy.core.numeric", "numpy._core.numeric"):
            safe_globals[(module_name, "_frombuffer")] = frombuffer
    return safe_globals


class _LegacyPandasNA:
    """Inert marker for pandas' missing-string singleton."""

    __slots__ = ()


_LEGACY_PANDAS_NA = _LegacyPandasNA()


class _LegacyPandasStringDtype:
    """Inert stand-in used while decoding a pandas string-array pickle."""

    __slots__ = ()

    def __init__(self, storage="python", na_value=np.nan):
        valid_nan = isinstance(na_value, float) and np.isnan(na_value)
        if storage != "python" or (
            not valid_nan and na_value is not _LEGACY_PANDAS_NA
        ):
            raise pickle.UnpicklingError(
                "Unsupported legacy pandas string dtype."
            )


class _LegacyPandasStringArray:
    """Capture the NumPy payload of a legacy pandas StringArray safely."""

    __slots__ = ("values",)

    def __init__(self):
        self.values = None

    def __setstate__(self, state):
        if (
            not isinstance(state, tuple)
            or len(state) not in (2, 3)
            or not isinstance(state[0], _LegacyPandasStringDtype)
            or not isinstance(state[1], np.ndarray)
            or (len(state) == 3 and state[2] != {})
        ):
            raise pickle.UnpicklingError("Invalid legacy pandas string-array state.")
        self.values = state[1]


def _reconstruct_legacy_pandas_string_array(array_type, checksum, state):
    """Replace pandas' Cython reconstruction function with an inert shim."""
    if (
        array_type is not _LegacyPandasStringArray
        or not isinstance(checksum, int)
        or state is not None
    ):
        raise pickle.UnpicklingError(
            "Invalid legacy pandas string-array constructor."
        )
    return _LegacyPandasStringArray()


def _normalize_legacy_pandas_arrays(value):
    if isinstance(value, _LegacyPandasStringArray):
        array = np.asarray(value.values)
        if array.ndim != 1 or array.dtype.kind not in ("O", "S", "U"):
            raise pickle.UnpicklingError(
                "Invalid legacy pandas string-array payload."
            )
        if array.dtype.kind == "O" and any(
            not isinstance(item, (str, np.str_)) for item in array
        ):
            raise pickle.UnpicklingError(
                "Legacy pandas string array contains non-string values."
            )
        return array.astype(str)
    if isinstance(value, dict):
        return {
            _normalize_legacy_pandas_arrays(key): _normalize_legacy_pandas_arrays(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_legacy_pandas_arrays(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize_legacy_pandas_arrays(item) for item in value)
    if isinstance(value, set):
        return {_normalize_legacy_pandas_arrays(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(_normalize_legacy_pandas_arrays(item) for item in value)
    return value


class RestrictedUnpickler(pickle.Unpickler):
    """Legacy reader limited to inert builtins and NumPy array machinery."""

    SAFE_GLOBALS = {
        ("builtins", "complex"): complex,
        ("builtins", "frozenset"): frozenset,
        ("builtins", "set"): set,
        ("builtins", "slice"): slice,
        (
            "pandas._libs.arrays",
            "__pyx_unpickle_NDArrayBacked",
        ): _reconstruct_legacy_pandas_string_array,
        ("pandas.arrays", "StringArray"): _LegacyPandasStringArray,
        ("pandas.core.arrays.string_", "StringArray"): _LegacyPandasStringArray,
        ("pandas.core.arrays.string_", "StringDtype"): _LegacyPandasStringDtype,
        ("pandas", "StringDtype"): _LegacyPandasStringDtype,
        ("pandas", "NA"): _LEGACY_PANDAS_NA,
        ("pandas._libs.missing", "NA"): _LEGACY_PANDAS_NA,
        **_numpy_pickle_globals(),
    }

    def find_class(self, module, name):
        try:
            return self.SAFE_GLOBALS[(module, name)]
        except KeyError as exc:
            raise pickle.UnpicklingError(
                "Legacy file contains unsupported type {}.{}".format(module, name)
            ) from exc


def load_legacy_pickle(file_path):
    """Load inert data from a legacy pickle with a consistent result tuple."""
    try:
        with open(file_path, "rb") as infile:
            data = RestrictedUnpickler(infile).load()
        return _normalize_legacy_pandas_arrays(data), None
    except OSError as exc:
        return None, "Unable to read file: {}".format(exc)
    except Exception as exc:
        return None, "Invalid or unsupported legacy HERBS file: {}".format(exc)


def _validate_payload(data, kind):
    required = REQUIRED_KEYS.get(kind)
    if required is not None and (
        not isinstance(data, dict) or not required.issubset(data)
    ):
        raise ValueError("File does not contain a complete {} payload.".format(kind))
    return data


def _encode(value, arrays, attachments):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if np.isfinite(value):
            return value
        return {"__type__": "float", "value": repr(value)}
    if isinstance(value, np.generic):
        return _encode(value.item(), arrays, attachments)
    if isinstance(value, ArchiveAttachment):
        name = "attachments/{:08d}.bin".format(len(attachments))
        attachments.append((name, value))
        return {
            "__type__": "attachment",
            "name": name,
            "display_name": value.display_name,
        }
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            return {
                "__type__": "object_array",
                "value": _encode(value.tolist(), arrays, attachments),
            }
        for existing_name, existing_array in arrays:
            if existing_array is value:
                return {"__type__": "ndarray", "name": existing_name}
        name = "arrays/{:08d}.npy".format(len(arrays))
        arrays.append((name, value))
        return {"__type__": "ndarray", "name": name}
    if isinstance(value, dict):
        return {
            "__type__": "dict",
            "items": [
                [
                    _encode(key, arrays, attachments),
                    _encode(item, arrays, attachments),
                ]
                for key, item in value.items()
            ],
        }
    if isinstance(value, list):
        return {
            "__type__": "list",
            "items": [_encode(item, arrays, attachments) for item in value],
        }
    if isinstance(value, tuple):
        return {
            "__type__": "tuple",
            "items": [_encode(item, arrays, attachments) for item in value],
        }
    if isinstance(value, Path):
        return {"__type__": "path", "value": str(value)}
    if value.__class__.__name__ == "QColor" and hasattr(value, "getRgb"):
        return {"__type__": "color", "rgba": list(value.getRgb())}
    raise TypeError(
        "Unsupported DriftlessMap data type: {}".format(type(value).__name__)
    )


def _decode(value, archive):
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    value_type = value["__type__"]
    if value_type == "float":
        return float(value["value"])
    if value_type == "ndarray":
        name = value["name"]
        if name not in archive.namelist() or not name.startswith("arrays/"):
            raise ValueError("Archive references a missing array: {}".format(name))
        with archive.open(name) as stream:
            return np.lib.format.read_array(stream, allow_pickle=False)
    if value_type == "attachment":
        name = value["name"]
        if name not in archive.namelist() or not name.startswith("attachments/"):
            raise ValueError("Archive references a missing attachment: {}".format(name))
        return ArchiveAttachment(
            archive_path=archive.filename,
            member_name=name,
            display_name=value.get("display_name"),
        )
    if value_type == "object_array":
        return np.asarray(_decode(value["value"], archive), dtype=object)
    if value_type == "dict":
        return {
            _decode(key, archive): _decode(item, archive)
            for key, item in value["items"]
        }
    if value_type == "list":
        return [_decode(item, archive) for item in value["items"]]
    if value_type == "tuple":
        return tuple(_decode(item, archive) for item in value["items"])
    if value_type == "path":
        return Path(value["value"])
    if value_type == "color":
        return tuple(value["rgba"])
    raise ValueError(
        "Unknown DriftlessMap archive value type: {}".format(value_type)
    )


def save_driftlessmap_file(file_path, data, kind):
    """Atomically save data in the versioned DriftlessMap archive format."""
    destination = Path(file_path)
    arrays = []
    attachments = []
    try:
        _validate_payload(data, kind)
        encoded = _encode(data, arrays, attachments)
        manifest = json.dumps(
            {
                "format": FORMAT_NAME,
                "version": FORMAT_VERSION,
                "kind": kind,
                "data": encoded,
            },
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=str(destination.parent),
            prefix=".driftlessmap-",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(
                temporary_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True
            ) as archive:
                archive.writestr(MANIFEST_NAME, manifest)
                for name, array in arrays:
                    with archive.open(name, "w", force_zip64=True) as stream:
                        np.lib.format.write_array(stream, array, allow_pickle=False)
                for name, attachment in attachments:
                    with attachment.open() as source, archive.open(
                        name, "w", force_zip64=True
                    ) as output:
                        shutil.copyfileobj(source, output, length=8 * 1024 * 1024)
            os.replace(str(temporary_path), str(destination))
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    except Exception as exc:
        return False, "Unable to save DriftlessMap file: {}".format(exc)
    return True, None


def load_driftlessmap_file(file_path, expected_kind=None):
    """Load a DriftlessMap or legacy HERBS archive safely."""
    try:
        if not zipfile.is_zipfile(file_path):
            data, error = load_legacy_pickle(file_path)
            if error is None and expected_kind is not None:
                try:
                    return _validate_payload(data, expected_kind), None
                except ValueError as exc:
                    return None, "Invalid DriftlessMap file: {}".format(exc)
            return data, error

        with zipfile.ZipFile(file_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("Archive contains duplicate entries.")
            total_size = sum(info.file_size for info in infos)
            if total_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Archive expands beyond the supported size limit.")
            if MANIFEST_NAME not in names:
                raise ValueError("Archive has no DriftlessMap manifest.")
            manifest_info = archive.getinfo(MANIFEST_NAME)
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise ValueError("DriftlessMap manifest is too large.")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if manifest.get("format") not in SUPPORTED_FORMAT_NAMES:
                raise ValueError("File is not a DriftlessMap or HERBS archive.")
            if manifest.get("version") != FORMAT_VERSION:
                raise ValueError(
                    "Unsupported DriftlessMap archive version: {}".format(
                        manifest.get("version")
                    )
                )
            if expected_kind is not None and manifest.get("kind") != expected_kind:
                raise ValueError(
                    "Expected a {} file, found {}.".format(
                        expected_kind, manifest.get("kind")
                    )
                )
            data = _decode(manifest["data"], archive)
            if expected_kind is not None:
                data = _validate_payload(data, expected_kind)
            return data, None
    except Exception as exc:
        return None, "Invalid DriftlessMap file: {}".format(exc)


# Backward compatibility for the public helper names used by HERBS scripts.
save_herbs_file = save_driftlessmap_file
load_herbs_file = load_driftlessmap_file
