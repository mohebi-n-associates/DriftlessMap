import unittest

from driftlessmap.registration_review import (
    NOT_RECORDED,
    NOT_REVIEWED,
    REVIEWED,
    RegistrationReview,
    legacy,
    registration_fingerprint,
)


def fingerprint(**changes):
    inputs = dict(atlas_points=[[1, 2], [3, 4], [5, 6]],
                  histology_points=[[10, 20], [30, 40], [50, 60]],
                  atlas_frame=[[0, 0], [9, 9]], histology_frame=[[0, 0], [90, 90]],
                  plane="sagittal", page=124, tilt=(3.0, -6.0), image_shape=(904, 1740, 3))
    inputs.update(changes)
    return registration_fingerprint(**inputs)


class ReviewTests(unittest.TestCase):
    def test_implicit_topology_matches_the_built_mesh(self):
        import numpy as np
        from driftlessmap.triangulation import canonical_simplices

        points = [[0., 0.], [10., 0.], [10., 10.], [0., 10.]]
        implicit = fingerprint(atlas_points=points, atlas_frame=[])
        explicit = fingerprint(atlas_points=points, atlas_frame=[],
                               simplices=canonical_simplices(np.asarray(points)))
        self.assertEqual(implicit, explicit)

    def test_topology_changes_invalidate_review_but_triangle_order_does_not(self):
        first = [[0, 1, 2], [0, 2, 3]]
        other = [[0, 1, 3], [1, 2, 3]]
        review = RegistrationReview(fingerprint(simplices=first))
        self.assertEqual(review.state(fingerprint(simplices=other)), NOT_REVIEWED)
        self.assertEqual(review.state(fingerprint(simplices=[[3, 2, 0], [2, 1, 0]])), REVIEWED)

    def test_legacy_fingerprint_is_the_one_written_before_a26(self):
        # sha256 of the pre-2.0.0a26 payload for these inputs, which had no
        # version or simplices; mapping records saved then are migrated with it.
        self.assertEqual(
            fingerprint(simplices=legacy),
            "8876fc0f97c33ff24d164bd9c72bc555503361110187100504d6254c04f5cd88")
        self.assertNotEqual(fingerprint(simplices=legacy), fingerprint())

    def test_review_applies_only_to_what_was_reviewed(self):
        review = RegistrationReview(fingerprint(), "2026-09-29T10:00:00Z")
        self.assertEqual(review.state(fingerprint()), REVIEWED)
        for change in ({"atlas_points": [[1, 2], [3, 4], [5, 7]]},
                       {"histology_frame": [[0, 0], [91, 90]]},
                       {"page": 125}, {"tilt": (3.0, -3.0)}, {"plane": "coronal"},
                       {"image_shape": (904, 1741, 3)}):
            with self.subTest(change):
                self.assertEqual(review.state(fingerprint(**change)), NOT_REVIEWED)

    def test_fingerprint_ignores_float_noise_and_channel_count(self):
        self.assertEqual(fingerprint(), fingerprint(atlas_points=[[1.0000001, 2], [3, 4], [5, 6]]))
        self.assertEqual(fingerprint(), fingerprint(image_shape=(904, 1740, 6)))

    def test_states_for_new_and_legacy_work(self):
        self.assertEqual(RegistrationReview().state(fingerprint()), NOT_REVIEWED)
        self.assertEqual(RegistrationReview(recorded=False).state(fingerprint()), NOT_RECORDED)
        self.assertEqual(RegistrationReview.from_dict(None).state(fingerprint()), NOT_RECORDED)

    def test_round_trip_and_validation(self):
        review = RegistrationReview(fingerprint(), "2026-09-29T10:00:00Z")
        self.assertEqual(RegistrationReview.from_dict(review.to_dict()), review)
        with self.assertRaises(ValueError):
            RegistrationReview.from_dict({"fingerprint": "short"})
        with self.assertRaises(ValueError):
            RegistrationReview.from_dict([1])


if __name__ == "__main__":
    unittest.main()
