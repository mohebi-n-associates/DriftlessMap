import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "layer_validation.py"
SPEC = importlib.util.spec_from_file_location("layer_validation", MODULE_PATH)
layer_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(layer_validation)


class LayerValidationTests(unittest.TestCase):
    def test_process_layer_requires_all_metadata(self):
        layer = {"data": np.zeros((4, 5)), "level": 255}
        self.assertFalse(
            layer_validation.image_layer_matches(
                layer, (4, 5), expected_level=255, require_metadata=True
            )
        )

    def test_process_layer_checks_data_size_declared_size_and_level(self):
        layer = {
            "data": np.zeros((4, 5, 3)),
            "size": (4, 5),
            "level": 255,
        }
        self.assertTrue(
            layer_validation.image_layer_matches(
                layer, (4, 5), expected_level=255, require_metadata=True
            )
        )
        layer["size"] = (5, 4)
        self.assertFalse(
            layer_validation.image_layer_matches(
                layer, (4, 5), expected_level=255, require_metadata=True
            )
        )

    def test_pixel_layer_must_match_current_image(self):
        self.assertFalse(
            layer_validation.image_layer_matches(
                {"data": np.zeros((5, 4))}, (4, 5)
            )
        )


if __name__ == "__main__":
    unittest.main()
