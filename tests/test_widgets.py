import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from driftlessmap.image_curves import CurvesPlot
from driftlessmap.toolbox import ToolBox
from driftlessmap.utils import make_hist_data
from driftlessmap.widgets_utils import ChannelSelector


class ToolBoxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_tool_settings_round_trip(self):
        source = ToolBox()
        source.pencil_size_valt.setText("4")
        source.eraser_size_slider.setValue(33)
        source.magic_tol_val.setText("12")
        source.is_closed = True
        source.remove_inside = False
        saved = source.get_tool_data()

        restored = ToolBox()
        restored.set_tool_data(saved)
        self.assertEqual(restored.get_tool_data(), saved)


class CurvesPlotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_each_image_starts_with_fresh_channel_state(self):
        plot = CurvesPlot()
        four = np.random.default_rng(0).integers(0, 255, (8, 8, 4)).astype(np.uint8)
        plot.set_data(make_hist_data(four, 255), [(255, 0, 0)] * 4, 255)
        self.assertEqual(len(plot.active_pen), 4)

        one = np.random.default_rng(1).integers(0, 255, (8, 8, 1)).astype(np.uint8)
        plot.set_data(make_hist_data(one, 255), [(0, 255, 0)], 255)
        self.assertEqual(len(plot.active_pen), 1)
        self.assertEqual(plot.enable_channel[:4], [True, False, False, False])
        self.assertFalse(any(plot.enable_channel[1:]))
        self.assertFalse(plot.hist_list[3].isVisible())


class ChannelSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_image_colour_swatch_is_added_and_removed_once(self):
        selector = ChannelSelector()
        base = selector.color_combo.count()
        selector.add_item((0.5, 1.0, 1.0))
        self.assertEqual(selector.color_combo.count(), base + 1)
        self.assertEqual(selector.color_combo.currentIndex(), base)
        selector.delete_item()
        self.assertEqual(selector.color_combo.count(), base)


if __name__ == "__main__":
    unittest.main()
