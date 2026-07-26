"""Build self-contained coordinate metadata for exported probe objects."""

from pathlib import Path

import numpy as np


PROBE_RECONSTRUCTION_SCHEMA_VERSION = 1
HERBS_AXES = ("LR", "AP", "DV")
HERBS_AXIS_DIRECTIONS = ("right", "anterior", "superior")
_OPPOSITE_DIRECTION = {
    "right": "left",
    "left": "right",
    "anterior": "posterior",
    "posterior": "anterior",
    "superior": "inferior",
    "inferior": "superior",
}
_ALLEN_CCF_2017_SHAPES = {
    10.0: (1320, 800, 1140),
    25.0: (528, 320, 456),
    50.0: (264, 160, 228),
    100.0: (132, 80, 114),
}
ALLEN_CCF_ESTIMATED_BREGMA_UM = np.array([5400.0, 440.0, 5700.0])
ALLEN_CCF_SAGITTAL_TILT_DEG = 5.0
ALLEN_CCF_DV_SCALE = 0.9434


def allen_ccf_estimated_bregma_vox(voxel_size_um):
    """Return the nearest source voxel to the estimated Allen CCF Bregma."""
    voxel_size_um = float(voxel_size_um)
    if not np.isfinite(voxel_size_um) or voxel_size_um <= 0:
        raise ValueError("Voxel size must be a positive finite value.")
    return np.floor(
        ALLEN_CCF_ESTIMATED_BREGMA_UM / voxel_size_um + 0.5
    ).astype(int)


def normalize_axis_info(axis_info, herbs_shape):
    """Validate an atlas transform and fill fields required for inversion."""
    herbs_shape = tuple(int(value) for value in herbs_shape)
    if len(herbs_shape) != 3 or any(value <= 0 for value in herbs_shape):
        raise ValueError("HERBS atlas shape must contain three positive dimensions.")

    supplied = axis_info is not None
    if axis_info is None:
        axis_info = {
            "to_HERBS": (0, 1, 2),
            "from_HERBS": (0, 1, 2),
            "direction_change": (False, False, False),
            "size": herbs_shape,
        }

    to_herbs = tuple(int(value) for value in axis_info["to_HERBS"])
    if len(to_herbs) != 3 or sorted(to_herbs) != [0, 1, 2]:
        raise ValueError("to_HERBS must be a permutation of three atlas axes.")

    inverse = tuple(int(value) for value in np.argsort(to_herbs))
    from_herbs = tuple(
        int(value) for value in axis_info.get("from_HERBS", inverse)
    )
    if from_herbs != inverse:
        raise ValueError("from_HERBS is not the inverse of to_HERBS.")

    direction_change = tuple(bool(value) for value in axis_info["direction_change"])
    if len(direction_change) != 3:
        raise ValueError("direction_change must describe exactly three source axes.")

    if "size" in axis_info:
        source_shape = tuple(int(value) for value in axis_info["size"])
    else:
        source_shape_array = np.empty(3, dtype=int)
        source_shape_array[np.asarray(to_herbs)] = np.asarray(herbs_shape)
        source_shape = tuple(source_shape_array.tolist())
    if len(source_shape) != 3 or any(value <= 0 for value in source_shape):
        raise ValueError("Source atlas shape must contain three positive dimensions.")

    expected_herbs_shape = tuple(np.asarray(source_shape)[np.asarray(to_herbs)])
    if expected_herbs_shape != herbs_shape:
        raise ValueError(
            "Atlas axis metadata does not match the atlas used for the probe."
        )

    return {
        "to_HERBS": to_herbs,
        "from_HERBS": from_herbs,
        "direction_change": direction_change,
        "size": source_shape,
        "available_from_atlas": supplied,
    }


def herbs_vox_to_source_vox(points, axis_info):
    """Convert one or more continuous HERBS voxels into source-atlas voxels."""
    points = np.asarray(points, dtype=float)
    if points.shape[-1:] != (3,):
        raise ValueError("Coordinate arrays must end with three values.")

    source_points = points[..., np.asarray(axis_info["from_HERBS"])].copy()
    source_shape = np.asarray(axis_info["size"], dtype=float)
    for axis, should_flip in enumerate(axis_info["direction_change"]):
        if should_flip:
            source_points[..., axis] = (
                source_shape[axis] - 1 - source_points[..., axis]
            )
    return source_points


def volume_view_vox_to_source_vox(points, view_shape, axis_info):
    """Convert AtlasView ``(DV, ML, AP-view)`` voxels to source-atlas voxels."""
    points = np.asarray(points, dtype=float)
    view_shape = tuple(int(value) for value in view_shape)
    if points.shape[-1:] != (3,):
        raise ValueError("Coordinate arrays must end with three values.")
    if len(view_shape) != 3 or any(value <= 0 for value in view_shape):
        raise ValueError("Atlas view shape must contain three positive dimensions.")

    herbs_points = np.stack(
        (
            points[..., 1],
            points[..., 2],
            view_shape[0] - 1 - points[..., 0],
        ),
        axis=-1,
    )
    herbs_shape = (view_shape[1], view_shape[2], view_shape[0])
    normalized_axis_info = normalize_axis_info(axis_info, herbs_shape)
    return herbs_vox_to_source_vox(herbs_points, normalized_axis_info)


def allen_ccf_to_estimated_bregma_mm(ccf_um):
    """Approximate Allen CCF ``(AP, DV, ML)`` µm as stereotaxic millimeters.

    The returned axes are ``(AP, DV, ML)`` with positive AP anterior, positive
    DV ventral, and positive ML right. This is a community-derived
    approximation, not a ground-truth targeting transform.
    """
    ccf_um = np.asarray(ccf_um, dtype=float)
    if ccf_um.shape[-1:] != (3,):
        raise ValueError("Allen CCF coordinates must end with AP, DV, and ML.")

    centered = ccf_um - ALLEN_CCF_ESTIMATED_BREGMA_UM
    ap = centered[..., 0]
    dv = centered[..., 1]
    ml = centered[..., 2]
    angle = np.deg2rad(ALLEN_CCF_SAGITTAL_TILT_DEG)
    rotated_ap = ap * np.cos(angle) - dv * np.sin(angle)
    rotated_dv = (
        ap * np.sin(angle) + dv * np.cos(angle)
    ) * ALLEN_CCF_DV_SCALE
    return np.stack((-rotated_ap, rotated_dv, ml), axis=-1) / 1000.0


def format_estimated_bregma_report(estimated_mm, surface_depth_um, region=""):
    """Format the concise Allen coordinate report used by the status bar."""
    estimated_mm = np.asarray(estimated_mm, dtype=float)
    if estimated_mm.shape != (3,):
        raise ValueError("Estimated coordinates must contain AP, DV, and ML.")
    report = (
        "Bregma est.: AP {:+.2f} mm | ML {:+.2f} mm | "
        "Depth {:.2f} mm from surface"
    ).format(
        estimated_mm[0],
        estimated_mm[2],
        float(surface_depth_um) / 1000.0,
    )
    if region:
        report = "{} | {}".format(report, region)
    return report


def _source_axis_metadata(axis_info):
    source_axes = [None, None, None]
    source_directions = [None, None, None]
    for herbs_axis, source_axis in enumerate(axis_info["to_HERBS"]):
        source_axes[source_axis] = HERBS_AXES[herbs_axis]
        direction = HERBS_AXIS_DIRECTIONS[herbs_axis]
        if axis_info["direction_change"][source_axis]:
            direction = _OPPOSITE_DIRECTION[direction]
        source_directions[source_axis] = direction
    return source_axes, source_directions


def is_allen_ccf_2017(axis_info, voxel_size_um):
    expected_shape = _ALLEN_CCF_2017_SHAPES.get(float(voxel_size_um))
    return (
        expected_shape == tuple(axis_info["size"])
        and tuple(axis_info["to_HERBS"]) == (2, 0, 1)
        and tuple(axis_info["direction_change"]) == (True, True, False)
    )


def _flatten_groups(groups, dtype=None):
    arrays = [np.asarray(group, dtype=dtype) for group in groups]
    if not arrays:
        return np.empty((0,), dtype=dtype)
    return np.concatenate(arrays, axis=0)


def _structure_text(structure_ids, label_info, key, default=""):
    lookup = {
        int(label_id): str(value)
        for label_id, value in zip(
            np.ravel(label_info["index"]), np.ravel(label_info[key])
        )
    }
    return [lookup.get(int(label_id), default) for label_id in structure_ids]


def _coordinate_record(relative_bregma_vox, bregma_herbs_vox, voxel_size_um,
                       axis_info, voxel_index=None, allen_ccf=False):
    relative_bregma_vox = np.asarray(relative_bregma_vox, dtype=float)
    herbs_vox = relative_bregma_vox + bregma_herbs_vox
    source_vox = herbs_vox_to_source_vox(herbs_vox, axis_info)
    record = {
        "herbs_vox": herbs_vox,
        "herbs_vox_index": (
            np.asarray(voxel_index, dtype=int)
            if voxel_index is not None
            else herbs_vox.astype(int)
        ),
        "bregma_um": relative_bregma_vox * voxel_size_um,
        "source_vox": source_vox,
        "source_um": source_vox * voxel_size_um,
    }
    if allen_ccf:
        record["allen_ccf_vox"] = record["source_vox"].copy()
        record["allen_ccf_um"] = record["source_um"].copy()
        record["estimated_stereotaxic_bregma_mm"] = (
            allen_ccf_to_estimated_bregma_mm(record["allen_ccf_um"])
        )
    return record


def build_probe_reconstruction(
    *,
    insertion_bregma_vox,
    terminus_bregma_vox,
    insertion_vox_index,
    terminus_vox_index,
    contact_bregma_vox,
    contact_vox_index,
    contact_structure_ids,
    contact_local_from_tip_base_um,
    probe_length_um,
    probe_settings,
    site_face,
    voxel_size_um,
    bregma_herbs_vox,
    herbs_atlas_shape,
    label_info,
    axis_info=None,
    atlas_identifier=None,
    atlas_path=None,
    software_version=None,
    trajectory_fit=None,
):
    """Create the reconstruction payload embedded in each merged probe.

    Contacts are flattened column-major. Within a column, index zero is the
    contact nearest the geometric tip for probe geometries generated by HERBS.
    """
    voxel_size_um = float(voxel_size_um)
    if not np.isfinite(voxel_size_um) or voxel_size_um <= 0:
        raise ValueError("Atlas voxel size must be a positive number.")
    bregma_herbs_vox = np.asarray(bregma_herbs_vox, dtype=float)
    if bregma_herbs_vox.shape != (3,):
        raise ValueError("Bregma must contain three HERBS voxel coordinates.")

    normalized_axis_info = normalize_axis_info(axis_info, herbs_atlas_shape)
    source_axes, source_directions = _source_axis_metadata(normalized_axis_info)
    allen_ccf = is_allen_ccf_2017(normalized_axis_info, voxel_size_um)

    contact_counts = [len(group) for group in contact_bregma_vox]
    if not (
        contact_counts == [len(group) for group in contact_vox_index]
        == [len(group) for group in contact_structure_ids]
        == [len(group) for group in contact_local_from_tip_base_um]
    ):
        raise ValueError("Probe contact coordinate groups do not have matching sizes.")

    contact_bregma_vox_flat = _flatten_groups(contact_bregma_vox, dtype=float)
    contact_vox_index_flat = _flatten_groups(contact_vox_index, dtype=int)
    structure_ids = _flatten_groups(contact_structure_ids, dtype=int)
    local_from_tip_base_um = _flatten_groups(
        contact_local_from_tip_base_um, dtype=float
    )
    column_index = np.concatenate(
        [np.full(count, column, dtype=int) for column, count in enumerate(contact_counts)]
    ) if contact_counts else np.empty((0,), dtype=int)
    index_in_column = np.concatenate(
        [np.arange(count, dtype=int) for count in contact_counts]
    ) if contact_counts else np.empty((0,), dtype=int)

    contact_herbs_vox = contact_bregma_vox_flat + bregma_herbs_vox
    contact_source_vox = herbs_vox_to_source_vox(
        contact_herbs_vox, normalized_axis_info
    )
    tip_length_um = float(probe_settings.get("tip_length") or 0)
    distance_from_tip_um = local_from_tip_base_um[:, 0] + tip_length_um
    contact_local_um = local_from_tip_base_um.copy()
    contact_local_um[:, 0] = distance_from_tip_um

    contacts = {
        "count": int(len(structure_ids)),
        "site_index": np.arange(len(structure_ids), dtype=int),
        "column_index": column_index,
        "index_in_column": index_in_column,
        "column_contact_counts": np.asarray(contact_counts, dtype=int),
        "ordering": "column-major; index_in_column 0 is tip-nearest",
        "probe_local_axes": ["distance_from_tip", "lateral", "surface_normal"],
        "probe_local_um": contact_local_um,
        "distance_from_tip_um": distance_from_tip_um,
        "distance_from_insertion_um": float(probe_length_um) - distance_from_tip_um,
        "axial_distance_up_from_tip_um": distance_from_tip_um,
        "axial_depth_from_insertion_um": (
            float(probe_length_um) - distance_from_tip_um
        ),
        "herbs_vox": contact_herbs_vox,
        "herbs_vox_index": contact_vox_index_flat,
        "bregma_um": contact_bregma_vox_flat * voxel_size_um,
        "source_vox": contact_source_vox,
        "source_um": contact_source_vox * voxel_size_um,
        "structure_id": structure_ids,
        "structure_acronym": _structure_text(
            structure_ids, label_info, "abbrev"
        ),
        "structure_name": _structure_text(structure_ids, label_info, "label"),
    }
    if allen_ccf:
        contacts["allen_ccf_vox"] = contacts["source_vox"].copy()
        contacts["allen_ccf_um"] = contacts["source_um"].copy()
        contacts["estimated_stereotaxic_bregma_mm"] = (
            allen_ccf_to_estimated_bregma_mm(contacts["allen_ccf_um"])
        )

    source_name = "Allen Mouse Common Coordinate Framework"
    source_version = "CCFv3 2017"
    if not allen_ccf:
        source_name = atlas_identifier or "Source atlas"
        source_version = None

    atlas = {
        "identifier": atlas_identifier,
        "path_at_export": str(Path(atlas_path).resolve()) if atlas_path else None,
        "voxel_size_um": voxel_size_um,
        "herbs_shape_vox": tuple(int(value) for value in herbs_atlas_shape),
        "bregma_herbs_vox": bregma_herbs_vox,
        "herbs_axes": list(HERBS_AXES),
        "herbs_axis_directions": list(HERBS_AXIS_DIRECTIONS),
        "source_name": source_name,
        "source_version": source_version,
        "source_shape_vox": tuple(normalized_axis_info["size"]),
        "source_axes": source_axes,
        "source_axis_directions": source_directions,
        "bregma_source_vox": herbs_vox_to_source_vox(
            bregma_herbs_vox, normalized_axis_info
        ),
        "axis_transform": normalized_axis_info,
        "label_lookup": label_info,
    }
    atlas["bregma_source_um"] = atlas["bregma_source_vox"] * voxel_size_um
    if allen_ccf:
        atlas["estimated_stereotaxic_transform"] = {
            "name": "Community-estimated Allen CCF to Bregma",
            "coordinate_order": ["AP", "DV", "ML"],
            "units": "mm",
            "positive_directions": ["anterior", "ventral", "right"],
            "ccf_bregma_um": ALLEN_CCF_ESTIMATED_BREGMA_UM.copy(),
            "sagittal_tilt_deg": ALLEN_CCF_SAGITTAL_TILT_DEG,
            "dv_scale": ALLEN_CCF_DV_SCALE,
            "ground_truth": False,
            "targeting_note": (
                "Approximate only; use measured depth from brain surface for "
                "surgical targeting rather than transformed DV."
            ),
        }

    return {
        "schema_version": PROBE_RECONSTRUCTION_SCHEMA_VERSION,
        "software": {"name": "HERBS", "version": software_version},
        "atlas": atlas,
        "probe": {
            "settings": probe_settings,
            "site_face": site_face,
            "contact_ordering": contacts["ordering"],
            "trajectory_fit": trajectory_fit,
        },
        "coordinates": {
            "tip": _coordinate_record(
                terminus_bregma_vox,
                bregma_herbs_vox,
                voxel_size_um,
                normalized_axis_info,
                voxel_index=terminus_vox_index,
                allen_ccf=allen_ccf,
            ),
            "insertion": _coordinate_record(
                insertion_bregma_vox,
                bregma_herbs_vox,
                voxel_size_um,
                normalized_axis_info,
                voxel_index=insertion_vox_index,
                allen_ccf=allen_ccf,
            ),
            "contacts": contacts,
        },
    }
