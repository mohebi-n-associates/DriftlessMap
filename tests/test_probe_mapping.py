import unittest

import numpy as np

from driftlessmap.probe_utiles import (
    calculate_probe_info,
    find_probe_surface_entry,
    line_fit_2d,
    robust_probe_line_fit,
)


class ProbeMappingTests(unittest.TestCase):
    def test_robust_fit_rejects_an_isolated_control_point(self):
        points = np.array(
            [[0.0, 0.0, z] for z in range(10, 4, -1)]
            + [[20.0, 20.0, 5.0]]
        )

        start, end, _center, direction, diagnostics = (
            robust_probe_line_fit(points)
        )

        np.testing.assert_allclose(start, [0, 0, 10], atol=1e-9)
        np.testing.assert_allclose(end, [0, 0, 5], atol=1e-9)
        np.testing.assert_allclose(direction, [0, 0, -1], atol=1e-9)
        np.testing.assert_array_equal(
            diagnostics["inlier_mask"],
            [True, True, True, True, True, True, False],
        )
        self.assertEqual(diagnostics["inlier_count"], 6)
        self.assertEqual(diagnostics["rms_error_vox"], 0)
        self.assertGreater(diagnostics["max_error_vox"], 20)

    def test_surface_entry_follows_the_fitted_3d_line(self):
        labels = np.zeros((21, 21, 21), dtype=int)
        labels[:, :, 5:15] = 1

        surface, error = find_probe_surface_entry(
            labels,
            center=np.array([10.0, 10.0, 10.0]),
            direction=np.array([0.0, 0.0, -1.0]),
            bregma=np.zeros(3),
        )

        self.assertEqual(error, 0)
        np.testing.assert_allclose(surface[:2], [10, 10])
        self.assertGreaterEqual(surface[2], 14)
        self.assertLess(surface[2], 15)
        self.assertNotEqual(labels[tuple(np.floor(surface).astype(int))], 0)

    def test_2d_surface_entry_uses_the_line_mask_intersection(self):
        labels = np.zeros((20, 20), dtype=int)
        labels[4:16, 2:18] = 1
        points = np.array([[10.0, 7.0], [10.0, 10.0], [10.0, 13.0]])

        endpoints, message = line_fit_2d(points, labels)

        self.assertIsNone(message)
        self.assertGreaterEqual(endpoints[0, 1], 4)
        self.assertLess(endpoints[0, 1], 5)
        self.assertGreater(endpoints[1, 1], endpoints[0, 1])

    def test_full_mapping_handles_outlier_and_single_region_track(self):
        labels = np.zeros((101, 101, 101), dtype=np.int32)
        labels[5:96, 5:96, 20:81] = 10
        label_info = {
            "index": np.array([10]),
            "label": np.array(["Test region"]),
            "abbrev": np.array(["TR"]),
            "color": np.array([[1, 2, 3]]),
            "parent": np.array([0]),
            "level_indicator": [1],
        }
        settings = {
            "probe_type": 2,
            "probe_type_name": "Linear-Silicon",
            "probe_thickness": 0,
            "probe_length": 600,
            "tip_length": 50,
            "site_height": 10,
            "site_width": 10,
            "per_max_sites": [5],
            "sites_distance": [100],
            "x_bias": [0],
            "y_bias": [50],
            "site_number_in_banks": None,
            "multi_shanks": None,
        }
        probe_points = [
            np.array(
                [
                    [0.0, 0.0, 25.0],
                    [0.2, 0.1, 10.0],
                    [-0.1, 0.2, -10.0],
                    [0.0, 0.0, -30.0],
                    [20.0, 20.0, -25.0],
                ]
            )
        ]

        info, error = calculate_probe_info(
            probe_points,
            ["probe piece"],
            labels,
            label_info,
            vxsize_um=10,
            probe_settings=settings,
            merge_sites=False,
            bregma=np.array([50.0, 50.0, 50.0]),
            site_face=0,
            n_hat=None,
            pre_plan=False,
        )

        self.assertEqual(error, 0)
        self.assertEqual(info["trajectory_fit"]["point_count"], 5)
        self.assertEqual(info["trajectory_fit"]["inlier_count"], 4)
        self.assertEqual(info["region_label"], [10])
        self.assertEqual(
            info["reconstruction"]["coordinates"]["contacts"]["count"],
            5,
        )
        self.assertEqual(
            info["reconstruction"]["probe"]["trajectory_fit"][
                "surface_method"
            ],
            "3D fitted-line intersection with atlas brain mask",
        )


if __name__ == "__main__":
    unittest.main()
