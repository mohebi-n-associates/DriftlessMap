"""Registration landmarks: state, topology invalidation and file checks."""

import numpy as np

from .utils import get_corner_line_from_rect, num_side_pnt_changed


LANDMARK_FIELDS = {
    "atlas_corner_points": None,
    "atlas_side_lines": None,
    "atlas_tri_data": list,
    "atlas_tri_inside_data": list,
    "atlas_tri_onside_data": list,
    "histo_corner_points": None,
    "histo_side_lines": None,
    "histo_tri_data": list,
    "histo_tri_inside_data": list,
    "histo_tri_onside_data": list,
    "working_atlas_text": list,
    "working_img_text": list,
    "tri_simplices": None,
    "triangulation_topology_point_count": None,
    "triangulation_registration": None,
}


class LandmarkModel:
    """Owns paired landmarks, their shared topology and their label items.

    The atlas and histology point lists, the triangle topology, the cached
    registration and the on-screen landmark labels live here, so that they
    can be reasoned about (and reset) together.
    """

    def __init__(self):
        for name, factory in LANDMARK_FIELDS.items():
            setattr(self, name, factory() if factory else None)
        self.registration_cache_key = None

    def invalidate(self, clear_topology=False):
        """Forget the built registration and, optionally, its topology."""
        self.triangulation_registration = None
        self.registration_cache_key = None
        if clear_topology:
            self.tri_simplices = None
            self.triangulation_topology_point_count = None

    def cache_key(self, atlas_shape, histology_shape, simplices):
        """Identify the inputs a registration was built from."""
        return (
            np.asarray(self.atlas_tri_data, dtype=float).tobytes(),
            np.asarray(self.histo_tri_data, dtype=float).tobytes(),
            tuple(np.ravel(atlas_shape)),
            tuple(np.ravel(histology_shape)),
            None if simplices is None else np.asarray(simplices).tobytes(),
        )


def triangulation_payload_error(tri_data, view_sizes, np_onside):
    """Return why a triangulation payload cannot be applied, or ``None``.

    ``view_sizes`` maps each atlas view name to its ``(height, width)`` slice
    size and ``np_onside`` is the current boundary-point setting.
    """
    required = (
        "atlas_corner_points",
        "atlas_side_lines",
        "atlas_tri_data",
        "atlas_tri_inside_data",
        "atlas_tri_onside_data",
        "atlas_display",
    )
    if not isinstance(tri_data, dict) or any(key not in tri_data for key in required):
        return "the file is not a triangulation points file."
    if tri_data["atlas_display"] not in ("coronal", "sagittal", "horizontal"):
        return "unknown atlas view {!r}.".format(tri_data["atlas_display"])
    point_sets = {}
    for key in ("atlas_corner_points", "atlas_tri_inside_data", "atlas_tri_onside_data"):
        try:
            points = np.asarray(tri_data[key], dtype=float).reshape(-1, 2)
        except (TypeError, ValueError):
            return "{} does not contain 2D points.".format(key)
        if not np.all(np.isfinite(points)):
            return "{} contains invalid coordinates.".format(key)
        point_sets[key] = points
    view_size = view_sizes[tri_data["atlas_display"]]
    view_corners, view_side_lines = get_corner_line_from_rect(
        (0, 0, int(view_size[1]), int(view_size[0]))
    )
    expected_corners = np.asarray(view_corners, dtype=float)
    if point_sets["atlas_corner_points"].shape != expected_corners.shape or not np.allclose(
        point_sets["atlas_corner_points"], expected_corners
    ):
        return (
            "it was saved for an atlas slice of a different size. Load the "
            "atlas used when the points were saved."
        )
    expected_onside = len(
        num_side_pnt_changed(np_onside, view_corners, view_side_lines)
    )
    if len(point_sets["atlas_tri_onside_data"]) != expected_onside:
        return (
            "it has {} boundary points but the current boundary-point "
            "setting produces {}. Use the same number of points per side "
            "as when the file was saved.".format(
                len(point_sets["atlas_tri_onside_data"]), expected_onside
            )
        )
    simplices = tri_data.get("tri_simplices")
    if simplices is not None:
        n_points = len(point_sets["atlas_tri_onside_data"]) + len(
            point_sets["atlas_tri_inside_data"]
        )
        try:
            simplices = np.asarray(simplices, dtype=np.int64)
        except (TypeError, ValueError):
            return "the triangle topology is not an integer array."
        if simplices.size and (
            simplices.ndim != 2
            or simplices.shape[1] != 3
            or simplices.min() < 0
            or simplices.max() >= n_points
        ):
            return "the triangle topology references missing points."
    return None
