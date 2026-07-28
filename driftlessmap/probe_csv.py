"""CSV exports for probe contacts, labeled track, trajectory, and regions."""

import csv
from pathlib import Path

import numpy as np


REGION_CSV_FIELDS = (
    "probe_name",
    "structure_id",
    "structure_acronym",
    "structure_name",
    "contact_count",
    "path_length_um",
)


def _reconstruction(probe_data):
    reconstruction = probe_data.get("reconstruction")
    if not isinstance(reconstruction, dict):
        raise ValueError(
            "This legacy probe has no coordinate reconstruction. Re-merge the "
            "probe with the current DriftlessMap version before exporting it."
        )
    return reconstruction


def _vector(values, name):
    values = np.asarray(values, dtype=float)
    if values.shape != (3,):
        raise ValueError("{} must contain three coordinates.".format(name))
    return values


def _coordinate_columns(record, source_axes):
    herbs = _vector(record["herbs_vox"], "HERBS coordinate")
    bregma_um = _vector(record["bregma_um"], "Bregma coordinate")
    source = _vector(record["source_vox"], "Source-atlas coordinate")
    row = {
        "herbs_ML_vox": float(herbs[0]),
        "herbs_AP_vox": float(herbs[1]),
        "herbs_DV_dorsal_vox": float(herbs[2]),
        "configured_ML_mm": float(bregma_um[0] / 1000.0),
        "configured_AP_mm": float(bregma_um[1] / 1000.0),
        "configured_DV_ventral_mm": float(-bregma_um[2] / 1000.0),
    }
    for axis in range(3):
        row["source_axis_{}_name".format(axis)] = source_axes[axis]
        row["source_axis_{}_vox".format(axis)] = float(source[axis])
    if "allen_ccf_vox" in record:
        allen = _vector(record["allen_ccf_vox"], "Allen CCF coordinate")
        estimated = _vector(
            record["estimated_stereotaxic_bregma_mm"],
            "Estimated Bregma coordinate",
        )
        row.update(
            {
                "allen_AP_vox": float(allen[0]),
                "allen_DV_vox": float(allen[1]),
                "allen_ML_vox": float(allen[2]),
                "estimated_AP_mm": float(estimated[0]),
                "estimated_ML_mm": float(estimated[2]),
                "affine_DV_mm_not_for_targeting": float(estimated[1]),
            }
        )
    return row


def _prefixed_coordinate_columns(record, source_axes, prefix):
    return {
        "{}_{}".format(prefix, key): value
        for key, value in _coordinate_columns(record, source_axes).items()
    }


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


def _contact_distances(contacts):
    distance_from_tip = np.asarray(
        contacts.get(
            "axial_distance_up_from_tip_um",
            contacts["distance_from_tip_um"],
        ),
        dtype=float,
    )
    depth_from_insertion = np.asarray(
        contacts.get(
            "axial_depth_from_insertion_um",
            contacts["distance_from_insertion_um"],
        ),
        dtype=float,
    )
    return distance_from_tip, depth_from_insertion


def iter_probe_contact_rows(probe_name, probe_data):
    """Yield physical contacts ordered from deepest to shallowest."""
    reconstruction = _reconstruction(probe_data)
    contacts = reconstruction["coordinates"]["contacts"]
    source_axes = reconstruction["atlas"]["source_axes"]
    count = int(contacts["count"])
    site_indexes = np.asarray(contacts["site_index"], dtype=int)
    column_indexes = np.asarray(contacts["column_index"], dtype=int)
    indexes_in_column = np.asarray(contacts["index_in_column"], dtype=int)
    distance_from_tip, depth_from_insertion = _contact_distances(contacts)
    probe_local = np.asarray(contacts["probe_local_um"], dtype=float)
    structure_ids = np.asarray(contacts["structure_id"], dtype=int)
    structure_acronyms = np.asarray(
        contacts["structure_acronym"], dtype=object
    )
    structure_names = np.asarray(contacts["structure_name"], dtype=object)

    depth_order = np.lexsort(
        (
            site_indexes,
            indexes_in_column,
            column_indexes,
            distance_from_tip,
        )
    )
    for depth_rank, index in enumerate(depth_order):
        row = {
            "probe_name": probe_name,
            "depth_rank_deepest_first": int(depth_rank),
            "site_index": int(site_indexes[index]),
            "column_index": int(column_indexes[index]),
            "index_in_column": int(indexes_in_column[index]),
            "axial_distance_up_from_tip_um": float(
                distance_from_tip[index]
            ),
            "axial_depth_from_insertion_um": float(
                depth_from_insertion[index]
            ),
            "probe_lateral_um": float(probe_local[index, 1]),
            "probe_surface_normal_um": float(probe_local[index, 2]),
        }
        coordinate = _indexed_coordinate_record(contacts, index)
        row.update(_coordinate_columns(coordinate, source_axes))
        row.update(
            {
                "structure_id": int(structure_ids[index]),
                "structure_acronym": str(structure_acronyms[index]),
                "structure_name": str(structure_names[index]),
            }
        )
        yield row


def iter_probe_track_rows(probe_name, probe_data):
    """Yield labeled centerline samples ordered from insertion to tip."""
    reconstruction = _reconstruction(probe_data)
    coordinates = reconstruction["coordinates"]
    if "track" not in coordinates:
        raise ValueError(
            "This probe has no labeled centerline. Re-merge the probe with the "
            "current DriftlessMap version before exporting it."
        )
    track = coordinates["track"]
    source_axes = reconstruction["atlas"]["source_axes"]
    count = int(track["count"])
    sample_indexes = np.asarray(track["sample_index"], dtype=int)
    depth_from_insertion = np.asarray(
        track["axial_depth_from_insertion_um"], dtype=float
    )
    distance_from_tip = np.asarray(
        track["axial_distance_up_from_tip_um"], dtype=float
    )
    structure_ids = np.asarray(track["structure_id"], dtype=int)
    structure_acronyms = np.asarray(
        track["structure_acronym"], dtype=object
    )
    structure_names = np.asarray(track["structure_name"], dtype=object)

    for index in range(count):
        coordinate = _indexed_coordinate_record(track, index)
        row = {
            "probe_name": probe_name,
            "track_sample_index": int(sample_indexes[index]),
            "axial_depth_from_insertion_um": float(
                depth_from_insertion[index]
            ),
            "axial_distance_up_from_tip_um": float(
                distance_from_tip[index]
            ),
        }
        row.update(_coordinate_columns(coordinate, source_axes))
        row.update(
            {
                "structure_id": int(structure_ids[index]),
                "structure_acronym": str(structure_acronyms[index]),
                "structure_name": str(structure_names[index]),
            }
        )
        yield row


def probe_trajectory_row(probe_name, probe_data):
    """Return one complete trajectory-summary row."""
    reconstruction = _reconstruction(probe_data)
    atlas = reconstruction["atlas"]
    probe = reconstruction["probe"]
    coordinates = reconstruction["coordinates"]
    source_axes = atlas["source_axes"]
    settings = probe.get("settings") or {}
    software = reconstruction.get("software") or {}
    contacts = coordinates["contacts"]
    track = coordinates.get("track") or {}
    row = {
        "probe_name": probe_name,
        "reconstruction_schema_version": int(reconstruction["schema_version"]),
        "software_name": software.get("name", "DriftlessMap"),
        "software_version": software.get("version") or "unknown",
        "probe_type": settings.get(
            "probe_type_name", probe_data.get("probe_type_name", "unspecified")
        ),
        "atlas_name": atlas.get("source_name") or "Source atlas",
        "atlas_voxel_size_um": float(atlas["voxel_size_um"]),
        "contact_ordering": probe.get(
            "contact_ordering", "column-major"
        ),
        "AP_tilt_deg_from_vertical": float(probe_data["ap_angle"]),
        "AP_tilt_direction": probe_data.get("ap_tilt", "unspecified"),
        "ML_tilt_deg_from_vertical": float(probe_data["ml_angle"]),
        "ML_tilt_direction": probe_data.get("ml_tilt", "unspecified"),
        "insertion_to_tip_length_um": float(probe_data["probe_length"]),
        "vertical_depth_change_um": float(probe_data["dv"]),
        "tip_to_lowest_contact_center_um": float(
            np.min(contacts["axial_distance_up_from_tip_um"])
        ),
    }
    if track:
        row["track_sampling_interval_um"] = float(
            track["sampling_interval_um"]
        )
    if atlas.get("source_version"):
        row["atlas_version"] = atlas["source_version"]
    if atlas.get("identifier"):
        row["atlas_identifier"] = atlas["identifier"]
    if probe.get("site_face") is not None:
        row["site_face"] = probe["site_face"]

    fit = probe_data.get("trajectory_fit") or probe.get("trajectory_fit")
    if fit:
        row.update(
            {
                "fit_method": fit["method"],
                "surface_method": fit["surface_method"],
                "fit_points": int(fit["point_count"]),
                "fit_inliers": int(fit["inlier_count"]),
                "fit_RMS_error_um": float(fit["rms_error_um"]),
                "fit_max_error_um": float(fit["max_error_um"]),
                "fit_explained_fraction": float(
                    fit["explained_fraction"]
                ),
                "surface_adjustment_um": float(
                    fit["surface_adjustment_um"]
                ),
            }
        )

    row.update(
        _prefixed_coordinate_columns(
            coordinates["insertion"], source_axes, "insertion"
        )
    )
    row.update(
        _prefixed_coordinate_columns(
            coordinates["tip"], source_axes, "tip"
        )
    )
    transform = atlas.get("estimated_stereotaxic_transform")
    if transform is not None:
        row["coordinate_note"] = transform["targeting_note"]
    return row


def iter_probe_region_rows(probe_name, probe_data):
    """Yield one compact row for each traversed anatomical region."""
    _reconstruction(probe_data)
    region_ids = np.ravel(probe_data.get("region_label", []))
    region_names = np.ravel(probe_data.get("label_name", []))
    region_acronyms = np.ravel(probe_data.get("label_acronym", []))
    region_contacts = np.ravel(probe_data.get("region_sites", []))
    region_lengths = np.ravel(probe_data.get("region_length", []))
    for index, region_id in enumerate(region_ids):
        yield {
            "probe_name": probe_name,
            "structure_id": int(region_id),
            "structure_acronym": (
                str(region_acronyms[index])
                if index < len(region_acronyms)
                else ""
            ),
            "structure_name": (
                str(region_names[index])
                if index < len(region_names)
                else ""
            ),
            "contact_count": (
                int(round(float(region_contacts[index])))
                if index < len(region_contacts)
                else 0
            ),
            "path_length_um": (
                float(region_lengths[index])
                if index < len(region_lengths)
                else 0.0
            ),
        }


def iter_probe_csv_rows(probe_name, probe_data):
    """Yield contact-only rows for compatibility with the original exporter."""
    yield from iter_probe_contact_rows(probe_name, probe_data)


def _write_rows(path, rows, fallback_fields):
    rows = list(rows)
    fieldnames = list(rows[0]) if rows else list(fallback_fields)
    with open(path, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_probe_csv(path, probe_name, probe_data):
    """Write only the depth-sorted physical-contact table to ``path``."""
    rows = list(iter_probe_contact_rows(probe_name, probe_data))
    fallback_fields = (
        "probe_name",
        "depth_rank_deepest_first",
        "site_index",
        "column_index",
        "index_in_column",
        "axial_distance_up_from_tip_um",
        "axial_depth_from_insertion_um",
    )
    _write_rows(path, rows, fallback_fields)


def _export_paths(path):
    path = Path(path)
    base_name = path.stem if path.suffix else path.name
    for suffix in ("_contacts", "_track", "_trajectory", "_regions"):
        if base_name.endswith(suffix):
            base_name = base_name[: -len(suffix)]
            break
    parent = path.parent
    return {
        "contacts": parent / "{}_contacts.csv".format(base_name),
        "track": parent / "{}_track.csv".format(base_name),
        "trajectory": parent / "{}_trajectory.csv".format(base_name),
        "regions": parent / "{}_regions.csv".format(base_name),
    }


def write_probe_csv_files(path, probe_name, probe_data):
    """Write contacts, labeled track, trajectory, and region CSV files."""
    paths = _export_paths(path)
    write_probe_csv(paths["contacts"], probe_name, probe_data)
    _write_rows(
        paths["track"],
        iter_probe_track_rows(probe_name, probe_data),
        (
            "probe_name",
            "track_sample_index",
            "axial_depth_from_insertion_um",
            "axial_distance_up_from_tip_um",
            "structure_id",
            "structure_acronym",
            "structure_name",
        ),
    )
    trajectory = probe_trajectory_row(probe_name, probe_data)
    _write_rows(paths["trajectory"], [trajectory], tuple(trajectory))
    _write_rows(
        paths["regions"],
        iter_probe_region_rows(probe_name, probe_data),
        REGION_CSV_FIELDS,
    )
    return paths
