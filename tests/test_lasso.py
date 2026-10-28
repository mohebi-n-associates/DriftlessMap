import unittest
from types import SimpleNamespace

from driftlessmap.layer_geometry import lasso_closes, lasso_point_closes, lasso_tolerance


class _ViewBox:
    def __init__(self, size):
        self.size = size

    def viewPixelSize(self):
        return self.size


class LassoTests(unittest.TestCase):
    def test_closing_distance_follows_the_zoom(self):
        # Zoomed out, one screen pixel covers 8 image pixels.
        self.assertEqual(lasso_tolerance(_ViewBox((8.0, 8.0)), pixels=12), 96.0)
        self.assertEqual(lasso_tolerance(_ViewBox((0.0, 0.0)), pixels=12), 12.0)
        path = [[0, 0], [500, 0], [500, 500]]
        self.assertTrue(lasso_closes(path, (60, 70), 96.0))
        self.assertFalse(lasso_closes(path, (90, 70), 96.0))
        # Two points do not make an area.
        self.assertFalse(lasso_closes(path[:2], (0, 0), 96.0))

    def test_only_the_first_point_closes(self):
        path = [[0, 0], [5, 0], [5, 5]]
        point = lambda i: SimpleNamespace(index=lambda: i)  # noqa: E731
        self.assertTrue(lasso_point_closes(path, [point(3), point(0)]))
        self.assertFalse(lasso_point_closes(path, [point(1)]))
        self.assertFalse(lasso_point_closes(path[:2], [point(0)]))


if __name__ == "__main__":
    unittest.main()
