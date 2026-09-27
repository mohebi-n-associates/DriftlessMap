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
    "probe_reconstruction", ROOT / "driftlessmap" / "probe_reconstruction.py"
)
persistence = load_module("persistence", ROOT / "driftlessmap" / "persistence.py")


class CoordinateTransformTests(unittest.TestCase):
    ALLEN_25 = {
        "to_HERBS": (2, 0, 1),
        "from_HERBS": (1, 2, 0),
        "direction_change": (True, True, False),
        "size": (528, 320, 456),
    }

    def test_allen_transform_round_trips_continuous_coordinates(self):
        axis_info = reconstruction.normalize_axis_info(self.ALLEN_25, (456, 528, 320))
        source_vox = np.array(
            [[100.25, 80.5, 120.75], [0.0, 319.0, 455.0], [527.9, 0.1, 3.0]]
        )
        herbs_vox = reconstruction.source_vox_to_herbs_vox(source_vox, axis_info)
        recovered = reconstruction.herbs_vox_to_source_vox(herbs_vox, axis_info)
        np.testing.assert_allclose(recovered, source_vox)

    def test_exported_source_voxel_holds_the_sampled_label(self):
        from driftlessmap.atlas_transform import transform_atlas_volumes

        source_shape = (12, 9, 7)
        rng = np.random.default_rng(3)
        source_labels = rng.integers(1, 50, size=source_shape)
        axis_info = {
            "to_HERBS": (2, 0, 1),
            "from_HERBS": (1, 2, 0),
            "direction_change": (True, True, False),
            "size": source_shape,
        }
        _, herbs_labels, _ = transform_atlas_volumes(
            source_labels, source_labels, (1, 1, 1), axis_info
        )
        normalized = reconstruction.normalize_axis_info(axis_info, herbs_labels.shape)
        continuous = rng.uniform(0, 1, size=(500, 3)) * np.asarray(herbs_labels.shape)
        integer = rng.integers(0, herbs_labels.shape, size=(100, 3)).astype(float)
        for points in (continuous, integer):
            sampled = herbs_labels[tuple(np.floor(points).astype(int).T)]
            source = reconstruction.herbs_vox_to_source_vox(points, normalized)
            exported = source_labels[tuple(np.floor(source).astype(int).T)]
            np.testing.assert_array_equal(exported, sampled)

    def test_view_rows_map_to_the_matching_source_voxel(self):
        # A point inside coronal view row 400 lies at HERBS DV 800 - 400 - f;
        # its Allen DV source voxel is row 400 itself.
        axis_info = dict(self.ALLEN_25, size=(1320, 800, 1140))
        source = reconstruction.volume_view_vox_to_source_vox(
            np.array([[400.3, 570.6, 779.0]]), (800, 1140, 1320), axis_info
        )
        self.assertEqual(int(np.floor(source[0, 1])), 400)

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

        self.assertEqual(payload["schema_version"], 2)
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
        track = payload["coordinates"]["track"]
        self.assertEqual(track["ordering"], "insertion-to-tip")
        self.assertEqual(track["count"], 6)
        np.testing.assert_allclose(
            track["axial_distance_up_from_tip_um"],
            [10000, 8000, 6000, 4000, 2000, 0],
        )
        self.assertEqual(track["structure_acronym"], ["R10"] * 3 + ["R11"] * 3)

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
