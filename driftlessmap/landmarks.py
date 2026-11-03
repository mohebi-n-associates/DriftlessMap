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


# Fewest pairs, and the smallest spread of the section landmarks along each
# axis (as a share of the image side), for fitting the frame to them.
FRAME_MIN_PAIRS = 3
FRAME_MIN_SPREAD = 0.05


def fit_frame(atlas_points, histology_points, atlas_shape, histology_shape):
    """Frame rectangles that agree with the landmark pairs.

    The frame's corner and side points pin the section's edges to the atlas;
    pinning image corner to image corner contradicts the landmarks whenever
    the section covers only part of the atlas slice (or more), stretching
    the tissue between the outermost landmarks and the edge. Here each axis
    is fitted as ``atlas = scale * section + offset`` to the pairs, and the
    section frame is the part of the section image that this fit places
    inside the atlas image; the atlas frame is where the fit puts it.

    Returns ``(atlas_rect, histology_rect)`` as (x, y, width, height), or
    None when the pairs are too few, too bunched or flipped to fit.
    """
    atlas = np.asarray(atlas_points, dtype=float).reshape(-1, 2)
    section = np.asarray(histology_points, dtype=float).reshape(-1, 2)
    if len(atlas) != len(section) or len(atlas) < FRAME_MIN_PAIRS:
        return None
    lows, highs = [], []
    for axis, (atlas_side, section_side) in enumerate(
            ((atlas_shape[1], histology_shape[1]), (atlas_shape[0], histology_shape[0]))):
        if np.std(section[:, axis]) < FRAME_MIN_SPREAD * section_side:
            return None
        scale, offset = np.polyfit(section[:, axis], atlas[:, axis], 1)
        if not np.isfinite(scale) or scale <= 0:
            return None
        low = max(0.0, -offset / scale)
        high = min(section_side - 1.0, (atlas_side - 1.0 - offset) / scale)
        if high - low < 0.1 * section_side:
            return None
        lows.append((low, scale * low + offset))
        highs.append((high, scale * high + offset))
    (hx0, ax0), (hy0, ay0) = lows
    (hx1, ax1), (hy1, ay1) = highs

    def rect(x0, y0, x1, y1):
        x0, y0, x1, y1 = (round(float(v), 2) for v in (x0, y0, x1, y1))
        return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)

    return rect(ax0, ay0, ax1, ay1), rect(hx0, hy0, hx1, hy1)


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
