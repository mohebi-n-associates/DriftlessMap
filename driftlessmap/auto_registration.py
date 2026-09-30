"""Automatic landmark proposal between an atlas slice and a histology section.

The atlas slice is the fixed image, so the fitted SimpleITK transform maps an
atlas point directly to the matching section point; sampling it at the tips
and notches of the outline and at edges that both images show yields landmark
pairs for DriftlessMap's piecewise-affine registration. They are suggestions
that the user confirms and edits.

Both images are given physical coordinates in DriftlessMap's convention
(pixel ``k`` spans ``[k, k + 1)``; its centre is ``k + 0.5``), so points need
no conversion on either side.

Stages:
1. moment-based initialisation and an affine fit of the tissue silhouettes;
2. a B-spline refinement on intensities with Mattes mutual information,
   which tolerates the different contrast of histology and atlas templates.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import SimpleITK as sitk

from .atlas_matching import histology_gray, tissue_mask

WORKING_SIZE = 384  # longest side used for registration


@dataclass(frozen=True)
class LandmarkProposal:
    atlas_points: np.ndarray       # (N, 2) x, y in atlas-slice pixels
    histology_points: np.ndarray   # (N, 2) x, y in histology pixels
    overlap_affine: float          # silhouette Dice after the affine stage
    overlap_final: float           # silhouette Dice after the B-spline stage
    deformable_used: bool
    boundary_points: np.ndarray    # extra atlas points mapped into the section,
                                   # clamped to the section image
    kinds: tuple = ()              # "outline" or "internal" for each landmark


def _as_image(array, scale):
    """Downsampled SimpleITK image whose physical space is original pixels."""
    image = sitk.GetImageFromArray(np.ascontiguousarray(array, dtype=np.float32))
    image.SetSpacing((float(scale), float(scale)))
    image.SetOrigin((0.5 * scale, 0.5 * scale))  # centre of pixel 0
    return image


def _downsample(array, interpolation):
    height, width = array.shape[:2]
    scale = max(1.0, max(height, width) / WORKING_SIZE)
    size = (max(1, int(round(width / scale))), max(1, int(round(height / scale))))
    resized = cv2.resize(np.asarray(array, dtype=np.float32), size, interpolation=interpolation)
    return resized, (width / size[0])


def _dice(fixed_mask, moving_mask, transform):
    warped = sitk.Resample(moving_mask, fixed_mask, transform, sitk.sitkNearestNeighbor, 0.0)
    a = sitk.GetArrayFromImage(fixed_mask) > 0.5
    b = sitk.GetArrayFromImage(warped) > 0.5
    total = a.sum() + b.sum()
    return float(2 * np.logical_and(a, b).sum() / total) if total else 0.0


def _physical_moments(mask_image):
    """Centroid and per-axis standard deviation of a mask, in physical units."""
    array = sitk.GetArrayFromImage(mask_image) > 0.5
    rows, cols = np.nonzero(array)
    spacing = mask_image.GetSpacing()[0]
    origin = mask_image.GetOrigin()
    x = origin[0] + cols * spacing
    y = origin[1] + rows * spacing
    return np.array([x.mean(), y.mean()]), np.array([x.std(), y.std()])


def _moment_initialisation(fixed_mask, moving_mask):
    """Axis-aligned affine matching centroids and spreads of the silhouettes.

    The section is already in the atlas orientation, so only scale (possibly
    anisotropic, from shrinkage) and translation are unknown at this point.
    """
    fixed_centre, fixed_spread = _physical_moments(fixed_mask)
    moving_centre, moving_spread = _physical_moments(moving_mask)
    scale = moving_spread / np.maximum(fixed_spread, 1e-6)
    transform = sitk.AffineTransform(2)
    transform.SetMatrix((float(scale[0]), 0.0, 0.0, float(scale[1])))
    transform.SetCenter(tuple(float(v) for v in fixed_centre))
    transform.SetTranslation(tuple(float(v) for v in moving_centre - fixed_centre))
    return transform


def _affine_on_silhouettes(fixed_mask, moving_mask):
    fixed_smooth = sitk.SmoothingRecursiveGaussian(fixed_mask, fixed_mask.GetSpacing()[0] * 3)
    moving_smooth = sitk.SmoothingRecursiveGaussian(moving_mask, moving_mask.GetSpacing()[0] * 3)
    initial = _moment_initialisation(fixed_mask, moving_mask)
    registration = sitk.ImageRegistrationMethod()
    registration.SetMetricAsMeanSquares()
    registration.SetOptimizerAsRegularStepGradientDescent(
        learningRate=1.0, minStep=1e-4, numberOfIterations=300,
        gradientMagnitudeTolerance=1e-8,
    )
    registration.SetOptimizerScalesFromPhysicalShift()
    registration.SetShrinkFactorsPerLevel([4, 2, 1])
    registration.SetSmoothingSigmasPerLevel([2, 1, 0])
    registration.SetInitialTransform(initial, inPlace=False)
    registration.SetInterpolator(sitk.sitkLinear)
    return registration.Execute(fixed_smooth, moving_smooth)


def _bspline_on_intensities(fixed, moving, fixed_mask, affine, mesh_size):
    bspline = sitk.BSplineTransformInitializer(fixed, [mesh_size, mesh_size])
    registration = sitk.ImageRegistrationMethod()
    # The affine stays fixed; only the B-spline is optimised (a composite
    # transform cannot be optimised directly).
    registration.SetMovingInitialTransform(affine)
    registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    registration.SetMetricFixedMask(fixed_mask)
    registration.SetMetricSamplingStrategy(registration.RANDOM)
    registration.SetMetricSamplingPercentage(0.3, seed=7)
    registration.SetOptimizerAsLBFGSB(gradientConvergenceTolerance=1e-5, numberOfIterations=150)
    registration.SetShrinkFactorsPerLevel([4, 2, 1])
    registration.SetSmoothingSigmasPerLevel([2, 1, 0])
    registration.SetInitialTransform(bspline, inPlace=True)
    registration.SetInterpolator(sitk.sitkLinear)
    before = registration.MetricEvaluate(fixed, moving)
    registration.Execute(fixed, moving)
    after = registration.MetricEvaluate(fixed, moving)
    composite = sitk.CompositeTransform(2)
    composite.AddTransform(affine)   # applied last
    composite.AddTransform(bspline)  # applied first
    # Mattes MI is negated by ITK: lower is better.
    return composite, after < before


OUTLINE_LANDMARKS = 5   # tips and notches of the outline
EDGE_MARGIN = 8         # atlas pixels; the slice may cut the brain at the image edge
MIN_AGREEMENT = 0.2     # internal edges must show clearly in both images


def _spacing(mask, count):
    """Typical distance between ``count`` points spread over ``mask``."""
    return max(2.0, float(np.sqrt(mask.sum() / max(count, 1))))


def _outer_contour(mask):
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_NONE)
    if not contours:
        return np.zeros((0, 2))
    return max(contours, key=cv2.contourArea)[:, 0, :].astype(float)


def _outline_points(atlas_mask, atlas_image, count):
    """The sharpest tips and notches of the atlas outline, most pronounced first.

    Points where the slice cuts the brain at the image edge are skipped, as
    are points where the labels extend past the visible template (the
    template can be dark at the brain surface), because neither is an
    outline that can be seen in the section.
    """
    contour = _outer_contour(atlas_mask)
    n = len(contour)
    if n < 20 or count <= 0:
        return np.zeros((0, 2))
    def turning(step):
        before = contour - np.roll(contour, step, axis=0)
        after = np.roll(contour, -step, axis=0) - contour
        return np.arctan2(before[:, 0] * after[:, 1] - before[:, 1] * after[:, 0],
                          (before * after).sum(axis=1))

    # A wide window finds the pronounced tips and notches; a narrow one then
    # places each at its sharpest point.
    k = max(4, n // 40)
    turn = turning(k)
    turn = np.convolve(np.r_[turn[-3:], turn, turn[:3]], np.ones(7) / 7, "valid")
    fine = turning(max(2, k // 3))

    def sharpest(index):
        window = (index + np.arange(-k, k + 1)) % n
        same_sign = window[np.sign(fine[window]) == np.sign(turn[index])]
        if not len(same_sign):
            return index
        return int(same_sign[np.argmax(np.abs(fine[same_sign]))])
    height, width = atlas_mask.shape
    visible = np.percentile(atlas_image[atlas_mask], 5)
    chosen = []
    for index in np.argsort(-np.abs(turn)):
        if len(chosen) == count:
            break
        index = sharpest(int(index))
        x, y = contour[index]
        if not (EDGE_MARGIN <= x < width - EDGE_MARGIN and EDGE_MARGIN <= y < height - EDGE_MARGIN):
            continue
        if atlas_image[int(y) - 1:int(y) + 2, int(x) - 1:int(x) + 2].mean() < visible:
            continue
        if all(min(abs(index - j), n - abs(index - j)) > n / 10 for j in chosen):
            chosen.append(index)
    return contour[chosen] + 0.5


def _edge_magnitude(image):
    blurred = cv2.GaussianBlur(np.asarray(image, dtype=np.float32), (0, 0), 1.0)
    return np.hypot(cv2.Sobel(blurred, cv2.CV_32F, 1, 0), cv2.Sobel(blurred, cv2.CV_32F, 0, 1))


def _local_correlation(a, b, radius=5):
    size = (2 * radius + 1, 2 * radius + 1)
    mean_a, mean_b = cv2.boxFilter(a, -1, size), cv2.boxFilter(b, -1, size)
    covariance = cv2.boxFilter(a * b, -1, size) - mean_a * mean_b
    var_a = cv2.boxFilter(a * a, -1, size) - mean_a ** 2
    var_b = cv2.boxFilter(b * b, -1, size) - mean_b ** 2
    return covariance / np.sqrt(np.maximum(var_a * var_b, 1e-12))


def _shared_edge_score(atlas_image, section_in_atlas, inner):
    """Strong atlas edges that the registered section shows too, in [0, 1].

    An edge seen in only one image (an atlas region border in uniform
    tissue, or a dye track in the section) scores near zero.
    """
    atlas_edges = _edge_magnitude(atlas_image)
    section_edges = _edge_magnitude(section_in_atlas)
    agreement = np.clip(_local_correlation(atlas_edges, section_edges), 0.0, 1.0)
    top = np.percentile(atlas_edges[inner], 99) if inner.any() else 0.0
    strength = np.clip(atlas_edges / top, 0.0, 1.0) if top > 0 else np.zeros_like(atlas_edges)
    return np.where(inner, agreement * strength, 0.0)


def _peaks(score, count, radius, taken=()):
    """Up to ``count`` score maxima above MIN_AGREEMENT, ``radius`` apart."""
    score = score.copy()
    for x, y in taken:
        cv2.circle(score, (int(x), int(y)), int(radius), 0, -1)
    points = []
    while len(points) < count:
        row, col = np.unravel_index(np.argmax(score), score.shape)
        if score[row, col] < MIN_AGREEMENT:
            break
        points.append((col + 0.5, row + 0.5))
        cv2.circle(score, (int(col), int(row)), int(radius), 0, -1)
    return np.asarray(points, dtype=float).reshape(-1, 2)


def _section_in_atlas(section_gray, atlas_shape, transform):
    """The section resampled onto the atlas slice's pixels."""
    reference = sitk.GetImageFromArray(np.zeros(atlas_shape, np.float32))
    reference.SetOrigin((0.5, 0.5))
    moving = sitk.GetImageFromArray(np.ascontiguousarray(section_gray, dtype=np.float32))
    moving.SetOrigin((0.5, 0.5))
    return sitk.GetArrayFromImage(sitk.Resample(moving, reference, transform, sitk.sitkLinear, 0.0))


def _snap_to_outline(points, contour, limit):
    """Move each point to the nearest point of ``contour`` if within ``limit``."""
    if not len(contour):
        return points
    snapped = points.copy()
    for i, point in enumerate(points):
        distances = np.linalg.norm(contour - point, axis=1)
        nearest = int(np.argmin(distances))
        if distances[nearest] <= limit:
            snapped[i] = contour[nearest] + 0.5
    return snapped


def propose_landmarks(atlas_intensity, atlas_labels, section, count=10,
                      deformable=True, mesh_size=6, boundary_points=None):
    """Propose paired landmarks mapping an atlas slice onto a section.

    ``section`` must already be in the atlas orientation (see
    ``atlas_matching``). Up to ``count`` landmarks are proposed: the sharpest
    tips and notches of the outline, snapped onto the section outline, then
    internal points on strong edges that both images show. They are
    suggestions for the user to confirm and edit. ``boundary_points`` are
    further atlas points (such as the mesh's frame points) to carry through
    the same transform; they are clamped into the section image so they
    remain valid landmarks. Returns a :class:`LandmarkProposal`.
    """
    atlas_mask = np.asarray(atlas_labels) > 0
    if atlas_mask.sum() < 100:
        raise ValueError("The atlas slice contains too little brain.")
    section_mask = tissue_mask(section)
    section_gray = histology_gray(section).astype(np.float32)
    atlas_image = cv2.normalize(np.asarray(atlas_intensity, dtype=np.float32),
                                None, 0, 1, cv2.NORM_MINMAX)

    fixed_array, fixed_scale = _downsample(atlas_image, cv2.INTER_AREA)
    fixed_mask_array, _ = _downsample(atlas_mask, cv2.INTER_NEAREST)
    moving_array, moving_scale = _downsample(section_gray / 255.0, cv2.INTER_AREA)
    moving_mask_array, _ = _downsample(section_mask, cv2.INTER_NEAREST)
    fixed = _as_image(fixed_array, fixed_scale)
    fixed_mask = _as_image(fixed_mask_array, fixed_scale)
    moving = _as_image(moving_array, moving_scale)
    moving_mask = _as_image(moving_mask_array, moving_scale)

    affine = _affine_on_silhouettes(fixed_mask, moving_mask)
    overlap_affine = _dice(fixed_mask, moving_mask, affine)
    transform, overlap_final, used = affine, overlap_affine, False
    if deformable:
        mask_uint8 = sitk.Cast(fixed_mask > 0.5, sitk.sitkUInt8)
        try:
            candidate, improved = _bspline_on_intensities(
                fixed, moving, mask_uint8, affine, mesh_size
            )
            candidate_overlap = _dice(fixed_mask, moving_mask, candidate)
            # Keep the deformable fit if it improved the intensity match
            # without noticeably breaking the outline match.
            if improved and candidate_overlap >= overlap_affine - 0.03:
                transform, overlap_final, used = candidate, candidate_overlap, True
        except RuntimeError:
            pass  # optimiser failure: fall back to the affine fit

    def to_section(points):
        return np.array([transform.TransformPoint((float(x), float(y)))
                         for x, y in points]).reshape(-1, 2)

    height, width = section_mask.shape
    spacing = _spacing(atlas_mask, count)

    outline_atlas = _outline_points(atlas_mask, atlas_image, min(OUTLINE_LANDMARKS, count))
    outline_section = _snap_to_outline(to_section(outline_atlas), _outer_contour(section_mask),
                                       limit=0.05 * np.hypot(height, width))

    inner = cv2.erode(atlas_mask.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=4) > 0
    score = _shared_edge_score(atlas_image, _section_in_atlas(section_gray / 255.0,
                                                              atlas_mask.shape, transform), inner)
    radius = 0.45 * spacing  # keeps internal points about a tenth of the section apart
    internal_atlas = _peaks(score, count - len(outline_atlas), radius, taken=outline_atlas)
    internal_section = to_section(internal_atlas)
    if len(internal_section):
        rows = np.clip(internal_section[:, 1].astype(int), 0, height - 1)
        cols = np.clip(internal_section[:, 0].astype(int), 0, width - 1)
        inside = ((internal_section[:, 0] >= 0) & (internal_section[:, 0] < width)
                  & (internal_section[:, 1] >= 0) & (internal_section[:, 1] < height))
        keep = inside & section_mask[rows, cols]
        internal_atlas, internal_section = internal_atlas[keep], internal_section[keep]

    boundary = np.asarray(boundary_points if boundary_points is not None else [],
                          dtype=float).reshape(-1, 2)
    carried = to_section(boundary)
    if len(carried):
        carried[:, 0] = np.clip(carried[:, 0], 0, width - 1)
        carried[:, 1] = np.clip(carried[:, 1], 0, height - 1)
    kinds = ("outline",) * len(outline_atlas) + ("internal",) * len(internal_atlas)
    return LandmarkProposal(np.vstack([outline_atlas, internal_atlas]),
                            np.vstack([outline_section, internal_section]),
                            overlap_affine, overlap_final, used, carried, kinds)
