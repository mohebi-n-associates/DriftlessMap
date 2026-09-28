import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from driftlessmap.image_reader import EmbeddedImageReader
from driftlessmap.image_view import ImageView
from driftlessmap.utils import rotate


class ImageGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def view_with(self, pixels):
        view = ImageView()
        view.set_data(EmbeddedImageReader(pixels))
        changes = []
        view.sig_image_changed.connect(lambda: changes.append(True))
        return view, changes

    def test_fine_rotation_resamples_from_the_original_once(self):
        rng = np.random.default_rng(1)
        pixels = rng.integers(0, 255, size=(40, 50, 1), dtype=np.uint8)
        view, _ = self.view_with(pixels)
        for _ in range(3):
            view.image_1_rotate("counter")
        expected = rotate(pixels[:, :, 0], 3)
        np.testing.assert_array_equal(view.current_img[:, :, 0], expected)

    def test_flips_and_turns_update_every_page_and_announce_the_change(self):
        pixels = np.zeros((6, 8, 1), dtype=np.uint8)
        view, changes = self.view_with(pixels)
        view.volume_img = np.arange(3 * 6 * 8, dtype=np.uint8).reshape(3, 6, 8)
        view.current_img = np.dstack([view.volume_img[1]])
        view.display_img_index = 1
        view.image_horizon_flip()
        np.testing.assert_array_equal(view.volume_img[0], np.arange(48).reshape(6, 8)[:, ::-1])
        view.image_90_rotate()
        self.assertEqual(view.volume_img.shape, (3, 8, 6))
        self.assertEqual(view.img_size, (8, 6))
        self.assertEqual(len(changes), 2)


if __name__ == "__main__":
    unittest.main()
