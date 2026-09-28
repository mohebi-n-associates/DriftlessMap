import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from driftlessmap.auto_registration import _importance, _select, propose_landmarks


def synthetic_slice(size=(160, 240)):
    """An atlas-like slice: outline plus internal structures of distinct contrast."""
    height, width = size
    labels = np.zeros(size, np.int32)
    intensity = np.zeros(size, np.float32)
    cv2.ellipse(labels, (120, 85), (100, 60), 0, 0, 360, 1, -1)
    cv2.ellipse(labels, (30, 100), (22, 18), 0, 0, 360, 1, -1)
    intensity[labels > 0] = 0.4
    for (x, y, rx, ry, value) in ((90, 70, 18, 10, 0.9), (150, 95, 22, 14, 0.15),
                                  (120, 45, 40, 6, 0.8), (175, 70, 10, 20, 1.0)):
        mask = np.zeros(size, np.uint8)
        cv2.ellipse(mask, (x, y), (rx, ry), 0, 0, 360, 1, -1)
        intensity[(mask > 0) & (labels > 0)] = value
    return intensity, labels


def known_warp(points, scale=2.5, shift=(30.0, 20.0)):
    """Ground truth atlas -> section mapping (affine + gentle bend)."""
    x, y = points[..., 0], points[..., 1]
    wx = scale * x + shift[0] + 6 * np.sin(y / 25.0)
    wy = scale * y + shift[1] + 4 * np.cos(x / 30.0)
    return np.stack([wx, wy], axis=-1)


def warped_section(intensity, labels):
    """Render the section by sampling the atlas at the inverse of known_warp."""
    height, width = int(labels.shape[0] * 2.5 + 60), int(labels.shape[1] * 2.5 + 80)
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32) + 0.5
    # invert numerically: a few fixed-point iterations of the gentle bend
    ax, ay = (xs - 30) / 2.5, (ys - 20) / 2.5
    for _ in range(5):
        ax = (xs - 30 - 6 * np.sin(ay / 25.0)) / 2.5
        ay = (ys - 20 - 4 * np.cos(ax / 30.0)) / 2.5
    image = cv2.remap(intensity, ax - 0.5, ay - 0.5, cv2.INTER_LINEAR)
    rng = np.random.default_rng(1)
    image = np.clip(image * 200 + rng.normal(0, 6, image.shape), 0, 255)
    # a different "stain": invert contrast inside tissue
    tissue = image > 20
    image[tissue] = 255 - image[tissue] * 0.7
    return np.dstack([image] * 3).astype(np.uint8)


class ProposeLandmarkTests(unittest.TestCase):
    def test_landmarks_follow_a_known_deformation(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        # Measure the fit on a fixed interior grid, independent of which
        # landmarks are selected, by carrying the grid through the transform.
        ys, xs = np.mgrid[10:160:12, 10:240:12]
        grid = np.column_stack([xs.ravel(), ys.ravel()]).astype(float) + 0.5
        inner = cv2.erode((labels > 0).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        grid = grid[inner[grid[:, 1].astype(int), grid[:, 0].astype(int)]]
        proposal = propose_landmarks(intensity, labels, section, boundary_points=grid)
        self.assertEqual(len(proposal.atlas_points), 10)
        errors = np.linalg.norm(proposal.boundary_points - known_warp(grid), axis=1)
        # section pixels are 2.5x atlas pixels: within ~1.6 atlas pixels,
        # including grid points close to the outline
        self.assertLess(np.median(errors), 4.0, errors)
        truth = known_warp(proposal.atlas_points)
        landmark_errors = np.linalg.norm(proposal.histology_points - truth, axis=1)
        self.assertLess(np.median(landmark_errors), 6.0, landmark_errors)
        self.assertGreater(proposal.overlap_final, 0.9)

    def test_landmarks_are_distinctive_and_spread_out(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        proposal = propose_landmarks(intensity, labels, section, deformable=False, count=8)
        points = proposal.atlas_points
        self.assertEqual(len(points), 8)
        inner = labels > 0
        importance = _importance(intensity, labels, inner)
        at_points = importance[points[:, 1].astype(int), points[:, 0].astype(int)]
        self.assertGreater(at_points.mean(), 2 * importance[inner].mean())
        gaps = np.linalg.norm(points[:, None] - points[None], axis=2)
        np.fill_diagonal(gaps, np.inf)
        self.assertGreater(gaps.min(), 10.0)  # not clustered

    def test_selection_prefers_weight_but_keeps_distance(self):
        points = np.array([[0.0, 0.0], [1.0, 0.0], [50.0, 0.0]])
        chosen = _select(points, np.array([1.0, 0.9, 0.5]), 2, spacing=20.0)
        self.assertEqual(chosen.tolist(), [0, 2])

    def test_affine_only_mode_and_empty_atlas(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        proposal = propose_landmarks(intensity, labels, section, deformable=False)
        self.assertFalse(proposal.deformable_used)
        with self.assertRaises(ValueError):
            propose_landmarks(intensity, np.zeros_like(labels), section)

    def test_frame_points_are_carried_and_clamped(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        height, width = labels.shape
        frame = np.array([[0.0, 0.0], [width, 0.0], [width, height], [0.0, height],
                          [width / 2, height / 2]])
        proposal = propose_landmarks(intensity, labels, section, deformable=False,
                                     boundary_points=frame)
        self.assertEqual(proposal.boundary_points.shape, (5, 2))
        sh, sw = section.shape[:2]
        self.assertTrue(np.all(proposal.boundary_points >= 0))
        self.assertTrue(np.all(proposal.boundary_points[:, 0] <= sw - 1))
        self.assertTrue(np.all(proposal.boundary_points[:, 1] <= sh - 1))
        # the centre point follows the fit rather than being clamped
        truth = known_warp(frame[4:])
        self.assertLess(np.linalg.norm(proposal.boundary_points[4] - truth[0]), 10.0)
        self.assertEqual(propose_landmarks(intensity, labels, section, deformable=False)
                         .boundary_points.shape, (0, 2))


SAMPLE = Path(os.environ.get("DRIFTLESSMAP_SAMPLE_SECTION", ""))
ATLAS = Path(os.environ.get("DRIFTLESSMAP_SAMPLE_ATLAS", ""))


@unittest.skipUnless(SAMPLE.is_file() and ATLAS.is_dir(), "sample section/atlas not configured")
class RealSectionTests(unittest.TestCase):
    def test_real_section_registers(self):
        from driftlessmap.atlas_loader import AtlasLoader
        from driftlessmap.atlas_matching import atlas_slice, suggest_sections

        loaded = AtlasLoader(str(ATLAS), load_boundaries=False)
        labels = np.transpose(loaded.segmentation_data, [2, 0, 1])[::-1, :, :]
        intensity = np.transpose(loaded.atlas_data, [2, 0, 1])[::-1, :, :]
        section = cv2.imread(str(SAMPLE))[..., ::-1]
        midline = int(loaded.atlas_info[3]["Bregma"][0])
        report = suggest_sections(section, labels, intensity, midline,
                                  (labels.shape[2] // 2, midline, labels.shape[0] // 2))
        best = report.suggestions[0]
        oriented = np.ascontiguousarray(best.orientation.apply(section))
        proposal = propose_landmarks(atlas_slice(intensity, best.plane, best.index),
                                     atlas_slice(labels, best.plane, best.index), oriented)
        self.assertGreater(proposal.overlap_final, 0.85)
        self.assertGreaterEqual(len(proposal.atlas_points), 20)


if __name__ == "__main__":
    unittest.main()
