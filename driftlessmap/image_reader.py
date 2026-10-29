"""Readers that normalize supported image files for :class:`ImageView`."""

import colorsys
import re
from pathlib import Path

import cv2
import numpy as np
import tifffile


# Channels per image. The display, curves and saved state are sized to this;
# images with more channels are refused with a clear error, never truncated.
MAX_CHANNELS = 16
RGB_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
# The first four colours and names are those of DriftlessMap 1.x.
CHANNEL_COLORS = [
    (128, 128, 128), (255, 0, 0), (0, 255, 0), (0, 0, 255),
    (255, 0, 255), (0, 255, 255), (255, 255, 0), (255, 128, 0),
    (128, 0, 255), (0, 255, 128), (255, 0, 128), (128, 255, 0),
    (0, 128, 255), (255, 128, 128), (128, 255, 255), (255, 255, 128),
]
CHANNEL_NAMES = ["Gray", "Red", "Green", "Blue"] + [
    "Channel {}".format(i + 1) for i in range(4, MAX_CHANNELS)
]
# Display colours for common fluorophore and stain names, used only when a
# file names its channels without giving their colours. Checked in order; the
# first match wins.
NAMED_CHANNEL_COLORS = (
    (("dapi", "hoechst", "draq", "405"), (0, 90, 255)),
    (("cy5", "647", "far red", "far-red", "alexa 680", "nir"), (255, 0, 255)),
    (("gfp", "yfp", "fitc", "488", "alexa 488", "venus", "citrine", "gcamp"), (0, 255, 0)),
    (("rfp", "tdtomato", "tomato", "mcherry", "cy3", "tritc", "dsred", "555", "561",
      "568", "594", "texas red"), (255, 0, 0)),
    (("brightfield", "bright field", "transmitted", "dic", "nissl"), (200, 200, 200)),
)


def _name_matches(key, text, tokens):
    if " " in key or "-" in key:
        return " {} ".format(key.replace("-", " ")) in text
    for token in tokens:
        # Whole words, plus one-letter prefixes (EGFP, mCherry) and dye
        # prefixes on wavelengths (AF488).
        if token == key or (token.endswith(key) and (key.isdigit() or len(token) - len(key) <= 1)):
            return True
        # Variants such as GCaMP6s.
        if key.isalpha() and len(key) >= 4 and token.startswith(key):
            return True
    return False


def named_channel_color(name):
    """The conventional display colour for a channel name, or None."""
    text = " {} ".format(re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip())
    tokens = text.split()
    for keys, rgb in NAMED_CHANNEL_COLORS:
        if any(_name_matches(key, text, tokens) for key in keys):
            return rgb
    return None


def default_channel_colors(names, n_channels):
    """Display colours for channels without stored colours.

    Recognised names (DAPI, GFP, tdTomato, Cy5, ...) get their conventional
    colour, each colour used once; other channels keep the positional default.
    """
    names = list(names or [])
    colours, used = [], set()
    for index in range(n_channels):
        rgb = named_channel_color(names[index]) if index < len(names) else None
        if rgb is None or rgb in used:
            rgb = CHANNEL_COLORS[index % len(CHANNEL_COLORS)]
        else:
            used.add(rgb)
        colours.append(rgb)
    return colours


HISTOLOGY_IMAGE_FILTERS = (
    "TIFF (*.tif *.tiff)",
    "CZI (*.czi)",
    "JPEG (*.jpg *.jpeg)",
    "PNG (*.png)",
    "BMP (*.bmp)",
)
HISTOLOGY_IMAGE_FILTER = ";;".join(HISTOLOGY_IMAGE_FILTERS)


def _hsv_colors(rgb_colors):
    result = []
    for red, green, blue in rgb_colors:
        hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
        result.append((hue, saturation, value / 255))
    return result


def read_bitmap(path, flags=cv2.IMREAD_COLOR):
    """Decode an image file with OpenCV, including non-ASCII paths.

    ``cv2.imread`` cannot open paths outside the system code page on Windows,
    so the bytes are read with NumPy and decoded in memory. Returns ``None``
    when the file is unreadable or not an image.
    """
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if buffer.size == 0:
        return None
    return cv2.imdecode(buffer, flags)


def _set_channel_metadata(reader, rgb_colors, channel_names):
    reader.rgb_colors = list(rgb_colors)
    reader.channel_name = list(channel_names)
    reader.hsv_colors = _hsv_colors(reader.rgb_colors)
    reader.gamma_val = []


class ImageReader(object):
    """Read a conventional bitmap as an eight-bit RGB image."""

    def __init__(self, image_file_path):
        self.error_index = 0
        self.is_czi = False
        self.file_name_list = [str(Path(image_file_path).with_suffix(""))]
        self.n_scenes = 1
        self.n_pages = 1
        self.scaling_val = None
        self.is_rgb = True
        self.pixel_type = "rgb24"
        self.level = 255
        self.n_channels = 3
        self.data_type = "uint8"
        _set_channel_metadata(self, RGB_COLORS, ["Red", "Green", "Blue"])

        image = read_bitmap(image_file_path, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("OpenCV could not decode the selected image.")
        self.data = {"scene 0": cv2.cvtColor(image, cv2.COLOR_BGR2RGB)}
        self.scale = {"scene 0": 1.0}


class EmbeddedImageReader(object):
    """Recreate the active histology raster when its source is unavailable.

    An embedded reader intentionally exposes one scene and one page.  The
    original scene/page indices remain in project provenance, while the saved
    active raster remains usable without pretending that unsaved source scenes
    are available.
    """

    def __init__(self, image, metadata=None):
        metadata = metadata or {}
        image = np.asarray(image)
        if image.ndim == 2:
            image = image[..., None]
        if image.ndim != 3 or image.shape[2] > MAX_CHANNELS:
            raise ValueError("Embedded histology must be an H x W x C image.")

        self.error_index = 0
        self.is_czi = False
        self.file_name_list = [metadata.get("display_name", "embedded-histology")]
        self.n_scenes = 1
        self.n_pages = 1
        self.scaling_val = metadata.get("scaling_val")
        self.is_rgb = bool(metadata.get("is_rgb", image.shape[2] in (3, 4)))
        self.n_channels = int(metadata.get("n_channels", image.shape[2]))
        if self.n_channels != image.shape[2]:
            self.n_channels = image.shape[2]
        self.data_type = metadata.get("data_type", image.dtype.name)
        default_level = int(np.iinfo(image.dtype).max) if image.dtype.kind == "u" else 255
        self.level = int(metadata.get("level", default_level))
        self.pixel_type = metadata.get(
            "pixel_type", "rgb24" if self.is_rgb else "gray{}".format(image.dtype.itemsize * 8)
        )

        if self.is_rgb:
            default_colors = RGB_COLORS[: self.n_channels]
            default_names = ["Red", "Green", "Blue"][: self.n_channels]
        else:
            default_colors = CHANNEL_COLORS[: self.n_channels]
            default_names = CHANNEL_NAMES[: self.n_channels]
        self.rgb_colors = [tuple(item) for item in metadata.get("rgb_colors", default_colors)]
        self.channel_name = list(metadata.get("channel_name", default_names))
        self.hsv_colors = [tuple(item) for item in metadata.get("hsv_colors", _hsv_colors(self.rgb_colors))]
        self.gamma_val = list(metadata.get("gamma_val", []))
        self.data = {"scene 0": image.copy()}
        try:
            image_scale = float(metadata.get("image_scale", 1.0))
        except (TypeError, ValueError):
            image_scale = 1.0
        if not np.isfinite(image_scale) or image_scale <= 0:
            image_scale = 1.0
        self.scale = {"scene 0": image_scale}


TIFF_ERRORS = {
    1: "The TIFF's series do not share one bit depth and channel layout, so "
       "they cannot be shown as scenes of one image.",
    2: "Only unsigned 8- and 16-bit TIFF data is supported.",
    7: "This TIFF's axis layout is not supported.",
    8: "The TIFF has more than {} channels.".format(MAX_CHANNELS),
    9: "A chosen plane is outside this TIFF's axis range.",
}
# Axes browsed as pages, in order of preference; other extra axes are fixed.
PAGE_AXES = ("Z", "T", "I", "Q", "R", "H", "E", "A", "V", "L", "P", "M")


def level_scales(series):
    """Scale of each pyramid level of a tifffile series relative to level 0."""
    levels = getattr(series, "levels", None) or [series]
    axes = series.axes
    if "X" not in axes:
        return [1.0]
    width = series.shape[axes.index("X")]
    return [level.shape[level.axes.index("X")] / float(width) for level in levels]


def choose_level(scales, scale):
    """The coarsest level that still has at least ``scale`` resolution."""
    if scale is None:
        return 0
    candidates = [index for index, value in enumerate(scales) if value >= scale - 1e-6]
    return candidates[-1] if candidates else 0


def plane_selection(value):
    """Validate a chosen plane per fixed TIFF axis, e.g. ``{"T": 3}``.

    Anything malformed becomes ``{}`` (the first plane of every axis, as in
    files saved before the choice existed).
    """
    if not isinstance(value, dict):
        return {}
    selection = {}
    for axis, index in value.items():
        if not (isinstance(axis, str) and len(axis) == 1 and axis.isalpha()
                and axis not in "YXCS"):
            return {}
        if isinstance(index, bool) or not isinstance(index, (int, np.integer)) or index < 0:
            return {}
        selection[axis] = int(index)
    return selection


# Pixel sizes (um) outside this range are taken as not recorded.
PIXEL_SIZE_RANGE_UM = (0.01, 1000.0)
_LENGTH_UNITS_UM = {"nm": 1e-3, "nanometer": 1e-3, "um": 1.0, "\u00b5m": 1.0,
                    "\u03bcm": 1.0, "micron": 1.0, "microns": 1.0, "micrometer": 1.0,
                    "\\u00b5m": 1.0, "mm": 1e3, "millimeter": 1e3, "cm": 1e4,
                    "centimeter": 1e4}


def valid_pixel_size(value):
    """``value`` as a pixel size in um, or None when unusable."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    low, high = PIXEL_SIZE_RANGE_UM
    return value if np.isfinite(value) and low <= value <= high else None


def tiff_pixel_size_um(tiff_file):
    """Pixel width in um recorded in a TIFF, or None.

    OME-XML ``PhysicalSizeX`` is read first, then ImageJ's resolution with its
    ``unit``, then resolution tags in centimetres. Resolution in inches is
    trusted only when finer than 20 um, since editors write 72-600 dpi by
    default; a resolution without a unit is ignored.
    """
    size = _ome_pixel_size(tiff_file.ome_metadata)
    if size is not None:
        return size
    if not tiff_file.pages:
        return None
    tags = tiff_file.pages[0].tags
    resolution = tags.get("XResolution")
    try:
        numerator, denominator = resolution.value
        per_unit = numerator / denominator
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None
    if not per_unit > 0:
        return None
    unit = tags.get("ResolutionUnit")
    unit = int(unit.value) if unit is not None else 2
    if tiff_file.is_imagej:
        name = str((tiff_file.imagej_metadata or {}).get("unit", "")).strip().lower()
        if name in _LENGTH_UNITS_UM:
            return valid_pixel_size(_LENGTH_UNITS_UM[name] / per_unit)
    if unit == 3:  # centimetre
        return valid_pixel_size(1e4 / per_unit)
    if unit == 2:  # inch
        size = valid_pixel_size(25400.0 / per_unit)
        return size if size is not None and size < 20.0 else None
    return None


def _ome_pixel_size(xml):
    if not xml:
        return None
    try:
        import xml.etree.ElementTree as ElementTree
        root = ElementTree.fromstring(xml)
    except Exception:
        return None
    pixels = next((element for element in root.iter() if element.tag.endswith("Pixels")), None)
    if pixels is None or pixels.get("PhysicalSizeX") is None:
        return None
    unit = pixels.get("PhysicalSizeXUnit", "\u00b5m").strip().lower()
    if unit not in _LENGTH_UNITS_UM:
        return None
    try:
        return valid_pixel_size(float(pixels.get("PhysicalSizeX")) * _LENGTH_UNITS_UM[unit])
    except ValueError:
        return None


def _ome_channels(tiff_file, n_channels):
    """Channel names and RGB colours from OME-XML, or ``(None, None)``."""
    xml = tiff_file.ome_metadata
    if not xml:
        return None, None
    try:
        import xml.etree.ElementTree as ElementTree
        root = ElementTree.fromstring(xml)
    except Exception:
        return None, None
    pixels = [element for element in root.iter() if element.tag.endswith("Pixels")]
    if not pixels:
        return None, None
    channels = [element for element in pixels[0] if element.tag.endswith("Channel")]
    if len(channels) != n_channels:
        return None, None
    names, colours = [], []
    for index, channel in enumerate(channels):
        names.append(channel.get("Name") or "Channel {}".format(index + 1))
        colour = channel.get("Color")
        if colour is None:
            colours.append(None)
            continue
        value = int(colour) & 0xFFFFFFFF  # signed 32-bit RGBA
        colours.append(((value >> 24) & 255, (value >> 16) & 255, (value >> 8) & 255))
    return names, colours


def _imagej_channels(tiff_file, n_channels):
    """Channel names and LUT colours from ImageJ metadata, or ``(None, None)``."""
    metadata = tiff_file.imagej_metadata or {}
    names = None
    labels = metadata.get("Labels")
    if isinstance(labels, (list, tuple)) and len(labels) == n_channels:
        names = [str(label) or "Channel {}".format(i + 1) for i, label in enumerate(labels)]
    colours = None
    luts = metadata.get("LUTs")
    if isinstance(luts, (list, tuple)) and len(luts) == n_channels:
        colours = []
        for lut in luts:
            lut = np.asarray(lut)
            colours.append(tuple(int(v) for v in lut[:, -1]) if lut.shape[:1] == (3,) else None)
    return names, colours


class TIFFReader(object):
    """Read grayscale, RGB, channel, page-stack and hyperstack TIFF data.

    Samples keep their native dtype. A channel axis (C) becomes the channel
    dimension; one further axis (Z preferred, then T and others) is browsed as
    pages; any remaining extra axes are fixed at the plane chosen in
    ``planes`` (default 0), recorded in :attr:`fixed_axes` with their sizes
    in :attr:`fixed_axis_sizes`, and reported in :attr:`notes`. Pyramidal
    single-plane files can be read at a lower level (:attr:`has_levels`,
    :meth:`read_data` with ``scale``); :attr:`scale` records the level read. Several series become scenes, read when first shown, and
    must share one bit depth and channel layout. Channel names and colours
    come from OME or ImageJ metadata when present.
    """

    def __init__(self, image_file_path, planes=None):
        self.error_index = 0
        self.error_message = None
        self.is_czi = False
        self.planes = plane_selection(planes)
        self.path = str(image_file_path)
        self.file_name_list = [str(Path(image_file_path).with_suffix(""))]
        self.n_scenes = 0
        self.n_pages = 1
        self.scaling_val = None
        self.software = None
        self.is_imagej = False
        self.is_rgb = False
        self.pixel_type = None
        self.level = None
        self.n_channels = 0
        self.data_type = None
        self.data = {}
        self.scale = {}
        self.notes = []
        self.axes = None
        self.page_axis = None
        self.fixed_axes = {}
        self.fixed_axis_sizes = {}
        self.level_scales = [1.0]
        self.has_levels = False
        _set_channel_metadata(self, [], [])

        with tifffile.TiffFile(image_file_path) as tiff_file:
            self.n_scenes = len(tiff_file.series)
            self.is_imagej = tiff_file.is_imagej
            if tiff_file.pages:
                self.software = tiff_file.pages[0].software
            self.scaling_val = tiff_pixel_size_um(tiff_file)
            if self.n_scenes == 0:
                self._fail(7)
                return
            series = tiff_file.series[0]
            image = np.asarray(series.asarray())
            axes = series.axes
            layout = self._interpret(image, axes)
            if layout is None:
                return
            self.level_scales = level_scales(series)
            # Lower levels of paged stacks are not offered: pages and levels
            # would have to be browsed together.
            self.has_levels = len(self.level_scales) > 1 and self.n_pages == 1
            for other in tiff_file.series[1:]:
                other_layout = self._layout_of(other.dtype, other.axes, other.shape)
                if other_layout != self._layout_key:
                    self._fail(1)
                    return
            names, colours = _ome_channels(tiff_file, self.n_channels)
            if names is None and self.is_imagej:
                names, colours = _imagej_channels(tiff_file, self.n_channels)
        if self.n_scenes > 1:
            self.file_name_list = [
                "{} (series {})".format(self.file_name_list[0], i + 1)
                for i in range(self.n_scenes)
            ]
        if not self.is_rgb:
            default_names = CHANNEL_NAMES[: self.n_channels]
            default_colours = default_channel_colors(names, self.n_channels)
            colours = [c if c is not None else default_colours[i]
                       for i, c in enumerate(colours or default_colours)]
            _set_channel_metadata(self, colours, names or default_names)
        self.data["scene 0"] = layout
        self.scale["scene 0"] = 1.0

    def _fail(self, index):
        self.error_index = index
        self.error_message = TIFF_ERRORS.get(index)
        return None

    def _layout_of(self, dtype, axes, shape):
        """The part of a series' layout that must match across scenes."""
        sizes = dict(zip(axes, shape))
        channels = sizes.get("C", 1) * (sizes.get("S", 1) if sizes.get("S", 1) not in (3, 4) else 1)
        rgb = sizes.get("S", 1) in (3, 4) and "C" not in sizes
        return (np.dtype(dtype).name, rgb, channels)

    def _interpret(self, image, axes):
        if image.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
            return self._fail(2)
        self.data_type = image.dtype.name
        self.level = int(np.iinfo(image.dtype).max)
        bit_depth = image.dtype.itemsize * 8
        self.axes = axes
        self._layout_key = self._layout_of(image.dtype, axes, image.shape)
        if "Y" not in axes or "X" not in axes or len(axes) != image.ndim:
            return self._fail(7)

        # Drop singleton axes other than Y and X.
        keep = [i for i, axis in enumerate(axes) if image.shape[i] > 1 or axis in "YX"]
        image = image.reshape([image.shape[i] for i in keep])
        axes = "".join(axes[i] for i in keep)

        if "S" in axes:
            size = image.shape[axes.index("S")]
            if "C" in axes or size not in (3, 4):
                return self._fail(7)
            image = np.moveaxis(image, axes.index("S"), -1)
            axes = axes.replace("S", "") + "S"
            if size == 4:
                image = image[..., :3]
                self.notes.append("The alpha channel of this RGBA TIFF is not shown.")
            self.is_rgb = True
            self.pixel_type = "rgb{}".format(bit_depth * 3)
            self.n_channels = 3
            _set_channel_metadata(self, RGB_COLORS, ["Red", "Green", "Blue"])
        elif "C" in axes:
            image = np.moveaxis(image, axes.index("C"), -1)
            axes = axes.replace("C", "") + "C"
            self.is_rgb = False
            self.pixel_type = "gray{}".format(bit_depth)
            self.n_channels = image.shape[-1]
        else:
            self.is_rgb = False
            self.pixel_type = "gray{}".format(bit_depth)
            self.n_channels = 1

        if self.n_channels > MAX_CHANNELS:
            return self._fail(8)

        extra = [axis for axis in axes if axis not in "YXCS"]
        page_axis = next((axis for axis in PAGE_AXES if axis in extra), extra[0] if extra else None)
        for axis in extra:
            if axis == page_axis:
                continue
            size = image.shape[axes.index(axis)]
            index = self.planes.get(axis, 0)
            if index >= size:
                return self._fail(9)
            image = np.take(image, index, axis=axes.index(axis))
            axes = axes.replace(axis, "")
            self.fixed_axes[axis] = index
            self.fixed_axis_sizes[axis] = size
            self.notes.append(
                "{} plane {} of {} is shown.".format(axis, index + 1, size))
        if page_axis is not None:
            image = np.moveaxis(image, axes.index(page_axis), 0)
            axes = page_axis + axes.replace(page_axis, "")
            self.page_axis = page_axis
            self.n_pages = image.shape[0]
        # Channel data is H x W x C (pages: P x H x W x C); a single channel
        # stays H x W x 1, or P x H x W for page stacks as in 1.x.
        if self.n_channels == 1 and not self.is_rgb:
            if page_axis is None:
                image = image.reshape(image.shape[:2] + (1,))
            else:
                image = image.reshape(image.shape[:3])
        return np.ascontiguousarray(image)

    def read_data(self, scale=None, scene_index=0):
        """Read the series of ``scene_index``.

        Without pyramid levels, scenes are full size. With them, ``scale``
        picks the coarsest level that still has at least that resolution.
        """
        indices = range(self.n_scenes) if scene_index is None else [scene_index]
        for index in indices:
            key = "scene {}".format(index)
            with tifffile.TiffFile(self.path) as tiff_file:
                series = tiff_file.series[index]
                scales = level_scales(series) if self.has_levels else [1.0]
                level = choose_level(scales, scale)
                if key in self.data and abs(self.scale.get(key, 1.0) - scales[level]) < 1e-9:
                    continue
                source = (getattr(series, "levels", None) or [series])[level]
                image = np.asarray(source.asarray())
                axes = source.axes
            notes, fixed = list(self.notes), dict(self.fixed_axes)
            sizes = dict(self.fixed_axis_sizes)
            layout = self._interpret(image, axes)
            self.notes, self.fixed_axes, self.fixed_axis_sizes = notes, fixed, sizes
            if layout is None:
                raise ValueError(self.error_message or "The TIFF series could not be read.")
            self.data[key] = layout
            self.scale[key] = scales[level]


class ImagesReader(object):
    """Read a folder of conventional images as deterministic RGB scenes."""

    SUPPORTED_SUFFIXES = {".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}

    def __init__(self, folder_path):
        self.error_index = 0
        self.is_czi = False
        self.is_rgb = True
        self.n_channels = 3
        self.n_pages = 1
        self.level = 255
        self.data_type = "uint8"
        self.pixel_type = "rgb24"
        self.scaling_val = None
        _set_channel_metadata(self, RGB_COLORS, ["Red", "Green", "Blue"])
        self.file_name_list = []
        self.data = {}
        self.scale = {}

        paths = sorted(
            (
                path
                for path in Path(folder_path).iterdir()
                if path.is_file() and path.suffix.lower() in self.SUPPORTED_SUFFIXES
            ),
            key=lambda path: path.name.casefold(),
        )
        if not paths:
            raise ValueError("The selected folder contains no supported images.")

        if all(path.suffix.lower() in (".tif", ".tiff") for path in paths):
            self._read_tiff_scenes(paths)
            return

        for scene_id, path in enumerate(paths):
            image = read_bitmap(path, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Could not decode image: {}".format(path.name))
            self.file_name_list.append(path.stem)
            self.data["scene {}".format(scene_id)] = cv2.cvtColor(
                image, cv2.COLOR_BGR2RGB
            )
            self.scale["scene {}".format(scene_id)] = 1.0

        self.n_scenes = len(self.data)

    def _read_tiff_scenes(self, paths):
        """Read a TIFF folder at its native bit depth and channel layout.

        Every file must share one layout, because the scenes share channel
        controls; otherwise the folder is rejected rather than silently
        reduced to eight-bit RGB.
        """
        layout = None
        for scene_id, path in enumerate(paths):
            tiff = TIFFReader(path)
            if tiff.error_index != 0 or tiff.n_pages != 1:
                raise ValueError(
                    "{} is not a single-page grayscale, channel or RGB TIFF.".format(
                        path.name
                    )
                )
            current = (
                tiff.data_type,
                tiff.n_channels,
                tiff.is_rgb,
                tiff.data["scene 0"].shape[2:],
            )
            if layout is None:
                layout = current
                self.is_rgb = tiff.is_rgb
                self.n_channels = tiff.n_channels
                self.level = tiff.level
                self.data_type = tiff.data_type
                self.pixel_type = tiff.pixel_type
                # Files of one folder come from one acquisition.
                self.scaling_val = tiff.scaling_val
                _set_channel_metadata(self, tiff.rgb_colors, tiff.channel_name)
            elif current != layout:
                raise ValueError(
                    "{} has a different bit depth or channel layout from the "
                    "other TIFF files in the folder.".format(path.name)
                )
            self.file_name_list.append(path.stem)
            self.data["scene {}".format(scene_id)] = tiff.data["scene 0"]
            self.scale["scene {}".format(scene_id)] = 1.0
        self.n_scenes = len(self.data)
