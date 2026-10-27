"""Records of mapped annotations: kept section marks and how they were mapped.

Mapping copies a section's marks onto the atlas with the current
registration. A :class:`MappingRecord` keeps those section marks and the
registration fingerprint they were mapped with, so the atlas copy can be
recognised as out of date and updated after landmarks or the atlas plane
change. One record exists per unit: a kind of mark on one section (and, for
probes, one probe). Mapping the same unit again replaces its record and
increases its revision; it never adds a second one.

Parts and built objects refer to records by ``(unit_id, revision)`` pairs,
see :func:`derivation_status`. Identities are random 32-hex strings, never
names or paths.
"""

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field, replace

import numpy as np

KINDS = ("cells", "probe", "drawing", "contour", "expression")

CURRENT = "current"
REGISTRATION_CHANGED = "registration changed"
SECTION_REPLACED = "section replaced"
REMAPPED = "mapped again since"
NOT_RECORDED = "origin not recorded"

_IDENTIFIER = re.compile(r"^[0-9a-f]{32}$")


def new_identifier():
    return uuid.uuid4().hex


def is_identifier(value):
    return isinstance(value, str) and bool(_IDENTIFIER.match(value))


def _validated_source(kind, source):
    """Return a normalised copy of ``source`` or raise ValueError."""
    if not isinstance(source, dict):
        raise ValueError("Kept marks must be a mapping.")
    if kind == "expression":
        mask = np.asarray(source.get("mask"))
        if mask.ndim not in (2, 3) or mask.size == 0:
            raise ValueError("Kept expression marks must be an image.")
        return {"mask": mask.copy()}
    points = np.asarray(source.get("points", []), dtype=float)
    if points.size == 0:
        points = points.reshape(0, 2)
    if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
        raise ValueError("Kept {} marks must be finite x, y points.".format(kind))
    result = {"points": points.copy()}
    if kind == "cells":
        count = len(points)
        sizes = [float(value) for value in source.get("size", [])]
        symbols = [str(value) for value in source.get("symbol", [])]
        layers = [int(value) for value in source.get("layer_index", [])]
        if not (len(sizes) == len(symbols) == len(layers) == count):
            raise ValueError("Kept cells need a size, symbol and channel for every cell.")
        result.update(size=sizes, symbol=symbols, layer_index=layers)
    if kind == "drawing":
        result["closed"] = bool(source.get("closed", False))
    return result


def source_digest(kind, source):
    """SHA-256 of kept marks, independent of how they are stored."""
    digest = hashlib.sha256(kind.encode("utf-8"))
    for key in sorted(source):
        value = source[key]
        digest.update(key.encode("utf-8"))
        if isinstance(value, np.ndarray):
            array = np.ascontiguousarray(value)
            digest.update(str(array.dtype).encode("utf-8"))
            digest.update(json.dumps(list(array.shape)).encode("utf-8"))
            digest.update(array.tobytes())
        else:
            digest.update(json.dumps(value, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class MappingRecord:
    unit_id: str
    section_id: str
    kind: str
    probe: object               # probe name for probe marks, else None
    source: dict = field(compare=False)
    source_digest: str = ""
    registration: str = ""      # registration fingerprint used for mapping
    review: str = NOT_RECORDED  # review state of that registration
    mapped_at: str = ""
    revision: int = 1

    @property
    def key(self):
        return (self.section_id, self.kind, self.probe)

    def status(self, section_id, registration):
        """CURRENT, SECTION_REPLACED or REGISTRATION_CHANGED."""
        if section_id != self.section_id:
            return SECTION_REPLACED
        if registration != self.registration:
            return REGISTRATION_CHANGED
        return CURRENT

    def to_dict(self):
        return {
            "unit_id": self.unit_id, "section_id": self.section_id, "kind": self.kind,
            "probe": self.probe, "source": dict(self.source),
            "source_digest": self.source_digest, "registration": self.registration,
            "review": self.review, "mapped_at": self.mapped_at, "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("A saved mapping record is not a mapping.")
        unit_id, section_id = data.get("unit_id"), data.get("section_id")
        if not is_identifier(unit_id) or not is_identifier(section_id):
            raise ValueError("A saved mapping record has an invalid identifier.")
        kind = data.get("kind")
        if kind not in KINDS:
            raise ValueError("A saved mapping record has an unknown kind.")
        probe = data.get("probe")
        if probe is not None and (kind != "probe" or not isinstance(probe, str)):
            raise ValueError("Only probe records name a probe.")
        source = _validated_source(kind, data.get("source"))
        digest = str(data.get("source_digest", ""))
        if digest != source_digest(kind, source):
            raise ValueError("A saved mapping record's kept marks do not match their digest.")
        registration = str(data.get("registration", ""))
        if len(registration) != 64:
            raise ValueError("A saved mapping record has an invalid registration fingerprint.")
        revision = data.get("revision", 1)
        if isinstance(revision, bool) or not isinstance(revision, (int, np.integer)) \
                or revision < 1:
            raise ValueError("A saved mapping record has an invalid revision.")
        return cls(unit_id, section_id, kind, probe, source, digest, registration,
                   str(data.get("review", NOT_RECORDED)), str(data.get("mapped_at", "")),
                   int(revision))


class MappingLedger:
    """The mapping records of a project, one per unit."""

    def __init__(self, records=()):
        self._records = {}
        for record in records:
            self._records[record.key] = record

    def __len__(self):
        return len(self._records)

    def records(self):
        return list(self._records.values())

    def get(self, section_id, kind, probe=None):
        return self._records.get((section_id, kind, probe))

    def by_unit(self, unit_id):
        return next((r for r in self._records.values() if r.unit_id == unit_id), None)

    def record(self, section_id, kind, source, registration, review, mapped_at, probe=None):
        """Record a mapping of a unit, replacing any earlier one; returns it."""
        if kind not in KINDS:
            raise ValueError("Unknown kind of mark: {!r}.".format(kind))
        if not is_identifier(section_id):
            raise ValueError("Invalid section identifier.")
        if probe is not None and kind != "probe":
            raise ValueError("Only probe marks name a probe.")
        source = _validated_source(kind, source)
        earlier = self._records.get((section_id, kind, probe))
        record = MappingRecord(
            unit_id=earlier.unit_id if earlier else new_identifier(),
            section_id=section_id, kind=kind, probe=probe, source=source,
            source_digest=source_digest(kind, source), registration=registration,
            review=review, mapped_at=mapped_at,
            revision=earlier.revision + 1 if earlier else 1,
        )
        self._records[record.key] = record
        return record

    def forget(self, unit_id):
        record = self.by_unit(unit_id)
        if record is not None:
            del self._records[record.key]
        return record

    def snapshot(self):
        """An independent copy for undo."""
        return MappingLedger(replace(r, source=_validated_source(r.kind, r.source))
                             for r in self._records.values())

    def to_list(self):
        return [record.to_dict() for record in self._records.values()]

    @classmethod
    def from_list(cls, data):
        """Rebuild from saved data; returns ``(ledger, problems)``.

        Invalid records are dropped and described, so one damaged record
        never prevents a project from opening.
        """
        records, problems = [], []
        for item in data if isinstance(data, (list, tuple)) else []:
            try:
                records.append(MappingRecord.from_dict(item))
            except (TypeError, ValueError) as exc:
                problems.append(str(exc))
        if data is not None and not isinstance(data, (list, tuple)):
            problems.append("The saved mapping records are not a list.")
        return cls(records), problems


def derivation(records):
    """The ``obj_derivation`` entry of an object made from ``records``."""
    return [[record.unit_id, record.revision] for record in records]


def valid_derivation(value):
    """A saved derivation entry, or [] when absent or malformed."""
    if not isinstance(value, (list, tuple)):
        return []
    entries = []
    for item in value:
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or not is_identifier(item[0])
                or isinstance(item[1], bool) or not isinstance(item[1], (int, np.integer))
                or item[1] < 1):
            return []
        entries.append([item[0], int(item[1])])
    return entries


def derivation_status(entries, ledger, section_id, registration):
    """CURRENT, NOT_RECORDED, or the first reason an object is out of date."""
    if not entries:
        return NOT_RECORDED
    for unit_id, revision in entries:
        record = ledger.by_unit(unit_id)
        if record is None:
            return NOT_RECORDED
        if record.revision != revision:
            return REMAPPED
        status = record.status(section_id, registration)
        if status != CURRENT:
            return status
    return CURRENT
