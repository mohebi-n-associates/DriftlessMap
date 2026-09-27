"""Tiny processed-atlas folder for integration tests."""

from pathlib import Path
import pickle

import numpy as np


def _dump(path, value):
    with Path(path).open("wb") as stream:
        pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)


def _cube_mesh(offset=0.0):
    import pyqtgraph.opengl as gl

    vertexes = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float32
    ) + offset
    faces = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]], dtype=np.uint32)
    return gl.MeshData(vertexes=vertexes, faces=faces)


def make_processed_atlas(folder, shape=(40, 32, 24), voxel_size=25):
    """Write a minimal processed atlas and return its folder.

    ``shape`` is the stored (anterior, dorsal, right) volume shape. The brain
    is a box filled with label 10 (``child``) whose dorsal half is label 20
    (``grandchild``); the outside is 0.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    atlas = np.zeros(shape, dtype=np.uint8)
    labels = np.zeros(shape, dtype=np.int32)
    inner = tuple(slice(4, n - 4) for n in shape)
    atlas[inner] = 120
    labels[inner] = 10
    dorsal = (inner[0], slice(4, shape[1] // 2), inner[2])
    labels[dorsal] = 20

    bregma = [shape[0] // 2, 4, shape[2] // 2]
    atlas_info = [
        {"name": "anterior", "values": np.arange(shape[0]) * voxel_size, "units": "um"},
        {"name": "dorsal", "values": np.arange(shape[1]) * voxel_size, "units": "um"},
        {"name": "right", "values": np.arange(shape[2]) * voxel_size, "units": "um"},
        {"vxsize": voxel_size, "Bregma": bregma},
    ]
    _dump(folder / "atlas_pre_made.pkl", {"data": atlas, "info": atlas_info})
    _dump(
        folder / "segment_pre_made.pkl",
        {"data": labels, "unique_label": np.array([0, 10, 20])},
    )
    _dump(
        folder / "atlas_labels.pkl",
        {
            "index": np.array([1, 10, 20]),
            "label": np.array(["root", "child", "grandchild"]),
            "parent": np.array([0, 1, 10]),
            "abbrev": np.array(["root", "CH", "GC"]),
            "color": np.array([[255, 255, 255], [200, 100, 50], [50, 100, 200]]),
            "level_indicator": [1, 2, 3],
        },
    )
    _dump(folder / "atlas_meshdata.pkl", _cube_mesh())
    _dump(
        folder / "atlas_small_meshdata.pkl",
        {"10": _cube_mesh(1.0), "20": _cube_mesh(2.0)},
    )
    return folder
