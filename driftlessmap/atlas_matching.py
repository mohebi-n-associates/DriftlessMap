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
    h_mask, h_gray = _prepared_section(histology, orientation)
    length = plane_length(label_volume.shape, plane)
    if indexes is None:
        step = max(1, int(np.ceil(length / MAX_SLICES_PER_PLANE)))
        indexes = range(0, length, step)
    indexes = list(indexes)
    rows = []
    for count, index in enumerate(indexes, start=1):
        measures = _measure(
            h_mask, h_gray, atlas_slice(label_volume, plane, index),
            atlas_slice(intensity_volume, plane, index),
        )
        if measures is not None:
            rows.append((index,) + measures)
        if progress is not None:
            progress(count / len(indexes))
    scores = _combined_scores(rows)
    matches = [DepthMatch(row[0], row[1], row[2], row[3], score)
               for row, score in zip(rows, scores)]
    matches.sort(key=lambda match: match.score, reverse=True)
    return matches


def _prepared_section(histology, orientation):
    section_mask = orientation.apply(tissue_mask(histology))
    section_gray = orientation.apply(histology_gray(histology)).astype(np.float32)
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


def tilted_slice(volume, plane, index, tilt_degrees, pivot, order=1):
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
    rows, columns = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
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


def refine_tilt(histology, label_volume, intensity_volume, plane, orientation,
                indexes, pivot, angles=(-6, -3, 0, 3, 6), progress=None):
    """Score each depth in ``indexes`` at every (h, v) tilt in ``angles``.

    Returns :class:`TiltMatch` objects, best first. Scores are comparable only
    within one call.
    """
    h_mask, h_gray = _prepared_section(histology, orientation)
    grid = [(index, (h, v)) for index in indexes for h in angles for v in angles]
    rows, keys = [], []
    for count, (index, tilt) in enumerate(grid, start=1):
        if tilt == (0, 0):
            labels = atlas_slice(label_volume, plane, index)
            intensity = atlas_slice(intensity_volume, plane, index)
        else:
            labels = tilted_slice(label_volume, plane, index, tilt, pivot, order=0)
            intensity = tilted_slice(intensity_volume, plane, index, tilt, pivot, order=1)
        measures = _measure(h_mask, h_gray, labels, intensity)
        if measures is not None:
            rows.append((index,) + measures)
            keys.append(tilt)
        if progress is not None:
            progress(count / len(grid))
    scores = _combined_scores(rows)
    matches = [TiltMatch(row[0], tuple(float(a) for a in tilt), row[1], row[2], row[3], score)
               for row, tilt, score in zip(rows, keys, scores)]
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


@dataclass(frozen=True)
class SuggestionReport:
    plane_candidates: tuple   # best Candidate per plane, best first
    suggestions: tuple        # Suggestion objects, best first
    midline: object           # sagittal midline index, or None

    @property
    def plane_margin(self):
        """Silhouette lead of the best plane over the runner-up."""
        if len(self.plane_candidates) < 2:
            return 1.0
        return self.plane_candidates[0].silhouette - self.plane_candidates[1].silhouette


def _distinct(indexes, count, spacing):
    chosen = []
    for index in indexes:
        if all(abs(index - other) >= spacing for other in chosen):
            chosen.append(index)
        if len(chosen) == count:
            break
    return chosen


def suggest_sections(histology, label_volume, intensity_volume, midline, pivot,
                     max_suggestions=6, depth_candidates=4,
                     angles=(-6, -3, 0, 3, 6), progress=None):
    """Plane, orientation, depth and tilt suggestions for one section.

    ``midline`` is the sagittal page index of the midline (for searching one
    hemisphere); ``pivot`` is the current (coronal, sagittal, horizontal) page
    indices of the atlas view.
    """
    def stage(start, end):
        if progress is None:
            return None
        return lambda fraction: progress(start + (end - start) * fraction)

    planes = best_by_plane(search_planes(histology, label_volume, progress=stage(0.0, 0.3)))
    best = planes[0]
    length = plane_length(label_volume.shape, best.plane)
    depths = rank_depths(
        histology, label_volume, intensity_volume, best.plane, best.orientation,
        indexes=hemisphere_indexes(best.plane, length, midline), progress=stage(0.3, 0.6),
    )
    spacing = max(2, length // 100)
    chosen = _distinct([match.index for match in depths], depth_candidates, spacing)
    tilts = refine_tilt(
        histology, label_volume, intensity_volume, best.plane, best.orientation,
        indexes=chosen, pivot=pivot, angles=angles, progress=stage(0.6, 1.0),
    )
    suggestions, seen = [], set()
    for match in tilts:
        if match.index in seen:
            continue  # the best tilt of each depth
        seen.add(match.index)
        suggestions.append(Suggestion(best.plane, best.orientation, match.index,
                                      match.tilt_degrees, match.score, match.silhouette))
        if len(suggestions) == max_suggestions:
            break
    return SuggestionReport(tuple(planes), tuple(suggestions),
                            midline if best.plane == "sagittal" else None)
