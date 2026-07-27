import numpy as np


def slice_info_is_ready(width, height, distance, bregma):
    """Return whether slice dimensions and spatial registration are usable."""
    try:
        dimensions = np.asarray([width, height], dtype=float)
        distance_value = float(distance)
        origin = np.asarray(bregma, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return False

    return bool(
        dimensions.shape == (2,)
        and np.all(np.isfinite(dimensions))
        and np.all(dimensions > 0)
        and np.isfinite(distance_value)
        and origin.shape == (2,)
        and np.all(np.isfinite(origin))
    )
