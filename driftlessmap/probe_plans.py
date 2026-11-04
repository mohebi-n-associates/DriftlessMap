"""Planned probes as poses (GUI-free; see ``probe_planning_design.md``).

A plan is the probe's tip, its tilts in the sagittal (AP) and coronal (ML)
planes and its roll about the shank. Everything the surgeon needs (the entry
on the brain surface, the depth along the probe, the regions along the
shank) is computed from the pose and the atlas labels by :func:`plan_readout`.

Frame: Bregma-relative, x = ML (positive is the animal's right), y = AP
(positive is anterior), z = DV (positive is dorsal), in micrometres. Atlas
voxel indexes are ``um / vox_um + bregma`` in the label volume the engine
builds probes from (``DriftlessMap._merge_label_volume``).
"""

import copy
import math

import numpy as np

MAX_TILT_DEG = 80.0
SAMPLE_STEP_VOX = 0.5
DEFAULT_DEPTH_UM = 3000.0
# Regions shorter than this along the shank are listed but not named in the
# one-line summary.
SUMMARY_MIN_UM = 50.0

PLAN_FIELDS = ("probe", "tip_um", "ap_tilt_deg", "ml_tilt_deg", "roll_deg",
               "probe_settings", "shank_offsets_um", "bank")
CHANNELS_PER_BANK = 384


# --------------------------------------------------------------- geometry
def direction_from_tilts(ap_tilt_deg, ml_tilt_deg):
    """Unit vector from the entry to the tip (pointing into the brain)."""
    vector = np.array([math.tan(math.radians(ml_tilt_deg)),
                       math.tan(math.radians(ap_tilt_deg)), -1.0])
    return vector / np.linalg.norm(vector)


def tilts_from_direction(direction):
    """(AP tilt, ML tilt) in degrees of a direction; it is turned to point down."""
    d = np.asarray(direction, dtype=float)
    if d[2] > 0:
        d = -d
    if abs(d[2]) < 1e-9:
        raise ValueError("A horizontal probe has no tilt from vertical.")
    return (math.degrees(math.atan2(d[1], -d[2])),
            math.degrees(math.atan2(d[0], -d[2])))


def face_normal(direction, roll_deg):
    """The direction the contacts face.

    At roll 0 they face anterior (the anterior axis made perpendicular to the
    shank); a positive roll turns them towards the animal's right, seen from
    above.
    """
    d = np.asarray(direction, dtype=float)
    d = d / np.linalg.norm(d)
    anterior = np.array([0.0, 1.0, 0.0])
    n0 = anterior - np.dot(anterior, d) * d
    n0 /= np.linalg.norm(n0)
    angle = math.radians(roll_deg)
    # Rodrigues' rotation about d (pointing down): anterior turns to the right.
    n = n0 * math.cos(angle) + np.cross(d, n0) * math.sin(angle)
    return n / np.linalg.norm(n)


def across_face(direction, normal):
    """The across-the-face axis the engine's multi-shank layout uses."""
    return np.cross(normal, direction)


def face_words(normal):
    """Name the main direction a unit vector points in."""
    names = (("the animal's left", "the animal's right"), ("posterior", "anterior"),
             ("ventral", "dorsal"))
    axis = int(np.argmax(np.abs(normal)))
    return names[axis][int(normal[axis] > 0)]


def tilt_words(plan, entry_um=None):
    """The tilts in words: which way the tip lies from the entry."""
    parts = []
    if abs(plan.ap_tilt_deg) >= 0.05:
        parts.append("{:.1f}° {}".format(abs(plan.ap_tilt_deg),
                                         "anterior" if plan.ap_tilt_deg > 0 else "posterior"))
    if abs(plan.ml_tilt_deg) >= 0.05:
        side = entry_um[0] if entry_um is not None else plan.tip_um[0]
        towards_right = plan.ml_tilt_deg > 0
        lateral = (side >= 0) == towards_right if side != 0 else True
        parts.append("{:.1f}° {} ({})".format(
            abs(plan.ml_tilt_deg), "lateral" if lateral else "medial",
            "towards the animal's right" if towards_right else "towards the animal's left"))
    return ", ".join(parts) if parts else "vertical"


# ------------------------------------------------------------------- plans
class ProbePlan:
    """One planned probe (see the module docstring for the frame)."""

    def __init__(self, probe, tip_um, ap_tilt_deg=0.0, ml_tilt_deg=0.0, roll_deg=0.0,
                 probe_settings=None, shank_offsets_um=None, bank=0):
        self.probe = str(probe)
        self.tip_um = [float(v) for v in tip_um]
        self.ap_tilt_deg = float(ap_tilt_deg)
        self.ml_tilt_deg = float(ml_tilt_deg)
        self.roll_deg = float(roll_deg) % 360.0
        self.probe_settings = copy.deepcopy(probe_settings) if probe_settings else None
        self.shank_offsets_um = ([float(v) for v in shank_offsets_um]
                                 if shank_offsets_um else None)
        # Recording window: the bank of channels counted from the tip (0 is
        # the lowest 384), or None for every site (2.8.1; absent means 0).
        self.bank = None if bank is None else int(bank)
        self.validate()

    def validate(self):
        if not self.probe.strip():
            raise ValueError("a plan needs its probe's name")
        if len(self.tip_um) != 3 or not all(math.isfinite(v) for v in self.tip_um):
            raise ValueError("the tip needs three finite coordinates")
        for name in ("ap_tilt_deg", "ml_tilt_deg", "roll_deg"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError("{} is not a number".format(name))
        for name in ("ap_tilt_deg", "ml_tilt_deg"):
            if abs(getattr(self, name)) > MAX_TILT_DEG:
                raise ValueError("tilts must lie within ±{:g}°".format(MAX_TILT_DEG))
        if self.probe_settings is not None:
            if not isinstance(self.probe_settings, dict):
                raise ValueError("the probe settings are not a dictionary")
            length = self.probe_settings.get("probe_length")
            if length is not None and not (isinstance(length, (int, float)) and length > 0):
                raise ValueError("the probe length must be positive")
        if self.bank is not None and not 0 <= self.bank < 64:
            raise ValueError("the bank must lie between 0 and 63")
        if self.shank_offsets_um is not None:
            if not all(math.isfinite(v) for v in self.shank_offsets_um):
                raise ValueError("shank offsets must be finite")
            if not 1 <= len(self.shank_offsets_um) <= 16:
                raise ValueError("a probe has 1 to 16 shanks")

    @property
    def direction(self):
        return direction_from_tilts(self.ap_tilt_deg, self.ml_tilt_deg)

    @property
    def normal(self):
        return face_normal(self.direction, self.roll_deg)

    @property
    def shank_length_um(self):
        settings = self.probe_settings or {}
        length = settings.get("probe_length")
        return float(length) if length else None

    def copy(self, **changes):
        data = self.to_dict()
        data.update(changes)
        return ProbePlan.from_dict(data)

    def to_dict(self):
        return {
            "probe": self.probe,
            "tip_um": list(self.tip_um),
            "ap_tilt_deg": self.ap_tilt_deg,
            "ml_tilt_deg": self.ml_tilt_deg,
            "roll_deg": self.roll_deg,
            "probe_settings": copy.deepcopy(self.probe_settings),
            "shank_offsets_um": (list(self.shank_offsets_um)
                                 if self.shank_offsets_um else None),
            "bank": self.bank,
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("a plan must be a dictionary")
        try:
            return cls(
                data["probe"], data["tip_um"],
                data.get("ap_tilt_deg", 0.0), data.get("ml_tilt_deg", 0.0),
                data.get("roll_deg", 0.0), data.get("probe_settings"),
                data.get("shank_offsets_um"), data.get("bank", 0))
        except (KeyError, TypeError) as exc:
            raise ValueError("incomplete plan ({})".format(exc)) from None

    def __eq__(self, other):
        return isinstance(other, ProbePlan) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return "ProbePlan({!r})".format(self.to_dict())


def plan_from_points(probe, entry_um, tip_um, **keep):
    """A plan through two points (entry above tip), keeping other settings."""
    entry = np.asarray(entry_um, dtype=float)
    tip = np.asarray(tip_um, dtype=float)
    if entry[2] < tip[2]:
        entry, tip = tip, entry
    if np.linalg.norm(tip - entry) < 1e-6:
        raise ValueError("the entry and the tip are the same point")
    ap, ml = tilts_from_direction(tip - entry)
    if max(abs(ap), abs(ml)) > MAX_TILT_DEG:
        raise ValueError("the two points lie too close to horizontal (tilt over "
                         "{:g}°)".format(MAX_TILT_DEG))
    return ProbePlan(probe, tip.tolist(), ap, ml, **keep)


def plan_from_entry_depth(plan, entry_um, depth_um):
    """``plan`` moved so the probe enters at ``entry_um`` and goes ``depth_um`` deep."""
    tip = np.asarray(entry_um, dtype=float) + plan.direction * float(depth_um)
    return plan.copy(tip_um=tip.tolist())


def column_surface(atlas, ml_um, ap_um):
    """The brain surface straight down at (ML, AP): a point in um, or None."""
    bottom = -atlas.bregma[2] * atlas.vox_um
    entry, _inside = surface_entry(atlas, [ml_um, ap_um, bottom], np.array([0.0, 0.0, -1.0]))
    return entry


def plan_from_surface(plan, atlas, ml_um, ap_um, depth_um):
    """``plan`` entering the brain at (ML, AP) on the surface, ``depth_um`` deep.

    The entry is the surface straight below (ML, AP); the tilts are kept.
    Raises ValueError when there is no brain at that point.
    """
    surface = column_surface(atlas, ml_um, ap_um)
    if surface is None:
        raise ValueError("there is no brain at AP {:.2f}, ML {:.2f} mm".format(
            ap_um / 1000.0, ml_um / 1000.0))
    return plan_from_entry_depth(plan, surface, depth_um)


def tip_to_surface(plan, atlas, along_probe=True):
    """``plan`` with its tip moved to the brain surface.

    Along the probe: back up the probe to where it enters the brain. Straight
    down: to the surface directly above or below the tip (same AP and ML).
    Raises ValueError when there is no surface to move to.
    """
    if along_probe:
        entry, _inside = surface_entry(atlas, plan.tip_um, plan.direction)
        if entry is None:
            raise ValueError("the probe does not meet the brain")
        return plan.copy(tip_um=list(entry))
    surface = column_surface(atlas, plan.tip_um[0], plan.tip_um[1])
    if surface is None:
        raise ValueError("there is no brain above or below the tip")
    return plan.copy(tip_um=list(surface))


class PlanBook:
    """The project's probe plans, keyed by probe name."""

    def __init__(self):
        self._plans = {}

    def __contains__(self, probe):
        return probe in self._plans

    def __len__(self):
        return len(self._plans)

    def get(self, probe):
        return self._plans.get(probe)

    def plans(self):
        return [self._plans[name] for name in sorted(self._plans)]

    def set(self, plan):
        plan.validate()
        self._plans[plan.probe] = plan
        return plan

    def remove(self, probe):
        return self._plans.pop(probe, None)

    def rename(self, old, new):
        plan = self._plans.pop(old, None)
        if plan is not None:
            plan.probe = new
            self._plans[new] = plan
        return plan

    def to_list(self):
        return [plan.to_dict() for plan in self.plans()]

    @classmethod
    def from_list(cls, items):
        """Plans from saved data and a list of problems with the invalid ones."""
        book, problems = cls(), []
        if items is None:
            return book, problems
        if not isinstance(items, list):
            return book, ["the saved probe plans are not a list"]
        for item in items:
            try:
                plan = ProbePlan.from_dict(item)
            except ValueError as exc:
                name = item.get("probe") if isinstance(item, dict) else None
                problems.append("{}: {}".format(name or "a plan", exc))
                continue
            if plan.probe in book:
                problems.append("{}: planned twice; the first plan was kept".format(plan.probe))
                continue
            book.set(plan)
        return book, problems


# ------------------------------------------------------------------- atlas
class PlanAtlas:
    """The label volume and names a plan is read against."""

    def __init__(self, label_data, label_info, vox_um, bregma_vox):
        self.labels = label_data
        self.vox_um = float(vox_um)
        self.bregma = np.asarray(bregma_vox, dtype=float)
        self.shape = np.asarray(label_data.shape, dtype=int)
        self.label_info = label_info
        self._names = {}
        if label_info is not None:
            for index, abbrev, name, colour in zip(
                    np.ravel(label_info["index"]), label_info["abbrev"],
                    label_info["label"], label_info["color"]):
                self._names[int(index)] = (str(abbrev), str(name),
                                           tuple(int(c) for c in np.ravel(colour)[:3]))
        self._children = None

    def to_vox(self, um):
        return np.asarray(um, dtype=float) / self.vox_um + self.bregma

    def to_um(self, vox):
        return (np.asarray(vox, dtype=float) - self.bregma) * self.vox_um

    def name(self, label):
        label = int(label)
        if label == 0:
            return ("outside", "outside the brain", (128, 128, 128))
        return self._names.get(label, ("?{}".format(label), "Unknown [{}]".format(label),
                                       (128, 128, 128)))

    def labels_at(self, vox_points):
        """Labels at continuous voxel positions; 0 outside the volume."""
        points = np.floor(np.asarray(vox_points, dtype=float)).astype(int)
        inside = np.all((points >= 0) & (points < self.shape), axis=1)
        out = np.zeros(len(points), dtype=np.int64)
        if np.any(inside):
            p = points[inside]
            out[inside] = self.labels[p[:, 0], p[:, 1], p[:, 2]]
        return out, inside

    def descendants(self, region_id):
        """``region_id`` and every region below it in the label tree."""
        if self._children is None:
            self._children = {}
            info = self.label_info or {}
            if "parent" in info:
                for index, parent in zip(np.ravel(info["index"]), np.ravel(info["parent"])):
                    self._children.setdefault(int(parent), []).append(int(index))
        found, stack = set(), [int(region_id)]
        while stack:
            current = stack.pop()
            if current in found:
                continue
            found.add(current)
            stack.extend(self._children.get(current, []))
        return found


def _line_samples(atlas, start_vox, direction, length_vox):
    count = max(2, int(math.ceil(length_vox / SAMPLE_STEP_VOX)) + 1)
    distances = np.linspace(0.0, length_vox, count)
    return distances, start_vox + distances[:, None] * direction


def surface_entry(atlas, tip_um, direction):
    """Where a line through ``tip_um`` along ``direction`` first meets the brain.

    Returns ``(entry_um, tip_inside)``: the first brain point coming down the
    line from above the brain (None when the line meets no brain above or at
    the tip) and whether the tip itself is inside the brain.
    """
    tip = atlas.to_vox(tip_um)
    d = np.asarray(direction, dtype=float)
    # Walk back up the line to where it leaves the volume.
    reach = []
    for axis in range(3):
        if abs(d[axis]) > 1e-12:
            bounds = (np.array([0.0, atlas.shape[axis] - 1.0]) - tip[axis]) / d[axis]
            reach.append(bounds.min())
    back = max(0.0, -max(reach)) if reach else 0.0
    start = tip - back * d
    distances, points = _line_samples(atlas, start, d, back)
    labels, _inside = atlas.labels_at(points)
    occupied = np.flatnonzero(labels != 0)
    tip_label = atlas.labels_at(tip[None, :])[0][0]
    if not len(occupied):
        return None, bool(tip_label != 0)
    first = int(occupied[0])
    if first == 0:
        return atlas.to_um(points[0]).tolist(), bool(tip_label != 0)
    # The exact point where the line enters the first brain voxel, so the
    # entry does not depend on where the samples fall along the line.
    low, high = distances[first - 1], distances[first]
    for _step in range(40):
        middle = (low + high) / 2.0
        if atlas.labels_at((start + middle * d)[None, :])[0][0] != 0:
            high = middle
        else:
            low = middle
    return atlas.to_um(start + high * d).tolist(), bool(tip_label != 0)


def regions_along(atlas, entry_um, tip_um):
    """Runs of one region from the entry to the tip.

    Each run is a dict with ``id``, ``acronym``, ``name``, ``colour`` and
    ``start_um``/``end_um``, depths along the probe from the entry.
    """
    entry = atlas.to_vox(entry_um)
    tip = atlas.to_vox(tip_um)
    length_vox = float(np.linalg.norm(tip - entry))
    if length_vox < 1e-9:
        return []
    direction = (tip - entry) / length_vox
    distances, points = _line_samples(atlas, entry, direction, length_vox)
    labels, _inside = atlas.labels_at(points)
    # A run changes label halfway between two samples.
    changes = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate([[0], changes])
    edges = np.concatenate([[0.0], (distances[changes - 1] + distances[changes]) / 2,
                            [length_vox]]) * atlas.vox_um
    runs = []
    for number, first in enumerate(starts):
        label = int(labels[first])
        acronym, name, colour = atlas.name(label)
        runs.append({"id": label, "acronym": acronym, "name": name, "colour": colour,
                     "start_um": float(edges[number]), "end_um": float(edges[number + 1]),
                     "length_um": float(edges[number + 1] - edges[number])})
    return runs


def site_offsets_um(settings):
    """Distance of every site of the full shank above the tip's base, sorted.

    Uses the engine's site layout (``get_sites_loc_related_to_base_center``);
    a tetrode has its four sites at the tip.
    """
    from .probe_utiles import get_sites_loc_related_to_base_center

    settings = settings or {}
    if settings.get("probe_type_name") == "Tetrode" or not settings.get("probe_length"):
        return np.zeros(1)
    shank = float(settings["probe_length"]) - float(settings.get("tip_length") or 0.0)
    columns = get_sites_loc_related_to_base_center(settings, shank)
    offsets = np.concatenate([np.asarray(column, dtype=float)[:, 0] for column in columns
                              if len(column)]) if columns else np.zeros(0)
    return np.sort(offsets)


def bank_count(settings):
    settings = settings or {}
    if not settings.get("site_number_in_banks"):
        return 1
    return max(1, int(math.ceil(len(site_offsets_um(settings)) / CHANNELS_PER_BANK)))


def recording_sites(plan):
    """Offsets (above the tip's base) of the sites in the plan's recording window."""
    settings = plan.probe_settings or {}
    offsets = site_offsets_um(settings)
    if plan.bank is None or not settings.get("site_number_in_banks"):
        return offsets
    bank = min(plan.bank, bank_count(settings) - 1)
    return offsets[bank * CHANNELS_PER_BANK:(bank + 1) * CHANNELS_PER_BANK]


def window_coverage(runs, top_um, bottom_um, site_depths=None):
    """Length (and sites) of each region inside the depth window [top, bottom]."""
    found = {}
    order = []
    for number, run in enumerate(runs):
        overlap = min(run["end_um"], bottom_um) - max(run["start_um"], top_um)
        if overlap < 0 or run["id"] == 0 or (overlap == 0 and site_depths is None):
            continue
        if run["id"] not in found:
            found[run["id"]] = {"id": run["id"], "acronym": run["acronym"],
                                "name": run["name"], "colour": run["colour"],
                                "length_um": 0.0, "sites": 0}
            order.append(run["id"])
        found[run["id"]]["length_um"] += overlap
        if site_depths is not None:
            # Runs are half open, [start, end), except the last one, which ends
            # at the tip; the window includes both its ends.
            last = number == len(runs) - 1
            below = site_depths <= run["end_um"] if last else site_depths < run["end_um"]
            inside = (site_depths >= run["start_um"]) & below & \
                (site_depths >= top_um) & (site_depths <= bottom_um)
            found[run["id"]]["sites"] += int(np.count_nonzero(inside))
    return [found[key] for key in order if found[key]["length_um"] > 0 or found[key]["sites"]]


def plan_readout(plan, atlas):
    """Everything a plan gives, as a plain dictionary (see the design, 2.3)."""
    direction = plan.direction
    entry, tip_inside = surface_entry(atlas, plan.tip_um, direction)
    warnings = []
    tip = np.asarray(plan.tip_um, dtype=float)
    tip_vox = atlas.to_vox(tip)
    readout = {
        "probe": plan.probe,
        "tip_um": tip.tolist(),
        "entry_um": entry,
        "depth_um": None,
        "ap_tilt_deg": plan.ap_tilt_deg,
        "ml_tilt_deg": plan.ml_tilt_deg,
        "roll_deg": plan.roll_deg,
        "tilt": tilt_words(plan, entry),
        "face": face_words(plan.normal),
        "regions": [],
        "tip_region": atlas.name(atlas.labels_at(tip_vox[None, :])[0][0]),
        "warnings": warnings,
        "reachable": False,
        "contacts_um": [],
        "window_um": None,
        "window_regions": [],
        "window_sites": 0,
        "window_sites_in_brain": 0,
    }
    if np.any(tip_vox < 0) or np.any(tip_vox > atlas.shape - 1):
        warnings.append("The tip lies outside the atlas.")
    if entry is None:
        warnings.append("The probe does not meet the brain above its tip; move the tip "
                        "into the brain.")
        return readout
    depth = float(np.dot(tip - np.asarray(entry), direction))
    readout["depth_um"] = depth
    if not tip_inside:
        warnings.append("The tip is not inside the brain.")
    readout["regions"] = regions_along(atlas, entry, tip)
    length = plan.shank_length_um
    readout["reachable"] = True
    _add_window(readout, plan, depth)
    if depth < atlas.vox_um:
        readout["reachable"] = False
        warnings.append("The tip is at the brain surface; move it deeper.")
    if length is not None and depth > length:
        readout["reachable"] = False
        warnings.append("The tip is {:.2f} mm deep, deeper than the {:.1f} mm shank "
                        "reaches.".format(depth / 1000.0, length / 1000.0))
    if entry[0] * tip[0] < 0 and min(abs(entry[0]), abs(tip[0])) > atlas.vox_um:
        warnings.append("The probe crosses the midline.")
    return readout


def _add_window(readout, plan, depth):
    """Contacts and the recording window along the shank, as depths from the entry."""
    settings = plan.probe_settings or {}
    tip_length = float(settings.get("tip_length") or 0.0)
    above_tip = depth - tip_length
    every = site_offsets_um(settings)
    window = recording_sites(plan)
    readout["contacts_um"] = (above_tip - every[every <= above_tip]).tolist()
    in_brain = window[window <= above_tip]
    readout["window_sites"] = int(len(window))
    readout["window_sites_in_brain"] = int(len(in_brain))
    if not len(window):
        readout["window_um"] = None
        readout["window_regions"] = []
        return
    top = above_tip - float(window.max())
    bottom = above_tip - float(window.min())
    readout["window_um"] = [top, bottom]
    depths = above_tip - window
    readout["window_regions"] = window_coverage(readout["regions"], max(top, 0.0), bottom,
                                                depths)


def region_summary(readout, limit=6):
    """The regions along the shank as one short line, dorsal to ventral."""
    names = []
    for run in readout.get("regions") or []:
        if run["id"] == 0 or run["length_um"] < SUMMARY_MIN_UM:
            continue
        if names and names[-1][0] == run["acronym"]:
            names[-1][1] += run["length_um"]
            continue
        names.append([run["acronym"], run["length_um"]])
    text = " → ".join("{} {:.2f}".format(name, length / 1000.0) for name, length in names[:limit])
    if len(names) > limit:
        text += " → …"
    return text + " (mm)" if text else ""


def coordinate_line(plan, readout, atlas_name=""):
    """One self-describing line for surgery notes."""
    def triple(values):
        return "AP {:+.3f}, ML {:+.3f}, DV {:+.3f} mm".format(
            values[1] / 1000.0, values[0] / 1000.0, values[2] / 1000.0)

    settings = plan.probe_settings or {}
    parts = [
        "{}:".format(plan.probe),
        "atlas {}".format(atlas_name) if atlas_name else "",
        "(from Bregma; ML + = animal's right, DV + = dorsal)",
        "entry {}".format(triple(readout["entry_um"])) if readout.get("entry_um") else "entry: none",
        "depth {:.3f} mm along the probe".format(readout["depth_um"] / 1000.0)
        if readout.get("depth_um") is not None else "",
        "tip {}".format(triple(readout["tip_um"])),
        "AP tilt {:+.1f}°, ML tilt {:+.1f}° ({})".format(
            plan.ap_tilt_deg, plan.ml_tilt_deg, readout.get("tilt", "")),
        "roll {:.0f}° (contacts face {})".format(plan.roll_deg, readout.get("face", "")),
        "probe {}".format(settings.get("probe_type_name")) if settings.get("probe_type_name") else "",
    ]
    regions = region_summary(readout)
    if regions:
        parts.append("regions {}".format(regions))
    window = window_text(plan, readout)
    if window:
        parts.append(window)
    return "; ".join(p for p in parts if p).replace(":;", ":")


def window_text(plan, readout):
    """The recording window in words, or ""."""
    if not readout.get("window_um"):
        return ""
    top, bottom = readout["window_um"]
    which = "every site" if plan.bank is None or bank_count(plan.probe_settings) <= 1 \
        else "bank {}".format(plan.bank)
    cover = ", ".join("{} {:.2f}".format(r["acronym"], r["length_um"] / 1000.0)
                      for r in readout.get("window_regions") or [])
    return "recording {} {:.2f}-{:.2f} mm deep ({} of {} sites in the brain){}".format(
        which, max(top, 0.0) / 1000.0, bottom / 1000.0, readout["window_sites_in_brain"],
        readout["window_sites"], ": " + cover + " (mm)" if cover else "")


def shank_lines(plan, readout, atlas):
    """Each shank's [entry, tip] in Bregma-relative voxels, for the engine's build.

    The shanks are offset across the face (``across_face``), as the engine's
    multi-shank layout does; each shank's entry is moved along the shank to
    the same height as the centre line's entry, and the engine finds each
    shank's own surface.
    """
    entry = np.asarray(readout["entry_um"], dtype=float)
    tip = np.asarray(plan.tip_um, dtype=float)
    direction = plan.direction
    across = across_face(direction, plan.normal)
    offsets = plan.shank_offsets_um or [0.0]
    lines = []
    for offset in offsets:
        shift = across * offset
        lines.append(np.vstack([entry + shift, tip + shift]) / atlas.vox_um)
    return lines


def probe_plane(atlas, plan, readout, half_width_um=1500.0, margin_um=500.0,
                max_pixels=360):
    """The atlas in the plane of the shank's face, around the probe.

    Rows run along the probe from ``margin_um`` above the entry to
    ``margin_um`` below the tip; columns run across the face (``across_face``)
    over ``±half_width_um``. Returns ``(labels, extent)``: an integer label image
    (0 outside the brain) and ``(top, bottom, left, right)`` in um (depth from
    the entry and distance across the face), or None without an entry.
    """
    entry = readout.get("entry_um")
    if entry is None:
        return None
    depth = float(readout["depth_um"])
    top, bottom = -margin_um, depth + margin_um
    pixel = max(atlas.vox_um, (bottom - top) / max_pixels, 2 * half_width_um / max_pixels)
    rows = np.arange(top + pixel / 2, bottom, pixel)
    cols = np.arange(-half_width_um + pixel / 2, half_width_um, pixel)
    direction = plan.direction
    across = across_face(direction, plan.normal)
    points = (np.asarray(entry, dtype=float)[None, None, :]
              + rows[:, None, None] * direction[None, None, :]
              + cols[None, :, None] * across[None, None, :])
    labels, _inside = atlas.labels_at(atlas.to_vox(points.reshape(-1, 3)))
    return labels.reshape(len(rows), len(cols)), (top, bottom, -half_width_um, half_width_um)


def region_centre(atlas, region_id, side=None, max_voxels=8_000_000):
    """A point inside ``region_id`` (and its sub-regions) near its centre, in um.

    ``side`` (+1 right, -1 left) keeps to one hemisphere, so a region present
    on both sides is not centred on the midline. The volume is searched on a
    strided copy (at most ``max_voxels``); the returned point is the region
    voxel nearest the centroid. Returns None when the region is not found.
    """
    ids = np.fromiter(atlas.descendants(region_id), dtype=np.int64)
    size = int(np.prod(atlas.shape))
    stride = max(1, int(math.ceil((size / max_voxels) ** (1.0 / 3.0))))
    sample = np.asarray(atlas.labels[::stride, ::stride, ::stride])
    mask = np.isin(sample, ids)
    if side is not None:
        ml = np.arange(sample.shape[0]) * stride + stride / 2.0 - atlas.bregma[0]
        keep = ml >= 0 if side >= 0 else ml < 0
        mask &= keep[:, None, None]
    found = np.argwhere(mask)
    if not len(found):
        return None
    # Continuous voxel positions of the sampled voxels' centres.
    vox = found * stride + 0.5
    centre = vox.mean(axis=0)
    nearest = vox[np.argmin(np.sum((vox - centre) ** 2, axis=1))]
    return atlas.to_um(nearest).tolist()
