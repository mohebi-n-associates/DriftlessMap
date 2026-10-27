import unittest

import numpy as np

from driftlessmap.atlas_matching import histology_gray, tissue_mask
from driftlessmap.registration_input import (
    RegistrationInput,
    check,
    default_for,
    prepare,
)


def three_channel_section():
    """DAPI-like tissue in channel 0, a bright off-tissue tracer in channel 1."""
    rng = np.random.default_rng(3)
    image = np.zeros((60, 80, 3), np.uint16)
    image[10:50, 10:60, 0] = 3000 + rng.integers(0, 400, (40, 50))
    image[5:15, 65:78, 1] = 60000          # tracer blob outside the tissue
    image[20:40, 20:40, 2] = 1200
    return image


class RecipeTests(unittest.TestCase):
    def test_round_trip_and_description(self):
        recipe = RegistrationInput.from_channels((0,), ["DAPI"])
        self.assertEqual(RegistrationInput.from_dict(recipe.to_dict()), recipe)
        self.assertEqual(recipe.describe(), "DAPI only")
        both = RegistrationInput.from_channels((0, 2), ["DAPI", "NeuN"])
        self.assertEqual(both.describe(), "DAPI + NeuN")
        self.assertEqual(RegistrationInput.from_dict({"mode": "legacy"}).mode, "legacy")
        self.assertIsNone(RegistrationInput.from_dict(None))

    def test_invalid_recipes_are_rejected(self):
        with self.assertRaises(ValueError):
            RegistrationInput.from_channels(())
        with self.assertRaises(ValueError):
            RegistrationInput.from_channels((1, 1))
        with self.assertRaises(ValueError):
            RegistrationInput.from_dict({"mode": "magic"})
        with self.assertRaises(ValueError):
            RegistrationInput.from_dict({"mode": "channels", "channels": [0], "version": 99})
        with self.assertRaises(ValueError):
            RegistrationInput.from_dict({"mode": "channels", "channels": [0],
                                         "percentiles": [90, 10]})

    def test_defaults_never_guess_microscopy_channels(self):
        self.assertEqual(default_for(1, False, ["DAPI"]).channels, (0,))
        self.assertEqual(default_for(3, True).mode, "legacy")
        self.assertIsNone(default_for(3, False, ["DAPI", "GFP", "Tracer"]))

    def test_missing_channels_are_reported(self):
        with self.assertRaises(ValueError):
            check(RegistrationInput.from_channels((4,)), 3)
        with self.assertRaises(ValueError):
            check(None, 3)


class PrepareTests(unittest.TestCase):
    def test_legacy_passes_the_image_through_unchanged(self):
        image = three_channel_section()
        prepared, record = prepare(image, RegistrationInput.legacy())
        self.assertIs(prepared, image)
        np.testing.assert_array_equal(tissue_mask(prepared), tissue_mask(image))
        np.testing.assert_array_equal(histology_gray(prepared), histology_gray(image))
        self.assertIsNone(record["bounds"])

    def test_dapi_only_ignores_every_other_channel(self):
        image = three_channel_section()
        recipe = RegistrationInput.from_channels((0,), ["DAPI"])
        plane, record = prepare(image, recipe)
        self.assertEqual(plane.shape, image.shape[:2])
        self.assertTrue(0.0 <= plane.min() and plane.max() <= 1.0)
        changed = image.copy()
        changed[..., 1] = 65535 - changed[..., 1]
        changed[..., 2] = 0
        np.testing.assert_array_equal(prepare(changed, recipe)[0], plane)
        self.assertEqual(len(record["bounds"]), 1)
        # The tracer blob is not part of the tissue outline.
        mask = tissue_mask(plane)
        self.assertFalse(mask[5:15, 65:78].any())
        self.assertTrue(tissue_mask(image)[5:15, 65:78].any())  # legacy includes it

    def test_several_channels_are_averaged_after_normalisation(self):
        image = three_channel_section()
        plane, record = prepare(image, RegistrationInput.from_channels((0, 2)))
        first, _ = prepare(image, RegistrationInput.from_channels((0,)))
        second, _ = prepare(image, RegistrationInput.from_channels((2,)))
        np.testing.assert_allclose(plane, (first + second) / 2, atol=1e-6)
        self.assertEqual(len(record["bounds"]), 2)

    def test_constant_channel_is_refused(self):
        image = three_channel_section()
        image[..., 2] = 7
        with self.assertRaises(ValueError):
            prepare(image, RegistrationInput.from_channels((2,), ["Empty"]))

    def test_single_channel_images(self):
        image = three_channel_section()[..., 0]
        plane, _ = prepare(image, RegistrationInput.from_channels((0,)))
        self.assertEqual(plane.shape, image.shape)


if __name__ == "__main__":
    unittest.main()
