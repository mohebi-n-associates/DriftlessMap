import os
from pathlib import Path
import pickle
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from driftlessmap.atlas_loader import (
    AtlasLoader,
    begin_atlas_processing,
    finish_atlas_processing,
)
from driftlessmap.persistence import write_cache_pickle
from tests.atlas_fixture import make_processed_atlas


class AtlasCacheIntegrityTests(unittest.TestCase):
    def test_interrupted_processing_marks_the_folder_unusable(self):
        with tempfile.TemporaryDirectory() as folder:
            atlas = make_processed_atlas(Path(folder) / "atlas")
            self.assertTrue(AtlasLoader(str(atlas), load_boundaries=False).success)

            begin_atlas_processing(str(atlas))
            loaded = AtlasLoader(str(atlas), load_boundaries=False)
            self.assertFalse(loaded.success)
            self.assertIn("did not finish", loaded.msg)

            finish_atlas_processing(str(atlas))
            self.assertTrue(AtlasLoader(str(atlas), load_boundaries=False).success)

    def test_cache_writes_replace_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "segment_pre_made.pkl"
            write_cache_pickle(path, {"data": [1, 2, 3]})
            with path.open("rb") as stream:
                self.assertEqual(pickle.load(stream), {"data": [1, 2, 3]})

            class Unpicklable:
                def __reduce__(self):
                    raise RuntimeError("stop mid-write")

            with self.assertRaises(RuntimeError):
                write_cache_pickle(path, {"data": Unpicklable()})
            with path.open("rb") as stream:
                self.assertEqual(pickle.load(stream), {"data": [1, 2, 3]})
            self.assertEqual(
                [p.name for p in Path(folder).iterdir()], ["segment_pre_made.pkl"]
            )


if __name__ == "__main__":
    unittest.main()
