"""Automatic landmark proposal between an atlas slice and a histology section.

The atlas slice is the fixed image, so the fitted SimpleITK transform maps an
atlas point directly to the matching section point; sampling it at a few
distinctive, well-spread atlas points yields landmark pairs for DriftlessMap's
piecewise-affine registration, which the user then reviews and edits.

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


def _spacing(mask, count):
    """Typical distance between ``count`` points spread over ``mask``."""
    return max(2.0, float(np.sqrt(mask.sum() / max(count, 1))))


def _importance(atlas_image, atlas_labels, inner):
    """How distinctive each atlas pixel is as a landmark, in [0, 2].

    Corner-like structure in the template image plus junctions of region
    boundaries; both are places that can be matched in two directions,
    unlike points along a straight edge or in uniform tissue.
    """
    def normalised(response):
        response = np.where(inner, response, 0.0)
        top = np.percentile(response[inner], 99) if inner.any() else 0.0
        return np.clip(response / top, 0.0, 1.0) if top > 0 else np.zeros_like(response)

    image = cv2.GaussianBlur(np.asarray(atlas_image, dtype=np.float32), (0, 0), 1.0)
    labels = np.asarray(atlas_labels).astype(np.int64)
    edge = np.zeros(labels.shape, np.float32)
    edge[:-1] += labels[:-1] != labels[1:]
    edge[:, :-1] += labels[:, :-1] != labels[:, 1:]
    edge = cv2.GaussianBlur(edge, (0, 0), 1.5)
    return (normalised(cv2.cornerMinEigenVal(image, 5, 3))
            + normalised(cv2.cornerMinEigenVal(edge, 5, 3)))


def _candidate_points(inner, spacing):
    """A fine grid of pixel-centre points inside ``inner``."""
    step = max(1, int(spacing / 6))
    rows, cols = np.nonzero(inner[::step, ::step])
    return np.column_stack([cols * step + 0.5, rows * step + 0.5]).astype(float)


def _select(points, weights, count, spacing):
    """Greedily pick up to ``count`` important points that are spread out.

    A point's weight is discounted while it is closer than ``spacing`` to an
    already chosen point, so the choice covers the whole section rather than
    clustering on the most distinctive region. Returns indexes, most
    distinctive first.
    """
    chosen = []
    nearest = np.full(len(points), np.inf)
    for _ in range(min(count, len(points))):
        score = weights * np.minimum(nearest / spacing, 1.0)
        index = int(np.argmax(score))
        if score[index] <= 0:
            break
        chosen.append(index)
        nearest = np.minimum(nearest, np.linalg.norm(points - points[index], axis=1))
    return np.asarray(chosen, dtype=int)


def propose_landmarks(atlas_intensity, atlas_labels, section, count=10,
                      deformable=True, mesh_size=6, boundary_points=None):
    """Propose paired landmarks mapping an atlas slice onto a section.

    ``section`` must already be in the atlas orientation (see
    ``atlas_matching``). Up to ``count`` landmarks are chosen at the most
    distinctive atlas points that land on tissue, spread over the section,
    most distinctive first. ``boundary_points`` are further atlas points (such
    as the mesh's frame points) to carry through the same transform; they are
    clamped into the section image so they remain valid landmarks.
    Returns a :class:`LandmarkProposal`.
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

    spacing = _spacing(atlas_mask, count)
    inner = cv2.erode(atlas_mask.astype(np.uint8), np.ones((3, 3), np.uint8),
                      iterations=max(1, int(spacing / 5))) > 0
    importance = _importance(atlas_image, atlas_labels, inner)
    atlas_points = _candidate_points(inner, spacing)
    mapped = np.array([transform.TransformPoint((float(x), float(y)))
                       for x, y in atlas_points]).reshape(-1, 2)
    height, width = section_mask.shape
    inside = (
        (mapped[:, 0] >= 0) & (mapped[:, 0] < width)
        & (mapped[:, 1] >= 0) & (mapped[:, 1] < height)
    )
    on_tissue = np.zeros(len(mapped), dtype=bool)
    rows = np.clip(mapped[inside, 1].astype(int), 0, height - 1)
    cols = np.clip(mapped[inside, 0].astype(int), 0, width - 1)
    on_tissue[inside] = section_mask[rows, cols]
    valid = np.flatnonzero(on_tissue)
    # A small floor keeps featureless regions eligible, so every part of the
    # section can still receive a landmark when it is far from the others.
    weights = 0.05 + importance[atlas_points[valid, 1].astype(int),
                                atlas_points[valid, 0].astype(int)]
    keep = valid[_select(atlas_points[valid], weights, count, spacing)]
    boundary = np.asarray(boundary_points if boundary_points is not None else [],
                          dtype=float).reshape(-1, 2)
    carried = np.array([transform.TransformPoint((float(x), float(y)))
                        for x, y in boundary]).reshape(-1, 2)
    if len(carried):
        carried[:, 0] = np.clip(carried[:, 0], 0, width - 1)
        carried[:, 1] = np.clip(carried[:, 1], 0, height - 1)
    return LandmarkProposal(atlas_points[keep], mapped[keep], overlap_affine,
                            overlap_final, used, carried)
