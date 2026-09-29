import unittest

from driftlessmap.registration_review import (
    NOT_RECORDED,
    NOT_REVIEWED,
    REVIEWED,
    RegistrationReview,
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
