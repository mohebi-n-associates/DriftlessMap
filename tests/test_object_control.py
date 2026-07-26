import os
import unittest
from unittest.mock import patch

import numpy as np


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from herbs.object_control import DrawingInfoWindow, ObjectControl
from herbs.roi_analysis import build_drawing_roi_info


def drawing_info():
    labels = np.zeros((3, 2, 7), dtype=int)
    labels[1, 0, 1:6] = 10
    return build_drawing_roi_info(
        [np.array([[0.0, 0.0, 2.0], [0.0, 0.0, 5.0]])],
        ["line drawing - piece"],
        bregma_herbs_vox=[1, 0, 0],
        voxel_size_um=10,
        herbs_shape=labels.shape,
        label_volume=labels,
        label_info={
            "index": np.array([10]),
            "label": np.array(["Test region"]),
            "abbrev": np.array(["TR"]),
            "color": np.array([[1, 2, 3]]),
        },
    )


class DrawingInfoWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_window_shows_region_summary_and_export_action(self):
        window = DrawingInfoWindow("line drawing", drawing_info())

        self.assertEqual(window.region_table.rowCount(), 1)
        self.assertEqual(window.region_table.item(0, 1).text(), "Test region")
        self.assertEqual(window.region_table.item(0, 2).text(), "TR")
        self.assertEqual(
            window.export_btn.text(), "Export coordinates as CSV"
        )

    def test_info_button_supports_an_unmerged_drawing_piece(self):
        control = ObjectControl()
        calls = []

        def provider(data, object_type, object_name):
            calls.append((data, object_type, object_name))
            return drawing_info()

        control.drawing_info_provider = provider
        piece = np.array([[0.0, 0.0, 2.0], [0.0, 0.0, 5.0]])
        control.add_object(
            "line drawing - piece", "drawing piece", piece, "opaque"
        )

        with patch.object(DrawingInfoWindow, "exec", return_value=0) as execute:
            control.info_btn_clicked()

        execute.assert_called_once_with()
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0][0], piece)
        self.assertEqual(calls[0][1], "drawing piece")


if __name__ == "__main__":
    unittest.main()
