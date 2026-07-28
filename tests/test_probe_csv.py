import csv
from pathlib import Path
import tempfile
import unittest

import numpy as np

from driftlessmap.probe_csv import (
    iter_probe_contact_rows,
    iter_probe_region_rows,
    iter_probe_track_rows,
    probe_trajectory_row,
    write_probe_csv_files,
)
from driftlessmap.probe_reconstruction import build_probe_reconstruction


def probe_data():
    trajectory_fit = {
        "method": "robust orthogonal 3D line fit",
        "surface_method": "3D fitted-line intersection with atlas brain mask",
        "point_count": 4,
        "inlier_count": 3,
        "rms_error_um": 4.5,
        "max_error_um": 80.0,
        "explained_fraction": 0.99,
        "surface_adjustment_um": 125.0,
    }
    reconstruction = build_probe_reconstruction(
        insertion_bregma_vox=np.array([0.0, 0.0, 1.0]),
        terminus_bregma_vox=np.array([0.0, 0.0, -4.0]),
        insertion_vox_index=np.array([228, 263, 160]),
        terminus_vox_index=np.array([228, 263, 155]),
        contact_bregma_vox=[
            np.array([[0.0, 0.0, -3.5], [0.0, 0.0, -2.5]]),
            np.array([[0.5, 0.0, -3.75]]),
        ],
        contact_vox_index=[
            np.array([[228, 263, 155], [228, 263, 156]]),
            np.array([[228, 263, 155]]),
        ],
        contact_structure_ids=[np.array([10, 11]), np.array([10])],
        contact_local_from_tip_base_um=[
            np.array([[10.0, -8.0, 12.0], [50.0, -8.0, 12.0]]),
            np.array([[30.0, 16.0, 12.0]]),
        ],
        track_bregma_vox=np.array(
            [[0.0, 0.0, value] for value in np.linspace(1.0, -4.0, 6)]
        ),
        track_vox_index=np.array(
            [[228, 263, value] for value in range(160, 154, -1)]
        ),
        track_structure_ids=np.array([10, 10, 10, 11, 11, 11]),
        track_axial_depth_from_insertion_um=np.linspace(0, 10000, 6),
        probe_length_um=10000,
        probe_settings={"probe_type_name": "test", "tip_length": 175},
        site_face="Front",
        voxel_size_um=25,
        bregma_herbs_vox=np.array([228.0, 263.0, 159.0]),
        herbs_atlas_shape=(456, 528, 320),
        label_info={
            "index": np.array([10, 11]),
            "label": np.array(["Region ten", "Region eleven"]),
            "abbrev": np.array(["R10", "R11"]),
            "parent": np.array([0, 10]),
            "color": np.array([[1, 2, 3], [4, 5, 6]]),
            "level_indicator": [1, 2],
        },
        axis_info={
            "to_HERBS": (2, 0, 1),
            "from_HERBS": (1, 2, 0),
            "direction_change": (True, True, False),
            "size": (528, 320, 456),
        },
        atlas_identifier="allen_mouse_25um",
        trajectory_fit=trajectory_fit,
    )
    return {
        "probe_type_name": "test",
        "ap_angle": 11.67,
        "ap_tilt": "posterior",
        "ml_angle": 2.5,
        "ml_tilt": "medial",
        "probe_length": 10000.0,
        "dv": 9500.0,
        "trajectory_fit": trajectory_fit,
        "region_label": np.array([10, 11]),
        "label_name": np.array(["Region ten", "Region eleven"]),
        "label_acronym": np.array(["R10", "R11"]),
        "region_sites": np.array([2, 1]),
        "region_length": np.array([600.0, 400.0]),
        "reconstruction": reconstruction,
    }


class ProbeCsvTests(unittest.TestCase):
    def test_contacts_are_depth_sorted_with_unambiguous_distance_names(self):
        rows = list(iter_probe_contact_rows("probe one", probe_data()))

        self.assertEqual([row["site_index"] for row in rows], [0, 2, 1])
        self.assertEqual(
            [row["depth_rank_deepest_first"] for row in rows],
            [0, 1, 2],
        )
        self.assertEqual(
            [row["axial_distance_up_from_tip_um"] for row in rows],
            [185, 205, 225],
        )
        self.assertEqual(
            [row["axial_depth_from_insertion_um"] for row in rows],
            [9815, 9795, 9775],
        )
        self.assertEqual(rows[0]["structure_acronym"], "R10")
        self.assertEqual(rows[0]["probe_lateral_um"], -8)
        self.assertIn("allen_AP_vox", rows[0])
        self.assertNotIn("record_type", rows[0])
        self.assertNotIn("distance_from_tip_um", rows[0])
        self.assertTrue(all(value != "" for row in rows for value in row.values()))

    def test_trajectory_and_region_rows_have_dedicated_schemas(self):
        data = probe_data()
        trajectory = probe_trajectory_row("probe one", data)
        regions = list(iter_probe_region_rows("probe one", data))

        self.assertEqual(trajectory["insertion_to_tip_length_um"], 10000)
        self.assertEqual(trajectory["fit_inliers"], 3)
        self.assertEqual(trajectory["reconstruction_schema_version"], 2)
        self.assertEqual(trajectory["tip_to_lowest_contact_center_um"], 185)
        self.assertEqual(trajectory["track_sampling_interval_um"], 2000)
        self.assertIn("insertion_allen_AP_vox", trajectory)
        self.assertIn("tip_allen_AP_vox", trajectory)
        self.assertNotIn("structure_id", trajectory)
        self.assertTrue(all(value != "" for value in trajectory.values()))

        self.assertEqual(len(regions), 2)
        self.assertEqual(regions[1]["structure_name"], "Region eleven")
        self.assertEqual(regions[1]["contact_count"], 1)
        self.assertEqual(regions[1]["path_length_um"], 400)
        self.assertNotIn("herbs_ML_vox", regions[1])
        self.assertTrue(
            all(value != "" for row in regions for value in row.values())
        )

    def test_track_rows_are_in_insertion_to_tip_order(self):
        rows = list(iter_probe_track_rows("probe one", probe_data()))

        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["axial_depth_from_insertion_um"], 0)
        self.assertEqual(rows[0]["axial_distance_up_from_tip_um"], 10000)
        self.assertEqual(rows[-1]["axial_depth_from_insertion_um"], 10000)
        self.assertEqual(rows[-1]["axial_distance_up_from_tip_um"], 0)
        self.assertEqual(rows[0]["structure_acronym"], "R10")
        self.assertEqual(rows[-1]["structure_acronym"], "R11")
        self.assertIn("allen_AP_vox", rows[0])

    def test_writer_creates_four_consistent_csv_files(self):
        with tempfile.TemporaryDirectory() as folder:
            selected_path = Path(folder) / "probe_export.csv"
            paths = write_probe_csv_files(
                selected_path, "probe one", probe_data()
            )

            self.assertEqual(
                paths,
                {
                    "contacts": Path(folder) / "probe_export_contacts.csv",
                    "track": Path(folder) / "probe_export_track.csv",
                    "trajectory": (
                        Path(folder) / "probe_export_trajectory.csv"
                    ),
                    "regions": Path(folder) / "probe_export_regions.csv",
                },
            )
            tables = {}
            for table_name, path in paths.items():
                with path.open(newline="", encoding="utf-8") as csv_file:
                    tables[table_name] = list(csv.DictReader(csv_file))

        self.assertEqual(len(tables["contacts"]), 3)
        self.assertEqual(len(tables["track"]), 6)
        self.assertEqual(len(tables["trajectory"]), 1)
        self.assertEqual(len(tables["regions"]), 2)
        self.assertNotIn("record_type", tables["contacts"][0])
        self.assertIn("structure_id", tables["track"][0])
        self.assertNotIn("structure_id", tables["trajectory"][0])
        self.assertNotIn("herbs_ML_vox", tables["regions"][0])

    def test_legacy_probe_requires_reconstruction_before_export(self):
        with self.assertRaisesRegex(ValueError, "Re-merge"):
            list(iter_probe_contact_rows("legacy probe", {}))


if __name__ == "__main__":
    unittest.main()
