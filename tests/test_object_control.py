import os
import unittest
from unittest.mock import patch

import numpy as np


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from herbs.object_control import (
    DrawingInfoWindow,
    ObjectControl,
    ProbeInfoWindow,
)
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


class ProbeInfoWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def probe_data(self):
        fit = {
            "method": "robust orthogonal 3D line fit",
            "surface_method": (
                "3D fitted-line intersection with atlas brain mask"
            ),
            "point_count": 5,
            "inlier_count": 4,
            "rms_error_um": 6.0,
            "max_error_um": 40.0,
            "explained_fraction": 0.995,
        }
        return {
            "vis_color": (0, 255, 0, 255),
            "ap_angle": 11.67,
            "ml_angle": 0.0,
            "ap_tilt": "posterior",
            "ml_tilt": "no tilt",
            "probe_length": 3569.69,
            "dv": 3495.93,
            "insertion_coords": np.array([325.0, 2537.55, 900.0]),
            "insertion_vox": np.array([241, 412, 249]),
            "terminus_coords": np.array([325.0, 1815.63, -2600.0]),
            "terminus_vox": np.array([241, 383, 109]),
            "region_sites": np.array([2]),
            "region_label": np.array([10]),
            "label_color": np.array([[0, 180, 100]]),
            "region_length": np.array([100.0]),
            "label_name": np.array(["Test region"]),
            "label_acronym": np.array(["TR"]),
            "vis_data": [
                {
                    "group_id": np.array([0]),
                    "start_loc": np.array([0.0]),
                    "end_loc": np.array([100.0]),
                    "sites": np.array([20.0, 40.0]),
                }
            ],
            "probe_type_name": "test",
            "sites_label": [np.array([10, 10])],
            "text_loc": np.array([50.0]),
            "trajectory_fit": fit,
            "reconstruction": {
                "atlas": {"voxel_size_um": 10.0},
                "probe": {"trajectory_fit": fit},
                "coordinates": {},
            },
        }

    def test_probe_window_explains_mapping_and_offers_csv_export(self):
        window = ProbeInfoWindow("probe one", self.probe_data())
        labels = [label.text() for label in window.findChildren(type(window.label))]

        self.assertEqual(
            window.export_btn.text(),
            "Export probe CSV files",
        )
        self.assertIn("AP tilt from vertical : ", labels)
        self.assertIn("Vertical depth change : ", labels)
        self.assertEqual(
            window.probe_region_text_items[0].toPlainText(),
            "TR: 2 contacts",
        )
        self.assertTrue(any(text.startswith("Good") for text in labels))

    def test_probe_window_export_uses_the_selected_path(self):
        window = ProbeInfoWindow("probe one", self.probe_data())

        with (
            patch(
                "herbs.object_control.QFileDialog.getSaveFileName",
                return_value=(
                    "/tmp/probe_export.csv",
                    "CSV files (*.csv)",
                ),
            ),
            patch(
                "herbs.object_control.write_probe_csv_files",
                return_value={
                    "contacts": "/tmp/probe_export_contacts.csv",
                    "trajectory": "/tmp/probe_export_trajectory.csv",
                    "regions": "/tmp/probe_export_regions.csv",
                },
            ) as writer,
            patch("herbs.object_control.QMessageBox.information") as message,
        ):
            window.export_coordinates()

        writer.assert_called_once_with(
            "/tmp/probe_export.csv", "probe one", window.probe_data
        )
        message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
