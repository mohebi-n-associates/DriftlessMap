"""Suggest which atlas plane, orientation and slice match a histology section.

The search is GUI-free and works on the atlas exactly as ``AtlasView``
displays it (``imageAxisOrder`` is row-major):

* coronal slice ``i``:    ``volume[:, :, i]``                (rows DV, columns ML)
* sagittal slice ``i``:   ``volume[:, i, :]``                (rows DV, columns AP)
* horizontal slice ``i``: ``volume[size0 - 1 - i, :, :]``    (rows ML, columns AP)

Stage 1 (this module's :func:`search_planes`) compares tissue silhouettes of
the section, in all eight rotations and flips, with every atlas slice. It is
reliable for choosing the plane and orientation. Silhouettes alone barely
change with depth, so depth is refined from internal anatomy separately.
"""

from dataclasses import dataclass

import cv2
import numpy as np


PLANES = ("coronal", "sagittal", "horizontal")
CANVAS = 192
FIT = 160
MAX_SLICES_PER_PLANE = 240


@dataclass(frozen=True)
class Orientation:
    """A rotation by ``quarter_turns`` x 90 degrees counter-clockwise,
    optionally followed by a horizontal mirror, applied to the histology to
    bring it into the atlas display frame."""

    quarter_turns: int
    mirrored: bool

    def apply(self, array):
        result = np.rot90(array, self.quarter_turns)
        return result[:, ::-1] if self.mirrored else result

    def describe(self):
        turns = {0: "no rotation", 1: "rotate 90° counter-clockwise",
                 2: "rotate 180°", 3: "rotate 90° clockwise"}[self.quarter_turns]
        return turns + (", then flip horizontally" if self.mirrored else "")


ORIENTATIONS = tuple(
    Orientation(turns, mirrored) for turns in range(4) for mirrored in (False, True)
)


@dataclass(frozen=True)
class Candidate:
    plane: str
    index: int
    orientation: Orientation
    silhouette: float


def tissue_mask(image):
    """Return the tissue mask of a histology image (H x W or H x W x C)."""
    image = np.asarray(image)
    if image.ndim == 3:
        planes = [
            cv2.normalize(image[..., c].astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
            for c in range(image.shape[2])
        ]
        gray = np.max(planes, axis=0)
    else:
        gray = cv2.normalize(image.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
    scale = 1024.0 / max(gray.shape)
    small = cv2.resize(gray, None, fx=min(1.0, scale), fy=min(1.0, scale),
                       interpolation=cv2.INTER_AREA) if scale < 1 else gray
    small = cv2.GaussianBlur(small, (0, 0), 2).astype(np.uint8)
    _, mask = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((9, 9), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count <= 1:
        raise ValueError("No tissue was found in the image.")
    largest = stats[1:, cv2.CC_STAT_AREA].max()
    keep = np.isin(labels, [i for i in range(1, count)
                            if stats[i, cv2.CC_STAT_AREA] > 0.02 * largest])
    keep = keep.astype(np.uint8) * 255
    # Fill holes (ventricles, tears) so the silhouette is the outer outline.
    flood = keep.copy()
    cv2.floodFill(flood, np.zeros((keep.shape[0] + 2, keep.shape[1] + 2), np.uint8), (0, 0), 255)
    filled = (keep | cv2.bitwise_not(flood)) > 0
    if filled.shape != gray.shape:
        filled = cv2.resize(filled.astype(np.uint8), (gray.shape[1], gray.shape[0]),
                            interpolation=cv2.INTER_NEAREST) > 0
    return filled


# Image axis that runs medio-laterally in each view (``None`` for sagittal,
# whose image contains no ML axis).
ML_AXIS = {"coronal": 1, "sagittal": None, "horizontal": 0}


def same_up_to_hemisphere(plane, first, second):
    """Whether two orientations differ only by a left-right mirror.

    The brain is nearly symmetric, so in coronal and horizontal views the
    silhouette cannot tell a section from its mirror image; the user decides.
    """
    probe = np.arange(12).reshape(3, 4)
    a, b = first.apply(probe), second.apply(probe)
    if a.shape == b.shape and np.array_equal(a, b):
        return True
    axis = ML_AXIS[plane]
    return axis is not None and a.shape == b.shape and np.array_equal(a, np.flip(b, axis))


def plane_length(shape, plane):
    return {"coronal": shape[2], "sagittal": shape[1], "horizontal": shape[0]}[plane]


def atlas_slice(volume, plane, index):
    """Return the 2-D slice that ``AtlasView`` shows for ``plane``/``index``."""
    if plane == "coronal":
        return volume[:, :, index]
    if plane == "sagittal":
        return volume[:, index, :]
    if plane == "horizontal":
        return volume[volume.shape[0] - 1 - index, :, :]
    raise ValueError("Unknown atlas plane {!r}.".format(plane))


def normalise(mask, *images, canvas=CANVAS, fit=FIT):
    """Crop to the mask's bounding box, scale its longest side to ``fit`` and
    centre on a ``canvas`` x ``canvas`` grid. Returns the mask then images."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        raise ValueError("The mask is empty.")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    scale = fit / max(y1 - y0, x1 - x0)
    width = max(1, int(round((x1 - x0) * scale)))
    height = max(1, int(round((y1 - y0) * scale)))
    oy, ox = (canvas - height) // 2, (canvas - width) // 2
    outputs = []
    for array, interpolation in [(mask, cv2.INTER_NEAREST)] + [
        (image, cv2.INTER_AREA) for image in images
    ]:
        crop = cv2.resize(np.asarray(array[y0:y1, x0:x1], dtype=np.float32),
                          (width, height), interpolation=interpolation)
        placed = np.zeros((canvas, canvas), np.float32)
        placed[oy:oy + height, ox:ox + width] = crop
        outputs.append(placed)
    outputs[0] = outputs[0] > 0.5
    return outputs


def _iou(a, b):
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def search_planes(histology, label_volume, planes=PLANES, progress=None):
    """Rank (plane, slice, orientation) triples by silhouette overlap.

    Returns candidates sorted best first. Slices are sampled so that at most
    ``MAX_SLICES_PER_PLANE`` are compared per plane.
    """
    mask = tissue_mask(histology)
    variants = [(orientation, normalise(orientation.apply(mask))[0])
                for orientation in ORIENTATIONS]
    shape = label_volume.shape
    total = sum(plane_length(shape, plane) for plane in planes)
    done = 0
    candidates = []
    for plane in planes:
        length = plane_length(shape, plane)
        step = max(1, int(np.ceil(length / MAX_SLICES_PER_PLANE)))
        for index in range(0, length, step):
            atlas_mask = atlas_slice(label_volume, plane, index) > 0
            if atlas_mask.sum() < 50:
                continue
            normalised = normalise(atlas_mask)[0]
            for orientation, variant in variants:
                candidates.append(
                    Candidate(plane, index, orientation, _iou(variant, normalised))
                )
            done += step
            if progress is not None:
                progress(min(1.0, done / total))
    candidates.sort(key=lambda candidate: candidate.silhouette, reverse=True)
    return candidates


def best_by_plane(candidates):
    """Return the best candidate of each plane, best plane first."""
    best = {}
    for candidate in candidates:
        best.setdefault(candidate.plane, candidate)
    return sorted(best.values(), key=lambda c: c.silhouette, reverse=True)
