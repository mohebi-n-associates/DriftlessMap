import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


ROOT = Path(__file__).parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reconstruction = load_module(
    "probe_reconstruction", ROOT / "herbs" / "probe_reconstruction.py"
)
persistence = load_module("persistence", ROOT / "herbs" / "persistence.py")


class CoordinateTransformTests(unittest.TestCase):
    def test_allen_transform_can_be_inverted_for_continuous_coordinates(self):
        axis_info = reconstruction.normalize_axis_info(
            {
                "to_HERBS": (2, 0, 1),
                "from_HERBS": (1, 2, 0),
                "direction_change": (True, True, False),
                "size": (528, 320, 456),
            },
            (456, 528, 320),
        )
        source_vox = np.array([[100.25, 80.5, 120.75]])
        flipped = source_vox.copy()
        flipped[:, 0] = 527 - flipped[:, 0]
        flipped[:, 1] = 319 - flipped[:, 1]
        herbs_vox = flipped[:, [2, 0, 1]]

        recovered = reconstruction.herbs_vox_to_source_vox(
            herbs_vox, axis_info
        )
        np.testing.assert_allclose(recovered, source_vox)

    def test_mismatched_atlas_shape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            reconstruction.normalize_axis_info(
                {
                    "to_HERBS": (2, 0, 1),
                    "direction_change": (True, True, False),
                    "size": (528, 320, 456),
                },
                (456, 527, 320),
            )

    def test_volume_view_coordinates_recover_raw_allen_axes(self):
        axis_info = {
            "to_HERBS": (2, 0, 1),
            "from_HERBS": (1, 2, 0),
            "direction_change": (True, True, False),
            "size": (1320, 800, 1140),
        }

        source = reconstruction.volume_view_vox_to_source_vox(
            np.array([44, 570, 779]),
            (800, 1140, 1320),
            axis_info,
        )

        np.testing.assert_allclose(source, [540, 44, 570])

    def test_community_allen_transform_has_explicit_sign_conventions(self):
        at_bregma = reconstruction.allen_ccf_to_estimated_bregma_mm(
            [5400, 440, 5700]
        )
        anterior = reconstruction.allen_ccf_to_estimated_bregma_mm(
            [4400, 440, 6700]
        )

        np.testing.assert_allclose(at_bregma, [0, 0, 0], atol=1e-12)
        self.assertGreater(anterior[0], 0)
        self.assertLess(anterior[1], 0)
        self.assertEqual(anterior[2], 1)

    def test_estimated_bregma_defaults_are_nearest_resolution_voxels(self):
        expected = {
            10: [540, 44, 570],
            25: [216, 18, 228],
            50: [108, 9, 114],
        }

        for resolution, voxel in expected.items():
            np.testing.assert_array_equal(
                reconstruction.allen_ccf_estimated_bregma_vox(resolution),
                voxel,
            )

    def test_status_report_prioritizes_targeting_coordinates(self):
        report = reconstruction.format_estimated_bregma_report(
            [2.404, 6.709, 1.869],
            7708,
            "[385]VISp: Primary visual area",
        )

        self.assertEqual(
            report,
            "Bregma est.: AP +2.40 mm | ML +1.87 mm | "
            "Depth 7.71 mm from surface | [385]VISp: Primary visual area",
        )
        self.assertNotIn("affine", report)
        self.assertNotIn("ground truth", report)
        self.assertNotIn("CCF voxel", report)


class ProbeReconstructionTests(unittest.TestCase):
    def make_payload(self):
        bregma = np.array([228.0, 263.0, 159.0])
        return reconstruction.build_probe_reconstruction(
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
            bregma_herbs_vox=bregma,
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
            atlas_path="/atlas/allen_mouse_25um",
            software_version="0.2.8.1",
        )

    def test_payload_is_self_contained_and_contact_order_is_explicit(self):
        payload = self.make_payload()
        atlas = payload["atlas"]
        contacts = payload["coordinates"]["contacts"]

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(atlas["source_version"], "CCFv3 2017")
        self.assertEqual(atlas["source_axes"], ["AP", "DV", "LR"])
        self.assertEqual(tuple(atlas["source_shape_vox"]), (528, 320, 456))
        self.assertEqual(contacts["count"], 3)
        np.testing.assert_array_equal(contacts["site_index"], [0, 1, 2])
        np.testing.assert_array_equal(contacts["column_index"], [0, 0, 1])
        np.testing.assert_array_equal(contacts["index_in_column"], [0, 1, 0])
        np.testing.assert_allclose(
            contacts["distance_from_tip_um"], [185, 225, 205]
        )
        np.testing.assert_allclose(
            contacts["axial_distance_up_from_tip_um"], [185, 225, 205]
        )
        np.testing.assert_allclose(
            contacts["axial_depth_from_insertion_um"],
            [9815, 9775, 9795],
        )
        self.assertEqual(contacts["structure_acronym"], ["R10", "R11", "R10"])
        np.testing.assert_allclose(
            contacts["allen_ccf_um"], contacts["source_um"]
        )
        np.testing.assert_allclose(
            contacts["estimated_stereotaxic_bregma_mm"],
            reconstruction.allen_ccf_to_estimated_bregma_mm(
                contacts["allen_ccf_um"]
            ),
        )
        transform = atlas["estimated_stereotaxic_transform"]
        self.assertFalse(transform["ground_truth"])
        self.assertIn("brain surface", transform["targeting_note"])

    def test_payload_round_trips_inside_one_herbs_object(self):
        data = {
            "type": "merged probe",
            "data": {"reconstruction": self.make_payload()},
            "name": "probe-1",
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe-1.herbsobj"
            success, error = persistence.save_herbs_file(path, data, "object")
            self.assertTrue(success, error)

            loaded, error = persistence.load_herbs_file(path, "object")
            self.assertIsNone(error)
            contacts = loaded["data"]["reconstruction"]["coordinates"]["contacts"]
            np.testing.assert_array_equal(contacts["site_index"], [0, 1, 2])
            np.testing.assert_allclose(
                contacts["allen_ccf_um"], contacts["source_um"]
            )


if __name__ == "__main__":
    unittest.main()
