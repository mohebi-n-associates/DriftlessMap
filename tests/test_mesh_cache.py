import os
from pathlib import Path
import pickle
import tempfile
import unittest

import numpy as np
import pyqtgraph.opengl as gl

from driftlessmap.obj_items import load_mesh_file


class MeshCacheSafetyTests(unittest.TestCase):
    def _write(self, folder, name, value):
        path = Path(folder) / name
        with path.open("wb") as stream:
            pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
        return path

    def _mesh(self):
        vertexes = np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32
        )
        faces = np.array([[0, 1, 2], [0, 1, 3]], dtype=np.uint32)
        return gl.MeshData(vertexes=vertexes, faces=faces)

    def test_whole_brain_and_region_meshes_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            single = self._write(folder, "atlas_meshdata.pkl", self._mesh())
            many = self._write(
                folder, "atlas_small_meshdata.pkl", {"10": self._mesh()}
            )

            md = load_mesh_file(single)
            self.assertIsInstance(md, gl.MeshData)
            np.testing.assert_array_equal(md.faces(), self._mesh().faces())
            np.testing.assert_array_equal(md.vertexes(), self._mesh().vertexes())

            region_meshes = load_mesh_file(many)
            self.assertEqual(list(region_meshes), ["10"])
            self.assertIsInstance(region_meshes["10"], gl.MeshData)

    def test_executable_mesh_pickle_is_rejected_without_running(self):
        class Malicious:
            def __reduce__(self):
                return os.system, ("touch {}".format(marker),)

        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "executed"
            path = self._write(folder, "atlas_meshdata.pkl", Malicious())
            with self.assertRaisesRegex(ValueError, "unsupported type"):
                load_mesh_file(path)
            self.assertFalse(marker.exists())

    def test_mesh_with_out_of_range_faces_is_rejected(self):
        mesh = self._mesh()
        mesh._faces = np.array([[0, 1, 99]], dtype=np.uint32)
        with tempfile.TemporaryDirectory() as folder:
            path = self._write(folder, "atlas_meshdata.pkl", mesh)
            with self.assertRaisesRegex(ValueError, "missing vertexes"):
                load_mesh_file(path)

    def test_non_mesh_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self._write(folder, "atlas_meshdata.pkl", {"a": 1})
            with self.assertRaisesRegex(ValueError, "does not contain mesh"):
                load_mesh_file(path)


if __name__ == "__main__":
    unittest.main()
