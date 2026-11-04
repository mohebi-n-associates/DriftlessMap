"""Planned probes as poses: geometry, readout, persistence and the engine build."""

import math
import unittest

import numpy as np

from driftlessmap.probe_plans import (
    MAX_TILT_DEG,
    recording_sites as _recording_sites,
    track_checks,
    ProposalRequest,
    propose_plans,
    target_coverage,
    Craniotomy,
    CraniotomyBook,
    arm_from_tilts,
    bregma_lambda_scale,
    clearance_warning,
    clearances,
    craniotomy_warning,
    fit_craniotomy,
    tilts_from_arm,
    validated_surgery_settings,
    PlanAtlas,
    PlanBook,
    ProbePlan,
    coordinate_line,
    direction_from_tilts,
    face_normal,
    bank_count,
    column_surface,
    plan_from_entry_depth,
    plan_from_points,
    plan_from_surface,
    recording_sites,
    site_offsets_um,
    tip_to_surface,
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


class WindowAndSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.atlas, self.labels, self.info = make_atlas()
        self.np1 = Probe().get_settings()

    def test_neuropixels_banks_count_from_the_tip(self):
        offsets = site_offsets_um(self.np1)
        self.assertEqual(len(offsets), 960)
        self.assertEqual(bank_count(self.np1), 3)
        # NP1: two sites per 20 um row, lowest 10 um above the tip's base.
        self.assertEqual(offsets[0], 10.0)
        bank0 = recording_sites(ProbePlan("P", [0, 0, -1000], probe_settings=self.np1))
        self.assertEqual(len(bank0), 384)
        self.assertAlmostEqual(bank0.max() - bank0.min(), 3820.0)
        bank2 = recording_sites(ProbePlan("P", [0, 0, -1000], probe_settings=self.np1, bank=2))
        self.assertEqual(len(bank2), 192)
        every = recording_sites(ProbePlan("P", [0, 0, -1000], probe_settings=self.np1,
                                          bank=None))
        self.assertEqual(len(every), 960)

    def test_the_window_lies_above_the_tip_and_covers_regions(self):
        settings = dict(self.np1)
        plan = ProbePlan("P", [-500, 0, -1400], probe_settings=settings)
        readout = plan_readout(plan, self.atlas)
        top, bottom = readout["window_um"]
        # The lowest site is the 175 um tip plus 10 um above the tip's end.
        self.assertAlmostEqual(bottom, 1400 - 175 - 10)
        self.assertAlmostEqual(bottom - top, 3820.0)
        self.assertLess(readout["window_sites_in_brain"], readout["window_sites"])
        cover = {r["acronym"]: r for r in readout["window_regions"]}
        self.assertAlmostEqual(cover["GC"]["length_um"], 500.0, delta=0.5 * VOX)
        self.assertAlmostEqual(cover["CH"]["length_um"], bottom - 500.0, delta=0.5 * VOX)
        self.assertEqual(cover["GC"]["sites"] + cover["CH"]["sites"],
                         readout["window_sites_in_brain"])
        self.assertTrue(all(0 <= d <= readout["depth_um"] for d in readout["contacts_um"]))

    def test_entry_and_depth_and_tip_to_surface(self):
        surface = column_surface(self.atlas, 300, -200)
        np.testing.assert_allclose(surface, [300, -200, 0], atol=1e-6)
        self.assertIsNone(column_surface(self.atlas, 2000, 0))
        plan = ProbePlan("P", [0, 0, -1000], ap_tilt_deg=15)
        moved = plan_from_surface(plan, self.atlas, 300, -200, 800)
        readout = plan_readout(moved, self.atlas)
        np.testing.assert_allclose(readout["entry_um"], [300, -200, 0], atol=1e-6)
        self.assertAlmostEqual(readout["depth_um"], 800, places=6)
        self.assertEqual(moved.ap_tilt_deg, 15)
        with self.assertRaises(ValueError):
            plan_from_surface(plan, self.atlas, 2000, 0, 800)
        along = tip_to_surface(moved, self.atlas, along_probe=True)
        np.testing.assert_allclose(along.tip_um, readout["entry_um"], atol=1e-6)
        down = tip_to_surface(moved, self.atlas, along_probe=False)
        np.testing.assert_allclose(down.tip_um, [moved.tip_um[0], moved.tip_um[1], 0],
                                   atol=1e-6)


class SurgeryTests(unittest.TestCase):
    def setUp(self):
        self.atlas, self.labels, self.info = make_atlas()

    def test_arm_angles_round_trip_and_match_the_direction(self):
        for ap, ml in [(0, 0), (10, 0), (0, 10), (12, -7), (-30, 25), (-5, -5)]:
            azimuth, elevation = arm_from_tilts(ap, ml)
            back = tilts_from_arm(azimuth, elevation)
            self.assertAlmostEqual(back[0], ap, places=9)
            self.assertAlmostEqual(back[1], ml, places=9)
            d = direction_from_tilts(ap, ml)
            # Elevation is the angle from vertical; azimuth from anterior to the right.
            self.assertAlmostEqual(math.degrees(math.acos(-d[2])), elevation, places=9)
            if elevation > 0:
                self.assertAlmostEqual(math.degrees(math.atan2(d[0], d[1])) % 360, azimuth,
                                       places=9)
        self.assertEqual(arm_from_tilts(0, 10)[0], 90.0)
        self.assertEqual(arm_from_tilts(0, -10)[0], 270.0)
        self.assertEqual(arm_from_tilts(-10, 0)[0], 180.0)

    def test_craniotomies_hold_their_entries(self):
        hole = Craniotomy("c1", "Left", [-500.0, 1000.0], 1000.0)
        self.assertIsNone(craniotomy_warning(hole, [-500.0, 1400.0, 0.0]))
        warning = craniotomy_warning(hole, [-500.0, 1600.0, 0.0])
        self.assertIn("0.60 mm from the centre of Left", warning)
        self.assertIsNone(craniotomy_warning(None, [0, 0, 0]))
        # Fitting: the smallest circle through the entries, with the margin.
        centre, diameter = fit_craniotomy([[0, 0, 0], [1000, 0, -5]], margin_um=250)
        np.testing.assert_allclose(centre, [500, 0], atol=1e-6)
        self.assertAlmostEqual(diameter, 1500.0, places=6)
        triangle = [[0, 0], [1000, 0], [500, 800]]
        centre, diameter = fit_craniotomy(triangle, margin_um=0, minimum_um=0)
        radii = [math.dist(centre, p) for p in triangle]
        self.assertAlmostEqual(max(radii), diameter / 2, places=6)
        self.assertAlmostEqual(max(radii), min(radii), places=6)   # the circumcircle
        self.assertEqual(fit_craniotomy([[3, 4]])[1], 500.0)
        book = CraniotomyBook()
        book.add(hole)
        self.assertEqual(book.new_name(), "Craniotomy 1")
        again, problems = CraniotomyBook.from_list(book.to_list() + [{"id": "x"}, "bad"])
        self.assertEqual(again.get("c1"), hole)
        self.assertEqual(len(problems), 2)
        with self.assertRaises(ValueError):
            Craniotomy("c", "n", [0, 0], 0)

    def test_clearance_between_planned_probes(self):
        a = ProbePlan("A", [0, 0, -1200])
        b = ProbePlan("B", [200, 0, -1200])
        c = ProbePlan("C", [-900, 0, -1200])
        planned = [(p, plan_readout(p, self.atlas)) for p in (a, b, c)]
        pairs = clearances(planned)
        self.assertEqual(pairs[0]["probes"], ("A", "B"))
        self.assertAlmostEqual(pairs[0]["distance_um"], 200.0, places=6)
        self.assertEqual(len(pairs), 3)
        self.assertAlmostEqual(pairs[-1]["distance_um"], 1100.0, places=6)
        # A probe that misses the brain has no track to compare.
        outside = ProbePlan("Z", [-1500, 0, -1200])
        self.assertEqual(clearances(planned[:1] + [(outside, plan_readout(outside,
                                                                          self.atlas))]), [])
        self.assertIn("A passes 0.20 mm from B", clearance_warning("A", pairs))
        self.assertIsNone(clearance_warning("C", pairs))
        # Leaning apart going down, so their lines cross 0.1 mm above the brain.
        d = ProbePlan("D", [400, 0, -1000], ml_tilt_deg=20)
        e = ProbePlan("E", [-400, 0, -1000], ml_tilt_deg=-20)
        crossing = clearances([(p, plan_readout(p, self.atlas)) for p in (d, e)])
        self.assertLess(crossing[0]["distance_um"], 1e-6)
        self.assertAlmostEqual(crossing[0]["depth_um"],
                               -(400 / math.tan(math.radians(20)) - 1000)
                               / math.cos(math.radians(20)), delta=1.0)
        self.assertIn("above the brain", clearance_warning("D", crossing))
        # Shanks count: a four-shank probe beside a single shank.
        f = ProbePlan("F", [0, 0, -1200], shank_offsets_um=[-375, -125, 125, 375])
        g = ProbePlan("G", [600, 0, -1200])
        near = clearances([(p, plan_readout(p, self.atlas)) for p in (f, g)])
        self.assertAlmostEqual(near[0]["distance_um"], 225.0, places=6)

    def test_bregma_lambda_scale(self):
        self.assertEqual(bregma_lambda_scale(None, 4200), 1.0)
        self.assertAlmostEqual(bregma_lambda_scale(3990, 4200), 0.95)
        with self.assertRaises(ValueError):
            bregma_lambda_scale(-1, 4200)
        self.assertEqual(validated_surgery_settings({"bregma_lambda_um": "4100",
                                                     "atlas_bregma_lambda_um": -3}),
                         {"bregma_lambda_um": 4100.0, "atlas_bregma_lambda_um": None})
        self.assertEqual(validated_surgery_settings(None),
                         {"bregma_lambda_um": None, "atlas_bregma_lambda_um": None})


def make_target_atlas():
    """A 4 mm cube brain (50 um voxels, surface at DV 0) with known targets.

    40 "A" and 41 "B": 0.2 mm blocks stacked straight down on the right
    (A above B); 42 "X": a block straight above A; 43 "C": a block across the
    midline; 44 "D": 0.3 mm lateral of B and 1 mm deeper; 45 "E": far left.
    """
    labels = np.zeros((80, 80, 80), dtype=np.int32)
    labels[10:70, 10:70, 10:70] = 10
    labels[50:54, 40:44, 50:54] = 40      # A
    labels[50:54, 40:44, 35:39] = 41      # B
    labels[50:54, 40:44, 58:62] = 42      # X, above A
    labels[36:44, 20:24, 40:44] = 43      # C, across the midline (ML index 40)
    labels[56:60, 40:44, 15:19] = 44      # D
    labels[18:22, 40:44, 50:54] = 45      # E, left
    names = ["root", "brain", "A", "B", "X", "C", "D", "E"]
    ids = [1, 10, 40, 41, 42, 43, 44, 45]
    info = {"index": np.array(ids), "label": np.array(names), "abbrev": np.array(names),
            "parent": np.array([0, 1, 10, 10, 10, 10, 10, 10]),
            "color": np.array([[200, 200, 200]] * len(ids))}
    return PlanAtlas(labels, info, VOX, [40.0, 40.0, 70.0]), labels


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.atlas, self.labels = make_target_atlas()
        self.plan = ProbePlan("P", [0, 0, -1000], probe_settings=Probe().get_settings())

    def readout_labels(self, plan):
        readout = plan_readout(plan, self.atlas)
        return {r["acronym"] for r in readout["regions"]}, readout

    def test_a_vertical_line_through_two_stacked_targets(self):
        request = ProposalRequest([40, 41], max_ap_tilt_deg=0, max_ml_tilt_deg=0)
        proposals, reasons = propose_plans(self.atlas, request, self.plan)
        self.assertEqual(reasons, [])
        best = proposals[0]
        self.assertEqual(best["reached"], 2)
        self.assertEqual((best["plan"].ap_tilt_deg, best["plan"].ml_tilt_deg), (0.0, 0.0))
        # Through the blocks' footprint: ML 0.5-0.7 mm, AP 0-0.2 mm.
        self.assertTrue(500 <= best["entry_um"][0] <= 700, best["entry_um"])
        self.assertTrue(0 <= best["entry_um"][1] <= 200, best["entry_um"])
        # The whole of both 0.2 mm targets is in the window.
        for name, length in best["coverage"]:
            self.assertAlmostEqual(length, 200.0, delta=VOX, msg=name)
        # The plan really records them, by the readout's own reckoning.
        names, readout = self.readout_labels(best["plan"])
        self.assertTrue({"A", "B"} <= names)
        self.assertEqual(readout["warnings"], [])
        covered = dict(target_coverage(best["plan"].copy(targets=[40, 41]), readout,
                                       self.atlas))
        self.assertAlmostEqual(covered["A"], 200.0, delta=VOX)
        self.assertAlmostEqual(covered["B"], 200.0, delta=VOX)
        # Shallowest of the best: B's bottom (1.75 mm) plus the 175 um tip and the
        # lowest site's 10 um, not the brain's floor.
        self.assertAlmostEqual(best["depth_um"], 1750.0 + 175.0 + 10.0, delta=0.5 * VOX)

    def test_avoiding_a_region_above_the_target_needs_a_tilt(self):
        vertical = ProposalRequest([40], avoid=[42], max_ap_tilt_deg=0, max_ml_tilt_deg=0)
        proposals, reasons = propose_plans(self.atlas, vertical, self.plan)
        self.assertTrue(any("cross a region to keep out of" in r for r in reasons), reasons)
        tilted = ProposalRequest([40], avoid=[42], max_ap_tilt_deg=30, max_ml_tilt_deg=30)
        proposals, reasons = propose_plans(self.atlas, tilted, self.plan)
        self.assertEqual(reasons, [])
        best = proposals[0]["plan"]
        self.assertGreater(abs(best.ap_tilt_deg) + abs(best.ml_tilt_deg), 0)
        self.assertLessEqual(max(abs(best.ap_tilt_deg), abs(best.ml_tilt_deg)), 30)
        names, _readout = self.readout_labels(best)
        self.assertIn("A", names)
        self.assertNotIn("X", names)

    def test_one_side_of_the_midline(self):
        left = ProposalRequest([43], side=-1, midline_um=100, max_ap_tilt_deg=0,
                               max_ml_tilt_deg=0)
        proposals, reasons = propose_plans(self.atlas, left, self.plan)
        self.assertEqual(reasons, [])
        for proposal in proposals:
            self.assertLessEqual(proposal["entry_um"][0], -100)
            self.assertLessEqual(proposal["plan"].tip_um[0], -100)

    def test_reasons_when_nothing_works(self):
        short = self.plan.copy(probe_settings=dict(self.plan.probe_settings, probe_length=900))
        proposals, reasons = propose_plans(
            self.atlas, ProposalRequest([41], max_ap_tilt_deg=0, max_ml_tilt_deg=0), short)
        self.assertTrue(any("need more than the 0.9 mm shank" in r for r in reasons), reasons)
        # D is 0.3 mm lateral of B and 1 mm deeper; the blocks are 0.2 mm wide, so
        # a line through both needs about 7° (0.1 mm across 0.8 mm), more than 5°.
        proposals, reasons = propose_plans(
            self.atlas, ProposalRequest([41, 44], max_ap_tilt_deg=5, max_ml_tilt_deg=5),
            self.plan)
        self.assertTrue(any("The best line found reaches 1 of the 2 targets" in r for r in reasons),
                        reasons)
        self.assertTrue(any("with tilts of up to 10°" in r for r in reasons),
                        reasons)
        wide = ProposalRequest([41, 44], max_ap_tilt_deg=10, max_ml_tilt_deg=10)
        proposals, reasons = propose_plans(self.atlas, wide, self.plan)
        self.assertEqual(reasons, [])
        self.assertEqual(proposals[0]["reached"], 2)
        # A and E lie side by side, 1.6 mm apart at the same depth.
        proposals, reasons = propose_plans(
            self.atlas, ProposalRequest([40, 45], max_ap_tilt_deg=30, max_ml_tilt_deg=30),
            self.plan)
        self.assertTrue(any("one probe per target" in r for r in reasons), reasons)
        self.assertEqual(propose_plans(self.atlas, ProposalRequest([999]), self.plan)[1],
                         ["None of the target regions is in this atlas volume."])
        with self.assertRaises(ValueError):
            ProposalRequest([])

    def test_an_angled_best_comes_with_a_straighter_option(self):
        # A slanted target (30° from vertical in the coronal plane): the angled
        # track records most of it, a vertical one only its width.
        labels = self.labels.copy()
        for dv in range(25, 61):
            ml = int(round(30 + (60 - dv) * math.tan(math.radians(30))))
            labels[ml:ml + 3, 38:46, dv] = 46
        info = dict(self.atlas.label_info)
        info["index"] = np.append(info["index"], 46)
        info["label"] = np.append(info["label"], "S")
        info["abbrev"] = np.append(info["abbrev"], "S")
        info["parent"] = np.append(info["parent"], 10)
        info["color"] = np.vstack([info["color"], [[1, 2, 3]]])
        atlas = PlanAtlas(labels, info, VOX, self.atlas.bregma)
        proposals, reasons = propose_plans(atlas, ProposalRequest([46], max_ap_tilt_deg=40,
                                                                  max_ml_tilt_deg=40),
                                           self.plan)
        self.assertEqual(reasons, [])
        best = proposals[0]
        self.assertGreater(best["coverage"][0][1], 1000.0)
        self.assertAlmostEqual(abs(best["plan"].ml_tilt_deg), 30.0, delta=3.0)
        elevations = [math.degrees(math.acos(-p["plan"].direction[2])) for p in proposals]
        self.assertLess(min(elevations), 5.0)

    # ------------------------------------------------- review of 2.8.3
    def physical_shanks(self, plan, atlas, region):
        """Each shank's own path (entry to tip) and window, measured independently."""
        from driftlessmap.probe_plans import across_face, surface_entry

        step = atlas.vox_um * 0.5
        window = _recording_sites(plan)
        tip_length = plan.probe_settings["tip_length"]
        across = across_face(plan.direction, plan.normal)
        out = []
        for offset in plan.shank_offsets_um or [0.0]:
            tip = np.asarray(plan.tip_um) + across * offset
            entry, inside = surface_entry(atlas, tip, plan.direction)
            path = np.linspace(entry, tip, 400)
            heights = np.arange(window.min(), window.max() + step / 2, step) + tip_length
            win = tip[None, :] - heights[:, None] * plan.direction[None, :]
            path_labels = atlas.labels_at(atlas.to_vox(path))[0]
            win_labels = atlas.labels_at(atlas.to_vox(win))[0]
            out.append({"entry": entry, "tip_inside": inside, "labels": set(path_labels.tolist()),
                        "recorded": float(np.count_nonzero(win_labels == region) * step)})
        return out

    def test_r1_every_shank_obeys_the_constraints_and_counts(self):
        labels = self.labels.copy()
        labels[58:64, 40:44, 55:64] = 42           # on an outer shank's path only
        atlas = PlanAtlas(labels, self.atlas.label_info, VOX, self.atlas.bregma)
        np2 = Probe()
        np2.set_np2()
        plan = self.plan.copy(probe_settings=np2.get_settings(),
                              shank_offsets_um=[-375, -125, 125, 375])
        hole = Craniotomy("hole", "small", [600, 100], 200)
        # Four shanks 0.75 mm wide cannot all enter a 0.2 mm opening.
        proposals, reasons = propose_plans(atlas, ProposalRequest(
            [40], avoid=[42], max_ap_tilt_deg=0, max_ml_tilt_deg=0, craniotomy=hole), plan)
        self.assertEqual(proposals, [])
        self.assertTrue(any("outside the craniotomy" in r for r in reasons), reasons)
        for roll in (0.0, 90.0, 30.0):
            rolled = plan.copy(roll_deg=roll)
            proposals, reasons = propose_plans(atlas, ProposalRequest(
                [40], avoid=[42], max_ap_tilt_deg=10, max_ml_tilt_deg=10), rolled)
            self.assertTrue(proposals, (roll, reasons))
            for proposal in proposals:
                shanks = self.physical_shanks(proposal["plan"], atlas, 40)
                for shank in shanks:
                    self.assertNotIn(42, shank["labels"], roll)
                    self.assertTrue(shank["tip_inside"], roll)
                # The stated coverage is what the shanks' windows record.
                self.assertAlmostEqual(proposal["coverage"][0][1],
                                       sum(s["recorded"] for s in shanks), delta=4 * VOX)
                self.assertEqual(len(proposal["shank_coverage"]), 4)
                hard, _soft = track_checks(proposal["plan"], atlas, [42])
                self.assertEqual(hard, [])

    def test_r1_the_readout_checks_every_shank(self):
        plan = ProbePlan("P", [600, 100, -1000], probe_settings=Probe().get_settings(),
                         shank_offsets_um=[-375, -125, 125, 375])
        labels = self.labels.copy()
        labels[58:64, 40:44, 55:64] = 42
        atlas = PlanAtlas(labels, self.atlas.label_info, VOX, self.atlas.bregma)
        hard, _soft = track_checks(plan, atlas, [42])
        self.assertEqual(len(hard), 1)
        # Roll 0: offsets run towards the animal's left, so shank 1 is the right one.
        self.assertIn("Shank 1 passes through X", hard[0])
        readout = plan_readout(plan.copy(avoid=[42]), atlas)
        self.assertTrue(any("Shank 1 passes through X" in w for w in readout["warnings"]))
        hole = Craniotomy("hole", "small", [600, 100], 200)
        hard, _soft = track_checks(plan, atlas, craniotomy=hole)
        self.assertEqual(len(hard), 4)              # every shank enters outside it

    def test_r4_contradictory_regions_are_refused(self):
        same = ProposalRequest([40], avoid=[40], max_ap_tilt_deg=0, max_ml_tilt_deg=0)
        self.assertEqual(same.avoid, [40])          # kept as given, not filtered
        proposals, reasons = propose_plans(self.atlas, same, self.plan)
        self.assertEqual(proposals, [])
        self.assertIn("A is to be recorded but is also to be kept out of", reasons[0])
        inside = ProposalRequest([40], avoid=[10], max_ap_tilt_deg=0, max_ml_tilt_deg=0)
        proposals, reasons = propose_plans(self.atlas, inside, self.plan)
        self.assertEqual(proposals, [])
        self.assertIn("A is to be recorded but lies in brain", reasons[0])
        # Keeping out of a part of a target is allowed: the rest is recorded.
        part = ProposalRequest([10], avoid=[40], max_ap_tilt_deg=0, max_ml_tilt_deg=0)
        proposals, reasons = propose_plans(self.atlas, part, self.plan)
        self.assertTrue(proposals, reasons)
        for proposal in proposals:
            self.assertNotIn(40, self.physical_shanks(proposal["plan"], self.atlas,
                                                      10)[0]["labels"])

    def test_r5_no_tip_in_a_gap_and_the_gap_is_disclosed(self):
        labels = self.labels.copy()
        labels[10:70, 10:70, 44:50] = 0             # a gap just below A
        atlas = PlanAtlas(labels, self.atlas.label_info, VOX, self.atlas.bregma)
        proposals, reasons = propose_plans(atlas, ProposalRequest(
            [40], max_ap_tilt_deg=0, max_ml_tilt_deg=0), self.plan)
        self.assertTrue(proposals, reasons)
        for proposal in proposals:
            readout = plan_readout(proposal["plan"], atlas)
            self.assertNotEqual(readout["tip_region"][0], "outside")
            self.assertFalse(any("not inside" in w for w in readout["warnings"]))
        self.assertTrue(any("leaves the atlas's labelled brain for 0.30 mm" in w
                            for w in proposals[0]["warnings"]), proposals[0]["warnings"])
        # The readout says the same for a hand-made plan through the gap.
        through = self.plan.copy(tip_um=proposals[0]["plan"].tip_um)
        self.assertTrue(any("labelled brain" in w for w in
                            plan_readout(through, atlas)["warnings"]))

    def test_r6_parent_and_child_targets_do_not_depend_on_order(self):
        results = {}
        for targets in ([10, 40], [40, 10]):
            request = ProposalRequest(targets, max_ap_tilt_deg=0, max_ml_tilt_deg=0)
            proposals, reasons = propose_plans(self.atlas, request, self.plan)
            self.assertEqual(reasons, [])
            best = proposals[0]
            self.assertEqual(best["reached"], 2)
            results[tuple(targets)] = dict(best["coverage"])
            readout = plan_readout(best["plan"], self.atlas)
            covered = dict(target_coverage(best["plan"], readout, self.atlas))
            self.assertGreaterEqual(covered["A"], 150.0)
            self.assertGreater(covered["brain"], covered["A"])
        self.assertEqual(results[(10, 40)].keys(), results[(40, 10)].keys())
        for name in ("A", "brain"):
            self.assertAlmostEqual(results[(10, 40)][name], results[(40, 10)][name],
                                   delta=VOX)

    def test_targets_and_avoid_are_saved_with_the_plan(self):
        plan = self.plan.copy(targets=[40, 41], avoid=[42])
        self.assertEqual(ProbePlan.from_dict(plan.to_dict()), plan)
        old = plan.to_dict()
        del old["targets"], old["avoid"]
        self.assertEqual(ProbePlan.from_dict(old).targets, [])
        with self.assertRaises(ValueError):
            ProbePlan.from_dict(dict(plan.to_dict(), targets=["PL"]))


class PersistenceTests(unittest.TestCase):
    def test_book_round_trip_rename_and_invalid_entries(self):
        book = PlanBook()
        book.set(ProbePlan("A", [1, 2, 3], 5, -6, 370, {"probe_length": 10000}, [-10, 10],
                           bank=None))
        book.set(ProbePlan("B", [0, 0, -100]))
        data = book.to_list()
        again, problems = PlanBook.from_list(data)
        self.assertEqual(problems, [])
        self.assertEqual(again.to_list(), data)
        self.assertEqual(again.get("A").roll_deg, 10.0)
        self.assertIsNone(again.get("A").bank)
        self.assertIsNone(again.get("A").craniotomy)
        self.assertEqual(again.get("B").bank, 0)
        # A 2.8.0 plan (no bank) opens with the lowest bank.
        old = dict(data[1])
        old.pop("bank")
        self.assertEqual(ProbePlan.from_dict(old).bank, 0)
        with self.assertRaises(ValueError):
            ProbePlan("X", [0, 0, 0], bank=99)
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
