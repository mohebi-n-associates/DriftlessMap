import csv
from pathlib import Path
import tempfile
import unittest

import numpy as np

from herbs.probe_csv import iter_probe_csv_rows, write_probe_csv
from herbs.probe_reconstruction import build_probe_reconstruction


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
    def test_rows_include_endpoints_contacts_and_region_summary(self):
        rows = list(iter_probe_csv_rows("probe one", probe_data()))

        self.assertEqual(
            [row["record_type"] for row in rows],
            [
                "insertion",
                "tip",
                "contact",
                "contact",
                "contact",
                "region_summary",
                "region_summary",
            ],
        )
        contact = rows[2]
        self.assertEqual(contact["site_index"], 0)
        self.assertEqual(contact["column_index"], 0)
        self.assertEqual(contact["structure_acronym"], "R10")
        self.assertEqual(contact["probe_lateral_um"], -8)
        self.assertEqual(contact["probe_surface_normal_um"], 12)
        self.assertIn("allen_AP_vox", contact)
        self.assertEqual(contact["fit_inliers"], 3)
        self.assertEqual(contact["AP_tilt_direction"], "posterior")

        region = rows[-1]
        self.assertEqual(region["structure_name"], "Region eleven")
        self.assertEqual(region["region_contact_count"], 1)
        self.assertEqual(region["region_path_length_um"], 400)

    def test_writer_creates_a_standard_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.csv"
            write_probe_csv(path, "probe one", probe_data())

            with path.open(newline="", encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))

        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["record_type"], "insertion")
        self.assertEqual(rows[2]["record_type"], "contact")
        self.assertEqual(rows[2]["structure_acronym"], "R10")
        self.assertEqual(rows[-1]["record_type"], "region_summary")

    def test_legacy_probe_requires_reconstruction_before_export(self):
        with self.assertRaisesRegex(ValueError, "Re-merge"):
            list(iter_probe_csv_rows("legacy probe", {}))


if __name__ == "__main__":
    unittest.main()
