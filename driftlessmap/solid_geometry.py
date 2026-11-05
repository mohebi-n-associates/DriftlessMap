"""Distances to convex implant solids, in the caller's physical units.

The hull includes the interior: containment is an intersection, not a large
positive distance to an outline. Segment radii are conservative capsules.
"""
import json
from functools import lru_cache

import numpy as np
from scipy.spatial import ConvexHull


def point_triangle(point, triangle):
    a, b, c = triangle
    normal = np.cross(b - a, c - a)
    norm = np.dot(normal, normal)
    if norm > 0:
        projected = point - normal * np.dot(point - a, normal) / norm
        signs = [np.dot(np.cross(y - x, projected - x), normal)
                 for x, y in ((a, b), (b, c), (c, a))]
        if min(signs) >= -1e-8:
            return float(np.linalg.norm(point - projected)), projected
    best = None
    for x, y in ((a, b), (b, c), (c, a)):
        edge = y - x
        t = np.clip(np.dot(point - x, edge) / max(np.dot(edge, edge), 1e-30), 0, 1)
        q = x + t * edge
        candidate = (float(np.linalg.norm(point - q)), q)
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best


class ConvexSolid:
    def __init__(self, vertices):
        self.vertices = np.asarray(vertices, dtype=float)
        hull = ConvexHull(self.vertices)
        self.equations = hull.equations
        self.triangles = self.vertices[hull.simplices]
        self.edges = sorted({tuple(sorted((int(a), int(b))))
                             for face in hull.simplices
                             for a, b in zip(face, np.roll(face, -1))})

    def segment_distance(self, start, end):
        from .probe_plans import _segment_distance

        start, end = np.asarray(start), np.asarray(end)
        # Clip against every outward-facing hull plane, including containment.
        low, high = 0.0, 1.0
        for equation in self.equations:
            offset = np.dot(equation[:3], start) + equation[3]
            slope = np.dot(equation[:3], end - start)
            if abs(slope) < 1e-12:
                if offset > 1e-8:
                    low, high = 1.0, 0.0
                    break
            elif slope > 0:
                high = min(high, -offset / slope)
            else:
                low = max(low, -offset / slope)
        if low <= high + 1e-10:
            return 0.0, start + np.clip(low, 0, 1) * (end - start)
        best = (float('inf'), start)
        for point in (start, end):
            for triangle in self.triangles:
                distance, _ = point_triangle(point, triangle)
                if distance < best[0]:
                    best = distance, point
        for i, j in self.edges:
            distance, point, _ = _segment_distance(start, end, self.vertices[i], self.vertices[j])
            if distance < best[0]:
                best = distance, point
        return best

    def distance(self, other):
        best = (float('inf'), self.vertices[0])
        for source, target in ((self, other), (other, self)):
            for i, j in source.edges:
                candidate = target.segment_distance(source.vertices[i], source.vertices[j])
                if candidate[0] < best[0]:
                    best = candidate
                if best[0] == 0:
                    return best
        return best


def prism_solid(plan):
    return _prism_solid(json.dumps(plan.to_dict(), sort_keys=True))


@lru_cache(maxsize=128)
def _prism_solid(payload):
    from .probe_plans import ProbePlan
    plan = ProbePlan.from_dict(json.loads(payload))
    from .implants import _prism_corners
    from .probe_plans import planned_model

    return ConvexSolid(_prism_corners(planned_model(plan, None, 1.0)))


def prism_pair_gap(plan_a, read_a, plan_b, read_b, above_um):
    from .probe_plans import plan_segments

    if read_a is None or read_b is None or read_a.get('entry_um') is None or read_b.get('entry_um') is None:
        return None
    if plan_a.kind == plan_b.kind == 'prism':
        return prism_solid(plan_a).distance(prism_solid(plan_b))
    prism, other, read = (plan_a, plan_b, read_b) if plan_a.kind == 'prism' else (plan_b, plan_a, read_a)
    solid = prism_solid(prism)
    best = None
    for start, end, radius in plan_segments(other, read, above_um):
        distance, point = solid.segment_distance(start, end)
        candidate = distance - radius, point
        if best is None or candidate[0] < best[0]:
            best = candidate
    return best
