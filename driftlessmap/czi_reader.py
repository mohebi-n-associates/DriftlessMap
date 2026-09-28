import cv2
from aicspylibczi import CziFile
from pathlib import Path
from os.path import dirname, realpath, join
import numpy as np
import colorsys
from .uuuuuu import hex2rgb
from .image_reader import CHANNEL_COLORS, MAX_CHANNELS

# czi_path = '~/Work/Kavli/Data/HERBS_DATA/abraham/Pecorino_mec_slide_1.czi'


def _hsv(rgb):
    chsv = colorsys.rgb_to_hsv(rgb[0], rgb[1], rgb[2])
    return (chsv[0], chsv[1], chsv[2] / 255)


def parse_czi_metadata(metadata, n_channels, is_rgb):
    """Read scaling and channel display settings from CZI XML metadata.

    Returns ``(scaling_um_per_px, rgb_colors, hsv_colors, names, gammas)``.
    Missing entries fall back to defaults instead of failing: scaling becomes
    ``None`` (lengths in pixels) and channels get default colours and names.
    """
    scaling_val = None
    for distance in metadata.findall("./Scaling/Items/Distance"):
        value = distance.findtext("Value")
        try:
            scaling_val = float(value) * 1e6
            break
        except (TypeError, ValueError):
            continue

    channels = metadata.findall("./DisplaySetting/Channels/Channel")
    gamma_val = []
    for channel in channels:
        gamma = channel.findtext("Gamma")
        if gamma is not None:
            gamma_val.append(gamma)

    if is_rgb:
        rgb_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        return (
            scaling_val,
            rgb_colors,
            [_hsv(rgb) for rgb in rgb_colors],
            ["Red", "Green", "Blue"],
            gamma_val,
        )

    rgb_colors, names = [], []
    for index in range(n_channels):
        channel = channels[index] if index < len(channels) else None
        colour = channel.findtext("Color") if channel is not None else None
        rgb = None
        if colour and len(colour) >= 7:
            # CZI stores #AARRGGBB; drop the alpha byte.
            try:
                rgb = tuple(int(v) for v in hex2rgb(colour[0] + colour[-6:]))
            except (TypeError, ValueError):
                rgb = None
        if rgb is None:
            rgb = CHANNEL_COLORS[index % len(CHANNEL_COLORS)]
        name = channel.findtext("ShortName") if channel is not None else None
        rgb_colors.append(rgb)
        names.append(name or "Channel {}".format(index + 1))
    return scaling_val, rgb_colors, [_hsv(rgb) for rgb in rgb_colors], names, gamma_val


class CZIReader(object):
    def __init__(self, czi_path):
        self.error_index = 0
        self.is_czi = True
        self.status = None
        self.file_name_list = [str(Path(czi_path).with_suffix(""))]
        self.czi = CziFile(czi_path)
        self.czi_info = self.czi.dims
        self.dimensions = self.czi.get_dims_shape()
        self.is_mosaic = self.czi.is_mosaic()
        self.pixel_type = self.czi.pixel_type
        self.n_pages = 1
        self.data = {}
        self.scale = {}

        if "T" in self.czi_info:
            if self.dimensions[0]["T"][1] != 1:
                self.status = "multi-T"

        if "A" in self.czi_info:
            self.is_rgb = True
            self.n_channels = 3
            if self.pixel_type == "bgr24":
                self.pixel_type = "rgb24"
                self.level = 255
                self.data_type = "uint8"
            else:
                da_power = int(self.pixel_type[-2:]) / 3
                self.pixel_type = "rgb" + self.pixel_type[-2:]
                self.level = int(np.power(2, da_power)) - 1
                self.data_type = "uint" + str(int(da_power))
        else:
            self.is_rgb = False
            if self.pixel_type == "gray16":
                self.level = 65535
                self.data_type = "uint16"
            elif self.pixel_type == "gray8":
                self.level = 255
                self.data_type = "uint8"
            else:
                self.error_index = 2
                return
            self.n_channels = self.dimensions[0]["C"][1]
            if self.n_channels > MAX_CHANNELS:
                self.error_index = 8
                return

        self.n_scenes = len(self.dimensions)
        self.has_fixed_box = False
        if self.n_scenes == 1:
            if self.dimensions[0]["S"][1] != 1:
                self.n_scenes = self.dimensions[0]["S"][1]
                self.has_fixed_box = True
        self.scene_bbox = []
        if self.is_mosaic:
            for i in range(self.n_scenes):
                bbox = self.czi.get_mosaic_scene_bounding_box(index=i)
                self.scene_bbox.append((bbox.x, bbox.y, bbox.w, bbox.h))
        else:
            for i in range(self.n_scenes):
                bbox = self.czi.get_scene_bounding_box(index=i)
                self.scene_bbox.append((bbox.x, bbox.y, bbox.w, bbox.h))

        # get colors and scaling from metadata
        (
            self.scaling_val,
            self.rgb_colors,
            self.hsv_colors,
            self.channel_name,
            self.gamma_val,
        ) = parse_czi_metadata(self.czi.meta[0], self.n_channels, self.is_rgb)

    def read_data(self, scale, scene_index=None):
        if not self.is_mosaic:
            # Non-mosaic images are always decoded at full resolution, so
            # the recorded scale must describe the pixels, not the request.
            scale = 1.0
        if scene_index is None:
            scene_index = np.arange(self.n_scenes)
        else:
            scene_index = [scene_index]

        for scind in scene_index:
            if self.is_rgb:
                if self.is_mosaic:
                    image_data = self.czi.read_mosaic(
                        C=0, scale_factor=scale, region=self.scene_bbox[scind]
                    )
                    if len(image_data.shape) == 4:
                        image_data = image_data[0]
                else:
                    image_data_full = self.czi.read_image(
                        region=self.scene_bbox[scind], S=scind
                    )
                    image_data = image_data_full[0]
                    image_info = image_data_full[1]
                    if image_info[0][0] == "C":
                        image_data = image_data[0]
                img = image_data.copy()
                if self.pixel_type == "rgb24":
                    img_data_temp = img.astype(np.uint8)
                else:
                    img_data_temp = img.astype(np.uint16)
                img_data_temp = cv2.cvtColor(img_data_temp, cv2.COLOR_BGR2RGB)
                self.data["scene %d" % scind] = img_data_temp
                self.scale["scene %d" % scind] = scale
            else:
                if self.n_channels != 1:
                    temp = []
                    for j in range(self.n_channels):
                        img = self._read_grayscale_plane(j, scale, scind)
                        temp.append(img)
                    img_data_temp = np.dstack(temp)
                    self.data["scene %d" % scind] = img_data_temp
                    self.scale["scene %d" % scind] = scale
                else:
                    img = self._read_grayscale_plane(0, scale, scind)
                    img_data_temp = img
                    self.data["scene %d" % scind] = img_data_temp.reshape(
                        img.shape[0], img.shape[1], 1
                    )
                    self.scale["scene %d" % scind] = scale

    def _read_grayscale_plane(self, channel, scale, scene_index):
        if self.is_mosaic:
            data = self.czi.read_mosaic(
                C=channel,
                scale_factor=scale,
                region=self.scene_bbox[scene_index],
            )
        else:
            data = self.czi.read_image(
                C=channel,
                S=scene_index,
                region=self.scene_bbox[scene_index],
            )[0]
        image = np.squeeze(np.asarray(data))
        if image.ndim != 2:
            raise ValueError("CZI channel did not decode to a two-dimensional image.")
        return image.copy()
