import unittest

import numpy as np

from driftlessmap.region_colors import (
    MIN_DIFFERENCE,
    color_areas,
    distinct_region_colors,
    lab_to_srgb,
    srgb_to_lab,
    touching_pairs,
)

GREEN_PL = (47, 168, 80)    # Allen prelimbic area
GREEN_IL = (89, 179, 99)    # Allen infralimbic area, which touches it


def difference(first, second):
    return float(np.linalg.norm(srgb_to_lab(first) - srgb_to_lab(second)))


def atlas():
    """PL and IL (each with two layers of their own colour) touching each
    other, and a red region touching only PL."""
    info = {
        "index": np.array([1, 10, 11, 12, 20, 21, 22, 30]),
        "parent": np.array([-1, 1, 10, 10, 1, 20, 20, 1]),
        "abbrev": np.array(["root", "PL", "PL1", "PL5", "IL", "IL1", "IL5", "R"]),
        "color": np.array([(200, 200, 200), GREEN_PL, GREEN_PL, GREEN_PL,
                           GREEN_IL, GREEN_IL, GREEN_IL, (220, 30, 30)]),
    }
    volume = np.zeros((8, 8, 8), dtype=np.int32)
    volume[:, 0:2] = 11
    volume[:, 2:4] = 12
    volume[:, 4:6] = 21
    volume[:, 6:7] = 22
    volume[:, 7:8] = 30
    volume[0] = 0
    return info, volume


class RegionColorTests(unittest.TestCase):
    def test_lab_round_trip(self):
        colors = np.array([(0, 0, 0), (255, 255, 255), GREEN_PL, (12, 200, 250)])
        np.testing.assert_array_equal(lab_to_srgb(srgb_to_lab(colors)), colors)

    def test_layers_of_an_area_share_its_colour(self):
        info, _volume = atlas()
        self.assertEqual(color_areas(info["index"], info["parent"], info["color"]),
                         [1, 10, 10, 10, 20, 20, 20, 30])

    def test_touching_pairs_ignore_background_and_unknown_ids(self):
        volume = np.array([[[0, 5, 6, 99]]])
        pairs = touching_pairs(volume, np.array([5, 6]), step=1)
        np.testing.assert_array_equal(pairs, [[0, 1]])

    def test_touching_areas_of_similar_colour_are_moved_apart(self):
        info, volume = atlas()
        self.assertLess(difference(GREEN_PL, GREEN_IL), MIN_DIFFERENCE)
        result, changed = distinct_region_colors(info, volume, step=1)
        colors = dict(zip(result["abbrev"], map(tuple, result["color"])))
        self.assertEqual(changed, 1)
        # The larger area (PL) keeps its colour; IL moves away from it.
        self.assertEqual(colors["PL"], GREEN_PL)
        self.assertGreaterEqual(difference(colors["PL"], colors["IL"]), MIN_DIFFERENCE)
        # Layers follow their area; untouched regions keep their colour.
        self.assertEqual(colors["PL1"], colors["PL5"])
        self.assertEqual(colors["IL1"], colors["IL"])
        self.assertEqual(colors["IL5"], colors["IL"])
        self.assertEqual(colors["R"], (220, 30, 30))
        self.assertEqual(colors["root"], (200, 200, 200))
        # The atlas colours are kept, and the input is not modified.
        np.testing.assert_array_equal(result["atlas_color"], info["color"])
        self.assertEqual(tuple(info["color"][4]), GREEN_IL)

    def test_regions_that_do_not_touch_keep_their_colours(self):
        info, volume = atlas()
        volume[:, 4:7] = 0          # IL no longer touches PL
        result, changed = distinct_region_colors(info, volume, step=1)
        self.assertEqual(changed, 0)
        np.testing.assert_array_equal(result["color"], info["color"])


if __name__ == "__main__":
    unittest.main()
