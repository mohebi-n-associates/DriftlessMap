import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from driftlessmap.atlas_matching import tissue_mask
from driftlessmap.auto_registration import (
    EDGE_MARGIN, MIN_AGREEMENT, _outer_contour, _outline_points, _shared_edge_score,
    propose_landmarks,
)


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
        self.assertTrue(3 <= len(proposal.atlas_points) <= 10)
        self.assertEqual(len(proposal.kinds), len(proposal.atlas_points))
        errors = np.linalg.norm(proposal.boundary_points - known_warp(grid), axis=1)
        # section pixels are 2.5x atlas pixels: within ~1.6 atlas pixels,
        # including grid points close to the outline
        self.assertLess(np.median(errors), 4.0, errors)
        internal = np.array([kind == "internal" for kind in proposal.kinds])
        if internal.any():
            truth = known_warp(proposal.atlas_points[internal])
            landmark_errors = np.linalg.norm(proposal.histology_points[internal] - truth, axis=1)
            self.assertLess(np.median(landmark_errors), 6.0, landmark_errors)
        self.assertGreater(proposal.overlap_final, 0.9)

    def test_outline_points_lie_on_both_outlines(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        proposal = propose_landmarks(intensity, labels, section, deformable=False)
        outline = np.array([kind == "outline" for kind in proposal.kinds])
        self.assertGreaterEqual(outline.sum(), 2)
        atlas_contour = _outer_contour(labels > 0) + 0.5
        section_contour = _outer_contour(tissue_mask(section)) + 0.5
        for a, h in zip(proposal.atlas_points[outline], proposal.histology_points[outline]):
            self.assertLess(np.linalg.norm(atlas_contour - a, axis=1).min(), 1.0)
            self.assertLess(np.linalg.norm(section_contour - h, axis=1).min(), 1.0)
        # a notch where the two lobes of the synthetic slice meet is found
        notch = np.array([[35.8, 117.4], [20.0, 84.0]])  # ellipse intersections
        self.assertLess(min(np.linalg.norm(proposal.atlas_points[outline] - q, axis=1).min()
                            for q in notch), 12.0)

    def test_internal_points_sit_on_edges_both_images_show(self):
        intensity, labels = synthetic_slice()
        section = warped_section(intensity, labels)
        proposal = propose_landmarks(intensity, labels, section, deformable=False)
        internal = proposal.atlas_points[[kind == "internal" for kind in proposal.kinds]]
        self.assertGreaterEqual(len(internal), 1)
        edges = cv2.Canny((intensity * 255).astype(np.uint8), 20, 60) > 0
        ys, xs = np.nonzero(edges)
        edge_points = np.column_stack([xs, ys]) + 0.5
        for point in internal:
            self.assertLess(np.linalg.norm(edge_points - point, axis=1).min(), 4.0)

    def test_an_edge_in_only_one_image_scores_nothing(self):
        atlas = np.full((80, 80), 0.4, np.float32)
        atlas[:, 40:] = 0.9                       # an edge in both images
        section = atlas.copy()
        section[20:60, 15] = 1.0                  # a "dye track" only in the section
        atlas_only = atlas.copy()
        atlas_only[40:, 60] = 0.1                 # a border only in the atlas
        inner = np.ones_like(atlas, bool)
        score = _shared_edge_score(atlas_only, section, inner)
        self.assertGreater(score[40, 39:41].max(), MIN_AGREEMENT)
        self.assertLess(score[40, 12:18].max(), MIN_AGREEMENT)
        self.assertLess(score[60, 58:62].max(), MIN_AGREEMENT)

    def test_outline_cut_by_the_image_edge_is_skipped(self):
        intensity, labels = synthetic_slice()
        cut = labels.copy()
        cut[:, :40] = 0
        cut[40:130, :40] = 1                      # brain runs off the left edge
        image = cv2.normalize(intensity + 0.4 * (cut > 0), None, 0, 1, cv2.NORM_MINMAX)
        points = _outline_points(cut > 0, image, 5)
        self.assertTrue(np.all(points[:, 0] >= EDGE_MARGIN), points)

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
