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
import shutil
import tempfile
import weakref
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

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

    @property
    def stored(self):
        return self.state is not None


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
        entry.state = entry.metadata = None

    def remove(self, section_id):
        if section_id == self.active_id:
            raise ValueError("Open another section before removing this one.")
        self._order.remove(section_id)
        return self._entries.pop(section_id)

    def move(self, section_id, step):
        index = self._order.index(section_id)
        target = max(0, min(len(self._order) - 1, index + step))
        self._order.insert(target, self._order.pop(index))


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
