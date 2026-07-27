"""Pure image preparation helpers for cell detection."""

import cv2
import numpy as np


def select_detection_channel(image, is_rgb, channel_visible):
    """Return an 8-bit detection plane and its DriftlessMap cell-layer index."""
    image = np.asarray(image)
    if image.ndim != 3:
        raise ValueError("Cell detection requires a channel-last image.")
    if is_rgb:
        if image.shape[2] < 3:
            raise ValueError("RGB cell detection requires three color channels.")
        plane = cv2.cvtColor(image[..., :3], cv2.COLOR_RGB2GRAY)
        layer_index = 0
    else:
        visible = np.flatnonzero(np.asarray(channel_visible)[: image.shape[2]])
        if len(visible) != 1:
            raise ValueError("Select exactly one image channel for cell detection.")
        channel_index = int(visible[0])
        plane = image[..., channel_index]
        layer_index = channel_index + 1

    if plane.dtype != np.uint8:
        plane = cv2.normalize(plane, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return plane, layer_index
