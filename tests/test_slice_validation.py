import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "slice_validation.py"
SPEC = importlib.util.spec_from_file_location("herbs_slice_validation_test", MODULE_PATH)
slice_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(slice_validation)
slice_info_is_ready = slice_validation.slice_info_is_ready


class SliceValidationTests(unittest.TestCase):
    def test_zero_distance_at_bregma_is_valid(self):
        self.assertTrue(slice_info_is_ready(5.0, 4.0, 0.0, [100, 80]))

    def test_negative_distance_is_valid(self):
        self.assertTrue(slice_info_is_ready(5.0, 4.0, -1.25, np.array([100, 80])))

    def test_missing_or_invalid_registration_is_rejected(self):
        self.assertFalse(slice_info_is_ready(5.0, 4.0, 0.0, []))
        self.assertFalse(slice_info_is_ready(0.0, 4.0, 0.0, [100, 80]))
        self.assertFalse(slice_info_is_ready(5.0, 4.0, float("nan"), [100, 80]))
        self.assertFalse(slice_info_is_ready(5.0, 4.0, 0.0, [100, float("inf")]))


if __name__ == "__main__":
    unittest.main()
