"""The hardware above a planned Neuropixels probe's shank (2.8.6).

Like Pinpoint, a planned probe is shown with what sits above its shank: the
probe base, the flex cable, the connector board (1.0) or headstage (2.0) at
the flex's end, and the dovetail adapter that holds it. Each part is an
oriented box in the probe's frame:

* ``along``: up the probe from the top of the shank (the base's bottom);
* ``across``: across the shank row (``probe_plans.across_face``), the base's
  width;
* ``normal``: the way the contacts face (``ProbePlan.normal``); parts lie
  behind the face (negative).

Sizes (micrometres). Probe base, flex width and thickness, flex length (2.0)
and the 2.0 headstage are imec's datasheet values (Neuropixels 1.0 and 2.0
datasheets, neuropixels.org). The 1.0 flex length and connector board and the
dovetail adapter (8 x 8 x 55 mm) are read from Pinpoint's probe models
(VirtualBrainLab/Pinpoint, measured, not copied); where they sit relative to
the base is approximate, as each rig mounts them its own way.

What is shown is a choice (``SHOWN``): nothing, the probe itself (its
shanks and base, ``PROBE_PARTS``), or the probe and its backend (the flex,
connector board or headstage and the dovetail adapter).

Everything is GUI-free; ``hardware_model`` gives the boxes in Bregma-relative
voxels for drawing (``implants.model_section``/``model_mesh``, type
``boxes``) and ``hardware_segments`` approximates them for clearances.
"""

import math

import numpy as np

# name, start along the probe above the shank's top (None: after the part
# before), length, width (across), thickness (normal), source
PARTS = {
    "NP1.0": [
        ("Probe base", 0.0, 10700.0, 6200.0, 1200.0, "imec NP1.0 datasheet"),
        ("Flex cable", None, 30000.0, 4300.0, 80.0, "width imec; length Pinpoint"),
        ("Connector board", None, 11400.0, 10900.0, 1000.0, "Pinpoint"),
    ],
    "NP2.0": [
        ("Probe base", 0.0, 7800.0, 3500.0, 1280.0, "imec NP2.0 datasheet"),
        ("Flex cable", None, 42000.0, 3500.0, 80.0, "imec NP2.0 datasheet"),
        ("Headstage", None, 14000.0, 10000.0, 3700.0, "imec NP2.0 datasheet"),
    ],
}
# The dovetail adapter, on the back of the base from its bottom up.
DOVETAIL = ("Dovetail adapter", 55000.0, 8000.0, 8000.0, "Pinpoint")
GAP_UM = 100.0          # between the base's back and the adapter
SHANK_WIDTH_UM, SHANK_THICKNESS_UM = 70.0, 24.0
# What may be shown: nothing, the probe (shanks and base), or the probe and
# its backend (flex, connector board or headstage, dovetail adapter).
NONE, PROBE, ALL = "none", "probe", "all"
SHOWN = {NONE: "None", PROBE: "Probe only", ALL: "Probe and backend"}
PROBE_PARTS = ("Shank", "Probe base")


def shown_parts(shown):
    """``shown`` as one of ``SHOWN``: True (2.8.6's switch on) is ALL, False or
    an unknown value NONE."""
    if shown is True:
        return ALL
    return shown if shown in SHOWN else NONE


def is_backend(box):
    """Whether a box (or part name) is backend rather than the probe itself."""
    name = box["name"] if isinstance(box, dict) else box
    return name not in PROBE_PARTS


def boxes_shown(boxes, shown):
    """The boxes to draw for ``shown`` (see ``SHOWN``)."""
    shown = shown_parts(shown)
    if shown == NONE:
        return []
    return [box for box in boxes if shown == ALL or not is_backend(box)]


def hardware_kind(plan):
    """"NP1.0", "NP2.0" or None (an implant, or a probe of another design)."""
    if not getattr(plan, "is_probe", True):
        return None
    name = (plan.probe_settings or {}).get("probe_type_name")
    return name if name in PARTS else None


def hardware_boxes(plan):
    """The planned probe's hardware as boxes in Bregma-relative micrometres:
    dicts with ``name``, ``centre``, ``axes`` (along, across, normal unit
    vectors) and ``half`` (half length, width, thickness), or [] when the
    probe's design has none."""
    kind = hardware_kind(plan)
    if kind is None:
        return []
    from .probe_plans import across_face

    direction = plan.direction
    up = -direction
    normal = plan.normal
    across = across_face(direction, normal)
    tip = np.asarray(plan.tip_um, dtype=float)
    length = float((plan.probe_settings or {}).get("probe_length") or 10000.0)
    # The shank row's middle: four shanks sit about the plan's centre line.
    offsets = plan.shank_offsets_um or [0.0]
    middle = tip + across * (min(offsets) + max(offsets)) / 2.0
    top = middle + up * length            # the top of the shank, the base's bottom
    boxes, start = [], 0.0
    # Each shank whole, from the tip to the base (the track line shows only
    # the part in the brain): 70 x 24 um (imec datasheets).
    for offset in offsets:
        centre = tip + across * offset + up * (length / 2.0)
        boxes.append({"name": "Shank", "centre": centre.tolist(),
                      "axes": [up.tolist(), across.tolist(), normal.tolist()],
                      "half": [length / 2.0, SHANK_WIDTH_UM / 2.0, SHANK_THICKNESS_UM / 2.0],
                      "source": "imec datasheet"})
    base_thickness = None
    for name, begin, size, width, thickness, source in PARTS[kind]:
        start = start if begin is None else begin
        if base_thickness is None:
            base_thickness = thickness
        centre = top + up * (start + size / 2.0) - normal * (thickness / 2.0)
        boxes.append({"name": name, "centre": centre.tolist(),
                      "axes": [up.tolist(), across.tolist(), normal.tolist()],
                      "half": [size / 2.0, width / 2.0, thickness / 2.0], "source": source})
        start += size
    name, size, width, thickness, source = DOVETAIL
    centre = top + up * (size / 2.0) - normal * (base_thickness + GAP_UM + thickness / 2.0)
    boxes.append({"name": name, "centre": centre.tolist(),
                  "axes": [up.tolist(), across.tolist(), normal.tolist()],
                  "half": [size / 2.0, width / 2.0, thickness / 2.0], "source": source})
    return boxes


def hardware_model(plan, vox_um, shown=ALL):
    """The hardware as a display model in Bregma-relative voxels (type
    ``boxes``), only the parts ``shown`` (see ``SHOWN``), or None."""
    boxes = boxes_shown(hardware_boxes(plan), shown)
    if not boxes:
        return None
    return {"type": "boxes", "boxes": [
        {"name": box["name"], "centre": (np.asarray(box["centre"]) / vox_um).tolist(),
         "axes": box["axes"], "half": (np.asarray(box["half"]) / vox_um).tolist()}
        for box in boxes]}


def box_corners(box):
    """The eight corners of a box (dict as in ``hardware_boxes``): the bottom
    four round, then the top four in the same order."""
    centre = np.asarray(box["centre"], dtype=float)
    up, across, normal = (np.asarray(a, dtype=float) for a in box["axes"])
    half = box["half"]
    return np.asarray([centre + h * half[0] * up + w * half[1] * across + d * half[2] * normal
                       for h in (-1, 1)
                       for w, d in ((-1, -1), (1, -1), (1, 1), (-1, 1))])


def hardware_segments(plan, spacing_um=500.0):
    """The hardware for clearances, as segments with radii ``[(start, end,
    radius)]``: each box as lines up its length, spread across its wider side
    at most ``spacing_um`` apart, with half its thinner side as radius. The
    distance it gives can exceed the true one by up to half the spacing."""
    segments = []
    for box in hardware_boxes(plan):
        if box["name"] == "Shank":
            continue            # the shanks are already checked as lines
        centre = np.asarray(box["centre"], dtype=float)
        up, across, normal = (np.asarray(a, dtype=float) for a in box["axes"])
        half_length, half_width, half_thickness = box["half"]
        if half_width < half_thickness:
            across, normal = normal, across
            half_width, half_thickness = half_thickness, half_width
        count = max(1, int(math.ceil(2.0 * half_width / spacing_um)) + 1)
        for w in np.linspace(-half_width + half_thickness, half_width - half_thickness,
                             count) if half_width > half_thickness else [0.0]:
            middle = centre + across * w
            segments.append((middle - up * half_length, middle + up * half_length,
                             half_thickness))
    return segments
