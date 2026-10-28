import os
from pathlib import Path
import unittest

import cv2
import numpy as np

from driftlessmap.atlas_matching import (
    ORIENTATIONS,
    Orientation,
    animal_right_edge,
    atlas_slice,
    Candidate,
    DepthMatch,
    best_by_plane,
    choose_orientation,
    orientation_contenders,
    preferred_form,
    bright_background,
    histology_gray,
    hemisphere_indexes,
    mirrored_index,
    rank_depths,
    refine_tilt,
    tilted_slice,
    mirror_hemisphere,
    mirrored_tilt,
    same_up_to_hemisphere,
    sagittal_side,
    search_factor,
    search_planes,
    suggest_sections,
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


def brightfield(section, gradient=60):
    """A fluorescence-like fake section as brightfield: dark tissue on a white
    slide, lit unevenly (darker toward the bottom)."""
    rows = np.linspace(0, gradient, section.shape[0])[:, None, None]
    slide = 245.0 - rows
    tissue = section.astype(np.float32) / 255.0
    return np.clip(slide * (1.0 - 0.6 * tissue), 0, 255).astype(np.uint8)


class BrightfieldTests(unittest.TestCase):
    def test_tissue_on_a_white_unevenly_lit_slide_is_found(self):
        image = np.zeros((200, 300, 3), np.uint8)
        # Tissue touching both side edges, so the background is split in two.
        cv2.ellipse(image, (150, 90), (160, 60), 0, 0, 360, (200, 180, 90), -1)
        cv2.circle(image, (150, 90), 15, (0, 0, 0), -1)        # a ventricle
        image = brightfield(image)
        self.assertTrue(bright_background(image))
        mask = tissue_mask(image)
        self.assertTrue(mask[90, 150])                           # hole filled
        self.assertTrue(mask[90, 5])
        self.assertFalse(mask[190, 150])                         # dim slide, not tissue
        self.assertFalse(mask[5, 150])
        gray = histology_gray(image, mask)
        self.assertEqual(gray[190, 150], 0)                      # black background
        self.assertGreater(gray[90, 60], 100)                    # bright tissue

    def test_fluorescence_is_not_inverted(self):
        section, _ = fake_section(synthetic_brain(), "coronal", 42, 0)
        self.assertFalse(bright_background(section))

    def test_brightfield_sections_find_their_plane_and_slice(self):
        labels = synthetic_brain()
        for plane, index, orientation_index in (("sagittal", 18, 0), ("coronal", 42, 5)):
            with self.subTest(plane=plane):
                section, expected = fake_section(labels, plane, index, orientation_index)
                best = search_planes(brightfield(section), labels)[0]
                self.assertEqual(best.plane, plane)
                self.assertTrue(same_up_to_hemisphere(plane, best.orientation, expected))


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


class TiltTests(unittest.TestCase):
    def reference_slice(self, volume, plane, index, tilt, pivot):
        """AtlasView's own formula, via pyqtgraph.affineSlice."""
        import pyqtgraph.functions as fn

        from driftlessmap.utils import rotation_x, rotation_y, rotation_z

        h, v = np.deg2rad(tilt)
        size0, size1, size2 = volume.shape
        c_id, s_id, h_index = pivot
        o_rot = np.array([size0 - 1 - h_index, s_id, c_id])
        if plane == "coronal":
            r = np.dot(rotation_x(h), rotation_y(v))
            o_val, axes, shape = np.array([0, 0, index]), ([1, 0, 0], [0, 1, 0]), (size0, size1)
        elif plane == "sagittal":
            r = np.dot(rotation_x(h), rotation_z(v))
            o_val, axes, shape = np.array([0, index, 0]), ([1, 0, 0], [0, 0, 1]), (size0, size2)
        else:
            r = np.dot(rotation_z(v), rotation_y(h))
            o_val = np.array([size0 - 1 - index, 0, 0])
            axes, shape = ([0, 1, 0], [0, 0, 1]), (size1, size2)
        origin = o_rot + np.dot(r, o_val - o_rot)
        return fn.affineSlice(volume, shape=shape, vectors=[r @ axes[0], r @ axes[1]],
                              origin=tuple(origin), axes=(0, 1, 2), order=1)

    def test_tilted_slices_match_the_atlas_view(self):
        _, intensity = brain_with_depth_cues()
        for plane, index in (("coronal", 38), ("sagittal", 30), ("horizontal", 18)):
            with self.subTest(plane=plane):
                # The view rotates about its own page, so that pivot is ``index``.
                pivot = {"coronal": (index, 25, 20), "sagittal": (40, index, 20),
                         "horizontal": (40, 25, index)}[plane]
                ours = tilted_slice(intensity, plane, index, (5.0, -4.0), (40, 25, 20))
                expected = self.reference_slice(intensity, plane, index, (5.0, -4.0), pivot)
                np.testing.assert_allclose(ours, expected, atol=1e-3)

    def test_known_tilt_scores_above_an_untilted_slice(self):
        labels, intensity = brain_with_depth_cues()
        pivot = (40, 25, 20)
        truth = tilted_slice(intensity, "sagittal", 34, (6.0, 0.0), pivot)
        section = cv2.resize(truth.astype(np.uint8), None, fx=4, fy=4)
        section = np.dstack([section] * 3)
        matches = refine_tilt(section, labels, intensity, "sagittal", ORIENTATIONS[0],
                              indexes=[33, 34, 35], pivot=pivot, angles=(-6, 0, 6))
        by_key = {(m.index, m.tilt_degrees): m.score for m in matches}
        self.assertGreater(by_key[(34, (6.0, 0.0))], by_key[(34, (0.0, 0.0))])
        self.assertEqual(matches[0].tilt_degrees[0], 6.0)


class OrientationChoiceTests(unittest.TestCase):
    def test_upright_orientations(self):
        upright = {(o.quarter_turns, o.mirrored) for o in ORIENTATIONS if o.upright}
        self.assertEqual(upright, {(0, False), (0, True)})
        # Rotate 180 degrees then mirror is an upside-down flip.
        self.assertFalse(Orientation(2, True).upright)

    def test_close_outlines_are_decided_by_anatomy_with_an_upright_preference(self):
        flipped, upright, turned = Orientation(2, True), Orientation(0, False), Orientation(1, False)
        candidates = [Candidate("coronal", 30, flipped, 0.88),
                      Candidate("coronal", 30, Orientation(2, False), 0.88),  # its mirror
                      Candidate("coronal", 31, upright, 0.87),
                      Candidate("sagittal", 9, upright, 0.86),
                      Candidate("coronal", 12, turned, 0.70)]
        contenders = orientation_contenders(candidates, candidates[0])
        self.assertEqual([c.orientation for c in contenders], [flipped, upright])

        def depth(anatomy):
            return [DepthMatch(30, anatomy, 0.0, 0.0, 1.0)]

        # Nearly equal anatomy: the upright section wins.
        chosen, _ = choose_orientation([(contenders[0], depth(1.02)),
                                        (contenders[1], depth(1.00))])
        self.assertEqual(chosen.orientation, upright)
        # Clearly better anatomy upside down: that wins.
        chosen, _ = choose_orientation([(contenders[0], depth(1.20)),
                                        (contenders[1], depth(1.00))])
        self.assertEqual(chosen.orientation, flipped)


class ConfidenceTests(unittest.TestCase):
    def _report(self, span, planes=1, margin=0.2):
        from driftlessmap.atlas_matching import Candidate, SuggestionReport

        candidates = tuple(Candidate(plane, 0, Orientation(0, False), 0.9 - k * margin)
                           for k, plane in enumerate(("coronal", "sagittal")[:planes]))
        return SuggestionReport(candidates, (), None, span)

    def _suggestion(self, anatomy):
        from driftlessmap.atlas_matching import Suggestion

        return Suggestion("coronal", Orientation(0, False), 10, (0.0, 0.0), 1.0, 0.95,
                          anatomy)

    def test_levels_follow_anatomy_depth_spread_and_plane(self):
        from driftlessmap.atlas_matching import confidence

        self.assertEqual(confidence(self._suggestion(0.9), self._report(20), 10.0),
                         ("high", []))
        level, reasons = confidence(self._suggestion(0.4), self._report(20), 10.0)
        self.assertEqual(level, "medium")
        self.assertIn("moderately", reasons[0])
        # A good outline does not help when the anatomy disagrees.
        self.assertEqual(confidence(self._suggestion(0.1), self._report(20), 10.0)[0], "low")
        # Depths far apart fitting as well make it low, whatever the anatomy.
        level, reasons = confidence(self._suggestion(0.9), self._report(200), 10.0)
        self.assertEqual(level, "low")
        self.assertIn("2.0 mm apart", reasons[0])
        # A detected plane that barely won limits confidence; a chosen one does not.
        level, reasons = confidence(self._suggestion(0.9), self._report(20, 2, 0.01), 10.0)
        self.assertEqual(level, "low")
        self.assertIn("ambiguous", reasons[0])

    def test_reports_carry_what_confidence_needs(self):
        from driftlessmap.atlas_matching import confidence

        labels = synthetic_brain()
        intensity = np.where(labels > 0, 120.0, 0.0)
        section, _ = fake_section(labels, "coronal", 42, 0)
        report = suggest_sections(section, labels, intensity, 25, (42, 25, 20),
                                  angles=(0,), planes=("coronal",))
        self.assertIsNotNone(report.depth_span)
        level, _reasons = confidence(report.suggestions[0], report, 25.0)
        self.assertIn(level, ("low", "medium", "high"))


class PlaneChoiceTests(unittest.TestCase):
    def test_file_names_name_the_plane(self):
        from driftlessmap.atlas_matching import plane_from_name, planes_for

        self.assertEqual(plane_from_name("/d/04-IM-1109_4x_coronal_DAPI.tif"), "coronal")
        self.assertEqual(plane_from_name("brain sagital 3.tif"), "sagittal")
        self.assertEqual(plane_from_name("slice_axial.png"), "horizontal")
        self.assertIsNone(plane_from_name("IM_1112_left.tif"))
        self.assertIsNone(plane_from_name("coronal_vs_sagittal.tif"))
        self.assertIsNone(plane_from_name(None))
        self.assertEqual(planes_for("auto"), ("coronal", "sagittal", "horizontal"))
        self.assertEqual(planes_for("sagittal"), ("sagittal",))
        with self.assertRaises(ValueError):
            planes_for("oblique")

    def test_the_search_stays_in_the_chosen_plane(self):
        labels = synthetic_brain()
        intensity = np.where(labels > 0, 120.0, 0.0)
        section, _ = fake_section(labels, "coronal", 42, 0)
        for plane in ("sagittal", "horizontal"):
            with self.subTest(plane=plane):
                report = suggest_sections(section, labels, intensity, 25, (42, 25, 20),
                                          angles=(0,), planes=(plane,))
                self.assertEqual({c.plane for c in report.plane_candidates}, {plane})
                self.assertTrue(all(s.plane == plane for s in report.suggestions))


class UprightPreferenceTests(unittest.TestCase):
    def test_mirror_images_resolve_to_the_unflipped_upright_form(self):
        self.assertEqual(preferred_form("coronal", Orientation(0, True)), Orientation(0, False))
        # Neither a 180-degree turn nor its mirror is upright: keep it unflipped.
        self.assertEqual(preferred_form("coronal", Orientation(2, True)), Orientation(2, False))
        self.assertEqual(preferred_form("sagittal", Orientation(0, True)), Orientation(0, True))

    def test_report_orientation_is_the_one_the_suggestions_use(self):
        labels = synthetic_brain()
        intensity = np.where(labels > 0, 120.0, 0.0)
        for orientation_index in (0, 1, 4):
            with self.subTest(orientation=orientation_index):
                section, expected = fake_section(labels, "coronal", 42, orientation_index)
                report = suggest_sections(section, labels, intensity, 25, (42, 25, 20),
                                          angles=(0,))
                chosen = report.plane_candidates[0].orientation
                self.assertTrue(all(s.orientation == chosen for s in report.suggestions))
                self.assertTrue(same_up_to_hemisphere("coronal", chosen, expected),
                                (chosen, expected))
                self.assertFalse(chosen.mirrored)


class SampledSearchTests(unittest.TestCase):
    def test_search_factor(self):
        self.assertEqual(search_factor((528, 320, 456)), 1)        # Allen 25 um
        self.assertEqual(search_factor((1320, 800, 1140)), 3)      # Allen 10 um
        self.assertEqual(search_factor((40, 50, 80), max_side=30), 3)

    def test_stepped_tilted_slice_samples_the_same_slice(self):
        _, intensity = brain_with_depth_cues()
        full = tilted_slice(intensity, "sagittal", 30, (5.0, -4.0), (40, 25, 20))
        coarse = tilted_slice(intensity, "sagittal", 30, (5.0, -4.0), (40, 25, 20), step=3)
        np.testing.assert_allclose(coarse, full[::3, ::3])

    def test_sampled_search_suggests_full_resolution_pages(self):
        from scipy.ndimage import zoom

        small_labels, small_intensity = brain_with_depth_cues()
        # Three times finer, so the search samples every third page and
        # sees the volume the other tests use.
        labels = zoom(small_labels, 3, order=0)
        intensity = zoom(small_intensity, 3, order=1)
        midline = labels.shape[1] // 2
        pivot = (120, midline, 60)
        for page in (midline + 22, midline + 41):
            with self.subTest(page=page):
                slice_ = atlas_slice(intensity, "sagittal", page).astype(np.uint8)
                section = np.dstack([cv2.resize(slice_, None, fx=1.5, fy=1.5)] * 3)
                sampled = suggest_sections(section, labels, intensity, midline, pivot,
                                           angles=(0,), max_side=90)
                exact = suggest_sections(section, labels, intensity, midline, pivot,
                                         angles=(0,), max_side=1000)
                best = sampled.suggestions[0]
                self.assertEqual(best.plane, "sagittal")
                self.assertLessEqual(abs(best.index - page), 2, sampled.suggestions[:3])
                self.assertLessEqual(abs(best.index - exact.suggestions[0].index), 2)
                self.assertEqual(sampled.midline, midline)
                self.assertEqual(sampled.plane_candidates[0].index % 3, 0)


class HemisphereTests(unittest.TestCase):
    def test_mirroring_differs_only_by_the_ml_axis_and_is_an_involution(self):
        for plane in ("coronal", "horizontal"):
            for orientation in ORIENTATIONS:
                mirrored = mirror_hemisphere(plane, orientation)
                self.assertNotEqual(mirrored, orientation)
                self.assertTrue(same_up_to_hemisphere(plane, orientation, mirrored))
                self.assertEqual(mirror_hemisphere(plane, mirrored), orientation)
        self.assertEqual(mirror_hemisphere("sagittal", ORIENTATIONS[3]), ORIENTATIONS[3])


    def test_animal_right_is_named_on_the_unoriented_section(self):
        # Coronal views show the animal's right on the right, horizontal views
        # at the bottom (positive ML is right).
        self.assertEqual(animal_right_edge("coronal", Orientation(0, False)), "right")
        self.assertEqual(animal_right_edge("coronal", Orientation(0, True)), "left")
        self.assertEqual(animal_right_edge("horizontal", Orientation(0, False)), "bottom")
        # Rotating 90° counter-clockwise brings the section's bottom to the right.
        self.assertEqual(animal_right_edge("coronal", Orientation(1, False)), "bottom")
        self.assertEqual(animal_right_edge("coronal", Orientation(2, False)), "left")
        self.assertIsNone(animal_right_edge("sagittal", Orientation(0, False)))
        opposite = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
        for plane in ("coronal", "horizontal"):
            for orientation in ORIENTATIONS:
                self.assertEqual(
                    animal_right_edge(plane, mirror_hemisphere(plane, orientation)),
                    opposite[animal_right_edge(plane, orientation)])

    def test_sagittal_side_follows_the_ml_axis(self):
        self.assertEqual(sagittal_side(30, 25), "right")
        self.assertEqual(sagittal_side(mirrored_index(30, 25), 25), "left")
        self.assertEqual(sagittal_side(25, 25), "midline")
        self.assertIsNone(sagittal_side(25, None))

class MirroredTiltTests(unittest.TestCase):
    def test_mirrored_tilt_reproduces_the_mirror_image_cut(self):
        rng = np.random.default_rng(4)
        volume = rng.random((24, 31, 36))   # odd ML size: exact midline 15
        mirrored_volume = volume[:, ::-1, :]
        midline = 15
        pivot = (18, midline, 12)
        tilt = (5.0, -4.0)
        cases = {
            "coronal": (20, 1),       # image axis 1 is ML
            "horizontal": (10, 0),    # image axis 0 is ML
        }
        for plane, (index, ml_axis) in cases.items():
            with self.subTest(plane=plane):
                original = tilted_slice(volume, plane, index, tilt, pivot)
                other = tilted_slice(mirrored_volume, plane, index,
                                     mirrored_tilt(plane, tilt), pivot)
                np.testing.assert_allclose(np.flip(original, ml_axis), other, atol=1e-6)
        original = tilted_slice(volume, "sagittal", 19, tilt, pivot)
        other = tilted_slice(mirrored_volume, "sagittal", mirrored_index(19, midline),
                             mirrored_tilt("sagittal", tilt), pivot)
        np.testing.assert_allclose(original, other, atol=1e-6)


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
