import unittest

import numpy as np

from driftlessmap.state_digest import state_digest


class StateDigestTests(unittest.TestCase):
    def test_equal_sum_raster_edits_and_late_annotations_are_detected(self):
        image = np.zeros((16, 16), dtype=np.uint16)
        image[0, 0] = 1000
        points = [[float(i), float(i)] for i in range(100)]
        before = state_digest({"image": image, "points": points})
        image[0, 0], image[0, 1] = 0, 1000
        self.assertNotEqual(before, state_digest({"image": image, "points": points}))
        before = state_digest(points)
        points[-1] = [12., 15.]
        self.assertNotEqual(before, state_digest(points))

    def test_shared_arrays_are_not_cached_across_edits(self):
        image = np.arange(100).reshape(10, 10)
        before = state_digest([image, image])
        image[-1, -1] += 1
        self.assertNotEqual(before, state_digest([image, image]))
        self.assertEqual(state_digest(image.T), state_digest(image.T.copy()))
        self.assertNotEqual(state_digest(image), state_digest(image.astype(float)))

    def test_nested_payload_is_complete_and_does_not_depend_on_dict_order(self):
        a = {"object": {"name": "A", "data": np.ones((2, 3))}, "implants": []}
        self.assertEqual(state_digest(a), state_digest(dict(reversed(list(a.items())))))
        before = state_digest(a)
        a["implants"].append({"specs": {"diameter_um": 100}})
        self.assertNotEqual(before, state_digest(a))


if __name__ == "__main__":
    unittest.main()
