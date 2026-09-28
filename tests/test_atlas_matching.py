import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from driftlessmap.atlas_matching import (
    ORIENTATIONS,
    atlas_slice,
    best_by_plane,
    hemisphere_indexes,
    mirrored_index,
    rank_depths,
    same_up_to_hemisphere,
    search_planes,
    tissue_mask,
)


def synthetic_brain():
    """A left-right symmetric 'brain' (rows DV, ML, AP) with an anterior bulb
    and a posterior dorsal lobe, labelled in view order like AtlasView."""
    dv, ml, ap = 40, 50, 80
    z, x, y = np.meshgrid(np.arange(dv), np.arange(ml), np.arange(ap), indexing="ij")
    body = ((z - 22) / 14) ** 2 + ((x - 25) / 20) ** 2 + ((y - 42) / 26) ** 2 <= 1
    bulb = ((z - 24) / 6) ** 2 + ((x - 25) / 7) ** 2 + ((y - 10) / 8) ** 2 <= 1
    lobe = ((z - 10) / 8) ** 2 + ((x - 25) / 12) ** 2 + ((y - 64) / 9) ** 2 <= 1
    labels = np.zeros((dv, ml, ap), np.int32)
    labels[body] = 10
    labels[bulb] = 20
    labels[lobe] = 30
    labels[31:] = 0  # flat ventral surface, as in a real brain
    return labels


def fake_section(labels, plane, index, orientation_index, scale=4):
    slice_ = (atlas_slice(labels, plane, index) > 0).astype(np.uint8) * 180
    section = cv2.resize(slice_, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    # Undo the target orientation: the search must find the one that restores it.
    target = ORIENTATIONS[orientation_index]
    inverse = next(o for o in ORIENTATIONS
                   if np.array_equal(o.apply(target.apply(np.arange(6).reshape(2, 3))),
                                     np.arange(6).reshape(2, 3)))
    section = np.ascontiguousarray(inverse.apply(section))
    rng = np.random.default_rng(0)
    noisy = section.astype(np.float32) + rng.normal(0, 12, section.shape)
    rgb = np.clip(np.dstack([noisy, noisy * 0.8, noisy * 0.5]), 0, 255).astype(np.uint8)
    return rgb, target


class TissueMaskTests(unittest.TestCase):
    def test_holes_are_filled_and_debris_ignored(self):
        image = np.zeros((200, 300, 3), np.uint8)
        cv2.ellipse(image, (150, 100), (100, 60), 0, 0, 360, (200, 180, 90), -1)
        cv2.circle(image, (150, 100), 15, (0, 0, 0), -1)      # a ventricle
        image[5:8, 5:8] = 255                                   # dust
        mask = tissue_mask(image)
        self.assertTrue(mask[100, 150])
        self.assertFalse(mask[6, 6])


class PlaneSearchTests(unittest.TestCase):
    def test_plane_orientation_and_slice_are_recovered(self):
        labels = synthetic_brain()
        cases = [("sagittal", 18, 0), ("sagittal", 14, 3), ("coronal", 42, 5),
                 ("horizontal", 22, 6)]
        for plane, index, orientation_index in cases:
            with self.subTest(plane=plane, index=index, orientation=orientation_index):
                section, expected = fake_section(labels, plane, index, orientation_index)
                best = search_planes(section, labels)[0]
                self.assertEqual(best.plane, plane)
                self.assertTrue(
                    same_up_to_hemisphere(plane, best.orientation, expected),
                    (best.orientation, expected),
                )
                if plane == "sagittal":
                    self.assertEqual(best.orientation, expected)

    def test_best_candidate_is_reported_for_each_plane(self):
        labels = synthetic_brain()
        section, _ = fake_section(labels, "sagittal", 20, 0)
        ranked = best_by_plane(search_planes(section, labels))
        self.assertEqual([c.plane for c in ranked][0], "sagittal")
        self.assertEqual(len(ranked), 3)
        self.assertGreater(ranked[0].silhouette, ranked[1].silhouette + 0.05)


def brain_with_depth_cues():
    """Synthetic brain whose internal structure moves with ML depth."""
    labels = synthetic_brain()
    dv, ml, ap = labels.shape
    intensity = np.where(labels > 0, 90.0, 0.0)
    z, y = np.meshgrid(np.arange(dv), np.arange(ap), indexing="ij")
    for x in range(ml):
        offset = abs(x - ml // 2)
        inside = ((z - 20) / 5) ** 2 + ((y - (30 + offset)) / 6) ** 2 <= 1
        inside &= labels[:, x, :] > 0
        labels[:, x, :][inside] = 40
        intensity[:, x, :][inside] = 200.0
    return labels, intensity


class DepthRankingTests(unittest.TestCase):
    def test_depth_is_recovered_from_internal_anatomy(self):
        labels, intensity = brain_with_depth_cues()
        midline = labels.shape[1] // 2
        for index in (midline + 3, midline + 9, midline + 15):
            with self.subTest(index=index):
                slice_ = atlas_slice(intensity, "sagittal", index).astype(np.uint8)
                section = cv2.resize(slice_, None, fx=4, fy=4, interpolation=cv2.INTER_LINEAR)
                section = np.dstack([section] * 3)
                ranked = rank_depths(
                    section, labels, intensity, "sagittal", ORIENTATIONS[0],
                    indexes=hemisphere_indexes("sagittal", labels.shape[1], midline),
                )
                self.assertLessEqual(abs(ranked[0].index - index), 1, ranked[:3])

    def test_mirrored_sagittal_index(self):
        self.assertEqual(mirrored_index(130, 114), 98)
        self.assertEqual(list(hemisphere_indexes("coronal", 5, 2)), [0, 1, 2, 3, 4])
        self.assertEqual(list(hemisphere_indexes("sagittal", 5, 2)), [2, 3, 4])


SAMPLE = Path(os.environ.get("DRIFTLESSMAP_SAMPLE_SECTION", ""))
ATLAS = Path(os.environ.get("DRIFTLESSMAP_SAMPLE_ATLAS", ""))


@unittest.skipUnless(SAMPLE.is_file() and ATLAS.is_dir(), "sample section/atlas not configured")
class RealSectionTests(unittest.TestCase):
    """Set DRIFTLESSMAP_SAMPLE_SECTION to a sagittal section image and
    DRIFTLESSMAP_SAMPLE_ATLAS to a processed atlas folder to run."""

    def test_sagittal_section_is_recognised(self):
        from driftlessmap.atlas_loader import AtlasLoader

        loaded = AtlasLoader(str(ATLAS), load_boundaries=False)
        labels = np.transpose(loaded.segmentation_data, [2, 0, 1])[::-1, :, :]
        section = cv2.imread(str(SAMPLE))[..., ::-1]
        ranked = best_by_plane(search_planes(section, labels))
        self.assertEqual(ranked[0].plane, "sagittal")
        self.assertGreater(ranked[0].silhouette, ranked[1].silhouette + 0.1)

        intensity = np.transpose(loaded.atlas_data, [2, 0, 1])[::-1, :, :]
        midline = int(loaded.atlas_info[3]["Bregma"][0])
        voxel_um = float(loaded.atlas_info[3]["vxsize"])
        depths = rank_depths(
            section, labels, intensity, "sagittal", ranked[0].orientation,
            indexes=hemisphere_indexes("sagittal", labels.shape[1], midline),
        )
        lateral_mm = abs(depths[0].index - midline) * voxel_um / 1000
        # Visual comparison places this section ~0.3-0.6 mm from the midline.
        self.assertGreater(lateral_mm, 0.1)
        self.assertLess(lateral_mm, 0.8)


if __name__ == "__main__":
    unittest.main()
