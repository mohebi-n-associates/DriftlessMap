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

import os
import re
from dataclasses import dataclass, replace

import cv2
import numpy as np


PLANES = ("coronal", "sagittal", "horizontal")
# The user's answer to "which plane is the section cut in?"; "auto" searches all.
PLANE_CHOICES = PLANES + ("auto",)
_PLANE_WORDS = {"coronal": "coronal", "sagittal": "sagittal", "sagital": "sagittal",
                "horizontal": "horizontal", "axial": "horizontal"}
CANVAS = 192
FIT = 160
MAX_SLICES_PER_PLANE = 240
# Every comparison shrinks both images to a CANVAS-pixel square, so the
# search runs on an atlas sampled to at most this many voxels per side (a
# 10 um Allen atlas is searched at 30 um) and only the final depth is refined
# page by page at full resolution.
SEARCH_MAX_SIDE = 560
# Orientations whose outline match is within this of the best one are told
# apart by internal anatomy: many section outlines look nearly the same
# upside down.
ORIENTATION_MARGIN = 0.03
# Between orientations whose anatomy matches within this, the upright one
# (dorsal side still on top) is preferred: sections are rarely mounted upside
# down.
UPRIGHT_PREFERENCE = 0.05
# Coronal and sagittal sections are kept upright (dorsal on top) unless a
# rotated or flipped orientation matches the outline better by more than
# this; smaller outline differences are noise.
UPRIGHT_OUTLINE_MARGIN = 0.05
UPRIGHT_PLANES = ("coronal", "sagittal")
# Pages per orientation used to tell close orientations apart.
CONTENDER_PAGES = 150
# Depth ranking: pages compared in the first pass, and how many of the best
# are then examined page by page.
DEPTH_PAGES = 120
DEPTH_NEIGHBOURHOODS = 8


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

    @property
    def upright(self):
        """Whether the section's top edge stays on top (only mirrored, if anything)."""
        corners = self.apply(np.array([[1, 2], [3, 4]]))
        return set(corners[0].tolist()) == {1, 2}

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


def bright_background(image):
    """Whether the section lies on a bright background (brightfield).

    The image border is mostly background: it is bright when its median is
    clearly above the image's median.
    """
    image = np.asarray(image, dtype=np.float32)
    gray = image[..., :3].mean(axis=2) if image.ndim == 3 else image
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)
    band = max(1, int(0.03 * min(gray.shape)))
    border = np.concatenate([gray[:band].ravel(), gray[-band:].ravel(),
                             gray[:, :band].ravel(), gray[:, -band:].ravel()])
    return float(np.median(border)) > float(np.median(gray)) + 10.0


def _absorbance(gray, rounds=4):
    """How much darker than the slide each pixel is, under uneven illumination.

    Brightfield backgrounds are seldom flat (vignetting, uneven light), so a
    smooth quadratic surface is fitted to the background, starting from the
    image border and refined from the pixels it then classifies as
    background, and the image is subtracted from it.
    """
    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    x, y = xx.ravel() / w, yy.ravel() / h
    terms = np.stack([np.ones_like(x), x, y, x * x, y * y, x * y], axis=1)
    values = gray.ravel()
    band = max(1, int(0.03 * min(h, w)))
    background = np.zeros((h, w), bool)
    background[:band] = background[-band:] = True
    background[:, :band] = background[:, -band:] = True
    signal = np.zeros((h, w), np.float32)
    for _round in range(rounds):
        chosen = background.ravel()
        # Every 4th background pixel is plenty for six coefficients.
        chosen = np.flatnonzero(chosen)[::4]
        coefficients, *_ = np.linalg.lstsq(terms[chosen], values[chosen], rcond=None)
        signal = np.clip((terms @ coefficients).reshape(h, w) - gray, 0, None)
        threshold, _ = cv2.threshold(np.clip(signal, 0, 255).astype(np.uint8), 0, 255,
                                     cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        background = signal < 0.5 * threshold
        if background.sum() < 100:
            break
    return signal


def tissue_mask(image):
    """Return the tissue mask of a histology image (H x W or H x W x C).

    Tissue is brighter than the background in fluorescence and darker in
    brightfield; brightfield images are inverted first.
    """
    image = np.asarray(image)
    bright = bright_background(image)
    if image.ndim == 3:
        planes = [
            cv2.normalize(image[..., c].astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
            for c in range(image.shape[2])
        ]
        # Brightfield: tissue absorbs in at least one channel.
        gray = np.min(planes, axis=0) if bright else np.max(planes, axis=0)
    else:
        gray = cv2.normalize(image.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
    scale = 1024.0 / max(gray.shape)
    small = cv2.resize(gray, None, fx=min(1.0, scale), fy=min(1.0, scale),
                       interpolation=cv2.INTER_AREA) if scale < 1 else gray
    small = cv2.GaussianBlur(small, (0, 0), 2)
    if bright:
        small = _absorbance(small)
    small = np.clip(small, 0, 255).astype(np.uint8)
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
    # A one-pixel frame joins every stretch of background that reaches the
    # image edge, also where the tissue itself touches two edges.
    flood = np.pad(keep, 1)
    cv2.floodFill(flood, np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8),
                  (0, 0), 255)
    filled = (keep | cv2.bitwise_not(flood[1:-1, 1:-1])) > 0
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


def planes_for(choice):
    """The planes searched for a plane choice (see :data:`PLANE_CHOICES`)."""
    if choice in (None, "auto"):
        return PLANES
    if choice not in PLANES:
        raise ValueError("Unknown section plane: {}".format(choice))
    return (choice,)


def plane_from_name(path):
    """The plane named in a file name (``..._coronal_...``), or None."""
    if not path:
        return None
    words = re.split(r"[^a-z]+", os.path.basename(str(path)).lower())
    found = {_PLANE_WORDS[word] for word in words if word in _PLANE_WORDS}
    return found.pop() if len(found) == 1 else None


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
    fit: object = None         # PhysicalSection fit parameters, or None
    placement: object = None   # Placement on the slice, or None


def histology_gray(image, mask=None):
    """Luminance with local contrast equalised, as 8-bit, shaped like the atlas.

    Brightfield images are inverted so tissue is bright, as in the atlas
    template; with ``mask`` (see :func:`tissue_mask`) the background is black.
    """
    image = np.asarray(image)
    if image.ndim == 3:
        gray = image[..., :3].astype(np.float32).mean(axis=2)
    else:
        gray = image.astype(np.float32)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if bright_background(image):
        gray = 255 - gray
    gray = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    if mask is not None:
        gray = np.where(np.asarray(mask, dtype=bool), gray, 0).astype(np.uint8)
    return gray


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
                indexes=None, progress=None, section=None, refine=False):
    """Rank slices of ``plane`` by silhouette and internal anatomy.

    After fitting the section to each slice (``section``: a
    :class:`PhysicalSection`, refined when ``refine``; by default a
    :class:`NormalisedSection`, an affine fit of silhouettes scaled to fill
    one box), the section's internal edges are correlated with the atlas
    template's edges and with the atlas region boundaries. The three measures
    are combined as z-scores across the compared slices. Returns
    :class:`DepthMatch` objects, best first.
    """
    if section is None:
        section = NormalisedSection(histology, orientation)
    length = plane_length(label_volume.shape, plane)
    if indexes is None:
        step = max(1, int(np.ceil(length / MAX_SLICES_PER_PLANE)))
        indexes = range(0, length, step)
    indexes = list(indexes)
    rows, fits = [], []
    for count, index in enumerate(indexes, start=1):
        result = section.measure(atlas_slice(label_volume, plane, index),
                                 atlas_slice(intensity_volume, plane, index), refine=refine)
        if result is not None:
            rows.append((index,) + tuple(result[0]))
            fits.append(result[1:])
        if progress is not None:
            progress(count / len(indexes))
    scores = _combined_scores(rows)
    matches = [DepthMatch(row[0], row[1], row[2], row[3], score, fit[0], fit[1])
               for row, fit, score in zip(rows, fits, scores)]
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def _prepared_section(histology, orientation):
    mask = tissue_mask(histology)
    section_mask = orientation.apply(mask)
    section_gray = orientation.apply(histology_gray(histology, mask)).astype(np.float32)
    return normalise(section_mask, section_gray)


def _measure(h_mask, h_gray, labels, intensity):
    """Silhouette overlap and internal-edge agreement for one atlas slice."""
    atlas_mask = labels > 0
    if atlas_mask.sum() < 50:
        return None
    a_mask, a_image, a_labels = normalise(
        atlas_mask, np.asarray(intensity, dtype=np.float32), labels=labels
    )
    warp = align_silhouettes(h_mask, a_mask)
    flags = cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP
    size = (CANVAS, CANVAS)
    warped_gray = cv2.warpAffine(h_gray, warp, size, flags=flags)
    warped_mask = cv2.warpAffine(h_mask.astype(np.float32), warp, size, flags=flags) > 0.5
    both = warped_mask & a_mask
    section_edges, inner = _edges(warped_gray, both)
    template_edges, _ = _edges(a_image, both)
    return (
        _iou(warped_mask, a_mask),
        _ncc(section_edges, template_edges, inner),
        _ncc(section_edges, _label_boundaries(a_labels), inner),
    )


# ------------------------------------------------------------------
# Placing the section on a slice at its physical size
#
# Comparing outlines scaled to fill the same box (``normalise``) fails on
# sections missing a part (often the ventral brain): the remaining piece is
# stretched over the whole slice and every internal structure lands in the
# wrong place. With the pixel size known, the section keeps its size up to
# tissue shrinkage and flattening (``FIT_SCALES``, ``FIT_STRETCHES``) and is
# placed *inside* the slice: each outline point is charged its distance to
# the atlas outline, capped at ``OUTLINE_REACH_UM`` so a cut edge inside the
# brain costs a bounded amount, plus ``OUTSIDE_WEIGHT`` times the share of
# tissue outside the brain. On sections cut from the Allen 10 um atlas with
# 35 % of the ventral part removed this found depth within 170 um (outline
# scaled to fill: 0.9-5.3 mm). Real fixed sections shrank by up to about 25 %
# (two coronal sections of one brain, 1.63 um pixels).
FIT_SCALES = (0.95, 1.07, 1.2, 1.35)      # section to atlas size (shrinkage)
FIT_STRETCHES = (1.0, 1.1, 1.2)           # height to width (flattening)
FIT_LIMITS = ((0.9, 1.5), (0.8, 1.3), (-10.0, 10.0))  # scale, stretch, degrees
# Without a pixel size the section is first sized to the slice's width; it
# may be narrower (a partial section) but hardly wider.
UNKNOWN_SCALES = (0.7, 0.85, 1.0)
UNKNOWN_LIMITS = ((0.55, 1.15), (0.8, 1.3), (-10.0, 10.0))
OUTLINE_REACH_UM = 180.0
COARSE_REACH_UM = 450.0                   # for the coarse grid, before refining
OUTSIDE_WEIGHT = 3.0
UNKNOWN_SIZE_SIDE = 160                   # working size of a section of unknown size


@dataclass(frozen=True)
class Placement:
    """Where the section sits on a slice: top-left corner in slice pixels,
    then ``scale`` (atlas size / section size), ``stretch`` (extra height
    factor) and ``angle`` (degrees) applied to the section."""

    cost: float
    top: int
    left: int
    scale: float
    stretch: float
    angle: float


def _outline(mask):
    return mask & ~(cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)


def _transformed(mask, gray, scale, stretch, angle):
    height, width = mask.shape
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    matrix[:, :2] = matrix[:, :2] @ np.diag([scale, scale * stretch])
    corners = np.array([[0, 0], [width, 0], [0, height], [width, height]], float)
    placed = corners @ matrix[:, :2].T
    matrix[:, 2] = 1 - placed.min(axis=0)
    size = tuple(int(v) + 3 for v in np.ceil(placed.max(axis=0) - placed.min(axis=0)))
    moved = cv2.warpAffine(mask.astype(np.float32), matrix, size) > 0.5
    return moved, cv2.warpAffine(gray, matrix, size)


class _AtlasOutline:
    """Per-slice maps for :meth:`PhysicalSection.place`, padded by ``pad``."""

    def __init__(self, atlas_mask, pad):
        self.pad = pad
        padded = np.pad(atlas_mask, pad)
        self.distance = cv2.distanceTransform(
            (~_outline(padded)).astype(np.uint8), cv2.DIST_L2, 3)
        self.outside = (~padded).astype(np.float32)
        self._capped = {}

    def capped(self, reach):
        if reach not in self._capped:
            self._capped[reach] = np.minimum(self.distance, reach) / reach
        return self._capped[reach]


class PhysicalSection:
    """A section prepared for placing on atlas slices of ``voxel_um``.

    With ``pixel_um`` (the section's pixel size) the section is resampled to
    the atlas voxel size; otherwise it is sized to each slice's width before
    fitting, and only shape and anatomy decide.
    """

    def __init__(self, histology, orientation, voxel_um, pixel_um=None):
        mask = tissue_mask(histology)
        gray = histology_gray(histology, mask).astype(np.float32)
        mask, gray = orientation.apply(mask), orientation.apply(gray)
        self.voxel_um = float(voxel_um)
        self.pixel_um = None if pixel_um is None else float(pixel_um)
        if self.pixel_um is not None:
            factor = self.pixel_um / self.voxel_um
        else:
            factor = UNKNOWN_SIZE_SIDE / float(max(mask.shape))
        size = (max(1, int(round(mask.shape[1] * factor))),
                max(1, int(round(mask.shape[0] * factor))))
        small = cv2.resize(mask.astype(np.uint8), size, interpolation=cv2.INTER_AREA) > 0
        gray = cv2.resize(np.ascontiguousarray(gray), size, interpolation=cv2.INTER_AREA)
        ys, xs = np.nonzero(small)
        if not len(ys):
            raise ValueError("No tissue was found in the section.")
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        self.mask = small[y0:y1, x0:x1]
        self.gray = np.ascontiguousarray(gray[y0:y1, x0:x1])

    @property
    def size_known(self):
        return self.pixel_um is not None

    def _base(self, atlas_mask):
        if self.size_known:
            return 1.0
        xs = np.nonzero(atlas_mask.any(axis=0))[0]
        return (xs[-1] - xs[0] + 1) / float(self.mask.shape[1])

    def place(self, atlas_mask, refine=True, start=None):
        """Best :class:`Placement` on a slice mask, with the moved section.

        The coarse grid is searched unless ``start`` (scale, stretch, angle)
        is given; ``refine`` then adjusts each parameter in shrinking steps.
        """
        base = self._base(atlas_mask)
        limits = FIT_LIMITS if self.size_known else UNKNOWN_LIMITS
        pad = int(0.3 * max(self.mask.shape) * base * limits[0][1])
        atlas = _AtlasOutline(atlas_mask, pad)
        reach = OUTLINE_REACH_UM / self.voxel_um
        coarse = COARSE_REACH_UM / self.voxel_um

        def evaluate(params, cap, atlas=atlas, source=(self.mask, self.gray), shrink=1):
            scale, stretch, angle = params
            mask, gray = _transformed(source[0], source[1], scale * base, stretch, angle)
            outline = _outline(mask).astype(np.float32)
            tissue = mask.astype(np.float32)
            if (mask.shape[0] > atlas.outside.shape[0]
                    or mask.shape[1] > atlas.outside.shape[1]):
                return None
            cost = (cv2.matchTemplate(atlas.capped(cap / shrink), outline, cv2.TM_CCORR)
                    / max(1.0, outline.sum()))
            cost += OUTSIDE_WEIGHT * (cv2.matchTemplate(atlas.outside, tissue, cv2.TM_CCORR)
                                      / max(1.0, tissue.sum()))
            top, left = np.unravel_index(int(np.argmin(cost)), cost.shape)
            return float(cost[top, left]), top - pad, left - pad, mask, gray

        if start is None:
            # The grid is searched at half resolution (a quarter of the work).
            half = (cv2.resize(self.mask.astype(np.uint8), None, fx=0.5, fy=0.5,
                               interpolation=cv2.INTER_AREA) > 0,
                    cv2.resize(self.gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))
            small = atlas_mask[::2, ::2]
            half_atlas = _AtlasOutline(small, pad // 2)
            scales = FIT_SCALES if self.size_known else UNKNOWN_SCALES
            tried = [(evaluate((scale, stretch, 0.0), coarse, half_atlas, half, 2),
                      (scale, stretch, 0.0))
                     for scale in scales for stretch in FIT_STRETCHES]
            tried = [item for item in tried if item[0] is not None]
            if not tried:
                return None
            params = list(min(tried, key=lambda item: item[0][0])[1])
            steps, rounds = [0.04, 0.04, 3.0], 3
        else:
            params = list(start)
            steps, rounds = [0.02, 0.02, 1.5], 2
        result = evaluate(params, reach)
        if result is None:
            return None
        if refine:
            for _ in range(rounds):
                for axis in range(3):
                    for sign in (1, -1):
                        while True:
                            trial = list(params)
                            trial[axis] += sign * steps[axis]
                            low, high = limits[axis]
                            if not low <= trial[axis] <= high:
                                break
                            candidate = evaluate(trial, reach)
                            if candidate is None or candidate[0] >= result[0] - 1e-4:
                                break
                            params, result = trial, candidate
                steps = [step / 2 for step in steps]
        cost, top, left, mask, gray = result
        return Placement(cost, int(top), int(left), params[0] * base, params[1],
                         params[2]), mask, gray, params

    def measure(self, labels, intensity, refine=False, start=None):
        """(outline agreement, template-edge and label-edge agreement), the
        raw fit parameters, and the :class:`Placement`; None without overlap."""
        labels = np.asarray(labels)
        atlas_mask = labels > 0
        if atlas_mask.sum() < 50:
            return None
        placed = self.place(atlas_mask, refine=refine, start=start)
        if placed is None:
            return None
        placement, mask, gray, params = placed
        height, width = atlas_mask.shape
        top, left = placement.top, placement.left
        y0, x0 = max(0, top), max(0, left)
        y1, x1 = min(height, top + mask.shape[0]), min(width, left + mask.shape[1])
        if y1 <= y0 or x1 <= x0:
            return None
        section_mask = np.zeros(atlas_mask.shape, bool)
        section_gray = np.zeros(atlas_mask.shape, np.float32)
        section_mask[y0:y1, x0:x1] = mask[y0 - top:y1 - top, x0 - left:x1 - left]
        section_gray[y0:y1, x0:x1] = gray[y0 - top:y1 - top, x0 - left:x1 - left]
        both = section_mask & atlas_mask
        section_edges, inner = _edges(section_gray, both)
        template_edges, _ = _edges(np.asarray(intensity, dtype=np.float32), both)
        measures = (max(0.0, 1.0 - placement.cost),
                    _ncc(section_edges, template_edges, inner),
                    _ncc(section_edges, _label_boundaries(labels), inner))
        return measures, tuple(params), placement


class NormalisedSection:
    """A section compared with slices after scaling both to fill one box
    (used when no voxel size is given)."""

    size_known = False

    def __init__(self, histology, orientation):
        self.mask, self.gray = _prepared_section(histology, orientation)

    def measure(self, labels, intensity, refine=False, start=None):
        measures = _measure(self.mask, self.gray, labels, intensity)
        return None if measures is None else (measures, None, None)


def _combined_scores(rows):
    if not rows:
        return []
    columns = list(zip(*rows))
    combined = _zscores(columns[1]) + _zscores(columns[2]) + _zscores(columns[3])
    return [float(value) for value in combined]


def hemisphere_indexes(plane, length, midline):
    """Slices of one hemisphere for sagittal search (the other mirrors it)."""
    if plane != "sagittal" or midline is None:
        return range(length)
    return range(int(midline), length)


def mirrored_index(index, midline):
    """The sagittal slice at the same distance on the other side of midline."""
    return int(round(2 * midline - index))


def _rotation_x(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _rotation_y(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rotation_z(theta):
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def tilted_slice(volume, plane, index, tilt_degrees, pivot, order=1, step=1):
    """Sample the tilted slice ``AtlasView`` shows for these rotation controls.

    ``tilt_degrees`` is the (horizontal, vertical) pair of the view's rotation
    spinboxes; ``pivot`` is the (coronal, sagittal, horizontal) page indices
    about which the view rotates. The view shows ``index`` as its own page,
    so that component of the pivot is always ``index``. Mirrors
    ``AtlasView.rotate_*_current_slice``.
    """
    from scipy.ndimage import map_coordinates

    h_rad, v_rad = np.deg2rad(tilt_degrees)
    size0, size1, size2 = volume.shape
    c_id, s_id, h_index = pivot
    if plane == "coronal":
        c_id = index
    elif plane == "sagittal":
        s_id = index
    elif plane == "horizontal":
        h_index = index
    o_rot = np.array([size0 - 1 - h_index, s_id, c_id], dtype=float)
    if plane == "coronal":
        rotation = _rotation_x(h_rad) @ _rotation_y(v_rad)
        o_val = np.array([0, 0, index], dtype=float)
        axes, shape = ((1, 0, 0), (0, 1, 0)), (size0, size1)
    elif plane == "sagittal":
        rotation = _rotation_x(h_rad) @ _rotation_z(v_rad)
        o_val = np.array([0, index, 0], dtype=float)
        axes, shape = ((1, 0, 0), (0, 0, 1)), (size0, size2)
    elif plane == "horizontal":
        rotation = _rotation_z(v_rad) @ _rotation_y(h_rad)
        o_val = np.array([size0 - 1 - index, 0, 0], dtype=float)
        axes, shape = ((0, 1, 0), (0, 0, 1)), (size1, size2)
    else:
        raise ValueError("Unknown atlas plane {!r}.".format(plane))
    first = rotation @ np.array(axes[0], dtype=float)
    second = rotation @ np.array(axes[1], dtype=float)
    origin = o_rot + rotation @ (o_val - o_rot)
    # ``step`` samples every step-th row and column (the same slice, coarser).
    rows, columns = np.meshgrid(np.arange(0, shape[0], step), np.arange(0, shape[1], step),
                                indexing="ij")
    coordinates = (origin[:, None, None] + first[:, None, None] * rows
                   + second[:, None, None] * columns)
    return map_coordinates(volume, coordinates, order=order, mode="constant", cval=0)


@dataclass(frozen=True)
class TiltMatch:
    """A depth and cutting-angle candidate, in rotation-control degrees."""

    index: int
    tilt_degrees: tuple
    silhouette: float
    template_edges: float
    label_edges: float
    score: float
    fit: object = None
    placement: object = None


def refine_tilt(histology, label_volume, intensity_volume, plane, orientation,
                indexes, pivot, angles=(-6, -3, 0, 3, 6), progress=None,
                section=None, starts=None):
    """Score each depth in ``indexes`` at every (h, v) tilt in ``angles``.

    ``section`` is as for :func:`rank_depths`; a :class:`PhysicalSection` is
    refined from the fit in ``starts`` (index to fit parameters) when given.
    Returns :class:`TiltMatch` objects, best first. Scores are comparable only
    within one call.
    """
    if section is None:
        section = NormalisedSection(histology, orientation)
    starts = starts or {}
    grid = [(index, (h, v)) for index in indexes for h in angles for v in angles]
    rows, keys, fits = [], [], []
    for count, (index, tilt) in enumerate(grid, start=1):
        if tilt == (0, 0):
            labels = atlas_slice(label_volume, plane, index)
            intensity = atlas_slice(intensity_volume, plane, index)
        else:
            labels = tilted_slice(label_volume, plane, index, tilt, pivot, order=0)
            intensity = tilted_slice(intensity_volume, plane, index, tilt, pivot, order=1)
        # The depth's fitted size and stretch carry over; only the position
        # is searched again (refining every tilt took most of the time).
        start = starts.get(index)
        result = section.measure(labels, intensity, refine=start is None, start=start)
        if result is not None:
            rows.append((index,) + tuple(result[0]))
            keys.append(tilt)
            fits.append(result[1:])
        if progress is not None:
            progress(count / len(grid))
    scores = _combined_scores(rows)
    matches = [TiltMatch(row[0], tuple(float(a) for a in tilt), row[1], row[2], row[3], score,
                         fit[0], fit[1])
               for row, tilt, fit, score in zip(rows, keys, fits, scores)]
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def mirrored_tilt(plane, tilt_degrees):
    """The rotation-control tilt of the mirror-image cut in the other hemisphere.

    Rotations mixing the medio-lateral axis change sign: in the view's axes
    (0 DV, 1 ML, 2 AP), ``rotation_x`` mixes ML-AP and ``rotation_z`` mixes
    DV-ML, while ``rotation_y`` (DV-AP) is unaffected.
    """
    h, v = tilt_degrees
    if plane == "coronal":      # Rx(h) @ Ry(v)
        return (-h, v)
    if plane == "sagittal":     # Rx(h) @ Rz(v)
        return (-h, -v)
    if plane == "horizontal":   # Rz(v) @ Ry(h)
        return (h, -v)
    raise ValueError("Unknown atlas plane {!r}.".format(plane))


# Screen edge of the displayed atlas slice on the animal's right. The view's
# ML axis increases toward the right (positive ML is right, as in the probe
# exports); coronal slices show it along columns, horizontal slices along rows,
# which grow downward. Sagittal slices contain no ML axis.
RIGHT_EDGE = {"coronal": "right", "horizontal": "bottom"}
_EDGES = {"right": (slice(None), -1), "left": (slice(None), 0),
          "bottom": (-1, slice(None)), "top": (0, slice(None))}
_OPPOSITE_EDGE = {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}


def animal_right_edge(plane, orientation):
    """The edge of the section, as shown before ``orientation`` is applied, that
    lies toward the animal's right once the section is oriented like the atlas.

    Returns "left", "right", "top" or "bottom", or None for sagittal views.
    """
    edge = RIGHT_EDGE.get(plane)
    if edge is None:
        return None
    rows, cols = np.mgrid[0:3, 0:5].astype(float)
    oriented_rows, oriented_cols = orientation.apply(rows), orientation.apply(cols)
    far, near = _EDGES[edge], _EDGES[_OPPOSITE_EDGE[edge]]
    d_row = oriented_rows[far].mean() - oriented_rows[near].mean()
    d_col = oriented_cols[far].mean() - oriented_cols[near].mean()
    if abs(d_col) > abs(d_row):
        return "right" if d_col > 0 else "left"
    return "bottom" if d_row > 0 else "top"


def sagittal_side(index, midline):
    """The hemisphere of a sagittal slice: "right", "left" or "midline"."""
    if midline is None:
        return None
    if abs(index - midline) < 0.5:
        return "midline"
    return "right" if index > midline else "left"


def mirror_hemisphere(plane, orientation):
    """The orientation showing the other hemisphere (coronal/horizontal).

    Mirrors the oriented section along the view's medio-lateral axis.
    """
    if plane == "coronal":
        return Orientation(orientation.quarter_turns, not orientation.mirrored)
    if plane == "horizontal":
        return Orientation((orientation.quarter_turns + 2) % 4, not orientation.mirrored)
    return orientation


@dataclass(frozen=True)
class Suggestion:
    """One ready-to-apply atlas section suggestion."""

    plane: str
    orientation: Orientation
    index: int
    tilt_degrees: tuple
    score: float
    silhouette: float
    template_edges: float = 0.0   # internal-anatomy agreement with the template
    # Atlas size / section size of the fit (tissue shrinkage) when the
    # section was placed at its physical size; None otherwise.
    fit_scale: object = None


@dataclass(frozen=True)
class SuggestionReport:
    plane_candidates: tuple   # best Candidate per plane, best first
    suggestions: tuple        # Suggestion objects, best first
    midline: object           # sagittal midline index, or None
    # Pages (full resolution) spanned by the depths that fit about as well as
    # the best one (see DEPTH_TIE); None for reports made before it existed.
    depth_span: object = None
    # True when the section was placed at its physical size, False when its
    # pixel size was unknown, None for the scale-free comparison.
    size_known: object = None

    @property
    def plane_margin(self):
        """Silhouette lead of the best plane over the runner-up."""
        if len(self.plane_candidates) < 2:
            return 1.0
        return self.plane_candidates[0].silhouette - self.plane_candidates[1].silhouette


# Depths whose combined score is within this many z units of the best one fit
# about as well; how far apart they lie tells how well depth is determined.
DEPTH_TIE = 1.0
# Confidence thresholds. Measured on sections cut from the Allen 10 um atlas
# (flattened by 15 %, with noise), where the right page is known: internal
# anatomy agreed 0.60-0.95, near-equal depths spanned at most 360 um and the
# depth was found within 60 um. Two real fluorescence sections, whose
# suggestions were far off, agreed only 0.09-0.15 with near-equal depths over
# 2-8.5 mm. The outline fit did not separate the two (above 0.9 for both).
# Not yet checked on real sections with known positions.
CONFIDENT_ANATOMY, FAIR_ANATOMY = 0.5, 0.3
CONFIDENT_SPAN_UM, FAIR_SPAN_UM = 500.0, 1000.0
CONFIDENCE_LEVELS = ("low", "medium", "high")


def confidence(suggestion, report, voxel_um):
    """How far a suggestion can be trusted: ``(level, reasons)``.

    ``level`` is "high", "medium" or "low", the lowest of: internal anatomy
    agreement, how narrowly depth is determined, "medium" when the section's
    pixel size was unknown, and (when the plane was detected) how clearly the
    plane was preferred. ``reasons`` explain each
    limit in words.
    """
    levels, reasons = [], []
    anatomy = suggestion.template_edges
    level = 2 if anatomy >= CONFIDENT_ANATOMY else 1 if anatomy >= FAIR_ANATOMY else 0
    levels.append(level)
    if level < 2:
        reasons.append("internal anatomy agrees {} ({:.2f})".format(
            "only moderately" if level else "weakly", anatomy))
    if report.depth_span is not None:
        span = report.depth_span * voxel_um
        level = 2 if span <= CONFIDENT_SPAN_UM else 1 if span <= FAIR_SPAN_UM else 0
        levels.append(level)
        if level < 2:
            reasons.append("depths {:.1f} mm apart fit about as well".format(span / 1000))
    if getattr(report, "size_known", None) is False:
        levels.append(1)
        reasons.append("the pixel size is unknown, so the section's size was guessed")
    if len(report.plane_candidates) > 1:
        margin = report.plane_margin
        level = 2 if margin >= 0.08 else 1 if margin >= 0.03 else 0
        levels.append(level)
        if level < 2:
            reasons.append("the plane is {}".format("uncertain" if level else "ambiguous"))
    return CONFIDENCE_LEVELS[min(levels)], reasons


def preferred_form(plane, orientation):
    """Of an orientation and its hemisphere mirror, the upright, unflipped one.

    Mirror images match equally well (the brain is nearly symmetric), and the
    user chooses the hemisphere in the suggestion dialog anyway.
    """
    options = {orientation, mirror_hemisphere(plane, orientation)}
    return min(options, key=lambda o: (plane in UPRIGHT_PLANES and not o.upright,
                                       o.mirrored, o.quarter_turns))


def orientation_contenders(candidates, best, margin=ORIENTATION_MARGIN, limit=4):
    """Best candidate of each distinct orientation of ``best``'s plane whose
    outline match is within ``margin`` of the best (mirror images, which the
    outline cannot tell apart, count as one)."""
    chosen = []
    for candidate in candidates:
        if candidate.plane != best.plane or candidate.silhouette < best.silhouette - margin:
            continue
        if any(same_up_to_hemisphere(best.plane, candidate.orientation, other.orientation)
               for other in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) == limit:
            break
    return chosen or [best]


def _anatomy(match):
    """Raw agreement of a depth match, comparable across orientations."""
    return match.silhouette + match.template_edges + match.label_edges


def choose_orientation(ranked, preference=UPRIGHT_PREFERENCE):
    """The ``(candidate, depths)`` pair whose best depth matches best.

    Upright orientations are preferred unless another matches clearly
    better (by more than ``preference``).
    """
    def merit(item):
        candidate, depths = item
        bonus = preference if candidate.orientation.upright else 0.0
        return _anatomy(depths[0]) + bonus

    return max(ranked, key=merit)


def _distinct(indexes, count, spacing):
    chosen = []
    for index in indexes:
        if all(abs(index - other) >= spacing for other in chosen):
            chosen.append(index)
        if len(chosen) == count:
            break
    return chosen


def search_factor(shape, max_side=SEARCH_MAX_SIDE):
    """The sampling step that keeps every side of ``shape`` within ``max_side``."""
    return max(1, int(np.ceil(max(shape) / float(max_side))))


def _refine_page(histology, label_volume, intensity_volume, plane, orientation,
                 index, tilt, pivot, factor, section=None, start=None):
    """The full-resolution page near coarse page ``index * factor`` that matches best.

    The pages between coarse samples are read from the full-resolution
    volume, at the tilt chosen for the coarse page.
    """
    if factor == 1:
        return index * factor
    if section is None:
        section = NormalisedSection(histology, orientation)
    length = plane_length(label_volume.shape, plane)
    centre = index * factor
    best = None
    for page in range(max(0, centre - factor + 1), min(length, centre + factor)):
        if tuple(tilt) == (0, 0):
            labels = atlas_slice(label_volume, plane, page)
            intensity = atlas_slice(intensity_volume, plane, page)
        else:
            labels = tilted_slice(label_volume, plane, page, tilt, pivot, order=0,
                                  step=factor)
            intensity = tilted_slice(intensity_volume, plane, page, tilt, pivot, order=1,
                                     step=factor)
        if tuple(tilt) == (0, 0):
            labels, intensity = labels[::factor, ::factor], intensity[::factor, ::factor]
        result = section.measure(labels, intensity, refine=True, start=start)
        if result is None:
            continue
        # Neighbouring pages differ little: a plain sum ranks them.
        total = float(sum(result[0]))
        if best is None or total > best[0]:
            best = (total, page)
    return best[1] if best is not None else centre


def suggest_sections(histology, label_volume, intensity_volume, midline, pivot,
                     max_suggestions=6, depth_candidates=4,
                     angles=(-6, -3, 0, 3, 6), progress=None,
                     max_side=SEARCH_MAX_SIDE, planes=PLANES, voxel_um=None,
                     pixel_um=None):
    """Plane, orientation, depth and tilt suggestions for one section.

    ``midline`` is the sagittal page index of the midline (for searching one
    hemisphere); ``pivot`` is the current (coronal, sagittal, horizontal) page
    indices of the atlas view. Large atlases are searched on a sampled copy
    (see :data:`SEARCH_MAX_SIDE`); the suggested pages are full-resolution
    pages. ``planes`` limits the search to the planes the section may be cut
    in; the outline alone does not reliably tell them apart, because it is
    compared without its physical size.

    With ``voxel_um`` (the atlas voxel size) depth and tilt are found by
    placing the section inside each slice (:class:`PhysicalSection`), which
    copes with partial sections; ``pixel_um`` (the section's pixel size)
    keeps it at its physical size, up to tissue shrinkage. Without
    ``voxel_um`` both are scaled to fill one box, as before 2.0.0rc16.
    """
    planes = tuple(planes)
    if not planes or any(plane not in PLANES for plane in planes):
        raise ValueError("Unknown section plane: {}".format(", ".join(planes)))

    def stage(start, end):
        if progress is None:
            return None
        return lambda fraction: progress(start + (end - start) * fraction)

    factor = search_factor(label_volume.shape, max_side)
    labels = np.ascontiguousarray(label_volume[::factor, ::factor, ::factor])
    intensity = np.ascontiguousarray(intensity_volume[::factor, ::factor, ::factor])
    coarse_midline = None if midline is None else midline / factor
    coarse_pivot = tuple(value / factor for value in pivot)

    def section_for(orientation):
        if voxel_um is None:
            return NormalisedSection(histology, orientation)
        return PhysicalSection(histology, orientation, voxel_um * factor, pixel_um)

    candidates = search_planes(histology, labels, planes, progress=stage(0.0, 0.25))
    planes = best_by_plane(candidates)
    best = planes[0]
    length = plane_length(labels.shape, best.plane)
    indexes = list(hemisphere_indexes(best.plane, length, coarse_midline))
    upright = [c for c in candidates if c.plane == best.plane and c.orientation.upright]
    if (best.plane in UPRIGHT_PLANES and upright
            and upright[0].silhouette >= best.silhouette - UPRIGHT_OUTLINE_MARGIN):
        contenders = [upright[0]]
        best = upright[0]
    else:
        contenders = orientation_contenders(candidates, best)
    if len(contenders) > 1:
        # Tell the orientations apart on every few pages; rank the winner's
        # pages one by one below.
        sample = indexes[::max(1, len(indexes) // CONTENDER_PAGES)]
        ranked = []
        for number, contender in enumerate(contenders):
            share = 0.15 / len(contenders)
            depths = rank_depths(
                histology, labels, intensity, best.plane, contender.orientation,
                indexes=sample, section=section_for(contender.orientation),
                progress=stage(0.25 + number * share, 0.25 + (number + 1) * share),
            )
            if depths:
                ranked.append((contender, depths))
        if ranked:
            best = choose_orientation(ranked)[0]
    # Of two mirror images (the hemisphere choice), show the unflipped one.
    best = replace(best, orientation=preferred_form(best.plane, best.orientation))
    # Depth in two passes: every few pages, then each page around the best
    # few (scores are compared within one pass only).
    section = section_for(best.orientation)
    stride = max(1, len(indexes) // DEPTH_PAGES)
    depths = rank_depths(
        histology, labels, intensity, best.plane, best.orientation,
        indexes=indexes[::stride], progress=stage(0.4, 0.45), section=section,
    )
    if not depths:
        raise ValueError("No atlas slice could be compared with the section.")
    # This pass covers every few pages of the plane: the depths that fit about
    # as well as the best one show how well depth is determined.
    near = [match.index for match in depths if match.score >= depths[0].score - DEPTH_TIE]
    depth_span = (max(near) - min(near)) * factor
    if stride > 1:
        around = sorted({page for match in depths[:DEPTH_NEIGHBOURHOODS]
                         for page in range(match.index - stride + 1, match.index + stride)
                         if indexes[0] <= page <= indexes[-1]})
        depths = rank_depths(
            histology, labels, intensity, best.plane, best.orientation,
            indexes=around, progress=stage(0.45, 0.5), section=section, refine=True,
        ) or depths
    spacing = max(2, length // 100)
    chosen = _distinct([match.index for match in depths], depth_candidates, spacing)
    fits = {match.index: match.fit for match in depths}
    tilts = refine_tilt(
        histology, labels, intensity, best.plane, best.orientation,
        indexes=chosen, pivot=coarse_pivot, angles=angles, progress=stage(0.5, 0.8),
        section=section, starts=fits,
    )
    picked, seen = [], set()
    for match in tilts:
        if match.index in seen:
            continue  # the best tilt of each depth
        seen.add(match.index)
        picked.append(match)
        if len(picked) == max_suggestions:
            break
    suggestions = []
    for count, match in enumerate(picked, start=1):
        page = _refine_page(histology, label_volume, intensity_volume, best.plane,
                            best.orientation, match.index, match.tilt_degrees, pivot, factor,
                            section=section, start=match.fit)
        fit_scale = None
        if match.placement is not None and section.size_known:
            fit_scale = match.placement.scale
        suggestions.append(Suggestion(best.plane, best.orientation, page,
                                      match.tilt_degrees, match.score, match.silhouette,
                                      match.template_edges, fit_scale))
        if progress is not None:
            progress(0.8 + 0.2 * count / len(picked))
    # The report's plane candidate carries the orientation actually chosen,
    # which the dialog shows and applies.
    planes = [best] + [candidate for candidate in planes if candidate.plane != best.plane]
    planes = tuple(replace(candidate, index=candidate.index * factor) for candidate in planes)
    size_known = None if voxel_um is None else section.size_known
    return SuggestionReport(planes, tuple(suggestions),
                            midline if best.plane == "sagittal" else None, depth_span,
                            size_known)
