"""Coordinate and anatomical summaries for drawing objects."""

import csv

import numpy as np

from .probe_reconstruction import (
    allen_ccf_to_estimated_bregma_mm,
    herbs_vox_to_source_vox,
    is_allen_ccf_2017,
    normalize_axis_info,
)


ROI_CSV_FIELDS = (
    "piece",
    "point",
    "herbs_ML_vox_from_bregma",
    "herbs_AP_vox_from_bregma",
    "herbs_DV_dorsal_vox_from_bregma",
    "configured_AP_mm",
    "configured_ML_mm",
    "configured_DV_ventral_mm",
    "allen_AP_vox",
    "allen_DV_vox",
    "allen_ML_vox",
    "estimated_AP_mm",
    "estimated_ML_mm",
    "affine_DV_mm_not_for_targeting",
    "surface_depth_mm",
    "structure_id",
    "structure_acronym",
    "structure_name",
)


def _drawing_pieces(pieces):
    result = []
    for piece in pieces:
        array = np.asarray(piece, dtype=float)
        if array.ndim != 2 or array.shape[1:] != (3,):
            raise ValueError("Drawing pieces must be arrays with shape (N, 3).")
        if not np.all(np.isfinite(array)):
            raise ValueError("Drawing coordinates must contain only finite values.")
        result.append(array)
    if not result or not any(len(piece) for piece in result):
        raise ValueError("A drawing must contain at least one coordinate.")
    return result


def _axis_statistics(values):
    values = np.asarray(values, dtype=float)
    result = {}
    for index, axis in enumerate(("AP", "ML", "DV")):
        column = values[:, index]
        finite = column[np.isfinite(column)]
        if finite.size:
            result[axis] = {
                "centroid": float(np.mean(finite)),
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
            }
    return result


def _surface_depth_mm(points, label_volume, voxel_size_um):
    points = np.asarray(points, dtype=float)
    indexes = points.astype(int)
    depths = np.full(len(points), np.nan, dtype=float)
    if label_volume is None:
        return depths

    labels = np.asarray(label_volume)
    if labels.ndim != 3:
        raise ValueError("The atlas label volume must be three-dimensional.")

    valid_xy = (
        (indexes[:, 0] >= 0)
        & (indexes[:, 0] < labels.shape[0])
        & (indexes[:, 1] >= 0)
        & (indexes[:, 1] < labels.shape[1])
    )
    point_indexes = np.flatnonzero(valid_xy)
    if not point_indexes.size:
        return depths

    pairs, inverse = np.unique(indexes[point_indexes, :2], axis=0, return_inverse=True)
    lower = np.full(len(pairs), -1, dtype=int)
    upper = np.full(len(pairs), -1, dtype=int)
    chunk_size = 4096
    for start in range(0, len(pairs), chunk_size):
        stop = min(start + chunk_size, len(pairs))
        chunk = pairs[start:stop]
        occupied = labels[chunk[:, 0], chunk[:, 1], :] != 0
        has_brain = np.any(occupied, axis=1)
        if not np.any(has_brain):
            continue
        valid_rows = np.flatnonzero(has_brain)
        lower[start + valid_rows] = np.argmax(occupied[valid_rows], axis=1)
        upper[start + valid_rows] = (
            labels.shape[2]
            - 1
            - np.argmax(occupied[valid_rows, ::-1], axis=1)
        )

    point_lower = lower[inverse]
    point_upper = upper[inverse]
    point_z = points[point_indexes, 2]
    inside_extent = (
        (point_lower >= 0)
        & (point_z >= point_lower)
        & (point_z <= point_upper)
    )
    selected = point_indexes[inside_extent]
    depths[selected] = (
        (point_upper[inside_extent] - point_z[inside_extent])
        * float(voxel_size_um)
        / 1000.0
    )
    return depths


def _structure_details(structure_ids, label_info):
    unique_ids, inverse = np.unique(structure_ids, return_inverse=True)
    unique_names = np.full(len(unique_ids), "", dtype=object)
    unique_acronyms = np.full(len(unique_ids), "", dtype=object)
    colors = {}
    if label_info is None:
        return unique_names[inverse], unique_acronyms[inverse], colors

    indexes = np.asarray(label_info.get("index", []), dtype=int).ravel()
    labels = np.asarray(label_info.get("label", []), dtype=object).ravel()
    abbrevs = np.asarray(label_info.get("abbrev", []), dtype=object).ravel()
    label_colors = np.asarray(label_info.get("color", []))
    lookup = {int(label_id): index for index, label_id in enumerate(indexes)}
    for row, label_id in enumerate(unique_ids):
        label_index = lookup.get(int(label_id))
        if label_index is None:
            continue
        if label_index < len(labels):
            unique_names[row] = str(labels[label_index])
        if label_index < len(abbrevs):
            unique_acronyms[row] = str(abbrevs[label_index])
        if label_index < len(label_colors):
            colors[int(label_id)] = tuple(
                int(value) for value in np.ravel(label_colors[label_index])[:3]
            )
    return unique_names[inverse], unique_acronyms[inverse], colors


def _region_summary(structure_ids, names, acronyms, colors):
    unique_ids, first_indexes, counts = np.unique(
        structure_ids, return_index=True, return_counts=True
    )
    total = max(1, len(structure_ids))
    rows = []
    for label_id, sample, count in zip(unique_ids, first_indexes, counts):
        if int(label_id) == 0:
            name = names[sample] or "Outside atlas / unlabeled"
            acronym = acronyms[sample] or "—"
            color = (128, 128, 128)
        else:
            name = names[sample] or "Unknown structure"
            acronym = acronyms[sample] or "—"
            color = colors.get(int(label_id), (128, 128, 128))
        rows.append(
            {
                "label_id": int(label_id),
                "name": name,
                "acronym": acronym,
                "color": color,
                "count": int(count),
                "percentage": float(count) * 100.0 / total,
            }
        )
    rows.sort(key=lambda row: (-row["count"], row["label_id"]))
    return rows


def _drawing_metric(pieces, plot_mode, voxel_size_um):
    scale_mm = float(voxel_size_um) / 1000.0
    if plot_mode == "area":
        return "sampled_area_mm2", sum(len(piece) for piece in pieces) * scale_mm**2

    length_vox = 0.0
    for piece in pieces:
        if len(piece) > 1:
            length_vox += float(np.linalg.norm(np.diff(piece, axis=0), axis=1).sum())
    return "line_length_mm", length_vox * scale_mm


def build_drawing_roi_info(
    pieces,
    piece_names,
    *,
    bregma_herbs_vox,
    voxel_size_um,
    herbs_shape,
    axis_info=None,
    label_volume=None,
    label_info=None,
):
    """Build an ROI report for one drawing piece or a merged drawing.

    Drawing coordinates use HERBS' internal ``(ML, AP, dorsal DV)`` axes and
    are relative to the configured Bregma voxel.
    """
    pieces = _drawing_pieces(pieces)
    voxel_size_um = float(voxel_size_um)
    if not np.isfinite(voxel_size_um) or voxel_size_um <= 0:
        raise ValueError("Voxel size must be a positive finite value.")

    herbs_shape = tuple(int(value) for value in herbs_shape)
    if len(herbs_shape) != 3 or any(value <= 0 for value in herbs_shape):
        raise ValueError("HERBS atlas shape must contain three positive dimensions.")
    bregma = np.asarray(bregma_herbs_vox, dtype=float)
    if bregma.shape != (3,):
        raise ValueError("Bregma must contain three HERBS voxel coordinates.")

    names = [str(name) for name in piece_names]
    if len(names) != len(pieces):
        raise ValueError("Each drawing piece must have one name.")

    points = np.vstack(pieces)
    piece_index = np.concatenate(
        [np.full(len(piece), index + 1, dtype=int) for index, piece in enumerate(pieces)]
    )
    point_index = np.concatenate(
        [np.arange(1, len(piece) + 1, dtype=int) for piece in pieces]
    )
    absolute_points = points + bregma
    configured_mm = np.stack(
        (points[:, 1], points[:, 0], -points[:, 2]), axis=1
    ) * (voxel_size_um / 1000.0)

    structure_ids = np.zeros(len(points), dtype=int)
    label_array = None
    if label_volume is not None:
        label_array = np.asarray(label_volume)
        if label_array.shape != herbs_shape:
            raise ValueError("Atlas labels do not match the HERBS atlas shape.")
        indexes = absolute_points.astype(int)
        valid = np.all(
            (indexes >= 0) & (indexes < np.asarray(herbs_shape, dtype=int)), axis=1
        )
        valid_indexes = indexes[valid]
        structure_ids[valid] = label_array[
            valid_indexes[:, 0], valid_indexes[:, 1], valid_indexes[:, 2]
        ].astype(int)

    structure_names, structure_acronyms, colors = _structure_details(
        structure_ids, label_info
    )
    surface_depth = _surface_depth_mm(
        absolute_points, label_array, voxel_size_um
    )

    normalized_axis_info = None
    source_vox = None
    estimated_mm = None
    try:
        normalized_axis_info = normalize_axis_info(axis_info, herbs_shape)
    except (KeyError, TypeError, ValueError):
        normalized_axis_info = None
    if normalized_axis_info is not None and is_allen_ccf_2017(
        normalized_axis_info, voxel_size_um
    ):
        source_vox = herbs_vox_to_source_vox(
            absolute_points, normalized_axis_info
        )
        estimated_mm = allen_ccf_to_estimated_bregma_mm(
            source_vox * voxel_size_um
        )
        reported_mm = estimated_mm[:, (0, 2, 1)]
        coordinate_basis = "Estimated Allen Bregma"
        ground_truth = False
    else:
        reported_mm = configured_mm
        coordinate_basis = "Configured atlas Bregma"
        ground_truth = None

    finite_depth = surface_depth[np.isfinite(surface_depth)]
    depth_summary = None
    if finite_depth.size:
        depth_summary = {
            "mean": float(np.mean(finite_depth)),
            "min": float(np.min(finite_depth)),
            "max": float(np.max(finite_depth)),
            "count": int(finite_depth.size),
        }

    plot_mode = "area" if names and "area" in names[0].lower() else "line"
    metric_name, metric_value = _drawing_metric(
        pieces, plot_mode, voxel_size_um
    )
    coordinates = {
        "relative_herbs_vox": points,
        "absolute_herbs_vox": absolute_points,
        "configured_bregma_mm": configured_mm,
        "surface_depth_mm": surface_depth,
    }
    if source_vox is not None:
        coordinates["allen_ccf_vox"] = source_vox
        coordinates["estimated_stereotaxic_bregma_mm"] = estimated_mm

    return {
        "plot_mode": plot_mode,
        "pieces_names": names,
        "point_count": int(len(points)),
        "piece_index": piece_index,
        "point_index": point_index,
        "metric_name": metric_name,
        "metric_value": float(metric_value),
        "coordinate_basis": coordinate_basis,
        "ground_truth": ground_truth,
        "coordinate_summary": _axis_statistics(reported_mm),
        "surface_depth_summary": depth_summary,
        "coordinates": coordinates,
        "structure_ids": structure_ids,
        "structure_names": structure_names,
        "structure_acronyms": structure_acronyms,
        "regions": _region_summary(
            structure_ids, structure_names, structure_acronyms, colors
        ),
    }


def iter_roi_csv_rows(info):
    """Yield dictionaries suitable for a coordinate CSV export."""
    coordinates = info["coordinates"]
    relative = coordinates["relative_herbs_vox"]
    configured = coordinates["configured_bregma_mm"]
    surface_depth = coordinates["surface_depth_mm"]
    source = coordinates.get("allen_ccf_vox")
    estimated = coordinates.get("estimated_stereotaxic_bregma_mm")

    for index in range(info["point_count"]):
        row = {
            "piece": int(info["piece_index"][index]),
            "point": int(info["point_index"][index]),
            "herbs_ML_vox_from_bregma": float(relative[index, 0]),
            "herbs_AP_vox_from_bregma": float(relative[index, 1]),
            "herbs_DV_dorsal_vox_from_bregma": float(relative[index, 2]),
            "configured_AP_mm": float(configured[index, 0]),
            "configured_ML_mm": float(configured[index, 1]),
            "configured_DV_ventral_mm": float(configured[index, 2]),
            "surface_depth_mm": (
                float(surface_depth[index])
                if np.isfinite(surface_depth[index])
                else ""
            ),
            "structure_id": int(info["structure_ids"][index]),
            "structure_acronym": str(info["structure_acronyms"][index]),
            "structure_name": str(info["structure_names"][index]),
        }
        if source is not None:
            row.update(
                {
                    "allen_AP_vox": float(source[index, 0]),
                    "allen_DV_vox": float(source[index, 1]),
                    "allen_ML_vox": float(source[index, 2]),
                    "estimated_AP_mm": float(estimated[index, 0]),
                    "estimated_ML_mm": float(estimated[index, 2]),
                    "affine_DV_mm_not_for_targeting": float(estimated[index, 1]),
                }
            )
        yield row


def write_roi_csv(path, info):
    """Write every sampled drawing coordinate and its annotation to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=ROI_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(iter_roi_csv_rows(info))
