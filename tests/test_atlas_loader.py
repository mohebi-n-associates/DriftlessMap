import importlib.util
from pathlib import Path
import pickle
import sys
import tempfile
import types
import unittest

import numpy as np


PACKAGE_PATH = Path(__file__).parents[1] / "herbs"
PACKAGE_NAME = "_herbs_atlas_loader_test"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault(PACKAGE_NAME, package)
SPEC = importlib.util.spec_from_file_location(
    "{}.atlas_loader".format(PACKAGE_NAME), PACKAGE_PATH / "atlas_loader.py"
)
atlas_loader = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = atlas_loader
SPEC.loader.exec_module(atlas_loader)


def dump(path, data):
    with Path(path).open("wb") as stream:
        pickle.dump(data, stream)


class AtlasLoaderFailureTests(unittest.TestCase):
    def test_read_failure_returns_none_instead_of_unbound_local(self):
        data, success = atlas_loader.check_data_path_and_load("missing.nrrd")
        self.assertIsNone(data)
        self.assertFalse(success)

    def test_raw_processing_failures_keep_six_item_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            result = atlas_loader.process_atlas_raw_data(
                folder,
                data_file="missing.nii.gz",
                segmentation_file="missing.nii.gz",
                bregma_coordinates=(1, 1, 1),
                lambda_coordinates=(1, 1, 1),
                voxel_size=25,
            )
        self.assertEqual(len(result), 6)
        self.assertIn("does not exist", result[-1])

    def test_boundaries_cannot_override_missing_core_files(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in (
                "sagital_contour_pre_made.pkl",
                "coronal_contour_pre_made.pkl",
                "horizontal_contour_pre_made.pkl",
            ):
                dump(Path(folder) / name, np.zeros((2, 2, 2)))

            loaded = atlas_loader.AtlasLoader(folder)
            self.assertFalse(loaded.success)
            self.assertIsNone(loaded.atlas_data)

    def test_one_corrupt_boundary_keeps_load_unsuccessful(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            volume = np.zeros((2, 2, 2))
            dump(folder / "atlas_labels.pkl", {"index": np.array([0])})
            dump(folder / "atlas_pre_made.pkl", {"data": volume, "info": []})
            dump(
                folder / "segment_pre_made.pkl",
                {"data": volume.astype(int), "unique_label": np.array([0])},
            )
            dump(folder / "sagital_contour_pre_made.pkl", volume)
            (folder / "coronal_contour_pre_made.pkl").write_bytes(b"broken")
            dump(folder / "horizontal_contour_pre_made.pkl", volume)

            loaded = atlas_loader.AtlasLoader(folder)
            self.assertFalse(loaded.success)
            self.assertIsNone(loaded.boundary)

    def test_gui_loading_compacts_core_volumes_and_skips_boundary_caches(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            volume = np.arange(24, dtype=np.float64).reshape(2, 3, 4)
            labels = np.arange(24, dtype=np.int64).reshape(2, 3, 4)
            dump(folder / "atlas_labels.pkl", {"index": np.array([0])})
            dump(
                folder / "atlas_pre_made.pkl",
                {"data": volume, "info": [{"example": True}]},
            )
            dump(
                folder / "segment_pre_made.pkl",
                {"data": labels, "unique_label": np.unique(labels)},
            )

            loaded = atlas_loader.AtlasLoader(folder, load_boundaries=False)

        self.assertTrue(loaded.success)
        self.assertEqual(loaded.atlas_data.dtype, np.float32)
        self.assertEqual(loaded.segmentation_data.dtype, np.int32)
        self.assertIsNone(loaded.boundary)


if __name__ == "__main__":
    unittest.main()
