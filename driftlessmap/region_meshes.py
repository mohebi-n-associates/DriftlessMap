"""Smooth 3-D surfaces of atlas regions, built from the label volume (2.8.5).

A region such as prelimbic area (PL) is labelled in the atlas as its layers
(PL1-PL6b); the processed atlas keeps a mesh per labelled structure, so a
checked region used to show as its layers' meshes, coarse and overlapping.
:func:`region_surface` instead makes one surface around the region and all
its sub-regions: their voxels on a strided copy, smoothed and cut at half,
as the fallback structure meshes are made (``obj_items.render_small_volume``),
in the same voxel frame.
"""

import math

import numpy as np
from scipy import ndimage as ndi

# The region is searched on a copy with at most this many voxels.
SEARCH_VOXELS = 20_000_000
# The surface is extracted from a crop of at most this many voxels.
SURFACE_VOXELS = 2_500_000
SMOOTHING = 1.0          # gaussian sigma, in voxels of the strided copy


def descendants(label_info, region_id):
    """``region_id`` and every region under it in ``label_info``'s tree."""
    children = {}
    for index, parent in zip(np.ravel(label_info["index"]), np.ravel(label_info["parent"])):
        children.setdefault(int(parent), []).append(int(index))
    found, stack = set(), [int(region_id)]
    while stack:
        current = stack.pop()
        if current not in found:
            found.add(current)
            stack.extend(children.get(current, []))
    return found


def region_surface(labels, ids):
    """``(vertices, faces)`` of a smooth surface around the voxels labelled with
    any of ``ids``, in the label volume's voxel indexes, or None when there are
    none."""
    import pyqtgraph as pg

    ids = np.asarray(sorted(int(i) for i in ids), dtype=np.int64)
    size = int(np.prod(labels.shape))
    stride = max(1, int(math.ceil((size / SEARCH_VOXELS) ** (1.0 / 3.0))))
    mask = np.isin(np.asarray(labels[::stride, ::stride, ::stride]), ids)
    if not mask.any():
        return None
    # Crop to the region, and coarsen a large one so extraction stays quick.
    found = np.argwhere(mask)
    low, high = found.min(axis=0), found.max(axis=0) + 1
    crop = int(np.prod(high - low))
    extra = max(1, int(math.ceil((crop / SURFACE_VOXELS) ** (1.0 / 3.0))))
    if extra > 1:
        stride *= extra
        mask = np.isin(np.asarray(labels[::stride, ::stride, ::stride]), ids)
        found = np.argwhere(mask)
        low, high = found.min(axis=0), found.max(axis=0) + 1
    pad = 3
    low = np.maximum(low - pad, 0)
    high = np.minimum(high + pad, mask.shape)
    block = mask[low[0]:high[0], low[1]:high[1], low[2]:high[2]].astype(np.float32)
    # Pad with empty voxels so a region touching the volume's edge is closed.
    block = np.pad(block, 1)
    smooth = ndi.gaussian_filter(block, SMOOTHING)
    vertices, faces = pg.isosurface(smooth, 0.5)
    if not len(faces):
        return None
    vertices = (np.asarray(vertices, dtype=float) - 1 + low) * stride
    return vertices, np.asarray(faces, dtype=np.int32)
