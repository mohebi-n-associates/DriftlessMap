"""Readers that normalize supported image files for :class:`ImageView`."""

import colorsys
from pathlib import Path

import cv2
import numpy as np
import tifffile


MAX_CHANNELS = 4
RGB_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
CHANNEL_COLORS = [(128, 128, 128), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
CHANNEL_NAMES = ["Gray", "Red", "Green", "Blue"]
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

        image = cv2.imread(str(image_file_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("OpenCV could not decode the selected image.")
        self.data = {"scene 0": cv2.cvtColor(image, cv2.COLOR_BGR2RGB)}
        self.scale = {"scene 0": 1.0}


class TIFFReader(object):
    """Read grayscale, RGB, channel, or page-stack TIFF data."""

    def __init__(self, image_file_path):
        self.error_index = 0
        self.is_czi = False
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
        _set_channel_metadata(self, [], [])

        with tifffile.TiffFile(image_file_path) as tiff_file:
            self.n_scenes = len(tiff_file.series)
            self.is_imagej = tiff_file.is_imagej
            if tiff_file.pages:
                self.software = tiff_file.pages[0].software
            if self.n_scenes != 1:
                self.error_index = 1
                return

            series = tiff_file.series[0]
            image = np.asarray(series.asarray())
            axes = series.axes

        if image.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
            self.error_index = 2
            return

        self.data_type = image.dtype.name
        self.level = int(np.iinfo(image.dtype).max)
        bit_depth = image.dtype.itemsize * 8

        if image.ndim == 2:
            image = image[..., None]
            self._set_grayscale(image, bit_depth, 1)
        elif image.ndim == 3 and image.shape[-1] in (3, 4) and axes.endswith("S"):
            self.is_rgb = True
            self.pixel_type = "rgb{}".format(bit_depth * 3)
            self.n_channels = 3
            image = image[..., :3]
            _set_channel_metadata(self, RGB_COLORS, ["Red", "Green", "Blue"])
        elif image.ndim == 3 and "C" in axes:
            channel_axis = axes.index("C")
            image = np.moveaxis(image, channel_axis, -1)
            self._set_grayscale(image, bit_depth, image.shape[-1])
        elif image.ndim == 3 and axes.endswith("YX"):
            self.n_pages = image.shape[0]
            self.is_rgb = False
            self.pixel_type = "gray{}".format(bit_depth)
            self.n_channels = 1
            _set_channel_metadata(self, CHANNEL_COLORS[:1], CHANNEL_NAMES[:1])
        else:
            self.error_index = 7
            return

        if self.n_channels > MAX_CHANNELS:
            self.error_index = 8
            return

        self.data["scene 0"] = image
        self.scale["scene 0"] = 1.0

    def _set_grayscale(self, image, bit_depth, n_channels):
        self.is_rgb = False
        self.pixel_type = "gray{}".format(bit_depth)
        self.n_channels = n_channels
        _set_channel_metadata(
            self, CHANNEL_COLORS[:n_channels], CHANNEL_NAMES[:n_channels]
        )


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

        for scene_id, path in enumerate(paths):
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Could not decode image: {}".format(path.name))
            self.file_name_list.append(path.stem)
            self.data["scene {}".format(scene_id)] = cv2.cvtColor(
                image, cv2.COLOR_BGR2RGB
            )
            self.scale["scene {}".format(scene_id)] = 1.0

        self.n_scenes = len(self.data)
