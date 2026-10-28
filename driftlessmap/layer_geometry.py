"""Pure geometry for shifting and rotating 2D annotation layers."""

import cv2
import numpy as np


def layer_center(onside_points):
    """Return the centre of the bounding box of a frame's boundary points."""
    points = np.asarray(onside_points, dtype=float)
    return tuple((points.min(axis=0) + points.max(axis=0)) / 2.0)


def rotation_matrix(center, angle):
    """Return OpenCV's affine matrix for rotating by ``angle`` degrees."""
    return cv2.getRotationMatrix2D(
        (float(center[0]), float(center[1])), float(angle), 1.0
    )


def rotate_points(points, center, angle):
    """Rotate ``(x, y)`` points exactly as :func:`rotate_raster` rotates pixels."""
    matrix = rotation_matrix(center, angle)
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    return points @ matrix[:, :2].T + matrix[:, 2]


def rotate_raster(image, center, angle):
    height, width = image.shape[:2]
    return cv2.warpAffine(image, rotation_matrix(center, angle), (width, height))


def shift_raster(image, moving_vec):
    """Translate an image by ``(dx, dy)`` pixels, keeping its size."""
    shift_mat = np.float32([[1, 0, moving_vec[0]], [0, 1, moving_vec[1]]])
    height, width = image.shape[:2]
    return cv2.warpAffine(image.copy(), shift_mat, (width, height))


# A click within this many screen pixels of a lasso's first point closes it.
LASSO_CLOSE_PIXELS = 12


def lasso_tolerance(view_box, pixels=LASSO_CLOSE_PIXELS):
    """Return ``pixels`` screen pixels in the data units of ``view_box``."""
    try:
        size = max(abs(value) for value in view_box.viewPixelSize())
    except Exception:
        size = 0.0
    return pixels * size if np.isfinite(size) and size > 0 else float(pixels)


def lasso_closes(path, point, tolerance):
    """Whether a click at ``point`` closes the open lasso ``path``."""
    if len(path) < 3:
        return False
    first = np.asarray(path[0], dtype=float)
    return float(np.hypot(*(np.asarray(point, dtype=float) - first))) <= tolerance


def lasso_point_closes(path, points):
    """Whether clicking the drawn ``points`` of ``path`` closes it.

    Only the first point closes a lasso. Overlapping points are all checked,
    because pyqtgraph lists the points under the cursor last first.
    """
    return len(path) >= 3 and any(point.index() == 0 for point in points)
