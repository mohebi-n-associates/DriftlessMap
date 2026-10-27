"""Implants: optical fibers and microprisms (see ``implants_design.md``).

An implant is a device of known shape. The user outlines what it left in each
section; the mapped outlines (atlas voxels relative to Bregma, axes ML right,
AP anterior, DV dorsal, as every other DriftlessMap object) are the evidence,
and :func:`fit_fiber` / :func:`fit_prism` fit the device to them and report
where it ended up. Everything here is GUI-free and deterministic.

Neuropixels probes are implants too, but they keep their own named-probe path
(``v2/probes.py``); this module covers the types added in 2.0.0a13.
"""

import math
from dataclasses import dataclass, field, replace

import numpy as np

from .mapping_records import is_identifier, new_identifier
from .probe_reconstruction import (
    _coordinate_record,
    is_allen_ccf_2017,
    normalize_axis_info,
)
from .probe_utiles import find_probe_surface_entry, get_angles, get_tilt_info

FIBER = "fiber"
PRISM = "prism"
TYPES = (FIBER, PRISM)
TYPE_NAMES = {FIBER: "Optical fiber", PRISM: "Microprism"}
SHORT_NAMES = {FIBER: "Fiber", PRISM: "Prism"}

FIBER_DIAMETERS_UM = (100.0, 105.0, 200.0, 400.0)
FIBER_NAS = (0.22, 0.37, 0.39, 0.50)
PRISM_FACES = ("medial", "lateral", "anterior", "posterior")
DEFAULT_SPECS = {
    FIBER: {"diameter_um": 200.0, "na": 0.39},
    # width runs along the imaging face, depth away from it.
    PRISM: {"width_um": 1500.0, "depth_um": 1500.0, "face": "lateral"},
}
_SPEC_RANGES = {
    "diameter_um": (10.0, 3000.0),
    "na": (0.05, 1.0),
    "width_um": (100.0, 5000.0),
    "depth_um": (100.0, 5000.0),
}
PALETTE = [
    (0, 184, 169), (242, 153, 74), (155, 81, 224), (47, 128, 237),
    (235, 87, 170), (39, 174, 96), (242, 201, 76), (232, 72, 85),
]

# Outline edges are resampled to at most this many section pixels before
# mapping, because the piecewise-affine registration bends straight edges.
RESAMPLE_SPACING_PX = 2.0
# A fiber outline wider than this times the diameter suggests damage or a tear.
FIBER_WIDE_FACTOR = 1.5
# Every section narrower than this times the diameter missed the fiber axis.
FIBER_NARROW_FACTOR = 0.5
# Prism outlines differing from the specified size by more than this warn.
PRISM_SIZE_TOLERANCE = 0.2

# Axes of mapped points: 0 = ML (right +), 1 = AP (anterior +), 2 = DV (dorsal +).
ML, AP, DV = 0, 1, 2
PLANE_NAMES = {ML: "sagittal", AP: "coronal", DV: "horizontal"}


# ---------------------------------------------------------------- definitions
def check_name(name):
    name = " ".join(str(name).split())
    if not name:
        raise ValueError("An implant needs a name.")
    if "-" in name:
        raise ValueError("Implant names cannot contain '-'.")
    if len(name) > 60:
        raise ValueError("Implant names are limited to 60 characters.")
    return name


def validated_specs(kind, specs):
    """A complete, checked copy of ``specs`` for ``kind``; raises ValueError."""
    if kind not in TYPES:
        raise ValueError("Unknown implant type: {!r}.".format(kind))
    specs = dict(specs or {})
    unknown = set(specs) - set(DEFAULT_SPECS[kind])
    if unknown:
        raise ValueError("Unknown {} settings: {}.".format(kind, ", ".join(sorted(unknown))))
    result = dict(DEFAULT_SPECS[kind])
    result.update(specs)
    for key, (low, high) in _SPEC_RANGES.items():
        if key not in result:
            continue
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
            raise ValueError("{} must be a number.".format(key))
        value = float(value)
        if not (math.isfinite(value) and low <= value <= high):
            raise ValueError("{} must be between {:g} and {:g}.".format(key, low, high))
        result[key] = value
    if kind == PRISM and result["face"] not in PRISM_FACES:
        raise ValueError("The prism face must be one of {}.".format(", ".join(PRISM_FACES)))
    return result


def describe_specs(kind, specs):
    if kind == FIBER:
        return "Ø {:g} µm · NA {:g}".format(specs["diameter_um"], specs["na"])
    return "{:g} × {:g} µm · {} face".format(specs["width_um"], specs["depth_um"],
                                            specs["face"])


@dataclass(frozen=True)
class Implant:
    implant_id: str
    name: str
    kind: str
    specs: dict = field(compare=False)
    colour: tuple = (0, 184, 169)

    @property
    def type_name(self):
        return TYPE_NAMES[self.kind]

    def to_dict(self):
        return {"implant_id": self.implant_id, "name": self.name, "kind": self.kind,
                "specs": dict(self.specs), "colour": list(self.colour)}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("A saved implant is not a mapping.")
        if not is_identifier(data.get("implant_id")):
            raise ValueError("A saved implant has an invalid identifier.")
        kind = data.get("kind")
        specs = validated_specs(kind, data.get("specs"))
        colour = data.get("colour", PALETTE[0])
        if (not isinstance(colour, (list, tuple)) or len(colour) != 3
                or not all(isinstance(c, (int, np.integer)) and 0 <= c <= 255 for c in colour)):
            raise ValueError("A saved implant has an invalid colour.")
        return cls(data["implant_id"], check_name(data.get("name", "")), kind, specs,
                   tuple(int(c) for c in colour))


class ImplantBook:
    """The fibers and prisms of a project, in the order they were added."""

    def __init__(self, implants=()):
        self._implants = {}
        for implant in implants:
            self._implants[implant.implant_id] = implant

    def __len__(self):
        return len(self._implants)

    def implants(self):
        return list(self._implants.values())

    def get(self, implant_id):
        return self._implants.get(implant_id)

    def by_name(self, name):
        return next((i for i in self._implants.values() if i.name == name), None)

    def _unique(self, name, ignore=None):
        other = self.by_name(name)
        if other is not None and other.implant_id != ignore:
            raise ValueError("There is already an implant called {}.".format(name))
        return name

    def default_name(self, kind, taken=()):
        taken = set(taken) | {i.name for i in self._implants.values()}
        number = 1
        while "{} {}".format(SHORT_NAMES[kind], number) in taken:
            number += 1
        return "{} {}".format(SHORT_NAMES[kind], number)

    def add(self, kind, name=None, specs=None, colour=None, taken=()):
        specs = validated_specs(kind, specs)
        name = self._unique(check_name(name)) if name else self.default_name(kind, taken)
        if colour is None:
            used = {i.colour for i in self._implants.values()}
            colour = next((c for c in PALETTE if c not in used), PALETTE[len(self) % len(PALETTE)])
        implant = Implant(new_identifier(), name, kind, specs, tuple(colour))
        self._implants[implant.implant_id] = implant
        return implant

    def rename(self, implant_id, name):
        implant = self._implants[implant_id]
        name = self._unique(check_name(name), ignore=implant_id)
        self._implants[implant_id] = replace(implant, name=name)
        return self._implants[implant_id]

    def set_specs(self, implant_id, specs):
        implant = self._implants[implant_id]
        self._implants[implant_id] = replace(implant, specs=validated_specs(implant.kind, specs))
        return self._implants[implant_id]

    def remove(self, implant_id):
        return self._implants.pop(implant_id, None)

    def to_list(self):
        return [implant.to_dict() for implant in self._implants.values()]

    @classmethod
    def from_list(cls, data):
        """Rebuild from saved data; returns ``(book, problems)``."""
        implants, problems, names = [], [], set()
        if data is not None and not isinstance(data, (list, tuple)):
            return cls(), ["The saved implants are not a list."]
        for item in data or []:
            try:
                implant = Implant.from_dict(item)
                if implant.name in names:
                    raise ValueError("Two saved implants are called {}.".format(implant.name))
            except (TypeError, ValueError, KeyError) as exc:
                problems.append(str(exc))
                continue
            names.add(implant.name)
            implants.append(implant)
        return cls(implants), problems


# ------------------------------------------------------------------- outlines
def validated_outline(points):
    """A closed outline as an ``(N, 2)`` float array (first vertex not repeated)."""
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.all(np.isfinite(points)):
        raise ValueError("An outline must be finite x, y vertices.")
    if len(points) > 1 and np.allclose(points[0], points[-1]):
        points = points[:-1]
    if len(points) < 3:
        raise ValueError("An outline needs at least three vertices.")
    if polygon_area(points) <= 0:
        raise ValueError("An outline must enclose an area.")
    return points.copy()


def polygon_area(points):
    x, y = np.asarray(points, dtype=float).T
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def resample_closed(points, spacing=RESAMPLE_SPACING_PX):
    """Insert vertices so no edge of the closed outline exceeds ``spacing``."""
    points = np.asarray(points, dtype=float)
    result = []
    for start, end in zip(points, np.roll(points, -1, axis=0)):
        count = max(1, int(math.ceil(np.linalg.norm(end - start) / spacing)))
        steps = np.arange(count)[:, None] / count
        result.append(start + steps * (end - start))
    return np.vstack(result)


def points_in_polygon(points, polygon):
    """Even-odd test of ``(M, 2)`` points against an ``(N, 2)`` polygon."""
    points = np.asarray(points, dtype=float)
    polygon = np.asarray(polygon, dtype=float)
    x, y = points[:, 0][:, None], points[:, 1][:, None]
    x0, y0 = polygon[:, 0][None, :], polygon[:, 1][None, :]
    x1, y1 = np.roll(polygon[:, 0], -1)[None, :], np.roll(polygon[:, 1], -1)[None, :]
    crosses = (y0 > y) != (y1 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at_x = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
    return np.count_nonzero(crosses & (x < at_x), axis=1) % 2 == 1


def plane_frame(points3):
    """``(centre, u, v, normal)`` of the plane through planar 3D points."""
    points3 = np.asarray(points3, dtype=float)
    centre = points3.mean(axis=0)
    _u, _s, vt = np.linalg.svd(points3 - centre, full_matrices=False)
    return centre, vt[0], vt[1], vt[2]


def fill_outline(outline3, step=0.5, max_samples=40000):
    """Interior samples (every ``step`` voxels) of a planar 3D outline."""
    outline3 = np.asarray(outline3, dtype=float)
    centre, u, v, _normal = plane_frame(outline3)
    flat = np.stack([(outline3 - centre) @ u, (outline3 - centre) @ v], axis=1)
    low, high = flat.min(axis=0), flat.max(axis=0)
    area = max(polygon_area(flat), step * step)
    step = max(step, math.sqrt(area / max_samples))
    gx = np.arange(low[0], high[0] + step, step)
    gy = np.arange(low[1], high[1] + step, step)
    grid = np.stack(np.meshgrid(gx, gy), axis=-1).reshape(-1, 2)
    inside = grid[points_in_polygon(grid, flat)]
    if not len(inside):
        inside = flat
    return centre + inside[:, :1] * u + inside[:, 1:] * v


def section_plane(normal):
    """The cutting plane of a section from its normal: 'coronal', etc."""
    return PLANE_NAMES[int(np.argmax(np.abs(normal)))]


# -------------------------------------------------------------------- reports
class AtlasFrame:
    """What a fit needs from the atlas: labels, Bregma, voxel size, axes."""

    def __init__(self, label_data, label_info, bregma, voxel_um, axis_info=None):
        self.label_data = np.asarray(label_data)
        self.label_info = label_info
        self.bregma = np.asarray(bregma, dtype=float)
        self.voxel_um = float(voxel_um)
        self.axis_info = None
        self.allen = False
        if axis_info is not None:
            try:
                self.axis_info = normalize_axis_info(axis_info, self.label_data.shape)
                self.allen = is_allen_ccf_2017(self.axis_info, self.voxel_um)
            except (KeyError, TypeError, ValueError):
                self.axis_info = None

    def region(self, point):
        """``(label_id, name, acronym)`` of the region at a Bregma-relative point."""
        index = np.floor(np.asarray(point, dtype=float) + self.bregma).astype(int)
        if np.any(index < 0) or np.any(index >= self.label_data.shape):
            return 0, "outside the atlas", ""
        label = int(self.label_data[tuple(index)])
        if label == 0 or self.label_info is None:
            return label, "outside the brain" if label == 0 else str(label), ""
        matches = np.flatnonzero(np.ravel(self.label_info["index"]) == label)
        if not len(matches):
            return label, "Unknown [{}]".format(label), "?{}".format(label)
        return (label, str(self.label_info["label"][matches[0]]),
                str(self.label_info["abbrev"][matches[0]]))

    def regions_along(self, points):
        """Distinct regions met by ``points``, in order, with sample counts."""
        seen = {}
        for point in points:
            label, name, acronym = self.region(point)
            if label == 0:
                continue
            entry = seen.setdefault(label, {"label_id": label, "name": name,
                                            "acronym": acronym, "samples": 0})
            entry["samples"] += 1
        return list(seen.values())

    def coordinates(self, point):
        """Report coordinates of a Bregma-relative voxel point."""
        point = np.asarray(point, dtype=float)
        um = point * self.voxel_um
        result = {
            "bregma_relative_vox": point.tolist(),
            "ml_um": float(um[ML]),
            "ap_um": float(um[AP]),
            # Ventral positive, as stereotaxic depth.
            "dv_um": float(-um[DV]),
        }
        if self.axis_info is not None:
            record = _coordinate_record(point, self.bregma, self.voxel_um, self.axis_info,
                                        allen_ccf=self.allen)
            result["source_um"] = np.asarray(record["source_um"], dtype=float).tolist()
            if self.allen:
                ap, dv, ml = np.asarray(record["estimated_stereotaxic_bregma_mm"], dtype=float)
                result["estimated_bregma_mm"] = {"ap": float(ap), "ml": float(ml),
                                                 "dv": float(dv)}
        label, name, acronym = self.region(point)
        result.update(region_id=label, region=name, region_acronym=acronym)
        return result

    def surface_entry(self, centre, direction, anchor):
        """Where a line (``direction`` pointing ventrally) enters the brain, or None."""
        entry, error = find_probe_surface_entry(self.label_data, centre, direction,
                                                self.bregma, anchor=anchor)
        return None if error else np.asarray(entry, dtype=float)


def _pieces(pieces):
    """Validated ``(outline (N, 3), point (3,) or None, normal)`` per piece."""
    result = []
    for piece in pieces:
        if not isinstance(piece, dict):
            raise ValueError("Implant parts must be mappings.")
        outline = np.asarray(piece.get("outline"), dtype=float)
        if outline.ndim != 2 or outline.shape[1] != 3 or len(outline) < 3 \
                or not np.all(np.isfinite(outline)):
            raise ValueError("Implant part outlines must be finite (N, 3) points.")
        point = piece.get("point")
        if point is not None:
            point = np.asarray(point, dtype=float).reshape(3)
            if not np.all(np.isfinite(point)):
                raise ValueError("Implant part points must be finite.")
        normal = plane_frame(outline)[3]
        result.append((outline, point, normal))
    if not result:
        raise ValueError("An implant needs at least one mapped section.")
    return result


def _ventral(direction):
    direction = np.asarray(direction, dtype=float)
    direction = direction / np.linalg.norm(direction)
    return -direction if direction[DV] > 0 else direction


def _principal(samples):
    samples = np.asarray(samples, dtype=float)
    _u, _s, vt = np.linalg.svd(samples - samples.mean(axis=0), full_matrices=False)
    return vt[0]


def _tilts(top, bottom):
    ap_angle, ml_angle = get_angles(bottom - top)
    ap_tilt, ml_tilt = get_tilt_info(top, bottom)
    return {"ap_angle_deg": float(ap_angle), "ap_tilt": ap_tilt,
            "ml_angle_deg": float(ml_angle), "ml_tilt": ml_tilt}


def _width_across(outline, normal, direction):
    """Width of a planar outline across ``direction`` within its plane (voxels)."""
    across = np.cross(normal, direction)
    if np.linalg.norm(across) < 0.2:
        # The axis crosses the section: the outline is a cross-section.
        centre, u, v, _n = plane_frame(outline)
        flat = np.stack([(outline - centre) @ u, (outline - centre) @ v], axis=1)
        return float(np.max(np.ptp(flat, axis=0)))
    across /= np.linalg.norm(across)
    return float(np.ptp(outline @ across))


# ---------------------------------------------------------------------- fiber
def fit_fiber(pieces, specs, frame):
    """Fit a fiber (cylinder) to mapped section outlines; returns a report dict.

    ``pieces`` are dicts with ``outline`` ((N, 3) Bregma-relative voxels) and
    an optional ``point`` (the tip the user clicked).
    """
    specs = validated_specs(FIBER, specs)
    parts = _pieces(pieces)
    voxel_um = frame.voxel_um
    samples = np.vstack([fill_outline(outline) for outline, _p, _n in parts])
    outlines = np.vstack([outline for outline, _p, _n in parts])
    planes = sorted({section_plane(normal) for _o, _p, normal in parts})
    warnings = []
    if len(parts) == 1:
        # One section: the axis lies in it, seen as the outline's long axis.
        warnings.append("Only one section: the fiber's tilt out of the {} plane is unknown."
                        .format(planes[0]))
    direction = _ventral(_principal(samples))
    centre = samples.mean(axis=0)
    along = (outlines - centre) @ direction
    fitted_tip = centre + along.max() * direction
    top = centre + along.min() * direction

    clicked = [point for _o, point, _n in parts if point is not None]
    tip, tip_source = fitted_tip, "deepest point of the outlines"
    tip_offset_um = None
    if clicked:
        deepest = max(clicked, key=lambda p: float((p - centre) @ direction))
        tip_offset_um = float(np.linalg.norm(deepest - fitted_tip) * voxel_um)
        tip, tip_source = deepest, "marked tip"

    entry = frame.surface_entry(centre, direction, top)
    if entry is None:
        warnings.append("The fiber axis does not meet the brain surface in the atlas; "
                        "the depth below the surface is not available.")

    widths_um = [_width_across(outline, normal, direction) * voxel_um
                 for outline, _p, normal in parts]
    diameter = specs["diameter_um"]
    widest = max(widths_um)
    if widest > FIBER_WIDE_FACTOR * diameter:
        warnings.append("The widest outline ({:.0f} µm) is more than {:g} × the fiber "
                        "diameter ({:g} µm): tissue damage, or a tear included in the "
                        "outline.".format(widest, FIBER_WIDE_FACTOR, diameter))
    elif widest < FIBER_NARROW_FACTOR * diameter:
        warnings.append("Every outline is narrower than {:g} × the fiber diameter: no "
                        "section passed near the fiber's centre, so its position across "
                        "the sections is uncertain.".format(FIBER_NARROW_FACTOR))

    start = entry if entry is not None else top
    report = {
        "kind": FIBER,
        "specs": specs,
        "sections": len(parts),
        "section_planes": planes,
        "tip": frame.coordinates(tip),
        "tip_source": tip_source,
        "tip_offset_from_fit_um": tip_offset_um,
        "entry": frame.coordinates(entry) if entry is not None else None,
        "depth_below_surface_um": (float(np.linalg.norm(tip - entry) * voxel_um)
                                   if entry is not None else None),
        "length_in_sections_um": float((along.max() - along.min()) * voxel_um),
        "widest_outline_um": widest,
        "outline_widths_um": widths_um,
        "angles": _tilts(start, tip),
        "warnings": warnings,
        "model": {
            "type": "cylinder",
            "top": np.asarray(start, dtype=float).tolist(),
            "bottom": np.asarray(tip, dtype=float).tolist(),
            "radius_vox": diameter / 2.0 / voxel_um,
        },
    }
    return report


# ---------------------------------------------------------------------- prism
_FACE_AXIS = {"medial": ML, "lateral": ML, "anterior": AP, "posterior": AP}


def _insertion_direction(outline, normal):
    """The in-plane rectangle axis of an outline that is closer to vertical."""
    centre, u, v, _n = plane_frame(outline)
    flat = np.stack([(outline - centre) @ u, (outline - centre) @ v], axis=1)
    best = None
    # Minimum-area bounding rectangle: one side lies along a hull edge.
    for start, end in zip(flat, np.roll(flat, -1, axis=0)):
        edge = end - start
        length = np.linalg.norm(edge)
        if length < 1e-9:
            continue
        a = edge / length
        b = np.array([-a[1], a[0]])
        area = np.ptp(flat @ a) * np.ptp(flat @ b)
        if best is None or area < best[0]:
            best = (area, a, b)
    axes = [best[1][0] * u + best[1][1] * v, best[2][0] * u + best[2][1] * v]
    vertical = max(axes, key=lambda axis: abs(axis[DV]))
    return _ventral(vertical)


def fit_prism(pieces, specs, frame):
    """Fit a microprism (rectangular block) to mapped outlines; returns a report."""
    specs = validated_specs(PRISM, specs)
    parts = _pieces(pieces)
    voxel_um = frame.voxel_um
    outlines = np.vstack([outline for outline, _p, _n in parts])
    planes = sorted({section_plane(normal) for _o, _p, normal in parts})
    warnings = []

    directions = [_insertion_direction(outline, normal) for outline, _p, normal in parts]
    direction = _ventral(np.mean(directions, axis=0))
    centre = outlines.mean(axis=0)
    along = (outlines - centre) @ direction
    deepest_t = along.max()
    bottom_points = outlines[along >= deepest_t - 1.0]
    bottom_centre = centre + deepest_t * direction
    clicked = [point for _o, point, _n in parts if point is not None]
    bottom_source = "deepest edge of the outlines"
    if clicked:
        bottom_centre = max(clicked, key=lambda p: float((p - centre) @ direction))
        bottom_source = "marked bottom edge"
    top = centre + along.min() * direction

    ml = outlines[:, ML] * voxel_um
    ap = outlines[:, AP] * voxel_um
    # The medial edge is the one nearer the midline.
    near, far = (ml.min(), ml.max()) if ml.mean() >= 0 else (ml.max(), ml.min())
    face = specs["face"]
    face_axis = _FACE_AXIS[face]
    if face_axis == ML:
        face_um = near if face == "medial" else far
    else:
        face_um = ap.max() if face == "anterior" else ap.min()

    if "coronal" not in planes and len(parts) > 0:
        warnings.append("Sagittal sections do not show ML directly: the ML edges come from "
                        "the sections that contain the prism and are only as precise as the "
                        "section spacing.")
    if "sagittal" not in planes:
        warnings.append("The AP extent comes from the first and last sections that contain "
                        "the prism and is only as precise as the section spacing.")
    if len(parts) == 1:
        warnings.append("Only one section: the prism's tilt out of the {} plane is unknown."
                        .format(planes[0]))

    # Expected extents: width runs along the face, depth away from it.
    expected = {ML: specs["depth_um"] if face_axis == ML else specs["width_um"],
                AP: specs["width_um"] if face_axis == ML else specs["depth_um"]}
    for outline, _p, normal in parts:
        plane_axis = int(np.argmax(np.abs(normal)))
        if plane_axis == DV:
            continue
        shown = ML if plane_axis == AP else AP
        extent = float(np.ptp(outline[:, shown]) * voxel_um)
        target = expected[shown]
        if abs(extent - target) > PRISM_SIZE_TOLERANCE * target:
            warnings.append("A {} outline is {:.0f} µm across ({}), against {:.0f} µm "
                            "specified: shrinkage, damage, or an outline that misses part "
                            "of the prism.".format(PLANE_NAMES[plane_axis], extent,
                                                   "ML" if shown == ML else "AP", target))
            break

    # Regions the face looks into: just outside the face, bottom to top.
    face_sign = {"medial": -np.sign(ml.mean() or 1.0), "lateral": np.sign(ml.mean() or 1.0),
                 "anterior": 1.0, "posterior": -1.0}[face]
    outward = np.zeros(3)
    outward[face_axis] = face_sign
    face_points = outlines[np.abs(outlines[:, face_axis] * voxel_um - face_um) <= voxel_um]
    face_regions = frame.regions_along(face_points + outward * 1.5) if len(face_points) else []

    entry = frame.surface_entry(centre, direction, top)
    if entry is None:
        warnings.append("The prism axis does not meet the brain surface in the atlas; "
                        "the depth below the surface is not available.")

    corners = bottom_points[np.argsort(bottom_points[:, ML])][[0, -1]]
    report = {
        "kind": PRISM,
        "specs": specs,
        "sections": len(parts),
        "section_planes": planes,
        "bottom": frame.coordinates(bottom_centre),
        "bottom_source": bottom_source,
        "bottom_corners": [frame.coordinates(corner) for corner in corners],
        "ml_medial_edge_um": float(near),
        "ml_lateral_edge_um": float(far),
        "ml_centre_um": float((near + far) / 2.0),
        "face": face,
        "face_um": float(face_um),
        "face_axis": "ML" if face_axis == ML else "AP",
        "ap_range_um": [float(ap.min()), float(ap.max())],
        "face_regions": face_regions,
        "entry": frame.coordinates(entry) if entry is not None else None,
        "depth_below_surface_um": (float(np.linalg.norm(bottom_centre - entry) * voxel_um)
                                   if entry is not None else None),
        "angles": _tilts(entry if entry is not None else top, bottom_centre),
        "warnings": warnings,
        "model": _prism_model(specs, outlines, direction, bottom_centre,
                              entry if entry is not None else top, face_axis, voxel_um),
    }
    return report


def _prism_model(specs, outlines, direction, bottom, top, face_axis, voxel_um):
    """A block: bottom centre, height axis, face normal and half sizes in voxels."""
    face_normal = np.zeros(3)
    face_normal[face_axis] = 1.0
    face_normal -= (face_normal @ direction) * direction
    face_normal /= np.linalg.norm(face_normal)
    across = np.cross(direction, face_normal)
    centre = outlines.mean(axis=0)
    # Centre the block on the outlines across the axis, keep its bottom.
    offset = centre - bottom
    offset -= (offset @ direction) * direction
    bottom = bottom + offset
    height = float(np.linalg.norm(np.asarray(top) - bottom))
    return {
        "type": "block",
        "bottom": bottom.tolist(),
        "up": (-direction).tolist(),
        "face_normal": face_normal.tolist(),
        "across": across.tolist(),
        "height_vox": height,
        "half_depth_vox": specs["depth_um"] / 2.0 / voxel_um,
        "half_width_vox": specs["width_um"] / 2.0 / voxel_um,
    }


# -------------------------------------------------------------------- display
def model_segments(model):
    """Line segments ``(2K, 3)`` drawing a fitted model in 3D."""
    if model["type"] == "cylinder":
        top, bottom = np.asarray(model["top"]), np.asarray(model["bottom"])
        axis = bottom - top
        length = np.linalg.norm(axis)
        axis = axis / length if length else np.array([0.0, 0.0, -1.0])
        helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        a = np.cross(axis, helper)
        a /= np.linalg.norm(a)
        b = np.cross(axis, a)
        angles = np.linspace(0, 2 * np.pi, 25)
        ring = (np.cos(angles)[:, None] * a + np.sin(angles)[:, None] * b) * model["radius_vox"]
        segments = []
        for end in (top, bottom):
            circle = end + ring
            segments += [p for pair in zip(circle[:-1], circle[1:]) for p in pair]
        for k in range(0, 24, 3):
            segments += [top + ring[k], bottom + ring[k]]
        return np.asarray(segments)
    bottom = np.asarray(model["bottom"])
    up, face, across = (np.asarray(model[k]) for k in ("up", "face_normal", "across"))
    corners = []
    for h in (0.0, model["height_vox"]):
        for d, w in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            corners.append(bottom + h * up + d * model["half_depth_vox"] * face
                           + w * model["half_width_vox"] * across)
    edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    return np.asarray([corners[i] for edge in edges for i in edge])


# ------------------------------------------------------------------- reporting
def _mm(value_um):
    return "{:+.3f} mm".format(value_um / 1000.0)


def _point_line(label, point):
    line = "{}: ML {} · AP {} · DV {} (from atlas Bregma, ventral +)".format(
        label, _mm(point["ml_um"]), _mm(point["ap_um"]), _mm(point["dv_um"]))
    estimate = point.get("estimated_bregma_mm")
    if estimate:
        line += "\n    stereotaxic estimate: AP {:+.2f} · ML {:+.2f} · DV {:+.2f} mm".format(
            estimate["ap"], estimate["ml"], estimate["dv"])
    if point.get("region"):
        line += "\n    region: {}{}".format(point["region"], " ({})".format(
            point["region_acronym"]) if point.get("region_acronym") else "")
    return line


def report_lines(report):
    """The report as lines of plain text, most important first."""
    lines = []
    if report["kind"] == FIBER:
        lines.append(_point_line("Tip ({})".format(report["tip_source"]), report["tip"]))
        if report["tip_offset_from_fit_um"] is not None:
            lines.append("Marked tip is {:.0f} µm from the deepest outline point.".format(
                report["tip_offset_from_fit_um"]))
    else:
        lines.append(_point_line("Bottom centre ({})".format(report["bottom_source"]),
                                 report["bottom"]))
        lines.append("ML: medial edge {} · lateral edge {} · centre {}".format(
            _mm(report["ml_medial_edge_um"]), _mm(report["ml_lateral_edge_um"]),
            _mm(report["ml_centre_um"])))
        lines.append("Imaging face ({}): {} {}".format(report["face"], report["face_axis"],
                                                      _mm(report["face_um"])))
        lines.append("AP extent: {} to {}".format(*(_mm(v) for v in report["ap_range_um"])))
        if report["face_regions"]:
            lines.append("Face looks into: " + ", ".join(
                r["acronym"] or r["name"] for r in report["face_regions"]))
    if report["depth_below_surface_um"] is not None:
        lines.append("Depth below the brain surface: {:.0f} µm along the insertion axis."
                     .format(report["depth_below_surface_um"]))
    angles = report["angles"]
    lines.append("Tilt from vertical: AP {:.1f}° {} · ML {:.1f}° {}".format(
        angles["ap_angle_deg"], angles["ap_tilt"], angles["ml_angle_deg"], angles["ml_tilt"]))
    lines.append("{} section{} ({}).".format(report["sections"], "" if report["sections"] == 1
                                           else "s", ", ".join(report["section_planes"])))
    lines += ["⚠ " + warning for warning in report["warnings"]]
    return lines


CSV_COLUMNS = (
    "name", "type", "specs", "sections", "section_planes",
    "point", "ml_um", "ap_um", "dv_um", "region", "region_acronym",
    "est_ap_mm", "est_ml_mm", "est_dv_mm", "depth_below_surface_um",
    "ml_medial_edge_um", "ml_lateral_edge_um", "ml_centre_um", "face", "face_um",
    "ap_min_um", "ap_max_um", "face_regions",
    "ap_tilt_deg", "ap_tilt", "ml_tilt_deg", "ml_tilt", "warnings",
)


def csv_row(name, report):
    """One CSV row (a dict over :data:`CSV_COLUMNS`) per built implant."""
    point = report["tip"] if report["kind"] == FIBER else report["bottom"]
    estimate = point.get("estimated_bregma_mm") or {}
    angles = report["angles"]
    row = {
        "name": name,
        "type": TYPE_NAMES[report["kind"]],
        "specs": describe_specs(report["kind"], report["specs"]),
        "sections": report["sections"],
        "section_planes": " ".join(report["section_planes"]),
        "point": "tip" if report["kind"] == FIBER else "bottom centre",
        "ml_um": round(point["ml_um"], 1),
        "ap_um": round(point["ap_um"], 1),
        "dv_um": round(point["dv_um"], 1),
        "region": point.get("region", ""),
        "region_acronym": point.get("region_acronym", ""),
        "est_ap_mm": estimate.get("ap", ""),
        "est_ml_mm": estimate.get("ml", ""),
        "est_dv_mm": estimate.get("dv", ""),
        "depth_below_surface_um": ("" if report["depth_below_surface_um"] is None
                                   else round(report["depth_below_surface_um"], 1)),
        "ap_tilt_deg": round(angles["ap_angle_deg"], 2),
        "ap_tilt": angles["ap_tilt"],
        "ml_tilt_deg": round(angles["ml_angle_deg"], 2),
        "ml_tilt": angles["ml_tilt"],
        "warnings": " | ".join(report["warnings"]),
    }
    if report["kind"] == PRISM:
        row.update(
            ml_medial_edge_um=round(report["ml_medial_edge_um"], 1),
            ml_lateral_edge_um=round(report["ml_lateral_edge_um"], 1),
            ml_centre_um=round(report["ml_centre_um"], 1),
            face=report["face"], face_um=round(report["face_um"], 1),
            ap_min_um=round(report["ap_range_um"][0], 1),
            ap_max_um=round(report["ap_range_um"][1], 1),
            face_regions=" ".join(r["acronym"] or r["name"] for r in report["face_regions"]))
    return {column: row.get(column, "") for column in CSV_COLUMNS}
