import unittest

import numpy as np

from driftlessmap.project_io import (
    CELL_COUNT_SLOTS,
    INTERFACE_STATE_LIMIT,
    clean_interface_state,
    default_working_atlas_data,
    default_working_img_data,
    layer_points,
    object_file_names,
    plot_points,
    with_defaults,
)


class ProjectIoTests(unittest.TestCase):
    def test_defaults_are_fresh_copies(self):
        first = default_working_img_data()
        first["img-probe"].append([1, 2])
        self.assertEqual(default_working_img_data()["img-probe"], [])
        self.assertEqual(default_working_atlas_data()["cell_count"], [0] * CELL_COUNT_SLOTS)

    def test_older_payloads_gain_new_fields_and_lose_retired_ones(self):
        merged = with_defaults(
            default_working_img_data(), {"img-probe": [[3, 4]], "legacy": True}
        )
        self.assertEqual(merged["img-probe"], [[3, 4]])
        self.assertIn("ruler_path", merged)
        self.assertNotIn("legacy", merged)

    def test_object_file_names_are_safe_and_unique(self):
        self.assertEqual(
            object_file_names(["a/b", "a:b", "A_B", "", " . "]),
            ["a_b", "a_b (2)", "A_B (3)", "object", "object (2)"],
        )


if __name__ == "__main__":
    unittest.main()


class LeftOffStateTests(unittest.TestCase):
    def test_interface_state_is_kept_as_plain_json(self):
        state = {"step": "annotate", "implants": {"drawing": {
            "vertices": np.array([[1.0, 2.0], [3.0, 4.0]]), "count": np.int64(2)}}}
        cleaned = clean_interface_state(state)
        self.assertEqual(cleaned["implants"]["drawing"]["vertices"], [[1.0, 2.0], [3.0, 4.0]])
        self.assertIsInstance(cleaned["implants"]["drawing"]["count"], int)

    def test_unusable_interface_state_is_dropped_not_fatal(self):
        self.assertEqual(clean_interface_state(None), {})          # projects before 2.0.0a25
        self.assertEqual(clean_interface_state([1, 2]), {})
        self.assertEqual(clean_interface_state({"x": object()}), {})
        self.assertEqual(clean_interface_state({"x": float("nan")}), {})
        self.assertEqual(clean_interface_state({"x": "a" * INTERFACE_STATE_LIMIT}), {})

    def test_empty_point_layers_read_as_empty(self):
        # A pencil click without a stroke used to be saved as [None, None].
        self.assertEqual(layer_points([None, None]).shape, (0, 2))
        self.assertEqual(layer_points([]).shape, (0, 2))
        self.assertEqual(layer_points([[1, 2], [3, 4]]).tolist(), [[1.0, 2.0], [3.0, 4.0]])
        self.assertEqual(plot_points((None, None)), [])
        self.assertEqual([list(p) for p in plot_points(([1, 3], [2, 4]))],
                         [[1.0, 2.0], [3.0, 4.0]])
