import unittest

import numpy as np

from driftlessmap.utils import make_hist_data


class HistogramDataTests(unittest.TestCase):
    def test_masks_and_nearly_black_channels_produce_curves(self):
        for max_value in (0, 1, 2):
            image = np.zeros((8, 8, 1), dtype=np.uint8)
            image[:2, :2, 0] = max_value
            curves = make_hist_data(image, 255)
            x, y = curves[0]
            self.assertEqual(len(x), 200)
            self.assertTrue(np.all(np.isfinite(y)))

    def test_fractional_float_channels_are_supported(self):
        image = np.random.default_rng(0).random((6, 6, 2)).astype(np.float32)
        curves = make_hist_data(image, 255)
        self.assertEqual(len(curves), 2)


if __name__ == "__main__":
    unittest.main()
