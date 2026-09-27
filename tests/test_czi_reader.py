import sys
import types
import unittest
from unittest.mock import patch

import numpy as np


def import_czi_reader():
    """Import ``czi_reader`` even where the optional CZI wheel is absent."""
    stub = types.ModuleType("aicspylibczi")
    stub.CziFile = object
    with patch.dict(sys.modules, {"aicspylibczi": sys.modules.get("aicspylibczi", stub)}):
        sys.modules.pop("driftlessmap.czi_reader", None)
        import driftlessmap.czi_reader as czi_reader
    return czi_reader


class FakeCzi:
    def __init__(self, full_shape=(40, 60)):
        self.full_shape = full_shape
        self.mosaic_scales = []

    def read_mosaic(self, C, scale_factor, region):
        self.mosaic_scales.append(scale_factor)
        height = int(self.full_shape[0] * scale_factor)
        width = int(self.full_shape[1] * scale_factor)
        return np.ones((1, height, width), dtype=np.uint16)

    def read_image(self, C, S, region):
        return np.ones((1, 1) + self.full_shape, dtype=np.uint16), [("C", 1)]


def grayscale_reader(czi_reader, is_mosaic):
    reader = czi_reader.CZIReader.__new__(czi_reader.CZIReader)
    reader.czi = FakeCzi()
    reader.is_mosaic = is_mosaic
    reader.is_rgb = False
    reader.n_channels = 1
    reader.n_scenes = 1
    reader.scene_bbox = [None]
    reader.data = {}
    reader.scale = {}
    return reader


class CziScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.czi_reader = import_czi_reader()

    def test_non_mosaic_reads_record_full_resolution(self):
        reader = grayscale_reader(self.czi_reader, is_mosaic=False)
        reader.read_data(0.1, scene_index=0)
        self.assertEqual(reader.data["scene 0"].shape[:2], (40, 60))
        self.assertEqual(reader.scale["scene 0"], 1.0)

    def test_mosaic_reads_record_the_requested_scale(self):
        reader = grayscale_reader(self.czi_reader, is_mosaic=True)
        reader.read_data(0.5, scene_index=0)
        self.assertEqual(reader.data["scene 0"].shape[:2], (20, 30))
        self.assertEqual(reader.scale["scene 0"], 0.5)


if __name__ == "__main__":
    unittest.main()
