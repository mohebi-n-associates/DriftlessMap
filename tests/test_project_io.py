import unittest

from driftlessmap.project_io import (
    default_working_atlas_data,
    default_working_img_data,
    object_file_names,
    with_defaults,
)


class ProjectIoTests(unittest.TestCase):
    def test_defaults_are_fresh_copies(self):
        first = default_working_img_data()
        first["img-probe"].append([1, 2])
        self.assertEqual(default_working_img_data()["img-probe"], [])
        self.assertEqual(default_working_atlas_data()["cell_count"], [0] * 5)

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
