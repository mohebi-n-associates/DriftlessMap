"""Validated, reproducible piecewise-affine registration for DriftlessMap."""

from __future__ import annotations

import cv2
import numpy as np
from scipy.spatial import Delaunay, QhullError


TRIANGULATION_SCHEMA_VERSION = 1
_DUPLICATE_DISTANCE_PX = 0.5
_MIN_DOUBLE_AREA_PX2 = 1.0
_BARYCENTRIC_TOLERANCE = 1e-6
_MAP_TILE_ROWS = 256


class TriangulationError(ValueError):
    """Raised when paired landmarks cannot define a safe registration."""


def _as_points(points, name):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1:] != (2,):
        raise TriangulationError(
            "{} landmarks must have shape (N, 2).".format(name)
        )
    if not np.all(np.isfinite(points)):
        raise TriangulationError(
            "{} landmarks contain non-finite coordinates.".format(name)
        )
    return points


def _as_shape(shape, name):
    try:
        shape = tuple(int(value) for value in shape[:2])
    except (TypeError, ValueError, IndexError):
        raise TriangulationError(
            "{} image shape must contain height and width.".format(name)
        ) from None
    if len(shape) != 2 or any(value <= 0 for value in shape):
        raise TriangulationError(
            "{} image shape must contain positive height and width.".format(name)
        )
    return shape


def _validate_bounds(points, shape, name):
    height, width = shape
    valid = (
        (points[:, 0] >= 0)
        & (points[:, 0] <= width - 1)
        & (points[:, 1] >= 0)
        & (points[:, 1] <= height - 1)
    )
    if not np.all(valid):
        bad = int(np.flatnonzero(~valid)[0])
        raise TriangulationError(
            "{} landmark {} is outside the image.".format(name, bad + 1)
        )


def _validate_duplicates(points, name):
    if len(points) < 2:
        return
    deltas = points[:, None, :] - points[None, :, :]
    distances = np.linalg.norm(deltas, axis=2)
    np.fill_diagonal(distances, np.inf)
    duplicate = np.argwhere(distances < _DUPLICATE_DISTANCE_PX)
    if duplicate.size:
        first, second = duplicate[0]
        raise TriangulationError(
            "{} landmarks {} and {} are duplicates or too close together.".format(
                name, int(first) + 1, int(second) + 1
            )
        )


def _canonical_simplices(points):
    try:
        simplices = Delaunay(points).simplices
    except QhullError as exc:
        raise TriangulationError(
            "Landmarks are collinear or cannot form a Delaunay mesh."
        ) from exc
    simplices = np.sort(np.asarray(simplices, dtype=np.int32), axis=1)
    order = np.lexsort(
        (simplices[:, 2], simplices[:, 1], simplices[:, 0])
    )
    return simplices[order]


def _validate_simplices(simplices, point_count):
    simplices = np.asarray(simplices, dtype=np.int32)
    if simplices.ndim != 2 or simplices.shape[1:] != (3,):
        raise TriangulationError("Triangle connectivity must have shape (T, 3).")
    if not len(simplices):
        raise TriangulationError("The landmark mesh contains no triangles.")
    if np.any(simplices < 0) or np.any(simplices >= point_count):
        raise TriangulationError("Triangle connectivity references a missing landmark.")
    if np.any(
        np.diff(np.sort(simplices, axis=1), axis=1) == 0
    ):
        raise TriangulationError("A triangle references the same landmark twice.")
    unique_rows = np.unique(np.sort(simplices, axis=1), axis=0)
    if len(unique_rows) != len(simplices):
        raise TriangulationError("Triangle connectivity contains duplicates.")
    return simplices


def _signed_double_area(triangles):
    edge_1 = triangles[:, 1] - triangles[:, 0]
    edge_2 = triangles[:, 2] - triangles[:, 0]
    return edge_1[:, 0] * edge_2[:, 1] - edge_1[:, 1] * edge_2[:, 0]


def _minimum_angles(triangles):
    result = np.zeros(len(triangles), dtype=float)
    for index, triangle in enumerate(triangles):
        sides = np.array(
            [
                np.linalg.norm(triangle[1] - triangle[2]),
                np.linalg.norm(triangle[0] - triangle[2]),
                np.linalg.norm(triangle[0] - triangle[1]),
            ],
            dtype=float,
        )
        if np.any(sides <= 0):
            result[index] = 0.0
            continue
        cosines = np.array(
            [
                (sides[1] ** 2 + sides[2] ** 2 - sides[0] ** 2)
                / (2 * sides[1] * sides[2]),
                (sides[0] ** 2 + sides[2] ** 2 - sides[1] ** 2)
                / (2 * sides[0] * sides[2]),
                (sides[0] ** 2 + sides[1] ** 2 - sides[2] ** 2)
                / (2 * sides[0] * sides[1]),
            ]
        )
        result[index] = float(
            np.min(np.degrees(np.arccos(np.clip(cosines, -1.0, 1.0))))
        )
    return result


def _affine_condition_numbers(source_triangles, target_triangles):
    conditions = np.full(len(source_triangles), np.inf, dtype=float)
    for index, (source, target) in enumerate(
        zip(source_triangles, target_triangles)
    ):
        source_edges = (source[1:] - source[0]).T
        target_edges = (target[1:] - target[0]).T
        try:
            linear = target_edges @ np.linalg.inv(source_edges)
        except np.linalg.LinAlgError:
            continue
        singular_values = np.linalg.svd(linear, compute_uv=False)
        if singular_values[-1] > np.finfo(float).eps:
            conditions[index] = float(
                singular_values[0] / singular_values[-1]
            )
    return conditions


def _mesh_quality(atlas_points, histology_points, simplices):
    atlas_triangles = atlas_points[simplices]
    histology_triangles = histology_points[simplices]
    atlas_area = _signed_double_area(atlas_triangles)
    histology_area = _signed_double_area(histology_triangles)
    degenerate = (
        (np.abs(atlas_area) < _MIN_DOUBLE_AREA_PX2)
        | (np.abs(histology_area) < _MIN_DOUBLE_AREA_PX2)
    )
    folded = (atlas_area * histology_area < 0) & ~degenerate

    area_ratio = np.full(len(simplices), np.nan, dtype=float)
    usable = np.abs(histology_area) >= _MIN_DOUBLE_AREA_PX2
    area_ratio[usable] = (
        np.abs(atlas_area[usable]) / np.abs(histology_area[usable])
    )
    finite_ratio = area_ratio[np.isfinite(area_ratio) & (area_ratio > 0)]
    median_ratio = float(np.median(finite_ratio)) if finite_ratio.size else 1.0
    normalized_area_ratio = area_ratio / median_ratio

    minimum_angle = np.minimum(
        _minimum_angles(atlas_triangles),
        _minimum_angles(histology_triangles),
    )
    condition = _affine_condition_numbers(
        histology_triangles, atlas_triangles
    )

    severity = np.zeros(len(simplices), dtype=np.uint8)
    warning = (
        (minimum_angle < 15.0)
        | (condition > 6.0)
        | (normalized_area_ratio < 0.25)
        | (normalized_area_ratio > 4.0)
    )
    severe = (
        degenerate
        | folded
        | (minimum_angle < 5.0)
        | (condition > 20.0)
        | (normalized_area_ratio < 0.05)
        | (normalized_area_ratio > 20.0)
    )
    severity[warning] = 1
    severity[severe] = 2

    finite_condition = condition[np.isfinite(condition)]
    summary = {
        "triangle_count": int(len(simplices)),
        "folded_count": int(np.count_nonzero(folded)),
        "degenerate_count": int(np.count_nonzero(degenerate)),
        "warning_count": int(np.count_nonzero(severity == 1)),
        "severe_count": int(np.count_nonzero(severity == 2)),
        "review_count": int(np.count_nonzero(severity > 0)),
        "minimum_angle_deg": (
            float(np.min(minimum_angle)) if len(minimum_angle) else 0.0
        ),
        "maximum_anisotropy": (
            float(np.max(finite_condition))
            if finite_condition.size
            else float("inf")
        ),
        "minimum_normalized_area": (
            float(np.nanmin(normalized_area_ratio))
            if np.any(np.isfinite(normalized_area_ratio))
            else float("nan")
        ),
        "maximum_normalized_area": (
            float(np.nanmax(normalized_area_ratio))
            if np.any(np.isfinite(normalized_area_ratio))
            else float("nan")
        ),
    }
    return {
        "atlas_signed_double_area": atlas_area,
        "histology_signed_double_area": histology_area,
        "normalized_area_ratio": normalized_area_ratio,
        "minimum_angle_deg": minimum_angle,
        "anisotropy": condition,
        "folded": folded,
        "degenerate": degenerate,
        "severity": severity,
        "summary": summary,
    }


def build_piecewise_affine_registration(
    atlas_points,
    histology_points,
    *,
    atlas_shape,
    histology_shape,
    simplices=None,
    allow_unsafe=False,
):
    """Create one topology shared by both registration directions.

    ``allow_unsafe`` is intended only for live mesh visualization. Transfers
    keep the default strict behavior and reject collapsed or folded triangles.
    """
    atlas_points = _as_points(atlas_points, "Atlas")
    histology_points = _as_points(histology_points, "Histology")
    atlas_shape = _as_shape(atlas_shape, "Atlas")
    histology_shape = _as_shape(histology_shape, "Histology")

    if len(atlas_points) != len(histology_points):
        raise TriangulationError(
            "Atlas and histology must contain the same number of paired landmarks."
        )
    if len(atlas_points) < 3:
        raise TriangulationError(
            "At least three paired landmarks are required."
        )
    _validate_bounds(atlas_points, atlas_shape, "Atlas")
    _validate_bounds(histology_points, histology_shape, "Histology")
    _validate_duplicates(atlas_points, "Atlas")
    _validate_duplicates(histology_points, "Histology")

    if simplices is None:
        simplices = _canonical_simplices(atlas_points)
    else:
        simplices = _validate_simplices(simplices, len(atlas_points))
    quality = _mesh_quality(atlas_points, histology_points, simplices)
    summary = quality["summary"]
    errors = []
    if summary["degenerate_count"]:
        errors.append(
            "{} triangle(s) collapse to a line or a point.".format(
                summary["degenerate_count"]
            )
        )
    if summary["folded_count"]:
        errors.append(
            "{} triangle(s) are folded. Move the corresponding landmarks "
            "until the red triangles disappear.".format(summary["folded_count"])
        )
    if errors and not allow_unsafe:
        raise TriangulationError(" ".join(errors))

    warnings = []
    if summary["warning_count"] or summary["severe_count"]:
        warnings.append(
            "{} triangle(s) have high stretch or narrow angles.".format(
                summary["warning_count"] + summary["severe_count"]
            )
        )
    return {
        "schema_version": TRIANGULATION_SCHEMA_VERSION,
        "method": "shared-atlas-delaunay-piecewise-affine",
        "atlas_points": atlas_points,
        "histology_points": histology_points,
        "atlas_shape": atlas_shape,
        "histology_shape": histology_shape,
        "simplices": np.asarray(simplices, dtype=np.int32),
        "quality": quality,
        "warnings": warnings,
        "errors": errors,
    }


def registration_summary_text(registration):
    summary = registration["quality"]["summary"]
    text = (
        "{triangle_count} triangles | {folded_count} folded | "
        "{review_count} warning/review | min angle {minimum_angle_deg:.1f}° | "
        "max anisotropy {maximum_anisotropy:.1f}×"
    ).format(**summary)
    return text


def triangle_colors(registration):
    """Return RGB colors for healthy, warning, and severe triangles."""
    severity = registration["quality"]["severity"]
    palette = np.array(
        [
            [60, 190, 90],
            [240, 180, 30],
            [225, 65, 65],
        ],
        dtype=np.uint8,
    )
    return palette[severity]


def _registration_spaces(registration, direction):
    if direction == "histology_to_atlas":
        return (
            registration["histology_points"],
            registration["atlas_points"],
            registration["atlas_shape"],
        )
    if direction == "atlas_to_histology":
        return (
            registration["atlas_points"],
            registration["histology_points"],
            registration["histology_shape"],
        )
    raise ValueError(
        "Direction must be 'histology_to_atlas' or 'atlas_to_histology'."
    )


def _barycentric(points, triangle):
    matrix = (triangle[1:] - triangle[0]).T
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return np.full((len(points), 3), np.nan, dtype=float)
    uv = (points - triangle[0]) @ inverse.T
    return np.column_stack((1.0 - uv[:, 0] - uv[:, 1], uv))


def dense_inverse_map(registration, direction):
    """Return OpenCV maps from every destination pixel back to the source."""
    source_points, destination_points, destination_shape = (
        _registration_spaces(registration, direction)
    )
    height, width = destination_shape
    map_x = np.full((height, width), -1.0, dtype=np.float32)
    map_y = np.full((height, width), -1.0, dtype=np.float32)
    assigned = np.zeros((height, width), dtype=bool)

    for simplex in registration["simplices"]:
        destination_triangle = destination_points[simplex]
        source_triangle = source_points[simplex]
        x_min = max(0, int(np.floor(np.min(destination_triangle[:, 0]))))
        x_max = min(
            width - 1, int(np.ceil(np.max(destination_triangle[:, 0])))
        )
        y_min = max(0, int(np.floor(np.min(destination_triangle[:, 1]))))
        y_max = min(
            height - 1, int(np.ceil(np.max(destination_triangle[:, 1])))
        )
        if x_max < x_min or y_max < y_min:
            continue

        for tile_y_min in range(y_min, y_max + 1, _MAP_TILE_ROWS):
            tile_y_max = min(y_max, tile_y_min + _MAP_TILE_ROWS - 1)
            grid_y, grid_x = np.mgrid[
                tile_y_min : tile_y_max + 1, x_min : x_max + 1
            ]
            coordinates = np.column_stack((grid_x.ravel(), grid_y.ravel()))
            weights = _barycentric(coordinates, destination_triangle)
            inside = np.all(weights >= -_BARYCENTRIC_TOLERANCE, axis=1)
            if not np.any(inside):
                continue
            destination_y = grid_y.ravel()[inside]
            destination_x = grid_x.ravel()[inside]
            new_pixels = ~assigned[destination_y, destination_x]
            if not np.any(new_pixels):
                continue
            destination_y = destination_y[new_pixels]
            destination_x = destination_x[new_pixels]
            source = weights[inside][new_pixels] @ source_triangle
            map_x[destination_y, destination_x] = source[:, 0]
            map_y[destination_y, destination_x] = source[:, 1]
            assigned[destination_y, destination_x] = True
    return map_x, map_y, assigned


def warp_image_piecewise(
    image,
    registration,
    direction,
    *,
    interpolation=cv2.INTER_LINEAR,
):
    """Warp an image with one dense inverse map, avoiding triangle seams."""
    image = np.asarray(image)
    if image.ndim not in (2, 3):
        raise ValueError("Images must be two- or three-dimensional.")
    source_points, _destination_points, _shape = _registration_spaces(
        registration, direction
    )
    expected_shape = (
        registration["histology_shape"]
        if direction == "histology_to_atlas"
        else registration["atlas_shape"]
    )
    if tuple(image.shape[:2]) != tuple(expected_shape):
        raise ValueError("The source image does not match the registration.")
    if not np.all(np.isfinite(source_points)):
        raise ValueError("Registration source points are invalid.")

    map_x, map_y, valid = dense_inverse_map(registration, direction)
    warped = cv2.remap(
        image,
        map_x,
        map_y,
        interpolation,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    if warped.ndim == 3:
        warped[~valid, :] = 0
    else:
        warped[~valid] = 0
    return warped


def transform_points_piecewise(points, registration, direction):
    """Transform points through the persisted mesh.

    Returns ``(transformed, valid, triangle_index)``. Invalid points retain NaN
    coordinates and can be reported or removed by the caller.
    """
    points = _as_points(points, "Input")
    source_points, destination_points, _destination_shape = _registration_spaces(
        registration, direction
    )
    transformed = np.full_like(points, np.nan, dtype=float)
    triangle_index = np.full(len(points), -1, dtype=np.int32)
    if not len(points):
        return transformed, np.zeros(0, dtype=bool), triangle_index

    height, width = (
        registration["histology_shape"]
        if direction == "histology_to_atlas"
        else registration["atlas_shape"]
    )
    in_bounds = (
        (points[:, 0] >= 0)
        & (points[:, 0] <= width - 1)
        & (points[:, 1] >= 0)
        & (points[:, 1] <= height - 1)
    )
    unassigned = in_bounds.copy()
    for tri_index, simplex in enumerate(registration["simplices"]):
        if not np.any(unassigned):
            break
        source_triangle = source_points[simplex]
        x_min, y_min = np.min(source_triangle, axis=0)
        x_max, y_max = np.max(source_triangle, axis=0)
        candidates = np.flatnonzero(
            unassigned
            & (points[:, 0] >= x_min - _BARYCENTRIC_TOLERANCE)
            & (points[:, 0] <= x_max + _BARYCENTRIC_TOLERANCE)
            & (points[:, 1] >= y_min - _BARYCENTRIC_TOLERANCE)
            & (points[:, 1] <= y_max + _BARYCENTRIC_TOLERANCE)
        )
        if not len(candidates):
            continue
        weights = _barycentric(points[candidates], source_triangle)
        inside = np.all(weights >= -_BARYCENTRIC_TOLERANCE, axis=1)
        selected = candidates[inside]
        if not len(selected):
            continue
        transformed[selected] = weights[inside] @ destination_points[simplex]
        triangle_index[selected] = tri_index
        unassigned[selected] = False
    valid = triangle_index >= 0
    return transformed, valid, triangle_index
