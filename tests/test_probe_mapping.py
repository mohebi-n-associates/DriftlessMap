import unittest

import numpy as np

from driftlessmap.probe_utiles import (
    MultiProbes,
    Probe,
    calculate_probe_info,
    calculate_vector_according_to_site_face,
    find_probe_surface_entry,
    line_fit_2d,
    robust_probe_line_fit,
)


class ProbeSettingsPersistenceTests(unittest.TestCase):
    def test_probe_settings_round_trip_includes_face(self):
        probe = Probe()
        probe.set_np2()
        probe.probe_faces_changed("Left")
        saved = probe.get_settings()

        restored = Probe()
        restored.set_settings(saved)

        self.assertEqual(restored.get_settings(), saved)

    def test_multi_probe_settings_can_be_cleared_and_restored(self):
        probes = MultiProbes()
        saved = {"x_vals": [1, 2], "y_vals": [3, 4], "faces": [0, 1]}
        probes.set_multi_probes(saved)
        self.assertEqual(probes.get_multi_settings(), saved)
        probes.set_multi_probes(None)
        self.assertIsNone(probes.get_multi_settings())


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
        track = info["reconstruction"]["coordinates"]["track"]
        self.assertGreaterEqual(track["count"], 2)
        self.assertEqual(track["ordering"], "insertion-to-tip")
        self.assertTrue(
            np.all(np.diff(track["axial_depth_from_insertion_um"]) >= 0)
        )
        self.assertEqual(
            track["structure_acronym"], ["TR"] * track["count"]
        )



class SiteFaceFrameTests(unittest.TestCase):
    DIRECTIONS = [
        [0.0, 0.0, -1.0],
        [0.5, 0.5, -np.sqrt(0.5)],
        [-0.3, 0.2, -0.93],
        [0.1, -0.6, -0.79],
        [0.8, 0.0, -0.6],
    ]

    def test_every_face_is_an_orthonormal_right_handed_frame(self):
        for direction in self.DIRECTIONS:
            for face in range(4):
                with self.subTest(direction=direction, face=face):
                    r_hat, u_hat, n_hat = calculate_vector_according_to_site_face(
                        np.asarray(direction), face
                    )
                    for vector in (r_hat, u_hat, n_hat):
                        self.assertAlmostEqual(np.linalg.norm(vector), 1.0)
                    self.assertAlmostEqual(float(np.dot(r_hat, u_hat)), 0.0)
                    self.assertAlmostEqual(float(np.dot(r_hat, n_hat)), 0.0)
                    self.assertAlmostEqual(float(np.dot(u_hat, n_hat)), 0.0)
                    np.testing.assert_allclose(
                        np.cross(r_hat, u_hat), n_hat, atol=1e-12
                    )

    def test_faces_are_rotations_of_face_zero_about_the_shank(self):
        for direction in self.DIRECTIONS:
            _, u0, n0 = calculate_vector_according_to_site_face(
                np.asarray(direction), 0
            )
            frames = [
                calculate_vector_according_to_site_face(np.asarray(direction), face)
                for face in range(4)
            ]
            np.testing.assert_allclose(frames[1][1:], [-u0, -n0], atol=1e-12)
            np.testing.assert_allclose(frames[2][1:], [-n0, u0], atol=1e-12)
            np.testing.assert_allclose(frames[3][1:], [n0, -u0], atol=1e-12)

    def test_vertical_probe_faces_match_the_documented_axes(self):
        direction = np.array([0.0, 0.0, -1.0])
        expected_normals = {
            0: [0, 1, 0],
            1: [0, -1, 0],
            2: [-1, 0, 0],
            3: [1, 0, 0],
        }
        for face, normal in expected_normals.items():
            _, _, n_hat = calculate_vector_according_to_site_face(direction, face)
            np.testing.assert_allclose(n_hat, normal, atol=1e-12)

if __name__ == "__main__":
    unittest.main()
