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


def normalise(mask, *images, canvas=CANVAS, fit=FIT, labels=None):
    """Crop to the mask's bounding box, scale its longest side to ``fit`` and
    centre on a ``canvas`` x ``canvas`` grid.

    Returns the mask, then each image, then ``labels`` (resampled with
    nearest-neighbour interpolation) when given.
    """
    ys, xs = np.nonzero(mask)
    if not len(ys):
        raise ValueError("The mask is empty.")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    scale = fit / max(y1 - y0, x1 - x0)
    width = max(1, int(round((x1 - x0) * scale)))
    height = max(1, int(round((y1 - y0) * scale)))
    oy, ox = (canvas - height) // 2, (canvas - width) // 2
    arrays = [(mask, cv2.INTER_NEAREST)] + [(image, cv2.INTER_AREA) for image in images]
    if labels is not None:
        arrays.append((labels, cv2.INTER_NEAREST))
    outputs = []
    for array, interpolation in arrays:
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


@dataclass(frozen=True)
class DepthMatch:
    """How well one slice of the chosen plane matches the section."""

    index: int
    silhouette: float
    template_edges: float
    label_edges: float
    score: float


def histology_gray(image):
    """Luminance with local contrast equalised, as 8-bit."""
    image = np.asarray(image)
    if image.ndim == 3:
        gray = image[..., :3].astype(np.float32).mean(axis=2)
    else:
        gray = image.astype(np.float32)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)


def _edges(image, mask):
    blurred = cv2.GaussianBlur(image.astype(np.float32), (0, 0), 1.5)
    magnitude = np.hypot(cv2.Sobel(blurred, cv2.CV_32F, 1, 0),
                         cv2.Sobel(blurred, cv2.CV_32F, 0, 1))
    inner = cv2.erode(mask.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    magnitude[~inner] = 0  # compare internal anatomy, not the outline
    return magnitude, inner


def _label_boundaries(labels):
    labels = np.round(labels).astype(np.int64)
    edge = np.zeros(labels.shape, np.float32)
    edge[:-1] += labels[:-1] != labels[1:]
    edge[:, :-1] += labels[:, :-1] != labels[:, 1:]
    return cv2.GaussianBlur(edge, (0, 0), 1.5)


def _ncc(a, b, mask):
    a, b = a[mask].astype(np.float64), b[mask].astype(np.float64)
    if a.size < 10:
        return 0.0
    a -= a.mean()
    b -= b.mean()
    denominator = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / denominator) if denominator > 0 else 0.0


def align_silhouettes(moving, fixed):
    """Affine warp (for ``cv2.warpAffine`` with ``WARP_INVERSE_MAP``) that
    maps the ``moving`` silhouette onto the ``fixed`` one."""
    warp = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-5)
    try:
        cv2.findTransformECC(
            cv2.GaussianBlur(fixed.astype(np.float32), (0, 0), 3),
            cv2.GaussianBlur(moving.astype(np.float32), (0, 0), 3),
            warp, cv2.MOTION_AFFINE, criteria, None, 5,
        )
    except cv2.error:
        pass  # keep the bounding-box alignment
    return warp


def _zscores(values):
    values = np.asarray(values, dtype=float)
    spread = values.std()
    return (values - values.mean()) / spread if spread > 0 else np.zeros_like(values)


def rank_depths(histology, label_volume, intensity_volume, plane, orientation,
                indexes=None, progress=None):
    """Rank slices of ``plane`` by silhouette and internal anatomy.

    After an affine fit of the silhouettes, the section's internal edges are
    correlated with the atlas template's edges and with the atlas region
    boundaries. The three measures are combined as z-scores across the
    compared slices. Returns :class:`DepthMatch` objects, best first.
    """
    section_mask = orientation.apply(tissue_mask(histology))
    section_gray = orientation.apply(histology_gray(histology)).astype(np.float32)
    h_mask, h_gray = normalise(section_mask, section_gray)
    length = plane_length(label_volume.shape, plane)
    if indexes is None:
        step = max(1, int(np.ceil(length / MAX_SLICES_PER_PLANE)))
        indexes = range(0, length, step)
    indexes = list(indexes)
    rows = []
    for count, index in enumerate(indexes, start=1):
        labels = atlas_slice(label_volume, plane, index)
        atlas_mask = labels > 0
        if atlas_mask.sum() < 50:
            continue
        a_mask, a_image, a_labels = normalise(
            atlas_mask, atlas_slice(intensity_volume, plane, index).astype(np.float32),
            labels=labels,
        )
        warp = align_silhouettes(h_mask, a_mask)
        flags = cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
        size = (CANVAS, CANVAS)
        warped_gray = cv2.warpAffine(h_gray, warp, size, flags=flags)
        warped_mask = cv2.warpAffine(h_mask.astype(np.float32), warp, size, flags=flags) > 0.5
        both = warped_mask & a_mask
        section_edges, inner = _edges(warped_gray, both)
        template_edges, _ = _edges(a_image, both)
        rows.append((
            index,
            _iou(warped_mask, a_mask),
            _ncc(section_edges, template_edges, inner),
            _ncc(section_edges, _label_boundaries(a_labels), inner),
        ))
        if progress is not None:
            progress(count / len(indexes))
    if not rows:
        return []
    columns = list(zip(*rows))
    combined = _zscores(columns[1]) + _zscores(columns[2]) + _zscores(columns[3])
    matches = [DepthMatch(index, silhouette, template, label, float(score))
               for (index, silhouette, template, label), score in zip(rows, combined)]
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def hemisphere_indexes(plane, length, midline):
    """Slices of one hemisphere for sagittal search (the other mirrors it)."""
    if plane != "sagittal" or midline is None:
        return range(length)
    return range(int(midline), length)


def mirrored_index(index, midline):
    """The sagittal slice at the same distance on the other side of midline."""
    return int(round(2 * midline - index))
