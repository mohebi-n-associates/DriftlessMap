"""Validation helpers for persisted DriftlessMap layer data."""

import numpy as np


def image_layer_matches(
    layer_dict, image_shape, *, expected_level=None, require_metadata=False
):
    """Return whether a persisted pixel layer matches the current image."""
    required = {"data"}
    if require_metadata:
        required.update({"level", "size"})
    if not isinstance(layer_dict, dict) or not required.issubset(layer_dict):
        return False

    data = np.asarray(layer_dict["data"])
    if data.ndim < 2 or tuple(data.shape[:2]) != tuple(image_shape):
        return False

    if require_metadata:
        if tuple(np.ravel(layer_dict["size"])) != tuple(image_shape):
            return False
        if layer_dict["level"] != expected_level:
            return False
    return True
