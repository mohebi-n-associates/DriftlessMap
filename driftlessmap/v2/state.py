"""Read-only summaries of the engine state for the V2 shell.

Nothing here changes scientific state. The shell polls these summaries to
show concrete status ("image loaded", "review pending") and to decide whether
the project has unsaved changes. Navigation (views, zoom, selection, hovering)
never changes the digest, so it never marks the project dirty.
"""

import numpy as np

from ..state_digest import state_digest

from ..mapping_records import (
    BUILD_CHANGED,
    CURRENT,
    NOT_RECORDED,
    OTHER_SECTION,
    REGISTRATION_CHANGED,
    REMAPPED,
    UNVERIFIED,
    is_out_of_date,
)


def _describe_len(value):
    try:
        return len(value)
    except TypeError:
        return 0 if value is None else 1


def scientific_digest(engine):
    """A digest of the state a save would record, excluding display-only views."""
    payload = engine.project_payload()
    for key in ("created_at", "saved_at", "software", "portable", "portable_sources",
                "atlas_provenance", "histology_provenance", "num_windows"):
        payload.pop(key, None)
    session = dict(payload["session_state"])
    session.pop("current_layout", None)
    payload["session_state"] = session
    for key, selection in (("object_data", "current_obj_index"),
                           ("layer_data", "current_layer_index")):
        if payload.get(key) is not None:
            payload[key] = dict(payload[key])
            payload[key].pop(selection, None)
    # Views, selection and the active tool are navigation. Unmapped probes
    # and an unfinished outline, however, are saved work.
    interface = payload.pop("interface_state", {})
    implants = interface.get("implants", {})
    payload["drafts"] = {key: implants.get(key) for key in ("probes", "drawing")}
    return state_digest(payload)


def atlas_summary(engine):
    """(title, detail) for the atlas card."""
    if engine.current_atlas == "slice" and engine.atlas_view.slice_image_data is not None:
        return "Slice atlas", "2D calibrated plate"
    if engine.atlas_view.atlas_data is None:
        return "No atlas", "Load a processed volume atlas folder."
    path = engine.current_atlas_path or ""
    name = path.rstrip("/\\").split("/")[-1].split("\\")[-1] or "Volume atlas"
    voxel = engine.atlas_view.vox_size_um
    shape = np.shape(engine.atlas_view.atlas_data)
    detail = "{} · {} µm voxels · {}×{}×{}".format(
        "Volume atlas", "{:g}".format(float(voxel)) if voxel else "?", *shape[:3])
    return name, detail


def section_summary(engine):
    """(title, detail) for the current section."""
    view = engine.image_view
    if view.current_img is None:
        return "No section", "Load a histology image (TIFF, CZI, PNG, JPEG)."
    image_file = view.image_file
    name = (engine.current_img_name or getattr(image_file, "file_name_list", ["Section"])[0])
    shape = np.shape(view.current_img)
    channels = shape[2] if len(shape) == 3 else 1
    kind = "RGB" if getattr(image_file, "is_rgb", False) else "{} channel{}".format(
        channels, "" if channels == 1 else "s")
    detail = "{} × {} px · {} · {}".format(shape[1], shape[0], view.current_img.dtype, kind)
    pages = getattr(image_file, "n_pages", 1)
    if pages > 1:
        detail += " · {} {} planes".format(pages, getattr(image_file, "page_axis", None) or "page")
    return str(name).split("/")[-1], detail


def sagittal_hemisphere(engine):
    """(side, mm from the midline) of the sagittal page shown, or None.

    ``side`` is "right", "left" or "midline" (the animal's sides; pages above
    the midline are the right hemisphere).
    """
    from ..atlas_matching import sagittal_side

    view = engine.atlas_view
    if view.atlas_data is None or engine.atlas_display != "sagittal" \
            or view.current_sagital_index is None:
        return None
    midline = float(view.origin_3d[0])
    index = int(view.current_sagital_index)
    return (sagittal_side(index, midline),
            abs(index - midline) * float(view.vox_size_um) / 1000.0)


def plane_summary(engine):
    """"Sagittal · page 124 of 228 · tilt +3.0° / −6.0°" for the canvas header."""
    view = engine.atlas_view
    if view.atlas_data is None:
        return "No atlas"
    plane = engine.atlas_display
    pages = {"coronal": (view.current_coronal_index, view.cpage_ctrl),
             "sagittal": (view.current_sagital_index, view.spage_ctrl),
             "horizontal": (view.current_horizontal_index, view.hpage_ctrl)}
    tilts = dict(zip(("coronal", "sagittal", "horizontal"), view.get_atlas_angles()))
    index, control = pages.get(plane, (None, None))
    total = control.page_slider.maximum() + 1 if control is not None else None
    tilt = tilts.get(plane, (0, 0))
    text = "{} · page {}".format(str(plane).capitalize(), index)
    if total:
        text += " of {}".format(total)
    side = sagittal_hemisphere(engine)
    if side is not None:
        text += " · midline" if side[0] == "midline" else \
            " · {} hemisphere {:.2f} mm".format(side[0], side[1])
    text += " · tilt {:+.1f}° / {:+.1f}°".format(float(tilt[0]), float(tilt[1]))
    return text


def step_status(engine):
    """Concrete status text for each workflow step."""
    has_atlas = engine.atlas_view.atlas_data is not None or engine.current_atlas == "slice"
    has_image = engine.image_view.current_img is not None
    pairs = len(engine.atlas_tri_inside_data)
    status = {}
    status["project"] = ("atlas and section loaded" if has_atlas and has_image
                         else "atlas loaded" if has_atlas
                         else "section loaded" if has_image else "nothing loaded")
    number, count, name = engine.section_position()
    if count > 1:
        status["project"] = "section {} of {}: {}".format(number, count, name)
    if not has_image:
        status["section"] = "no image"
    elif engine.registration_input is None:
        status["section"] = "choose registration channels"
    else:
        status["section"] = "registers on " + engine.registration_input.describe()
    status["match"] = "no atlas" if not has_atlas else plane_summary(engine).split(" · tilt")[0]
    if pairs == 0:
        status["register"] = "no landmarks"
    else:
        review = engine.registration_review_state()
        status["register"] = "{} pair{} · {}".format(pairs, "" if pairs == 1 else "s",
                                                     "reviewed" if review == "reviewed"
                                                     else "review pending")
    if engine.h2a_transferred:
        status["register"] += " · warp preview on"
    marks = sum(_describe_len(engine.working_img_data.get(key)) for key in
                ("img-probe", "img-cells", "img-drawing", "img-contour"))
    atlas_marks = sum(_describe_len(engine.working_atlas_data.get(key)) for key in
                      ("atlas-probe", "atlas-cells", "atlas-drawing", "atlas-contour"))
    status["annotate"] = "{} section mark{}, {} atlas mark{}".format(
        marks, "" if marks == 1 else "s", atlas_marks, "" if atlas_marks == 1 else "s")
    implants = len(engine.implants)
    if implants:
        outlines = sum(1 for entry in engine.implant_outlines.values() if entry["points"])
        status["annotate"] += " · {} implant{}".format(implants, "" if implants == 1 else "s")
        if outlines:
            status["annotate"] += ", {} outline{} to map".format(
                outlines, "" if outlines == 1 else "s")
    objects = len(engine.object_ctrl.obj_name)
    status["results"] = "{} stored object{} or part{}".format(
        objects, "" if objects == 1 else "s", "" if objects == 1 else "s")
    records, object_states = engine.mapping_overview()
    stale_records = sum(is_out_of_date(state) for _record, state in records)
    stale_objects = sum(is_out_of_date(state) for state in object_states)
    if stale_records:
        status["annotate"] += " · {} mapping{} out of date".format(
            stale_records, "" if stale_records == 1 else "s")
    if stale_objects:
        status["results"] += " · {} out of date".format(stale_objects)
    unverified = sum(state == UNVERIFIED for state in object_states)
    if unverified:
        status["results"] += " · {} not verified".format(unverified)
    return status


STATUS_TEXT = {
    BUILD_CHANGED: "out of date: build settings changed; build again",
    CURRENT: "current",
    REGISTRATION_CHANGED: "out of date: registration changed",
    REMAPPED: "out of date: marks mapped again since",
    OTHER_SECTION: "from another section",
    UNVERIFIED: "not verified: open its section once to check",
    NOT_RECORDED: "origin not recorded",
}


def mapping_status_text(status):
    return STATUS_TEXT.get(status, str(status))


# The annotation kinds of the Annotate pipeline: (name, section key, atlas key,
# part type, built type). Probes and implants have their own cards.
PIPELINE_KINDS = (
    ("cells", "img-cells", "atlas-cells", "cells piece", "merged cells"),
    ("expression", "img-virus", "atlas-virus", "virus piece", "merged virus"),
    ("contour", "img-contour", "atlas-contour", "contour piece", "merged contour"),
    ("drawing", "img-drawing", "atlas-drawing", "drawing piece", "merged drawing"),
)


def _has(value):
    if value is None:
        return False
    try:
        return len(value) > 0
    except TypeError:
        return True


def annotation_pipeline(engine):
    """Where the cells, expression, contours and drawings are in the pipeline
    Mark → Check registration → Map → Make parts → Build.

    Returns a dict with the kinds at each stage (``marked``: on the section,
    not mapped; ``mapped``: atlas marks not made into parts; ``parts``: parts
    not built; ``built``), the review state and ``next``: one of "mark",
    "map", "parts", "build", "inspect".
    """
    types = list(engine.object_ctrl.obj_type)
    stages = {"marked": [], "mapped": [], "parts": [], "built": []}
    for kind, section_key, atlas_key, piece, merged in PIPELINE_KINDS:
        mask = engine.working_img_data.get(section_key)
        if kind == "expression":
            marked = mask is not None and bool(np.any(mask))
        else:
            marked = _has(mask)
        if marked:
            stages["marked"].append(kind)
        if _has(engine.working_atlas_data.get(atlas_key)):
            stages["mapped"].append(kind)
        if piece in types:
            stages["parts"].append(kind)
        if merged in types:
            stages["built"].append(kind)
    next_step = ("map" if stages["marked"] else "parts" if stages["mapped"] else
                 "build" if stages["parts"] else "inspect" if stages["built"] else "mark")
    return dict(stages, next=next_step, review=engine.registration_review_state())
