import unittest

import numpy as np

from driftlessmap.landmarks import LandmarkModel, triangulation_payload_error
from driftlessmap.utils import get_corner_line_from_rect


def payload(corners, inside=(), display="coronal", simplices=None):
    corners = [list(point) for point in corners]
    data = {
        "atlas_corner_points": corners,
        "atlas_side_lines": [],
        "atlas_tri_data": corners + [list(point) for point in inside],
        "atlas_tri_inside_data": [list(point) for point in inside],
        "atlas_tri_onside_data": corners,
        "atlas_display": display,
    }
    if simplices is not None:
        data["tri_simplices"] = simplices
    return data


class LandmarkModelTests(unittest.TestCase):
    def test_invalidation_clears_registration_and_optionally_topology(self):
        model = LandmarkModel()
        model.triangulation_registration = {"built": True}
        model.registration_cache_key = ("key",)
        model.tri_simplices = np.array([[0, 1, 2]])
        model.invalidate()
        self.assertIsNone(model.triangulation_registration)
        self.assertIsNotNone(model.tri_simplices)
        model.invalidate(clear_topology=True)
        self.assertIsNone(model.tri_simplices)

    def test_cache_key_changes_with_any_landmark(self):
        model = LandmarkModel()
        model.atlas_tri_data = [[0.0, 0.0], [1.0, 1.0]]
        model.histo_tri_data = [[0.0, 0.0], [2.0, 2.0]]
        first = model.cache_key((10, 10), (20, 20), None)
        model.histo_tri_data[1] = [2.5, 2.0]
        self.assertNotEqual(first, model.cache_key((10, 10), (20, 20), None))


class TriangulationPayloadTests(unittest.TestCase):
    SIZES = {"coronal": (24, 40), "sagittal": (24, 32), "horizontal": (40, 32)}

    def corners(self, display="coronal"):
        height, width = self.SIZES[display]
        return get_corner_line_from_rect((0, 0, width, height))[0]

    def test_matching_payload_is_accepted(self):
        data = payload(self.corners(), inside=[[5, 5]], simplices=[[0, 1, 4]])
        self.assertIsNone(triangulation_payload_error(data, self.SIZES, 2))

    def test_mismatches_are_explained(self):
        wrong_size = payload([[0, 0], [99, 0], [99, 79], [0, 79]])
        self.assertIn("different size", triangulation_payload_error(wrong_size, self.SIZES, 2))
        bad_topology = payload(self.corners(), simplices=[[0, 1, 9]])
        self.assertIn("missing points", triangulation_payload_error(bad_topology, self.SIZES, 2))
        self.assertIn("boundary points", triangulation_payload_error(
            payload(self.corners()), self.SIZES, 3))
        self.assertIn("not a triangulation", triangulation_payload_error({}, self.SIZES, 2))


if __name__ == "__main__":
    unittest.main()
