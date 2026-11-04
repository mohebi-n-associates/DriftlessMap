"""Planned probes as poses: geometry, readout, persistence and the engine build."""

import math
import unittest

import numpy as np

from driftlessmap.probe_plans import (
    MAX_TILT_DEG,
    PlanAtlas,
    PlanBook,
    ProbePlan,
    coordinate_line,
    direction_from_tilts,
    face_normal,
    plan_from_entry_depth,
    plan_from_points,
    plan_readout,
    region_centre,
    region_summary,
    shank_lines,
    tilts_from_direction,
)
from driftlessmap.probe_utiles import Probe, calculate_probe_info

VOX = 50.0
# Label volume in the engine's probe frame: axis 0 ML (right +), 1 AP
# (anterior +), 2 DV (dorsal +). The brain is the box ML 10-49, AP 10-49,
# DV 10-39: label 20 ("GC") in its top 10 voxels (500 um), 10 ("CH") below;
# a 30 ("RT") block on the animal's right at ML 35-44, AP 25-34, DV 15-24.
SHAPE = (60, 60, 60)
BREGMA = np.array([30.0, 30.0, 40.0])   # on the brain's top surface


def make_atlas():
    labels = np.zeros(SHAPE, dtype=np.int32)
    labels[10:50, 10:50, 10:40] = 10
    labels[10:50, 10:50, 30:40] = 20
    labels[35:45, 25:35, 15:25] = 30
    info = {
        "index": np.array([1, 10, 20, 30]),
        "label": np.array(["root", "child", "grandchild", "right thing"]),
        "parent": np.array([0, 1, 10, 10]),
        "abbrev": np.array(["root", "CH", "GC", "RT"]),
        "color": np.array([[255, 255, 255], [200, 100, 50], [50, 100, 200], [9, 9, 9]]),
    }
    return PlanAtlas(labels, info, VOX, BREGMA), labels, info


class GeometryTests(unittest.TestCase):
    def test_tilts_and_directions_round_trip(self):
        for ap, ml in [(0, 0), (30, 0), (0, -20), (15, 25), (-40, 10)]:
            d = direction_from_tilts(ap, ml)
            self.assertAlmostEqual(np.linalg.norm(d), 1.0)
            self.assertLess(d[2], 0)
            got = tilts_from_direction(d)
            self.assertAlmostEqual(got[0], ap, places=9)
            self.assertAlmostEqual(got[1], ml, places=9)
            # The same angles the engine's Region table reports, unsigned.
            from driftlessmap.probe_utiles import get_angles
            self.assertAlmostEqual(get_angles(d)[0], abs(ap), places=6)
            self.assertAlmostEqual(get_angles(d)[1], abs(ml), places=6)

    def test_positive_tilts_move_the_tip_anterior_and_to_the_right(self):
        d = direction_from_tilts(10, 0)
        self.assertGreater(d[1], 0)
        self.assertAlmostEqual(d[0], 0)
        d = direction_from_tilts(0, 10)
        self.assertGreater(d[0], 0)

    def test_roll_turns_the_face_from_anterior_to_the_right(self):
        d = direction_from_tilts(0, 0)
        np.testing.assert_allclose(face_normal(d, 0), [0, 1, 0], atol=1e-12)
        np.testing.assert_allclose(face_normal(d, 90), [1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(face_normal(d, 180), [0, -1, 0], atol=1e-12)
        tilted = direction_from_tilts(20, -30)
        for roll in (0, 45, 200):
            n = face_normal(tilted, roll)
            self.assertAlmostEqual(np.linalg.norm(n), 1.0)
            self.assertAlmostEqual(float(np.dot(n, tilted)), 0.0)

    def test_plan_from_points_and_entry_depth(self):
        plan = plan_from_points("P", [0, 0, 0], [500, 1000, -3000])
        np.testing.assert_allclose(plan.tip_um, [500, 1000, -3000])
        self.assertAlmostEqual(plan.ap_tilt_deg, math.degrees(math.atan2(1000, 3000)))
        self.assertAlmostEqual(plan.ml_tilt_deg, math.degrees(math.atan2(500, 3000)))
        # Either order of the two points gives the same plan.
        self.assertEqual(plan_from_points("P", [500, 1000, -3000], [0, 0, 0]), plan)
        moved = plan_from_entry_depth(plan, [0, 0, 0], np.linalg.norm([500, 1000, 3000]))
        np.testing.assert_allclose(moved.tip_um, plan.tip_um, atol=1e-9)
        with self.assertRaises(ValueError):
            plan_from_points("P", [0, 0, 0], [5000, 0, -100])
        with self.assertRaises(ValueError):
            plan_from_points("P", [1, 2, 3], [1, 2, 3])


class ReadoutTests(unittest.TestCase):
    def setUp(self):
        self.atlas, self.labels, self.info = make_atlas()
        self.settings = Probe().get_settings()

    def test_a_vertical_probe_enters_at_the_surface_and_lists_its_regions(self):
        plan = ProbePlan("P", [-500, 0, -1200], probe_settings=self.settings)
        readout = plan_readout(plan, self.atlas)
        step = 0.5 * VOX     # the line is sampled every half voxel
        np.testing.assert_allclose(readout["entry_um"][:2], [-500, 0], atol=1e-9)
        # The surface is the top of voxel 39 (DV 0): found exactly, not to a sample.
        self.assertAlmostEqual(readout["entry_um"][2], 0.0, places=6)
        self.assertAlmostEqual(readout["depth_um"], 1200.0, places=6)
        regions = [(r["acronym"], r["start_um"], r["end_um"]) for r in readout["regions"]]
        self.assertEqual([r[0] for r in regions], ["GC", "CH"])
        # GC is the top 500 um; the boundary lies within one sample of it.
        self.assertAlmostEqual(regions[0][2], 500 + readout["entry_um"][2], delta=step)
        self.assertAlmostEqual(regions[-1][2], readout["depth_um"], places=6)
        self.assertEqual(readout["tip_region"][0], "CH")
        self.assertEqual(readout["warnings"], [])
        self.assertTrue(readout["reachable"])
        self.assertEqual(readout["tilt"], "vertical")
        self.assertEqual(readout["face"], "anterior")
        self.assertIn("GC 0.4", region_summary(readout))

    def test_a_tilted_probe_enters_on_its_own_line(self):
        plan = ProbePlan("P", [500, 0, -1500], ap_tilt_deg=20, ml_tilt_deg=-10,
                         probe_settings=self.settings)
        readout = plan_readout(plan, self.atlas)
        entry = np.asarray(readout["entry_um"])
        tip = np.asarray(plan.tip_um)
        along = (tip - entry) / np.linalg.norm(tip - entry)
        np.testing.assert_allclose(along, plan.direction, atol=1e-9)
        # The top of the brain is DV 0 everywhere; the entry lies on it.
        self.assertAlmostEqual(entry[2], 0.0, places=6)
        # A positive AP tilt puts the tip anterior of the entry.
        self.assertGreater(tip[1], entry[1])
        self.assertIn("20.0° anterior", readout["tilt"])
        self.assertIn("medial", readout["tilt"])   # right hemisphere, leaning left

    def test_warnings_for_plans_that_cannot_work(self):
        settings = dict(self.settings, probe_length=1000)
        too_deep = plan_readout(ProbePlan("P", [0, 0, -1400], probe_settings=settings),
                                self.atlas)
        self.assertFalse(too_deep["reachable"])
        self.assertTrue(any("deeper than the 1.0 mm shank" in w for w in too_deep["warnings"]))

        above = plan_readout(ProbePlan("P", [0, 0, 400]), self.atlas)
        self.assertIsNone(above["entry_um"])
        self.assertTrue(any("does not meet the brain" in w for w in above["warnings"]))

        beside = plan_readout(ProbePlan("P", [1200, 0, -500]), self.atlas)
        self.assertIsNone(beside["entry_um"])

        crossing = plan_readout(ProbePlan("P", [400, 0, -1500], ml_tilt_deg=40), self.atlas)
        self.assertTrue(any("midline" in w for w in crossing["warnings"]))

    def test_region_centre_stays_in_one_hemisphere_and_inside_the_region(self):
        centre = region_centre(self.atlas, 30)
        vox = self.atlas.to_vox(centre)
        self.assertEqual(int(self.labels[tuple(np.floor(vox).astype(int))]), 30)
        # The block spans voxels 35-44 etc.: its centre is 40, 30, 20.
        np.testing.assert_allclose(vox, [40, 30, 20], atol=0.51)
        self.assertIsNone(region_centre(self.atlas, 30, side=-1))
        # A parent region includes its sub-regions; the side keeps to one half.
        left = region_centre(self.atlas, 10, side=-1)
        self.assertLess(left[0], 0)
        self.assertGreater(region_centre(self.atlas, 10, side=1)[0], 0)
        self.assertIsNone(region_centre(self.atlas, 999))
        # A strided search still lands on a voxel of the region.
        coarse = region_centre(self.atlas, 30, max_voxels=5000)
        cvox = np.floor(self.atlas.to_vox(coarse)).astype(int)
        self.assertEqual(int(self.labels[tuple(cvox)]), 30)

    def test_coordinate_line_names_frame_entry_depth_and_regions(self):
        plan = ProbePlan("Left probe", [-500, 0, -1200], roll_deg=90,
                         probe_settings=self.settings)
        line = coordinate_line(plan, plan_readout(plan, self.atlas), "test atlas")
        for text in ("Left probe:", "atlas test atlas", "from Bregma", "entry AP +0.000, ML -0.500",
                     "depth 1.", "tip AP +0.000, ML -0.500, DV -1.200 mm", "roll 90°",
                     "contacts face the animal's right", "probe NP1.0", "regions GC"):
            self.assertIn(text, line)

    def test_the_engine_build_reports_the_plan(self):
        """A plan built by the engine's own calculation keeps its entry, tip and angles."""
        plan = ProbePlan("P", [600, -300, -1800], ap_tilt_deg=12, ml_tilt_deg=-8,
                         roll_deg=30, probe_settings=self.settings)
        readout = plan_readout(plan, self.atlas)
        [line] = shank_lines(plan, readout, self.atlas)
        info, error = calculate_probe_info(
            [line], ["P plan"], self.labels, self.info, VOX, self.settings, False,
            BREGMA, 0, plan.normal, True, None)
        self.assertEqual(error, 0)
        self.assertAlmostEqual(info["ap_angle"], 12, places=6)
        self.assertAlmostEqual(info["ml_angle"], 8, places=6)
        np.testing.assert_allclose(info["terminus_coords"], plan.tip_um, atol=1e-6)
        np.testing.assert_allclose(info["insertion_coords"], readout["entry_um"],
                                   atol=0.5 * VOX + 1e-6)
        self.assertAlmostEqual(info["probe_length"], readout["depth_um"], delta=0.5 * VOX)

    def test_shanks_spread_across_the_face(self):
        plan = ProbePlan("P", [0, 0, -1500], roll_deg=0,
                         shank_offsets_um=[-375, -125, 125, 375])
        readout = plan_readout(plan, self.atlas)
        lines = shank_lines(plan, readout, self.atlas)
        self.assertEqual(len(lines), 4)
        tips = np.asarray([line[1] for line in lines]) * VOX
        # Roll 0: contacts face anterior, shanks lie along ML, 250 um apart.
        np.testing.assert_allclose(np.diff(sorted(tips[:, 0])), [250, 250, 250], atol=1e-9)
        np.testing.assert_allclose(tips[:, 1:], [[0, -1500]] * 4, atol=1e-9)
        rolled = plan_readout(plan.copy(roll_deg=90), self.atlas)
        tips = np.asarray([line[1] for line in shank_lines(plan.copy(roll_deg=90), rolled,
                                                             self.atlas)]) * VOX
        np.testing.assert_allclose(tips[:, 0], [0] * 4, atol=1e-9)


class PersistenceTests(unittest.TestCase):
    def test_book_round_trip_rename_and_invalid_entries(self):
        book = PlanBook()
        book.set(ProbePlan("A", [1, 2, 3], 5, -6, 370, {"probe_length": 10000}, [-10, 10]))
        book.set(ProbePlan("B", [0, 0, -100]))
        data = book.to_list()
        again, problems = PlanBook.from_list(data)
        self.assertEqual(problems, [])
        self.assertEqual(again.to_list(), data)
        self.assertEqual(again.get("A").roll_deg, 10.0)
        self.assertEqual(again.rename("A", "C").probe, "C")
        self.assertIsNone(again.get("A"))
        self.assertEqual(again.get("C").tip_um, [1.0, 2.0, 3.0])
        self.assertEqual(again.remove("C").probe, "C")

        bad = data + [{"probe": "D", "tip_um": [0, 0]}, {"probe": "E", "tip_um": [0, 0, 0],
                                                         "ap_tilt_deg": MAX_TILT_DEG + 1},
                      "nonsense", dict(data[1])]
        restored, problems = PlanBook.from_list(bad)
        self.assertEqual([p.probe for p in restored.plans()], ["A", "B"])
        self.assertEqual(len(problems), 4)
        self.assertEqual(PlanBook.from_list(None)[0].to_list(), [])
        self.assertEqual(PlanBook.from_list({"x": 1})[1], ["the saved probe plans are not a list"])


if __name__ == "__main__":
    unittest.main()
