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
               "probe_settings", "shank_offsets_um", "bank", "craniotomy", "targets",
               "avoid")
# Clearance between planned probes: checked from this far above each entry
# down to the tip, and reported when closer than CLEARANCE_UM.
CLEARANCE_ABOVE_UM = 3000.0
CLEARANCE_UM = 300.0
CRANIOTOMY_MARGIN_UM = 250.0
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
                 probe_settings=None, shank_offsets_um=None, bank=0, craniotomy=None,
                 targets=None, avoid=None):
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
        # The craniotomy the probe goes through (an id in the project's
        # CraniotomyBook), or None (2.10.0; absent means None).
        self.craniotomy = None if craniotomy is None else str(craniotomy)
        # Regions the probe is meant to record and to keep out of (ids; 2.8.3,
        # absent means none). Proposals search for them; the readout scores them.
        self.targets = [int(t) for t in targets or []]
        self.avoid = [int(a) for a in avoid or []]
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
        if len(self.targets) > 32 or len(self.avoid) > 256:
            raise ValueError("too many target or avoided regions")
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
            "craniotomy": self.craniotomy,
            "targets": list(self.targets),
            "avoid": list(self.avoid),
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
                data.get("shank_offsets_um"), data.get("bank", 0), data.get("craniotomy"),
                data.get("targets"), data.get("avoid"))
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
    for _step in range(30):          # half a voxel / 2**30: about 1e-8 um at 25 um voxels
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
    # Every physical shank, against the plan's regions to keep out of; tissue
    # gaps along the track are reported (review R1 and R5 of 2.8.3).
    hard, soft = track_checks(plan, atlas, plan.avoid)
    for message in hard + soft:
        if message.startswith("The probe's tip") or message in warnings:
            continue   # the tip is reported above for a single shank
        warnings.append(message)
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
        "arm azimuth {:.1f}°, elevation {:.1f}°".format(*readout["arm"])
        if readout.get("arm") else "",
        "roll {:.0f}° (contacts face {})".format(plan.roll_deg, readout.get("face", "")),
        "probe {}".format(settings.get("probe_type_name")) if settings.get("probe_type_name") else "",
    ]
    regions = region_summary(readout)
    if regions:
        parts.append("regions {}".format(regions))
    window = window_text(plan, readout)
    if window:
        parts.append(window)
    craniotomy = readout.get("craniotomy")
    if craniotomy:
        parts.append("through {} (centre AP {:+.3f}, ML {:+.3f} mm, {:.2f} mm across)".format(
            craniotomy["name"], craniotomy["centre_um"][1] / 1000.0,
            craniotomy["centre_um"][0] / 1000.0, craniotomy["diameter_um"] / 1000.0))
    scale = readout.get("scale", 1.0)
    if scale is None:
        parts.append("for this animal: unavailable (the atlas's Bregma-Lambda distance is "
                      "unknown)")
    elif abs(scale - 1.0) > 1e-9 and readout.get("entry_um") is not None:
        parts.append("for this animal (Bregma-Lambda scale x{:.3f}): entry {}, depth {:.3f} "
                     "mm".format(scale, triple(np.asarray(readout["entry_um"]) * scale),
                                 readout["depth_um"] * scale / 1000.0))
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


# ------------------------------------------------------------- arm angles
def arm_from_tilts(ap_tilt_deg, ml_tilt_deg):
    """(azimuth, elevation) of a probe from its AP and ML tilts.

    Elevation is the angle from vertical; azimuth is the direction the tip
    leans towards in the horizontal plane, from anterior (0) towards the
    animal's right (90). A vertical probe has azimuth 0.
    """
    lean_ml = math.tan(math.radians(ml_tilt_deg))
    lean_ap = math.tan(math.radians(ap_tilt_deg))
    lean = math.hypot(lean_ml, lean_ap)
    elevation = math.degrees(math.atan(lean))
    azimuth = math.degrees(math.atan2(lean_ml, lean_ap)) % 360.0 if lean > 1e-12 else 0.0
    return azimuth, elevation


def tilts_from_arm(azimuth_deg, elevation_deg):
    """(AP tilt, ML tilt) of a probe from its azimuth and elevation (exact inverse)."""
    lean = math.tan(math.radians(elevation_deg))
    return (math.degrees(math.atan(lean * math.cos(math.radians(azimuth_deg)))),
            math.degrees(math.atan(lean * math.sin(math.radians(azimuth_deg)))))


# ------------------------------------------------------------- craniotomies
class Craniotomy:
    """A circular opening in the skull: centre (ML, AP from Bregma) and diameter, in um."""

    def __init__(self, craniotomy_id, name, centre_um, diameter_um):
        self.craniotomy_id = str(craniotomy_id)
        self.name = " ".join(str(name).split())
        self.centre_um = [float(v) for v in centre_um]
        self.diameter_um = float(diameter_um)
        if not self.craniotomy_id or not self.name:
            raise ValueError("a craniotomy needs an id and a name")
        if len(self.centre_um) != 2 or not all(math.isfinite(v) for v in self.centre_um):
            raise ValueError("a craniotomy's centre needs ML and AP")
        if not (math.isfinite(self.diameter_um) and 0 < self.diameter_um <= 20000):
            raise ValueError("a craniotomy's diameter must lie between 0 and 20 mm")

    def distance_um(self, point_um):
        """Distance in the horizontal plane from the centre to ``point_um``."""
        return math.hypot(point_um[0] - self.centre_um[0], point_um[1] - self.centre_um[1])

    def to_dict(self):
        return {"id": self.craniotomy_id, "name": self.name, "centre_um": list(self.centre_um),
                "diameter_um": self.diameter_um}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("a craniotomy must be a dictionary")
        try:
            return cls(data["id"], data["name"], data["centre_um"], data["diameter_um"])
        except (KeyError, TypeError) as exc:
            raise ValueError("incomplete craniotomy ({})".format(exc)) from None

    def __eq__(self, other):
        return isinstance(other, Craniotomy) and self.to_dict() == other.to_dict()


class CraniotomyBook:
    def __init__(self):
        self._items = {}

    def __len__(self):
        return len(self._items)

    def get(self, craniotomy_id):
        return self._items.get(craniotomy_id)

    def craniotomies(self):
        return sorted(self._items.values(), key=lambda c: c.name)

    def add(self, craniotomy):
        self._items[craniotomy.craniotomy_id] = craniotomy
        return craniotomy

    def remove(self, craniotomy_id):
        return self._items.pop(craniotomy_id, None)

    def new_name(self):
        names = {c.name for c in self._items.values()}
        number = 1
        while "Craniotomy {}".format(number) in names:
            number += 1
        return "Craniotomy {}".format(number)

    def to_list(self):
        return [c.to_dict() for c in self.craniotomies()]

    @classmethod
    def from_list(cls, items):
        book, problems = cls(), []
        if items is None:
            return book, problems
        if not isinstance(items, list):
            return book, ["the saved craniotomies are not a list"]
        for item in items:
            try:
                craniotomy = Craniotomy.from_dict(item)
            except ValueError as exc:
                problems.append(str(exc))
                continue
            if book.get(craniotomy.craniotomy_id) is not None:
                problems.append("{} is saved twice".format(craniotomy.name))
                continue
            book.add(craniotomy)
        return book, problems


def craniotomy_warning(craniotomy, entry_um):
    """A warning when the entry lies outside the craniotomy, else None."""
    if craniotomy is None or entry_um is None:
        return None
    distance = craniotomy.distance_um(entry_um)
    if distance <= craniotomy.diameter_um / 2.0:
        return None
    return "The entry is {:.2f} mm from the centre of {}, outside its {:.2f} mm opening.".format(
        distance / 1000.0, craniotomy.name, craniotomy.diameter_um / 1000.0)


def _enclosing_circle(points):
    """The smallest circle holding every point (exact; for a few dozen points)."""
    def holds(centre, radius):
        return np.all(np.sum((points - centre) ** 2, axis=1) <= (radius + 1e-6) ** 2)

    if len(points) == 1:
        return points[0], 0.0
    best = None
    count = len(points)
    for i in range(count):
        for j in range(i + 1, count):
            centre = (points[i] + points[j]) / 2.0
            radius = float(np.linalg.norm(points[i] - centre))
            if (best is None or radius < best[1]) and holds(centre, radius):
                best = (centre, radius)
            for k in range(j + 1, count):
                a, b, c = points[i], points[j], points[k]
                d = 2.0 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
                if abs(d) < 1e-12:
                    continue
                ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1])
                      + (c @ c) * (a[1] - b[1])) / d
                uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0])
                      + (c @ c) * (b[0] - a[0])) / d
                centre = np.array([ux, uy])
                radius = float(np.linalg.norm(a - centre))
                if (best is None or radius < best[1]) and holds(centre, radius):
                    best = (centre, radius)
    return best


def fit_craniotomy(entries_um, margin_um=CRANIOTOMY_MARGIN_UM, minimum_um=500.0):
    """(centre, diameter) of the smallest circle holding every entry, with
    ``margin_um`` to spare and at least ``minimum_um`` across."""
    points = np.asarray([e[:2] for e in entries_um], dtype=float)
    if not len(points):
        raise ValueError("there are no entries to fit")
    centre, radius = _enclosing_circle(points)
    return np.asarray(centre, dtype=float).tolist(), max(minimum_um, 2.0 * (radius + margin_um))


# ---------------------------------------------------------------- clearance
def _segment_distance(p0, p1, q0, q1):
    """Shortest distance between segments p0-p1 and q0-q1, and the points."""
    u, v, w = p1 - p0, q1 - q0, p0 - q0
    a, b, c, d, e = u @ u, u @ v, v @ v, u @ w, v @ w
    denominator = a * c - b * b
    s_n, s_d, t_n, t_d = 0.0, denominator, 0.0, denominator
    if denominator < 1e-12:
        s_n, s_d, t_n, t_d = 0.0, 1.0, e, c
    else:
        s_n, t_n = b * e - c * d, a * e - b * d
        if s_n < 0:
            s_n, t_n, t_d = 0.0, e, c
        elif s_n > s_d:
            s_n, t_n, t_d = s_d, e + b, c
    if t_n < 0:
        t_n = 0.0
        s_n, s_d = (0.0, s_d) if -d < 0 else ((s_d, s_d) if -d > a else (-d, a))
    elif t_n > t_d:
        t_n = t_d
        s_n, s_d = (0.0, s_d) if (-d + b) < 0 else ((s_d, s_d) if (-d + b) > a else (-d + b, a))
    s = 0.0 if abs(s_n) < 1e-12 else s_n / s_d
    t = 0.0 if abs(t_n) < 1e-12 else t_n / t_d
    first, second = p0 + s * u, q0 + t * v
    return float(np.linalg.norm(first - second)), first, second


def plan_segments(plan, readout, above_um=CLEARANCE_ABOVE_UM):
    """Each shank as a segment (um) from ``above_um`` above the entry to the tip."""
    if readout is None or readout.get("entry_um") is None:
        return []
    direction = plan.direction
    across = across_face(direction, plan.normal)
    top = np.asarray(readout["entry_um"], dtype=float) - direction * above_um
    tip = np.asarray(plan.tip_um, dtype=float)
    return [(top + across * offset, tip + across * offset)
            for offset in plan.shank_offsets_um or [0.0]]


def clearances(planned, above_um=CLEARANCE_ABOVE_UM):
    """Closest approach of every pair of planned probes.

    ``planned`` is a list of ``(plan, readout)``. Returns dicts with
    ``probes`` (two names), ``distance_um`` and ``depth_um`` (the closest point's
    depth below the first probe's entry; negative above the brain), closest
    first.
    """
    found = []
    for i in range(len(planned)):
        for j in range(i + 1, len(planned)):
            plan_a, read_a = planned[i]
            plan_b, read_b = planned[j]
            best = None
            for a0, a1 in plan_segments(plan_a, read_a, above_um):
                for b0, b1 in plan_segments(plan_b, read_b, above_um):
                    distance, point, _other = _segment_distance(a0, a1, b0, b1)
                    if best is None or distance < best[0]:
                        best = (distance, point)
            if best is None:
                continue
            depth = float(np.dot(best[1] - np.asarray(read_a["entry_um"]), plan_a.direction))
            found.append({"probes": (plan_a.probe, plan_b.probe), "distance_um": best[0],
                          "depth_um": depth})
    return sorted(found, key=lambda item: item["distance_um"])


def clearance_warning(probe, pairs, limit_um=CLEARANCE_UM):
    """A warning naming the closest probe within ``limit_um`` of ``probe``, else None."""
    for pair in pairs:
        if probe in pair["probes"] and pair["distance_um"] < limit_um:
            other = pair["probes"][1] if pair["probes"][0] == probe else pair["probes"][0]
            where = ("{:.2f} mm deep".format(pair["depth_um"] / 1000.0) if pair["depth_um"] >= 0
                     else "{:.2f} mm above the brain".format(-pair["depth_um"] / 1000.0))
            return "{} passes {:.2f} mm from {} ({}).".format(
                probe, pair["distance_um"] / 1000.0, other, where)
    return None


# -------------------------------------------------------- Bregma-Lambda scale
def bregma_lambda_scale(measured_um, atlas_um):
    """Scale from atlas to animal coordinates (measured / atlas), or 1.0 when unset."""
    if not measured_um or not atlas_um:
        return 1.0
    measured_um, atlas_um = float(measured_um), float(atlas_um)
    if not (math.isfinite(measured_um) and math.isfinite(atlas_um)
            and measured_um > 0 and atlas_um > 0):
        raise ValueError("Bregma-Lambda distances must be positive")
    return measured_um / atlas_um


def validated_surgery_settings(data):
    """The project's surgery settings, cleaned; unusable values become None."""
    data = data if isinstance(data, dict) else {}
    out = {}
    for key in ("bregma_lambda_um", "atlas_bregma_lambda_um"):
        value = data.get(key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
        out[key] = value if value is not None and math.isfinite(value) and 0 < value < 50000 \
            else None
    return out


# ----------------------------------------------------------------- proposals
PROPOSAL_TILT_STEP_DEG = 5.0
PROPOSAL_FINE_STEP_DEG = 1.0
PROPOSAL_SCREEN_VOXELS = 4_000_000
PROPOSAL_LINES_PER_DIRECTION = 12
PROPOSAL_REFINE = 6
PROPOSAL_KEEP = 8
PROPOSAL_ABOVE_UM = 2000.0  # sampled above the centre entry, where outer shanks may enter
PROPOSAL_EXTRA_UM = 5000.0  # looked at below the shank, to say how deep a target is
REACHED_UM = 100.0          # a target counts as reached with this much of it in the window
# Ranking: each degree from vertical costs this much window in the targets, so a
# nearly as good, straighter track comes first; and the list keeps the best
# track of each band of tilts, so a vertical option is shown next to angled ones.
PROPOSAL_TILT_PENALTY_UM_PER_DEG = 10.0
PROPOSAL_TILT_BANDS_DEG = (5.0, 15.0, 25.0)


class ProposalRequest:
    """What a proposal must do (see ``propose_plans``).

    ``targets`` and ``avoid`` are region ids (each with its sub-regions);
    ``side`` keeps the probe in one hemisphere (+1 right, -1 left, None
    either); ``midline_um`` keeps it this far from the midline;
    ``max_ap_tilt_deg``/``max_ml_tilt_deg`` bound the tilts (0 and 0: vertical);
    ``craniotomy`` (a Craniotomy) must hold the entry of every shank. The
    lists are kept as given: contradictions are refused by :meth:`check`, never
    resolved silently (review R4 of 2.8.3).
    """

    def __init__(self, targets, avoid=(), side=None, midline_um=0.0, max_ap_tilt_deg=30.0,
                 max_ml_tilt_deg=30.0, craniotomy=None):
        self.targets = list(dict.fromkeys(int(t) for t in targets))
        self.avoid = list(dict.fromkeys(int(a) for a in avoid))
        self.side = None if side is None else (1 if side >= 0 else -1)
        self.midline_um = max(0.0, float(midline_um))
        self.max_ap_tilt_deg = float(np.clip(max_ap_tilt_deg, 0.0, MAX_TILT_DEG))
        self.max_ml_tilt_deg = float(np.clip(max_ml_tilt_deg, 0.0, MAX_TILT_DEG))
        self.craniotomy = craniotomy
        if not self.targets:
            raise ValueError("choose at least one target region")

    def check(self, atlas):
        """Raise ValueError naming a target that lies in a region to keep out of.

        A region to keep out of that lies inside a target (record HPF, keep
        out of DG) is allowed: those voxels are avoided, the rest recorded.
        """
        for target in self.targets:
            for avoided in self.avoid:
                if target == avoided or target in atlas.descendants(avoided):
                    raise ValueError(
                        "{} is to be recorded but {} to be kept out of; remove it from one "
                        "of the lists".format(atlas.name(target)[0], "is also" if target ==
                                              avoided else "lies in {}, which is".format(
                                                  atlas.name(avoided)[0])))

    def describe(self):
        """The request as plain values, to tell whether results still match it."""
        return (tuple(self.targets), tuple(self.avoid), self.side, self.midline_um,
                self.max_ap_tilt_deg, self.max_ml_tilt_deg,
                None if self.craniotomy is None else json_key(self.craniotomy.to_dict()))


def json_key(value):
    import json
    return json.dumps(value, sort_keys=True)


def region_ids(atlas, regions):
    """Each region's label ids (the region and its sub-regions), sorted."""
    return [np.asarray(sorted(atlas.descendants(region)), dtype=np.int64)
            for region in regions]


def _members(labels, ids_list):
    """(samples, regions) booleans: whether each label lies in each region.

    Membership is per region, so a label in a parent and in its child counts
    for both (review R6 of 2.8.3).
    """
    labels = np.asarray(labels, dtype=np.int64)
    if not ids_list:
        return np.zeros(labels.shape + (0,), dtype=bool)
    return np.stack([np.isin(labels, ids) for ids in ids_list], axis=-1)


def shank_offsets(plan):
    return plan.shank_offsets_um or [0.0]


def traverse(atlas, start_um, end_um):
    """Every voxel the segment passes through, in order, exactly.

    Returns ``(labels, lengths_um, entry_points_um)``: the label of each voxel
    crossed (0 outside the volume), the length of segment inside it and where
    the segment enters it. A 3-D grid walk (Amanatides and Woo), so a line
    grazing a voxel's corner is not missed between samples.
    """
    start = atlas.to_vox(start_um)
    end = atlas.to_vox(end_um)
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length == 0:
        label = atlas.labels_at(start[None, :])[0][0]
        return np.array([label]), np.array([0.0]), np.asarray([start_um], dtype=float)
    voxel = np.floor(start).astype(int)
    step = np.sign(delta).astype(int)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_delta = np.where(delta != 0, np.abs(1.0 / delta), np.inf)
        next_edge = voxel + (step > 0)
        t_max = np.where(delta != 0, (next_edge - start) / delta, np.inf)
    t = 0.0
    visited, spans, starts = [], [], []
    shape = atlas.shape
    while t < 1.0:
        axis = int(np.argmin(t_max))
        t_next = min(1.0, float(t_max[axis]))
        if t_next > t:
            inside = np.all(voxel >= 0) and np.all(voxel < shape)
            visited.append(int(atlas.labels[voxel[0], voxel[1], voxel[2]]) if inside else 0)
            spans.append((t_next - t) * length * atlas.vox_um)
            starts.append(t)
        voxel[axis] += step[axis]
        t = t_next
        t_max[axis] += t_delta[axis]
    points = (np.asarray(start_um, dtype=float)[None, :]
              + np.asarray(starts)[:, None] * (np.asarray(end_um, float) - start_um)[None, :])
    return np.asarray(visited), np.asarray(spans), points


def track_checks(plan, atlas, avoid=(), side=None, midline_um=0.0, craniotomy=None):
    """Problems with every physical shank of ``plan``, as (hard, soft) messages.

    Each shank runs parallel to the centre line, offset across the face, from
    its own surface entry to its own tip. Hard problems make the plan break a
    constraint: a shank's tip outside the brain, a shank in a region to keep
    out of, on the wrong side or within the midline margin, or entering
    outside the craniotomy. Soft ones are shown: the track leaving the
    labelled brain between entry and tip (a gap in the atlas).
    """
    hard, soft = [], []
    direction = plan.direction
    across = across_face(direction, plan.normal)
    tip = np.asarray(plan.tip_um, dtype=float)
    avoid_ids = region_ids(atlas, avoid)
    shanks = shank_offsets(plan)
    for number, offset in enumerate(shanks):
        name = "Shank {}".format(number + 1) if len(shanks) > 1 else "The probe"
        shank_tip = tip + across * offset
        entry, tip_inside = surface_entry(atlas, shank_tip, direction)
        if entry is None or not tip_inside:
            hard.append("{}'s tip is not inside the brain.".format(name))
            if entry is None:
                continue
        length = float(np.dot(shank_tip - np.asarray(entry), direction))
        if length <= 0:
            continue
        # Every voxel on the shank's path, exactly (not samples).
        labels, spans, starts = traverse(atlas, entry, shank_tip)
        points = np.vstack([starts, shank_tip[None, :]])
        tissue = labels != 0
        tissue_points = np.append(tissue, True)
        if avoid_ids:
            crossed = _members(labels, avoid_ids).any(axis=0)
            for region, hit in zip(avoid, crossed):
                if hit:
                    hard.append("{} passes through {}, which is to be kept out of.".format(
                        name, atlas.name(region)[0]))
        if side is not None and np.any(tissue_points & (points[:, 0] * side < 0)):
            hard.append("{} crosses to the other side of the midline.".format(name))
        if midline_um > 0 and np.any(tissue_points & (np.abs(points[:, 0]) < midline_um)):
            hard.append("{} comes within {:.2f} mm of the midline.".format(
                name, midline_um / 1000.0))
        if craniotomy is not None and \
                craniotomy.distance_um(entry) > craniotomy.diameter_um / 2.0 + 1e-6:
            hard.append("{} enters {:.2f} mm from the centre of {}, outside its opening."
                        .format(name, craniotomy.distance_um(entry) / 1000.0, craniotomy.name))
        gap = float(spans[~tissue].sum())
        if gap > 1e-6:
            soft.append("{} leaves the atlas's labelled brain for {:.2f} mm between its "
                        "entry and its tip.".format(name, gap / 1000.0))
    return hard, soft


class _LineScorer:
    """Scores probe positions for one request and one probe design.

    Every shank is sampled (review R1 of 2.8.3): constraints apply to each,
    and the recording window is counted on each, summed over the shanks.
    """

    def __init__(self, atlas, request, plan):
        self.atlas = atlas
        self.request = request
        self.plan = plan
        self.target_ids = region_ids(atlas, request.targets)
        self.avoid_ids = region_ids(atlas, request.avoid)
        settings = plan.probe_settings or {}
        self.shank_um = float(settings.get("probe_length") or 10000.0)
        self.tip_um = float(settings.get("tip_length") or 0.0)
        window = recording_sites(plan)
        self.window_low = float(window.min()) if len(window) else 0.0
        self.window_high = float(window.max()) if len(window) else 0.0
        self.step_um = atlas.vox_um * SAMPLE_STEP_VOX
        # Depths along the probe from the centre line's entry; negative above it.
        self.depths = np.arange(-PROPOSAL_ABOVE_UM, self.shank_um + PROPOSAL_EXTRA_UM,
                                self.step_um)
        self.count = len(self.depths)
        self.offsets = shank_offsets(plan)
        # Why lines through every target could not be used.
        self.reasons = {"avoid": 0, "midline": 0, "too_deep": 0, "craniotomy": 0,
                        "window": 0, "tip": 0}
        self.through_all = 0
        self.deepest_needed_um = []

    def evaluate(self, direction, through_um):
        """The best tip for the probe whose centre line runs through ``through_um``.

        Returns a dict (tip_um, entry_um, depth_um, coverage_um per target,
        shank_coverage_um, reached, total_um, elevation_deg) or None when no
        position on the line is usable.
        """
        atlas, request = self.atlas, self.request
        far = np.asarray(through_um, dtype=float) + direction * self.shank_um
        entry, _inside = surface_entry(atlas, far, direction)
        if entry is None:
            return None
        entry = np.asarray(entry)
        across = across_face(direction, face_normal(direction, self.plan.roll_deg))
        n = len(request.targets)
        centre = entry[None, :] + self.depths[:, None] * direction[None, :]
        members, tissue, avoided, near_midline, shank_entries = [], [], [], [], []
        for offset in self.offsets:
            points = centre + across[None, :] * offset
            labels, _inside = atlas.labels_at(atlas.to_vox(points))
            in_tissue = labels != 0
            first = np.flatnonzero(in_tissue)
            if not len(first):
                return None
            shank_entries.append(int(first[0]))
            members.append(_members(labels, self.target_ids))
            tissue.append(in_tissue)
            avoided.append(_members(labels, self.avoid_ids).any(axis=1) if self.avoid_ids
                           else np.zeros(self.count, dtype=bool))
            close = np.zeros(self.count, dtype=bool)
            if request.midline_um > 0:
                close |= in_tissue & (np.abs(points[:, 0]) < request.midline_um)
            if request.side is not None:
                close |= in_tissue & (points[:, 0] * request.side < 0)
            near_midline.append(close)
        tissue = np.stack(tissue)            # (shanks, samples)
        avoided = np.stack(avoided).any(axis=0)
        near_midline = np.stack(near_midline).any(axis=0)
        members = np.stack(members)          # (shanks, samples, targets)
        outside_hole = False
        if request.craniotomy is not None:
            for offset, index in zip(self.offsets, shank_entries):
                point = centre[index] + across * offset
                if request.craniotomy.distance_um(point) > request.craniotomy.diameter_um / 2.0:
                    outside_hole = True
        # Shallowest sample where some shank meets a stop; the tip must stay above it.
        stops = np.flatnonzero(avoided | near_midline)
        first_blocked = int(stops[0]) if len(stops) else self.count
        first_avoided = int(np.argmax(avoided)) if avoided.any() else self.count
        # The longest shank inside the brain may be no longer than the shank.
        top_entry = min(shank_entries)
        shank_end = min(self.count - 1, top_entry + int(self.shank_um / self.step_um))
        hits = members.any(axis=0)           # (samples, targets): on any shank
        through_all = bool(np.all(hits.any(axis=0)))
        needed = int(max(np.flatnonzero(hits[:, k])[0] for k in range(n))) \
            if through_all else None
        if through_all:
            self.through_all += 1
            self.deepest_needed_um.append(self.depths[needed] - self.depths[top_entry])
            if outside_hole:
                self.reasons["craniotomy"] += 1
            elif first_blocked <= needed:
                self.reasons["avoid" if first_avoided <= needed else "midline"] += 1
            elif needed > shank_end:
                self.reasons["too_deep"] += 1
        if outside_hole:
            return None
        limit = min(first_blocked - 1, shank_end)
        # A tip is admissible only where every shank's tip is in labelled tissue
        # (review R5 of 2.8.3), below every shank's entry.
        lowest_entry = max(shank_entries)
        tips = np.arange(lowest_entry + 1, limit + 1)
        if not len(tips):
            return None
        tips = tips[tissue[:, tips].all(axis=0)]
        if not len(tips):
            if through_all and first_blocked > needed:
                self.reasons["tip"] += 1
            return None
        # Window coverage of each target, and of any target, summed over shanks.
        tip_depth = self.depths[tips]
        top = np.clip(np.searchsorted(self.depths, tip_depth - self.tip_um - self.window_high),
                      0, self.count)
        bottom = np.clip(np.searchsorted(self.depths, tip_depth - self.tip_um - self.window_low,
                                         side="right"), 0, self.count)
        cover = np.zeros((len(tips), n))
        union = np.zeros(len(tips))
        per_shank = []
        for shank in range(len(self.offsets)):
            member = members[shank].astype(float)
            cumulative = np.vstack([np.zeros((1, n)), np.cumsum(member, axis=0)])
            shank_cover = (cumulative[bottom] - cumulative[top]) * self.step_um
            any_target = np.concatenate([[0.0], np.cumsum(members[shank].any(axis=1))])
            union += (any_target[bottom] - any_target[top]) * self.step_um
            cover += shank_cover
            per_shank.append(shank_cover)
        reached = (cover >= REACHED_UM).sum(axis=1)
        # Most targets reached, then most window in them, then shallowest.
        best = int(np.lexsort((tip_depth, -union, -reached))[0])
        if reached[best] == 0:
            return None
        if through_all and reached[best] < n and first_blocked > needed \
                and needed <= shank_end:
            self.reasons["window"] += 1
        tip = entry + direction * tip_depth[best]
        return {"tip_um": tip.tolist(), "entry_um": entry.tolist(),
                "depth_um": float(tip_depth[best]), "coverage_um": cover[best].tolist(),
                "shank_coverage_um": [s[best].tolist() for s in per_shank],
                "reached": int(reached[best]), "total_um": float(union[best]),
                "elevation_deg": math.degrees(math.acos(float(np.clip(-direction[2], -1, 1))))}


def _directions(max_ap, max_ml, step):
    aps = np.arange(-max_ap, max_ap + 1e-9, step) if max_ap > 0 else np.zeros(1)
    mls = np.arange(-max_ml, max_ml + 1e-9, step) if max_ml > 0 else np.zeros(1)
    return [(float(a), float(m)) for a in aps for m in mls]


def _target_voxels(atlas, request, sample, stride):
    """Positions (um) and target memberships of the strided target voxels."""
    found = np.argwhere(sample.any(axis=-1))
    member = sample[found[:, 0], found[:, 1], found[:, 2]]
    um = atlas.to_um(found * stride + stride / 2.0)
    if request.side is not None:
        keep_side = um[:, 0] * request.side > 0
        um, member = um[keep_side], member[keep_side]
    return um, member, stride


def _screen_lines(atlas, request, voxels, direction, keep, plan=None):
    """Centre lines along ``direction`` that put a shank through the most target voxels.

    ``voxels`` (from ``_target_voxels``) are the target voxels of a strided
    copy of the atlas. For each shank offset, each voxel is moved to where the
    centre line would pass for that shank to go through it, then projected
    along ``direction`` onto the plane across it; cells holding voxels of the
    most targets, then the most voxels, are the lines worth evaluating
    exactly. Returns points (um) on those centre lines.
    """
    um, member, stride = voxels
    if not len(um):
        return []
    offsets = shank_offsets(plan) if plan is not None else [0.0]
    if len(offsets) > 1:
        across = across_face(direction, face_normal(direction, plan.roll_deg))
        um = np.vstack([um - across * offset for offset in offsets])
        member = np.vstack([member] * len(offsets))
    helper = np.array([1.0, 0.0, 0.0]) if abs(direction[0]) < 0.9 else np.array([0, 1.0, 0])
    first = np.cross(direction, helper)
    first /= np.linalg.norm(first)
    second = np.cross(direction, first)
    cell = stride * atlas.vox_um
    keys = np.stack([np.floor(um @ first / cell), np.floor(um @ second / cell)], axis=1)
    keys = keys.astype(np.int64)
    cells, inverse = np.unique(keys, axis=0, return_inverse=True)
    inverse = np.ravel(inverse)
    targets = member.shape[1]
    present = np.zeros((len(cells), targets), dtype=bool)
    for k in range(targets):
        present[inverse[member[:, k]], k] = True
    voxel_count = np.bincount(inverse, minlength=len(cells))
    order = np.lexsort((-voxel_count, -present.sum(axis=1)))[:keep]
    return [um[inverse == index].mean(axis=0) for index in order]


class SearchStopped(Exception):
    """Raised inside the search when its progress callback asks it to stop."""


def propose_plans(atlas, request, plan, progress=None):
    """Ranked plans for ``plan``'s probe that best record ``request.targets``.

    Searches centre lines over the allowed tilts on a coarse copy of the
    atlas, evaluates the promising ones at full resolution on every shank
    (sliding the recording window to its best depth), refines the best, and
    checks the final ones with ``track_checks`` exactly as the readout does.
    ``progress(done, total, stage)`` may return False to stop; the best found
    so far are then returned with a reason saying so.

    Returns ``(proposals, reasons)``: proposals are dicts with ``plan`` (a
    ProbePlan keeping the probe's settings, roll, bank and craniotomy and
    carrying the request's targets and regions to avoid), ``entry_um``,
    ``depth_um``, ``coverage`` ([(acronym, um)] per target, summed over the
    shanks), ``shank_coverage``, ``reached``, ``score`` and ``warnings`` (soft
    checks); ``reasons`` explain, in words, why no proposal records every
    target (empty when one does).
    """
    try:
        request.check(atlas)
    except ValueError as exc:
        return [], [str(exc)[0].upper() + str(exc)[1:] + "."]
    plan = plan.copy(targets=request.targets, avoid=request.avoid)
    scorer = _LineScorer(atlas, request, plan)
    size = int(np.prod(atlas.shape))
    stride = max(1, int(math.ceil((size / PROPOSAL_SCREEN_VOXELS) ** (1.0 / 3.0))))
    sample = _members(np.asarray(atlas.labels[::stride, ::stride, ::stride]),
                      scorer.target_ids)
    if not sample.any():
        # Regions smaller than the coarse grid: look at every voxel instead.
        stride = 1
        sample = _members(np.asarray(atlas.labels), scorer.target_ids)
        if not sample.any():
            return [], ["None of the target regions is in this atlas volume."]
    voxels = _target_voxels(atlas, request, sample, stride)
    directions = _directions(request.max_ap_tilt_deg, request.max_ml_tilt_deg,
                             PROPOSAL_TILT_STEP_DEG)
    total = len(directions) + PROPOSAL_REFINE
    candidates = []
    stopped = False

    def tick(done, stage):
        if progress is not None and progress(done, total, stage) is False:
            raise SearchStopped()

    try:
        for number, (ap, ml) in enumerate(directions):
            direction = direction_from_tilts(ap, ml)
            for point in _screen_lines(atlas, request, voxels, direction,
                                       PROPOSAL_LINES_PER_DIRECTION, plan):
                result = scorer.evaluate(direction, point)
                if result is not None:
                    candidates.append((ap, ml, result))
            tick(number + 1, "Searching the allowed tilts")
        ranked = _rank(candidates, atlas)
        # Refine the best: finer tilts, at full resolution.
        refined = []
        for number, (ap, ml, result) in enumerate(ranked[:PROPOSAL_REFINE]):
            best = (ap, ml, result)
            for d_ap in (-2, -1, 0, 1, 2):
                for d_ml in (-2, -1, 0, 1, 2):
                    new_ap = float(np.clip(ap + d_ap * PROPOSAL_FINE_STEP_DEG,
                                           -request.max_ap_tilt_deg, request.max_ap_tilt_deg))
                    new_ml = float(np.clip(ml + d_ml * PROPOSAL_FINE_STEP_DEG,
                                           -request.max_ml_tilt_deg, request.max_ml_tilt_deg))
                    trial = scorer.evaluate(direction_from_tilts(new_ap, new_ml),
                                            result["tip_um"])
                    if trial is not None and _key(trial) < _key(best[2]):
                        best = (new_ap, new_ml, trial)
            refined.append(best)
            tick(len(directions) + number + 1, "Refining the best")
        ranked = _rank(refined + ranked[PROPOSAL_REFINE:], atlas)
    except SearchStopped:
        stopped = True
        ranked = _rank(candidates, atlas)
    proposals, rejected = [], 0
    for ap, ml, result in ranked:
        if len(proposals) == PROPOSAL_KEEP:
            break
        proposed = plan.copy(tip_um=result["tip_um"], ap_tilt_deg=ap, ml_tilt_deg=ml)
        hard, soft = track_checks(proposed, atlas, request.avoid, request.side,
                                  request.midline_um, request.craniotomy)
        readout = plan_readout(proposed, atlas)
        hard += [w for w in readout["warnings"] if "deeper than" in w or "outside the atlas"
                 in w]
        if hard:
            rejected += 1
            continue
        soft += [w for w in readout["warnings"] if w not in soft and "not inside" not in w]
        proposals.append({
            "plan": proposed, "entry_um": result["entry_um"], "depth_um": result["depth_um"],
            "coverage": [(atlas.name(region)[0], length) for region, length
                         in zip(request.targets, result["coverage_um"])],
            "shank_coverage": result["shank_coverage_um"],
            "reached": result["reached"], "score": result["total_um"], "warnings": soft})
    reasons = []
    if stopped:
        reasons.append("The search was stopped; these are the best found so far.")
    if not proposals or proposals[0]["reached"] < len(request.targets):
        reasons += _reasons(scorer, request, atlas, voxels, proposals, plan)
    if rejected and not proposals:
        reasons.append("{} candidate(s) failed the final check of every shank.".format(
            rejected))
    return proposals, reasons


def _score(result):
    return result["total_um"] - PROPOSAL_TILT_PENALTY_UM_PER_DEG * result["elevation_deg"]


def _key(result):
    """Most targets reached, then the best score, then the shallowest tip."""
    return (-result["reached"], -round(_score(result), 6), result["depth_um"])


def _band(result):
    return sum(result["elevation_deg"] >= edge for edge in PROPOSAL_TILT_BANDS_DEG)


def _rank(candidates, atlas, apart_um=500.0, apart_deg=5.0):
    """Best first, near-duplicates dropped, the best of each tilt band kept."""
    ordered = sorted(candidates, key=lambda item: _key(item[2]))
    unique = []
    for ap, ml, result in ordered:
        if any(math.dist(result["entry_um"], other["entry_um"]) < apart_um
               and abs(ap - a) < apart_deg and abs(ml - m) < apart_deg
               for a, m, other in unique):
            continue
        unique.append((ap, ml, result))
    if not unique:
        return unique
    # The best of every band that reaches as many targets as the best overall.
    most = unique[0][2]["reached"]
    firsts = {}
    for item in unique:
        if item[2]["reached"] == most:
            firsts.setdefault(_band(item[2]), item)
    chosen = list(firsts.values())
    rest = [item for item in unique if all(item is not other for other in chosen)]
    return sorted(chosen, key=lambda item: _key(item[2])) + rest


def _reasons(scorer, request, atlas, voxels, proposals, plan):
    """Why no proposal records every target, in words.

    The search samples lines; its failures say what this search found, not
    that no plan exists (review UI-5 of 2.8.3).
    """
    reasons = []
    n = len(request.targets)
    names = [atlas.name(t)[0] for t in request.targets]
    best = proposals[0]["reached"] if proposals else 0
    if n > 1:
        reasons.append("The best line found reaches {} of the {} targets ({}).".format(
            best, n, ", ".join(names)))
    if scorer.through_all == 0:
        wider = None
        if n > 1:
            for limit in (10.0, 20.0, 30.0, 45.0, 60.0, MAX_TILT_DEG):
                if limit <= max(request.max_ap_tilt_deg, request.max_ml_tilt_deg):
                    continue
                for ap, ml in _directions(limit, limit, PROPOSAL_TILT_STEP_DEG):
                    lines = _screen_lines(atlas, request, voxels,
                                          direction_from_tilts(ap, ml), 1, plan)
                    if lines and _line_spans_targets(scorer, ap, ml, lines[0]):
                        wider = limit
                        break
                if wider is not None:
                    break
        if wider is not None:
            reasons.append("No line through every target was found within the tilt limits; "
                           "the search found one with tilts of up to {:.0f}°.".format(wider))
        elif n > 1:
            reasons.append("No line the {:.1f} mm shank can follow through every target was "
                           "found at any tilt up to {:.0f}°: consider one probe per target or "
                           "group.".format(scorer.shank_um / 1000.0, MAX_TILT_DEG))
        return reasons
    words = {
        "craniotomy": "enter the brain outside the craniotomy (some shank)",
        "avoid": "cross a region to keep out of (some shank)",
        "midline": "come too close to the midline or cross it (some shank)",
        "too_deep": "need more than the {:.1f} mm shank (the shallowest needs {:.1f} mm)".format(
            scorer.shank_um / 1000.0,
            min(scorer.deepest_needed_um) / 1000.0 if scorer.deepest_needed_um else 0.0),
        "window": "spread the targets over more than the {:.2f} mm recording window; record "
                  "every site or choose another bank".format(
                      (scorer.window_high - scorer.window_low) / 1000.0),
        "tip": "end where no shank tip can be in the labelled brain",
    }
    for reason, count in sorted(scorer.reasons.items(), key=lambda item: -item[1]):
        if count:
            reasons.append("Of the lines found through every target, {} {}.".format(
                count, words[reason]))
    return reasons


def _line_spans_targets(scorer, ap, ml, point):
    """Whether the line through ``point`` meets every target within one shank length."""
    direction = direction_from_tilts(ap, ml)
    atlas = scorer.atlas
    span = np.linspace(-15000.0, 15000.0, int(30000.0 / scorer.step_um) + 1)
    points = np.asarray(point, dtype=float)[None, :] + span[:, None] * direction[None, :]
    labels, _inside = atlas.labels_at(atlas.to_vox(points))
    member = _members(labels, scorer.target_ids)
    tissue = span[np.flatnonzero(labels != 0)]
    if not member.any(axis=0).all() or not len(tissue):
        return False
    # Touching every target: from where the line enters the brain down to the
    # first voxel of the deepest target (positions grow along the probe).
    needed = max(span[np.flatnonzero(member[:, k])].min() for k in range(member.shape[1])) \
        - tissue.min()
    return needed <= scorer.shank_um - scorer.tip_um


def target_coverage(plan, readout, atlas):
    """Length of each of the plan's targets inside its recording window (um),
    summed over the shanks; each target counted on its own, so a parent and
    its child are both measured, whatever their order (review R6 of 2.8.3)."""
    if not plan.targets or readout.get("window_um") is None:
        return []
    ids = region_ids(atlas, plan.targets)
    lengths = np.zeros(len(plan.targets))
    settings = plan.probe_settings or {}
    tip_length = float(settings.get("tip_length") or 0.0)
    window = recording_sites(plan)
    if not len(window):
        return [(atlas.name(t)[0], 0.0) for t in plan.targets]
    direction = plan.direction
    across = across_face(direction, plan.normal)
    step = atlas.vox_um * SAMPLE_STEP_VOX
    tip = np.asarray(plan.tip_um, dtype=float)
    for offset in shank_offsets(plan):
        shank_tip = tip + across * offset
        # Window: from the highest to the lowest recording site above the tip.
        heights = np.arange(window.min(), window.max() + step / 2, step) + tip_length
        points = shank_tip[None, :] - heights[:, None] * direction[None, :]
        labels, _inside = atlas.labels_at(atlas.to_vox(points))
        lengths += _members(labels, ids).sum(axis=0) * step
    return [(atlas.name(t)[0], float(length)) for t, length in zip(plan.targets, lengths)]
