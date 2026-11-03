"""Sections of a project: each one's image, registration, placement and marks.

GUI-free part of multi-section projects (see ``multi_section_design.md``). A
project payload has document fields, shared by every section, and section
fields, which :data:`SECTION_FIELDS` names. The open (active) section lives in
the engine as before; every other section is a :class:`SectionEntry` holding
its section fields, with large arrays spilled to memory-mapped files by
:class:`SpillCache` so inactive sections do not stay in memory.
"""

import copy
import hashlib
import os
import re
import shutil
import tempfile
import weakref
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .mapping_records import is_identifier
from .state_digest import state_digest

# Project payload keys that belong to one section. ``atlas_control`` (the
# plane, page and tilt the section is matched to) belongs to the section only
# with a volume atlas; a slice atlas is the document's (see section_fields).
SECTION_FIELDS = (
    "img_path", "histology_provenance", "img_ctrl_data", "processing_img",
    "overlay_img", "registration_input", "registration_review",
    "mapping_review_state", "section_id", "setting_data", "np_onside",
    "atlas_control", "working_img_data", "working_atlas_data", "atlas_mark_origin",
    "layer_data", "implant_outlines",
)

# Engine attributes that belong to one section but are not in the payload.
SECTION_METADATA = (
    "current_img_path", "current_img_name", "save_path",
    "_loaded_histology_signature", "_temporary_histology_source", "editing_units",
    "tri_simplices", "triangulation_topology_point_count",
)

# Arrays at least this large are spilled to disk when a section is put away.
SPILL_BYTES = 1 << 20

# Version of the ``sections`` block of a project payload (project schema 4).
SECTIONS_SCHEMA_VERSION = 1


def section_fields(payload):
    """The keys of ``payload`` that belong to its open section."""
    keys = [key for key in SECTION_FIELDS if key in payload]
    if payload.get("current_atlas") != "volume" and "atlas_control" in keys:
        keys.remove("atlas_control")
    return keys


def section_state(payload):
    """The open section's fields of ``payload`` (values borrowed, not copied)."""
    return {key: payload[key] for key in section_fields(payload)}


@dataclass
class SectionEntry:
    """One section. ``state`` and ``metadata`` are None while it is open."""

    section_id: str
    name: str
    state: Optional[dict] = None
    metadata: Optional[dict] = None
    summary: dict = field(default_factory=dict)
    # The packed original source of a section opened from a portable project.
    portable: Optional[dict] = None
    _digest: Optional[str] = field(default=None, repr=False)

    @property
    def stored(self):
        return self.state is not None

    def digest(self):
        """Digest of the stored fields, computed once: a stored section does
        not change until it is opened again."""
        if self._digest is None:
            self._digest = state_digest(self.state)
        return self._digest

    def saved(self, state=None):
        """The section as written to a project file."""
        return {"section_id": self.section_id, "name": self.name,
                "summary": dict(self.summary),
                "state": self.state if state is None else state}


class SectionBook:
    """The ordered sections of a project; one of them is open (active)."""

    def __init__(self, active_id, name=None):
        self._entries = {active_id: SectionEntry(active_id, name or "")}
        self._order = [active_id]
        self.active_id = active_id

    def __len__(self):
        return len(self._order)

    def entries(self):
        return [self._entries[section_id] for section_id in self._order]

    def entry(self, section_id):
        return self._entries.get(section_id)

    def names(self):
        return [entry.name for entry in self.entries()]

    def unique_name(self, base, ignore=None):
        base = (base or "").strip() or "Section {}".format(len(self._order) + 1)
        taken = {entry.name for entry in self._entries.values() if entry.section_id != ignore}
        name, number = base, 2
        while name in taken:
            name = "{} ({})".format(base, number)
            number += 1
        return name

    def rename(self, section_id, name):
        entry = self._entries[section_id]
        entry.name = self.unique_name(name, ignore=section_id)
        return entry.name

    def follow_active(self, section_id, name=None):
        """The open section was given a new identity (it was read again)."""
        if section_id == self.active_id:
            if name and not self._entries[section_id].name:
                self._entries[section_id].name = self.unique_name(name, ignore=section_id)
            return
        entry = self._entries.pop(self.active_id)
        entry.section_id = section_id
        if name and not entry.name:
            entry.name = self.unique_name(name, ignore=self.active_id)
        self._order[self._order.index(self.active_id)] = section_id
        self._entries[section_id] = entry
        self.active_id = section_id

    def put_away(self, state, metadata, summary=None):
        """Store the open section's fields; it stays listed but is not open."""
        entry = self._entries[self.active_id]
        entry.state, entry.metadata = state, metadata
        entry.summary = dict(summary or {})
        entry._digest = None

    def add(self, section_id, name):
        """Add a new open section after the current one."""
        if section_id in self._entries:
            raise ValueError("Section {} is already in the project.".format(section_id))
        if not self._entries[self.active_id].stored:
            raise ValueError("Put the open section away before adding another.")
        self._entries[section_id] = SectionEntry(section_id, self.unique_name(name))
        self._order.insert(self._order.index(self.active_id) + 1, section_id)
        self.active_id = section_id
        return self._entries[section_id]

    def activate(self, section_id):
        """Make a stored section the open one; returns its entry (fields kept
        on the entry until :meth:`opened`)."""
        entry = self._entries[section_id]
        if not entry.stored:
            raise ValueError("Section {} is not stored.".format(entry.name))
        if not self._entries[self.active_id].stored:
            raise ValueError("Put the open section away before opening another.")
        self.active_id = section_id
        return entry

    def opened(self, section_id):
        """The section is installed in the engine: drop its stored fields."""
        entry = self._entries[section_id]
        entry.state = entry.metadata = entry.portable = None
        entry._digest = None

    def remove(self, section_id):
        if section_id == self.active_id:
            raise ValueError("Open another section before removing this one.")
        self._order.remove(section_id)
        return self._entries.pop(section_id)

    def move(self, section_id, step):
        index = self._order.index(section_id)
        target = max(0, min(len(self._order) - 1, index + step))
        self._order.insert(target, self._order.pop(index))

    def index(self):
        """What the change digest needs: order, names and stored contents."""
        return {
            "schema_version": SECTIONS_SCHEMA_VERSION,
            "active_section_id": self.active_id,
            "order": list(self._order),
            "names": {entry.section_id: entry.name for entry in self.entries()},
            "stored": {entry.section_id: entry.digest()
                       for entry in self.entries() if entry.stored},
        }

    @classmethod
    def from_saved(cls, block, active_id, active_name=None):
        """The book of a saved ``sections`` block; returns (book, problems).

        Stored sections that cannot be used are left out and named in
        ``problems``; the open section is always kept.
        """
        problems = []
        book = cls(active_id, active_name)
        if not isinstance(block, dict):
            return book, problems
        if block.get("schema_version") != SECTIONS_SCHEMA_VERSION:
            problems.append("unknown sections format {!r}".format(block.get("schema_version")))
            return book, problems
        names = block.get("names") if isinstance(block.get("names"), dict) else {}
        if isinstance(names.get(active_id), str):
            book._entries[active_id].name = names[active_id]
        stored = {}
        for item in block.get("stored") or []:
            reason = _stored_problem(item, active_id, stored)
            if reason:
                name = item.get("name") if isinstance(item, dict) else None
                problems.append("{}: {}".format(name or "a section", reason))
                continue
            stored[item["section_id"]] = item
        order = [sid for sid in block.get("order") or [] if sid in stored or sid == active_id]
        order += [sid for sid in stored if sid not in order]
        if active_id not in order:
            order.insert(0, active_id)
        book._order = []
        for section_id in order:
            if section_id == active_id:
                book._order.append(active_id)
                continue
            item = stored[section_id]
            entry = SectionEntry(section_id, book.unique_name(item.get("name")),
                                 summary=_valid_summary(item.get("summary")))
            entry.state = item["state"]
            book._entries[section_id] = entry
            book._order.append(section_id)
        return book, problems


def _valid_summary(value):
    """A stored section's summary; an invalid registration fingerprint
    (checked against its mappings) is dropped, so it is treated as unknown."""
    summary = dict(value) if isinstance(value, dict) else {}
    registration = summary.get("registration")
    if registration is not None and not (
            isinstance(registration, str) and re.fullmatch(r"[0-9a-f]{64}", registration)):
        del summary["registration"]
    return summary


def section_pixel_size_um(img_ctrl_data):
    """Micrometres per pixel of a section's saved working raster, or None."""
    from .image_reader import valid_pixel_size

    source = img_ctrl_data.get("source_metadata") or {}
    size = valid_pixel_size(img_ctrl_data.get("pixel_size_um")) or \
        valid_pixel_size(source.get("scaling_val"))
    if size is None:
        return None
    try:
        scale = float(img_ctrl_data.get("image_scale") or source.get("image_scale") or 1.0)
    except (TypeError, ValueError):
        scale = 1.0
    return size / scale if np.isfinite(scale) and scale > 0 else size


def write_section_image(path, raster, channel_names=(), pixel_um=None):
    """Write a section's working raster as a lossless TIFF (channels first,
    ImageJ hyperstack where ImageJ supports the type), with its channel names
    and pixel size."""
    import tifffile

    raster = np.asarray(raster)
    data = raster if raster.ndim == 2 else np.moveaxis(raster, -1, 0)
    axes = "YX" if raster.ndim == 2 else "CYX"
    resolution = None if pixel_um is None else (1.0 / pixel_um, 1.0 / pixel_um)
    if data.dtype in (np.uint8, np.uint16, np.float32):
        metadata = {"axes": axes, "unit": "um"}
        names = [str(name) for name in channel_names]
        if axes == "CYX" and len(names) == data.shape[0]:
            metadata["Labels"] = names
        tifffile.imwrite(path, data, imagej=True, metadata=metadata, resolution=resolution,
                         compression="zlib")
    else:
        tifffile.imwrite(path, data, metadata={"axes": axes}, resolution=resolution,
                         resolutionunit="MICROMETER" if resolution else None,
                         compression="zlib")


def _stored_problem(item, active_id, seen):
    """Why a saved stored section cannot be used, or None."""
    if not isinstance(item, dict):
        return "not a section record"
    section_id = item.get("section_id")
    if not is_identifier(section_id):
        return "invalid section identity"
    if section_id == active_id or section_id in seen:
        return "duplicate section identity"
    state = item.get("state")
    if not isinstance(state, dict) or state.get("section_id") != section_id:
        return "its stored fields do not belong to it"
    image = state.get("img_ctrl_data")
    if not isinstance(image, dict) or not isinstance(image.get("current_img"), np.ndarray):
        return "its image is missing"
    if not isinstance(state.get("setting_data"), dict):
        return "its registration is missing"
    if not isinstance(item.get("name", ""), str):
        return "invalid name"
    return None


class SpillCache:
    """Content-addressed ``.npy`` files for the large arrays of stored sections.

    Arrays are reopened with ``mmap_mode="c"`` (copy-on-write): reading pages
    them in on demand, and changes stay in memory instead of reaching the file.
    Identical contents share one file, so putting a section away again does not
    duplicate it. The folder is removed by :meth:`close`.
    """

    def __init__(self, min_bytes=SPILL_BYTES):
        self.min_bytes = min_bytes
        self._folder = None

    @property
    def folder(self):
        if self._folder is None:
            self._folder = tempfile.mkdtemp(prefix="driftlessmap-sections-")
            # Removed when the cache is closed, collected or the program exits.
            self._finalizer = weakref.finalize(self, shutil.rmtree, self._folder, True)
        return self._folder

    def spill(self, value):
        """A copy of ``value`` whose large arrays are memory-mapped files."""
        if isinstance(value, np.ndarray):
            if value.nbytes < self.min_bytes or value.dtype.hasobject:
                return value.copy()
            return self._file_array(value)
        if isinstance(value, dict):
            return {key: self.spill(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.spill(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.spill(item) for item in value)
        if isinstance(value, set):
            return set(value)
        return copy.deepcopy(value)

    def _file_array(self, array):
        array = np.ascontiguousarray(array)
        digest = hashlib.sha256("{}{}".format(array.dtype.str, array.shape).encode())
        flat = array.reshape(-1).view(np.uint8)
        step = 64 << 20
        for start in range(0, flat.size, step):
            digest.update(flat[start:start + step])
        path = os.path.join(self.folder, digest.hexdigest() + ".npy")
        if not os.path.exists(path):
            partial = path + ".part"
            with open(partial, "wb") as stream:
                np.save(stream, array, allow_pickle=False)
            os.replace(partial, path)
        return np.load(path, mmap_mode="c", allow_pickle=False)

    def close(self):
        if self._folder is not None:
            self._finalizer()
            self._folder = None
