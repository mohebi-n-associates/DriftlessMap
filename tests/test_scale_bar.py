import tests.settings_isolation  # noqa: F401
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pyqtgraph as pg  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from driftlessmap.scale_bar import ScaleBar, length_label, nice_length  # noqa: E402

APPLICATION = QApplication.instance() or QApplication([])


class ScaleBarTests(unittest.TestCase):
    def test_nice_lengths(self):
        self.assertEqual(nice_length(730), 500)
        self.assertEqual(nice_length(2000), 2000)
        self.assertEqual(nice_length(1999), 1000)
        self.assertEqual(nice_length(0.37), 0.2)
        self.assertIsNone(nice_length(0))
        self.assertEqual(length_label(500), "500 µm")
        self.assertEqual(length_label(2000), "2 mm")
        self.assertEqual(length_label(0.5), "0.5 µm")

    def test_bar_follows_zoom_and_hides_without_a_unit(self):
        widget = pg.GraphicsLayoutWidget()
        view = widget.addViewBox()
        view.setAspectLocked()
        widget.resize(400, 300)
        bar = ScaleBar(view)
        self.assertFalse(bar.isVisible())
        bar.set_unit(10.0)  # 10 um per voxel
        view.setRange(xRange=(0, 1000), padding=0)
        bar.updateBar()
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.length_um, 2000)  # a fifth of 10 mm
        self.assertEqual(bar.text.textItem.toPlainText(), "2 mm")
        view.setRange(xRange=(0, 100), padding=0)
        bar.updateBar()
        self.assertEqual(bar.length_um, 200)
        bar.set_unit(None)
        self.assertFalse(bar.isVisible())
        widget.close()


class PixelSizeDialogTests(unittest.TestCase):
    def test_choices(self):
        from driftlessmap import pixel_size_dialog as module

        dialog = module.PixelSizeDialog(current=None, file_size=1.634, allow_unknown=True)
        self.assertAlmostEqual(dialog.spin.value(), 1.634)
        dialog.spin.setValue(2.0)
        dialog._finish(module.SET)
        self.assertEqual((dialog.choice, dialog.size_um), (module.SET, 2.0))
        dialog.file_button.click()
        self.assertEqual((dialog.choice, dialog.size_um), (module.FROM_FILE, None))
        dialog.unknown_button.click()
        self.assertEqual(dialog.choice, module.UNKNOWN)
        plain = module.PixelSizeDialog()
        self.assertFalse(hasattr(plain, "file_button"))
        self.assertFalse(hasattr(plain, "unknown_button"))


if __name__ == "__main__":
    unittest.main()
