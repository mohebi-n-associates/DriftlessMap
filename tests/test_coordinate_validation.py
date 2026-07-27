import importlib.util
from pathlib import Path
import unittest

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "coordinate_validation.py"
SPEC = importlib.util.spec_from_file_location("coordinate_validation", MODULE_PATH)
coordinate_validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coordinate_validation)


class CoordinateValidationTests(unittest.TestCase):
    def test_rejects_negative_coordinates_that_numpy_would_wrap(self):
        self.assertFalse(
            coordinate_validation.coordinates_in_bounds((-1, 2, 3), (5, 5, 5))
        )

    def test_rejects_coordinate_equal_to_axis_size(self):
        self.assertFalse(
            coordinate_validation.coordinates_in_bounds((1, 5, 3), (5, 5, 5))
        )

    def test_rejects_malformed_coordinates(self):
        self.assertFalse(
            coordinate_validation.coordinates_in_bounds(np.array([1, 2]), (5, 5, 5))
        )

    def test_accepts_groups_only_when_every_voxel_is_inside(self):
        groups = [np.array([[0, 0, 0], [4, 4, 4]]), np.array([[2, 3, 1]])]
        self.assertTrue(
            coordinate_validation.coordinate_groups_in_bounds(groups, (5, 5, 5))
        )
        groups.append(np.array([[2, 3, -1]]))
        self.assertFalse(
            coordinate_validation.coordinate_groups_in_bounds(groups, (5, 5, 5))
        )


if __name__ == "__main__":
    unittest.main()
