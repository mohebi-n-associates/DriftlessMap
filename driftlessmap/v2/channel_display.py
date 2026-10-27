"""Per-channel display range (brightness/contrast) and gamma for ImageView.

These helpers write the same per-channel state that the 1.x curve editor
uses (curve end points, lookup table and gamma), so saving and reopening a
project restores what the V2 channel panel shows. They change display only;
raw samples, registration input and coordinates are never touched.
"""

import numpy as np

from ..utils import gamma_line

# Auto contrast saturates this percentage of samples at each end, as ImageJ's
# "Auto" does (0.35 % in total).
AUTO_SATURATION = 0.35


def channel_count(view):
    image = view.current_img
    if image is None:
        return 0
    return int(np.shape(image)[2]) if np.ndim(image) == 3 else 1


def intensity_limit(view):
    """The largest sample value of the image type (255 or 65535)."""
    return int(view.image_file.level) if view.image_file is not None else 255


def channel_levels(view, index):
    """(black, white, gamma) of one channel in native intensity units."""
    points = view.curve_widget.curve_plot.lut_points[index].data["pos"]
    black, white = float(points[0, 0]), float(points[-1, 0])
    return black, white, float(view.curve_widget.gamma[index])


def set_channel_levels(view, index, black, white, gamma=None):
    """Show ``index`` between ``black`` and ``white`` with ``gamma``.

    Values are clamped to the image's intensity range; white is kept above
    black. The curve editor is switched to its gamma mode first, because a
    display window is defined there by its two end points.
    """
    curve = view.curve_widget
    plot = curve.curve_plot
    if curve.line_type != "gamma":
        curve.line_type_combo.setCurrentText("gamma")
    limit = intensity_limit(view)
    black = float(np.clip(black, 0, limit - 1))
    white = float(np.clip(white, black + 1, limit))
    if gamma is None:
        gamma = curve.gamma[index]
    gamma = float(np.clip(gamma, 0.01, 16.0))
    curve.gamma[index] = gamma
    points = np.array([[black, 0.0], [white, float(plot.depth_level)]])
    plot.set_lut_points(points, index)
    table = gamma_line(plot.table_input, (black, white), gamma, curve.gray_max).astype(int)
    if index < len(curve.table_output):
        curve.table_output[index] = table
    plot.set_lut_line(table, index)
    view.image_curve_changed((table, index))
    if any(plot.enable_channel[: channel_count(view)]):
        curve.set_enable_induced_slider()
    return black, white, gamma


def auto_levels(view, index, saturation=AUTO_SATURATION):
    """Display limits that saturate ``saturation`` percent of the channel."""
    values = np.asarray(view.current_img)[..., index] if np.ndim(view.current_img) == 3 \
        else np.asarray(view.current_img)
    low, high = np.percentile(values, [saturation / 2, 100 - saturation / 2])
    if high <= low:
        low, high = float(values.min()), float(values.max())
    if high <= low:
        high = low + 1
    return float(low), float(high)


def reset_levels(view, index):
    """The full intensity range of the channel's data, with gamma 1."""
    values = np.asarray(view.current_img)[..., index] if np.ndim(view.current_img) == 3 \
        else np.asarray(view.current_img)
    low, high = float(values.min()), float(values.max())
    return low, max(high, low + 1), 1.0


def brightness_contrast(black, white, limit):
    """Brightness and contrast (0-100) for a display window, ImageJ style.

    Brightness is the window centre as a percentage of the intensity range.
    Contrast is 50 for the full range and rises logarithmically to 100 as the
    window narrows to one intensity level; below 50 the window is wider than
    the data range.
    """
    centre = (black + white) / 2.0
    width = max(white - black, 1.0)
    brightness = 100.0 * centre / limit
    contrast = 50.0 + 50.0 * np.log2(limit / width) / np.log2(max(limit, 2))
    return float(np.clip(brightness, 0, 100)), float(np.clip(contrast, 0, 100))


def window_from_brightness_contrast(brightness, contrast, limit):
    """The inverse of :func:`brightness_contrast`."""
    centre = limit * float(brightness) / 100.0
    width = limit / (2.0 ** ((float(contrast) - 50.0) / 50.0 * np.log2(max(limit, 2))))
    width = max(width, 1.0)
    return centre - width / 2.0, centre + width / 2.0
