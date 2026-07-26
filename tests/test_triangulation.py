import unittest

import cv2
import numpy as np

from herbs.triangulation import (
    TriangulationError,
    build_piecewise_affine_registration,
    dense_inverse_map,
    registration_summary_text,
    transform_points_piecewise,
    warp_image_piecewise,
)


def rectangle_points(width, height):
    return np.array(
        [
            [0.0, 0.0],
            [width - 1.0, 0.0],
            [width - 1.0, height - 1.0],
            [0.0, height - 1.0],
        ]
    )


class PiecewiseAffineRegistrationTests(unittest.TestCase):
    def test_identity_dense_warp_has_no_triangle_seams(self):
        shape = (5, 6)
        points = rectangle_points(shape[1], shape[0])
        registration = build_piecewise_affine_registration(
            points,
            points,
            atlas_shape=shape,
            histology_shape=shape,
        )
        image = np.arange(np.prod(shape), dtype=np.uint8).reshape(shape)

        warped = warp_image_piecewise(
            image,
            registration,
            "histology_to_atlas",
            interpolation=cv2.INTER_NEAREST,
        )
        _map_x, _map_y, valid = dense_inverse_map(
            registration, "histology_to_atlas"
        )

        np.testing.assert_array_equal(warped, image)
        self.assertTrue(np.all(valid))

    def test_one_topology_round_trips_points_in_both_directions(self):
        atlas_shape = (8, 9)
        histology_shape = (5, 6)
        atlas = rectangle_points(atlas_shape[1], atlas_shape[0])
        histology = rectangle_points(
            histology_shape[1], histology_shape[0]
        )
        registration = build_piecewise_affine_registration(
            atlas,
            histology,
            atlas_shape=atlas_shape,
            histology_shape=histology_shape,
        )
        histology_points = np.array([[1.25, 2.5], [4.0, 1.0]])

        atlas_points, valid, forward_triangles = transform_points_piecewise(
            histology_points, registration, "histology_to_atlas"
        )
        recovered, reverse_valid, reverse_triangles = (
            transform_points_piecewise(
                atlas_points, registration, "atlas_to_histology"
            )
        )

        self.assertTrue(np.all(valid))
        self.assertTrue(np.all(reverse_valid))
        np.testing.assert_allclose(recovered, histology_points, atol=1e-9)
        self.assertEqual(
            set(forward_triangles.tolist()),
            set(reverse_triangles.tolist()),
        )

    def test_persisted_connectivity_is_reused_after_landmark_motion(self):
        shape = (10, 10)
        atlas = np.vstack((rectangle_points(10, 10), [[5.0, 5.0]]))
        histology = atlas.copy()
        first = build_piecewise_affine_registration(
            atlas,
            histology,
            atlas_shape=shape,
            histology_shape=shape,
        )
        moved_histology = histology.copy()
        moved_histology[-1] = [6.0, 4.0]

        second = build_piecewise_affine_registration(
            atlas,
            moved_histology,
            atlas_shape=shape,
            histology_shape=shape,
            simplices=first["simplices"],
        )

        np.testing.assert_array_equal(
            second["simplices"], first["simplices"]
        )

    def test_folded_triangle_is_rejected(self):
        atlas = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 4.0]])
        histology = np.array([[0.0, 0.0], [0.0, 4.0], [4.0, 0.0]])

        with self.assertRaisesRegex(TriangulationError, "folded"):
            build_piecewise_affine_registration(
                atlas,
                histology,
                atlas_shape=(5, 5),
                histology_shape=(5, 5),
            )

    def test_folded_triangle_can_be_inspected_for_live_feedback(self):
        atlas = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 4.0]])
        histology = np.array([[0.0, 0.0], [0.0, 4.0], [4.0, 0.0]])

        registration = build_piecewise_affine_registration(
            atlas,
            histology,
            atlas_shape=(5, 5),
            histology_shape=(5, 5),
            allow_unsafe=True,
        )

        self.assertEqual(
            registration["quality"]["summary"]["folded_count"], 1
        )
        self.assertTrue(registration["errors"])

    def test_duplicate_landmarks_are_rejected(self):
        atlas = np.array(
            [[0.0, 0.0], [4.0, 0.0], [0.0, 4.0], [0.1, 0.1]]
        )

        with self.assertRaisesRegex(TriangulationError, "too close"):
            build_piecewise_affine_registration(
                atlas,
                atlas,
                atlas_shape=(5, 5),
                histology_shape=(5, 5),
            )

    def test_skinny_triangles_produce_visible_quality_warning(self):
        atlas = np.array(
            [[0.0, 0.0], [9.0, 0.0], [9.0, 9.0], [0.0, 9.0]]
        )
        histology = np.array(
            [[0.0, 0.0], [9.0, 0.0], [9.0, 9.0], [0.0, 0.5]]
        )
        registration = build_piecewise_affine_registration(
            atlas,
            histology,
            atlas_shape=(10, 10),
            histology_shape=(10, 10),
        )

        self.assertTrue(registration["warnings"])
        self.assertIn("warning", registration_summary_text(registration))

    def test_points_outside_the_mesh_are_preserved_as_invalid(self):
        shape = (5, 5)
        points = rectangle_points(5, 5)
        registration = build_piecewise_affine_registration(
            points,
            points,
            atlas_shape=shape,
            histology_shape=shape,
        )

        transformed, valid, triangle_index = transform_points_piecewise(
            np.array([[2.0, 2.0], [10.0, 10.0]]),
            registration,
            "histology_to_atlas",
        )

        self.assertTrue(valid[0])
        self.assertFalse(valid[1])
        self.assertEqual(triangle_index[1], -1)
        self.assertTrue(np.all(np.isnan(transformed[1])))


if __name__ == "__main__":
    unittest.main()
