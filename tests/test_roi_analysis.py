import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from driftlessmap.roi_analysis import (
    build_drawing_roi_info,
    iter_roi_csv_rows,
    write_roi_csv,
)


class DrawingRoiAnalysisTests(unittest.TestCase):
    def test_allen_origin_reports_zero_estimated_bregma(self):
        info = build_drawing_roi_info(
            [np.array([[0.0, 0.0, 0.0]])],
            ["area drawing - piece"],
            bregma_herbs_vox=[570, 779, 755],
            voxel_size_um=10,
            herbs_shape=(1140, 1320, 800),
            axis_info={
                "to_HERBS": (2, 0, 1),
                "from_HERBS": (1, 2, 0),
                "direction_change": (True, True, False),
                "size": (1320, 800, 1140),
            },
        )

        self.assertEqual(info["coordinate_basis"], "Estimated Allen Bregma")
        self.assertFalse(info["ground_truth"])
        np.testing.assert_allclose(
            info["coordinates"]["allen_ccf_vox"][0], [540, 44, 570]
        )
        np.testing.assert_allclose(
            info["coordinates"]["estimated_stereotaxic_bregma_mm"][0],
            [0, 0, 0],
            atol=1e-12,
        )
        self.assertAlmostEqual(info["metric_value"], 0.0001)

    def test_custom_coordinates_surface_depth_and_regions_are_summarized(self):
        labels = np.zeros((3, 2, 7), dtype=int)
        labels[1, 0, 1:6] = 10
        pieces = [np.array([[0.0, 0.0, 2.0], [0.0, 0.0, 5.0]])]

        info = build_drawing_roi_info(
            pieces,
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

        self.assertEqual(info["coordinate_basis"], "Configured atlas Bregma")
        self.assertEqual(info["metric_name"], "line_length_mm")
        self.assertAlmostEqual(info["metric_value"], 0.03)
        np.testing.assert_allclose(
            info["coordinates"]["surface_depth_mm"], [0.03, 0.0]
        )
        self.assertAlmostEqual(info["surface_depth_summary"]["mean"], 0.015)
        self.assertEqual(
            info["regions"],
            [
                {
                    "label_id": 10,
                    "name": "Test region",
                    "acronym": "TR",
                    "color": (1, 2, 3),
                    "count": 2,
                    "percentage": 100.0,
                }
            ],
        )
        self.assertAlmostEqual(
            info["coordinate_summary"]["DV"]["centroid"], -0.035
        )

    def test_line_length_does_not_bridge_separate_pieces(self):
        info = build_drawing_roi_info(
            [
                np.array([[0, 0, 0], [3, 4, 0]]),
                np.array([[100, 100, 0], [100, 102, 0]]),
            ],
            ["line drawing - piece", "line drawing - piece"],
            bregma_herbs_vox=[0, 0, 0],
            voxel_size_um=10,
            herbs_shape=(200, 200, 10),
        )

        self.assertAlmostEqual(info["metric_value"], 0.07)

    def test_csv_contains_allen_and_anatomical_coordinates(self):
        info = build_drawing_roi_info(
            [np.array([[0.0, 0.0, 0.0]])],
            ["area drawing - piece"],
            bregma_herbs_vox=[570, 779, 755],
            voxel_size_um=10,
            herbs_shape=(1140, 1320, 800),
            axis_info={
                "to_HERBS": (2, 0, 1),
                "from_HERBS": (1, 2, 0),
                "direction_change": (True, True, False),
                "size": (1320, 800, 1140),
            },
        )

        row = next(iter_roi_csv_rows(info))
        self.assertEqual(row["piece"], 1)
        self.assertEqual(row["structure_acronym"], "")
        self.assertEqual(row["allen_AP_vox"], 540.0)
        self.assertEqual(row["estimated_AP_mm"], 0.0)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "roi.csv"
            write_roi_csv(path, info)
            with path.open(newline="", encoding="utf-8") as csv_file:
                exported = list(csv.DictReader(csv_file))
        self.assertEqual(len(exported), 1)
        self.assertEqual(exported[0]["structure_name"], "")
        self.assertEqual(exported[0]["affine_DV_mm_not_for_targeting"], "0.0")

    def test_out_of_bounds_points_are_exported_as_unlabeled(self):
        labels = np.ones((2, 2, 2), dtype=int)
        info = build_drawing_roi_info(
            [np.array([[5.0, 5.0, 5.0]])],
            ["area drawing - piece"],
            bregma_herbs_vox=[0, 0, 0],
            voxel_size_um=25,
            herbs_shape=labels.shape,
            label_volume=labels,
        )

        self.assertEqual(info["structure_ids"][0], 0)
        self.assertEqual(info["regions"][0]["name"], "Outside atlas / unlabeled")
        self.assertTrue(
            np.isnan(info["coordinates"]["surface_depth_mm"][0])
        )


if __name__ == "__main__":
    unittest.main()
