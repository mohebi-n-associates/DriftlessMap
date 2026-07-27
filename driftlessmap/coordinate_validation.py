"""Validation helpers for voxel and image coordinates."""

import numpy as np


def coordinates_in_bounds(coordinates, shape):
    """Return whether every coordinate lies inside an array of ``shape``."""
    coordinates = np.asarray(coordinates)
    shape = np.asarray(shape)
    if shape.ndim != 1 or coordinates.ndim == 0:
        return False
    if coordinates.shape[-1] != len(shape):
        return False
    return bool(np.all(coordinates >= 0) and np.all(coordinates < shape))


def coordinate_groups_in_bounds(coordinate_groups, shape):
    """Validate a sequence of coordinate arrays against one array shape."""
    return all(coordinates_in_bounds(group, shape) for group in coordinate_groups)
