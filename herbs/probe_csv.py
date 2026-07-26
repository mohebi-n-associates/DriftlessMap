"""CSV export for reconstructed probe trajectories and physical contacts."""

import csv

import numpy as np


PROBE_CSV_FIELDS = (
    "probe_name",
    "record_type",
    "site_index",
    "column_index",
    "index_in_column",
    "distance_from_insertion_um",
    "distance_from_tip_um",
    "probe_lateral_um",
    "probe_surface_normal_um",
    "herbs_ML_vox",
    "herbs_AP_vox",
    "herbs_DV_dorsal_vox",
    "configured_ML_mm",
    "configured_AP_mm",
    "configured_DV_ventral_mm",
    "source_axis_0_name",
    "source_axis_0_vox",
    "source_axis_1_name",
    "source_axis_1_vox",
    "source_axis_2_name",
    "source_axis_2_vox",
    "allen_AP_vox",
    "allen_DV_vox",
    "allen_ML_vox",
    "estimated_AP_mm",
    "estimated_ML_mm",
    "affine_DV_mm_not_for_targeting",
    "structure_id",
    "structure_acronym",
    "structure_name",
    "region_contact_count",
    "region_path_length_um",
    "AP_tilt_deg_from_vertical",
    "AP_tilt_direction",
    "ML_tilt_deg_from_vertical",
    "ML_tilt_direction",
    "trajectory_length_um",
    "vertical_depth_change_um",
    "fit_method",
    "surface_method",
    "fit_points",
    "fit_inliers",
    "fit_RMS_error_um",
    "fit_max_error_um",
    "fit_explained_fraction",
    "surface_adjustment_um",
    "coordinate_note",
)


def _vector(values, name):
    values = np.asarray(values, dtype=float)
    if values.shape != (3,):
        raise ValueError("{} must contain three coordinates.".format(name))
    return values


def _base_row(probe_name, probe_data, reconstruction):
    fit = probe_data.get("trajectory_fit") or reconstruction["probe"].get(
        "trajectory_fit"
    ) or {}
    note = ""
    transform = reconstruction["atlas"].get("estimated_stereotaxic_transform")
    if transform is not None:
        note = transform.get("targeting_note", "")
    return {
        "probe_name": probe_name,
        "AP_tilt_deg_from_vertical": probe_data.get("ap_angle", ""),
        "AP_tilt_direction": probe_data.get("ap_tilt", ""),
        "ML_tilt_deg_from_vertical": probe_data.get("ml_angle", ""),
        "ML_tilt_direction": probe_data.get("ml_tilt", ""),
        "trajectory_length_um": probe_data.get("probe_length", ""),
        "vertical_depth_change_um": probe_data.get("dv", ""),
        "fit_method": fit.get("method", ""),
        "surface_method": fit.get("surface_method", ""),
        "fit_points": fit.get("point_count", ""),
        "fit_inliers": fit.get("inlier_count", ""),
        "fit_RMS_error_um": fit.get("rms_error_um", ""),
        "fit_max_error_um": fit.get("max_error_um", ""),
        "fit_explained_fraction": fit.get("explained_fraction", ""),
        "surface_adjustment_um": fit.get("surface_adjustment_um", ""),
        "coordinate_note": note,
    }


def _coordinate_columns(record, source_axes):
    herbs = _vector(record["herbs_vox"], "HERBS coordinate")
    bregma_um = _vector(record["bregma_um"], "Bregma coordinate")
    source = _vector(record["source_vox"], "Source-atlas coordinate")
    row = {
        "herbs_ML_vox": herbs[0],
        "herbs_AP_vox": herbs[1],
        "herbs_DV_dorsal_vox": herbs[2],
        "configured_ML_mm": bregma_um[0] / 1000.0,
        "configured_AP_mm": bregma_um[1] / 1000.0,
        "configured_DV_ventral_mm": -bregma_um[2] / 1000.0,
    }
    for axis in range(3):
        row["source_axis_{}_name".format(axis)] = source_axes[axis]
        row["source_axis_{}_vox".format(axis)] = source[axis]
    if "allen_ccf_vox" in record:
        allen = _vector(record["allen_ccf_vox"], "Allen CCF coordinate")
        estimated = _vector(
            record["estimated_stereotaxic_bregma_mm"],
            "Estimated Bregma coordinate",
        )
        row.update(
            {
                "allen_AP_vox": allen[0],
                "allen_DV_vox": allen[1],
                "allen_ML_vox": allen[2],
                "estimated_AP_mm": estimated[0],
                "estimated_ML_mm": estimated[2],
                "affine_DV_mm_not_for_targeting": estimated[1],
            }
        )
    return row


def _indexed_coordinate_record(coordinates, index):
    record = {}
    for key in (
        "herbs_vox",
        "bregma_um",
        "source_vox",
        "allen_ccf_vox",
        "estimated_stereotaxic_bregma_mm",
    ):
        if key in coordinates:
            record[key] = np.asarray(coordinates[key])[index]
    return record


def iter_probe_csv_rows(probe_name, probe_data):
    """Yield insertion, tip, physical-contact, and region-summary rows."""
    reconstruction = probe_data.get("reconstruction")
    if not isinstance(reconstruction, dict):
        raise ValueError(
            "This legacy probe has no coordinate reconstruction. Re-merge the "
            "probe with the current HERBS version before exporting it."
        )
    coordinates = reconstruction["coordinates"]
    source_axes = reconstruction["atlas"]["source_axes"]
    base = _base_row(probe_name, probe_data, reconstruction)

    for record_type in ("insertion", "tip"):
        row = dict(base)
        row["record_type"] = record_type
        row.update(
            _coordinate_columns(coordinates[record_type], source_axes)
        )
        yield row

    contacts = coordinates["contacts"]
    count = int(contacts["count"])
    structure_ids = np.asarray(contacts["structure_id"], dtype=int)
    structure_acronyms = np.asarray(
        contacts["structure_acronym"], dtype=object
    )
    structure_names = np.asarray(contacts["structure_name"], dtype=object)
    probe_local = np.asarray(contacts["probe_local_um"], dtype=float)
    for index in range(count):
        row = dict(base)
        row.update(
            {
                "record_type": "contact",
                "site_index": int(contacts["site_index"][index]),
                "column_index": int(contacts["column_index"][index]),
                "index_in_column": int(
                    contacts["index_in_column"][index]
                ),
                "distance_from_insertion_um": float(
                    contacts["distance_from_insertion_um"][index]
                ),
                "distance_from_tip_um": float(
                    contacts["distance_from_tip_um"][index]
                ),
                "probe_lateral_um": float(probe_local[index, 1]),
                "probe_surface_normal_um": float(probe_local[index, 2]),
                "structure_id": int(structure_ids[index]),
                "structure_acronym": str(structure_acronyms[index]),
                "structure_name": str(structure_names[index]),
            }
        )
        coordinate = _indexed_coordinate_record(contacts, index)
        row.update(_coordinate_columns(coordinate, source_axes))
        yield row

    region_ids = np.ravel(probe_data.get("region_label", []))
    region_names = np.ravel(probe_data.get("label_name", []))
    region_acronyms = np.ravel(probe_data.get("label_acronym", []))
    region_contacts = np.ravel(probe_data.get("region_sites", []))
    region_lengths = np.ravel(probe_data.get("region_length", []))
    for index, region_id in enumerate(region_ids):
        row = dict(base)
        row.update(
            {
                "record_type": "region_summary",
                "structure_id": int(region_id),
                "structure_name": (
                    str(region_names[index])
                    if index < len(region_names)
                    else ""
                ),
                "structure_acronym": (
                    str(region_acronyms[index])
                    if index < len(region_acronyms)
                    else ""
                ),
                "region_contact_count": (
                    int(round(float(region_contacts[index])))
                    if index < len(region_contacts)
                    else ""
                ),
                "region_path_length_um": (
                    float(region_lengths[index])
                    if index < len(region_lengths)
                    else ""
                ),
            }
        )
        yield row


def write_probe_csv(path, probe_name, probe_data):
    """Write a reconstructed probe and its anatomical assignments to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=PROBE_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(iter_probe_csv_rows(probe_name, probe_data))
