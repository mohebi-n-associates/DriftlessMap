import unittest

import numpy as np

from driftlessmap.layer_geometry import (
    layer_center,
    rotate_points,
    rotate_raster,
    shift_raster,
)


class LayerTransformTests(unittest.TestCase):
    def test_vector_rotation_matches_raster_rotation(self):
        image = np.zeros((61, 61), dtype=np.uint8)
        points = np.array([[20, 15], [30, 22], [45, 40]])
        for x, y in points:
            image[y, x] = 255
        center = (30.0, 30.0)
        for angle in (90, 180, 270):
            rotated = rotate_raster(image, center, angle)
            ys, xs = np.nonzero(rotated)
            expected = sorted(zip(xs.tolist(), ys.tolist()))
            moved = rotate_points(points, center, angle)
            actual = sorted(tuple(int(round(v)) for v in p) for p in moved)
            self.assertEqual(actual, expected, angle)

    def test_rotation_handles_any_number_of_points(self):
        for count in (1, 2, 5):
            points = np.arange(count * 2, dtype=float).reshape(count, 2)
            moved = rotate_points(points, (0.0, 0.0), 30)
            self.assertEqual(moved.shape, (count, 2))

    def test_shifted_raster_keeps_its_shape(self):
        image = np.zeros((20, 50, 4), dtype=np.uint8)
        image[5, 10] = 255
        shifted = shift_raster(image, np.array([3, 2]))
        self.assertEqual(shifted.shape, image.shape)
        self.assertEqual(shifted[7, 13, 0], 255)

    def test_layer_center_is_the_bounding_box_center(self):
        center = layer_center([[0, 0], [99, 0], [99, 49], [0, 49]])
        self.assertEqual(center, (49.5, 24.5))


if __name__ == "__main__":
    unittest.main()
