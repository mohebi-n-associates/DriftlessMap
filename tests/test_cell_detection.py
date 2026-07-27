import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "cell_detection.py"
SPEC = importlib.util.spec_from_file_location("cell_detection", MODULE_PATH)
cell_detection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cell_detection)


class CellDetectionChannelTests(unittest.TestCase):
    def test_rgb_detection_always_produces_gray_layer_zero(self):
        image = np.zeros((4, 5, 3), dtype=np.uint8)
        image[..., 0] = 255
        plane, layer_index = cell_detection.select_detection_channel(
            image, True, [False, False, False, False]
        )
        self.assertEqual(plane.shape, (4, 5))
        self.assertEqual(layer_index, 0)

    def test_grayscale_detection_requires_one_visible_channel(self):
        image = np.zeros((4, 5, 2), dtype=np.uint16)
        with self.assertRaises(ValueError):
            cell_detection.select_detection_channel(image, False, [True, True])

        plane, layer_index = cell_detection.select_detection_channel(
            image, False, [False, True]
        )
        self.assertEqual(plane.dtype, np.uint8)
        self.assertEqual(layer_index, 2)


if __name__ == "__main__":
    unittest.main()
