"""Planned optical fibers and microprisms (2.8.5): geometry, checks and saving."""

import unittest

import numpy as np

from driftlessmap.implants import (
    DEFAULT_SPECS,
    PRISM,
    describe_specs,
    model_section,
    model_segments,
    prism_rise,
    validated_specs,
)
from driftlessmap.probe_plans import (
    Craniotomy,
    PlanBook,
    ProbePlan,
    clearances,
    coordinate_line,
    device_lines,
    face_view,
    plan_readout,
    planned_model,
    track_checks,
)
from tests.test_probe_plans import make_atlas

# The test atlas (see test_probe_plans): 50 um voxels, Bregma on the top of
# the brain box ML/AP -1..+1 mm, DV -1.5..0 mm; RT ("right thing", 30) is the
# block ML 0.25..0.75, AP -0.25..+0.25, DV -1.25..-0.75 mm in CH (10).
SMALL_PRISM = {"width_um": 400.0, "depth_um": 400.0, "length_um": 2000.0,
               "bevel_deg": 45.0, "face": "lateral"}


def fiber(tip, diameter=400.0, **keep):
    return ProbePlan("Fiber 1", tip, kind="fiber", specs={"diameter_um": diameter},
                     implant_id="f" * 32, **keep)


def prism(tip, roll=90.0, **specs):
    return ProbePlan("Prism 1", tip, roll_deg=roll, kind="prism",
                     specs=dict(SMALL_PRISM, **specs), implant_id="a" * 32)


class SpecsAndSavingTests(unittest.TestCase):
    def test_prism_defaults_and_older_specs(self):
        self.assertEqual(DEFAULT_SPECS[PRISM]["length_um"], 3000.0)
        self.assertEqual(DEFAULT_SPECS[PRISM]["bevel_deg"], 45.0)
        # A prism saved before 2.8.5 has no length or bevel: the defaults apply.
        old = validated_specs(PRISM, {"width_um": 1500.0, "depth_um": 1500.0,
                                      "face": "medial"})
        self.assertEqual((old["length_um"], old["bevel_deg"]), (3000.0, 45.0))
        self.assertEqual(describe_specs(PRISM, {"width_um": 1500.0, "depth_um": 1500.0,
                                                "face": "medial"}),
                         "1500 × 1500 × 3000 µm · 45° bottom · medial face")
        self.assertAlmostEqual(prism_rise(old), 1.0)
        self.assertEqual(prism_rise(dict(old, bevel_deg=90.0)), 0.0)
        with self.assertRaises(ValueError):
            validated_specs(PRISM, {"bevel_deg": 10.0})

    def test_implant_plans_round_trip_and_are_saved_apart(self):
        probe = ProbePlan("Probe 1", [0.0, 0.0, -1000.0])
        self.assertNotIn("kind", probe.to_dict())     # read as in 2.8.4
        planned = [probe, fiber([0.0, 0.0, -800.0]), prism([100.0, 0.0, -900.0])]
        for plan in planned[1:]:
            again = ProbePlan.from_dict(plan.to_dict())
            self.assertEqual(again, plan)
            self.assertIsNone(again.probe_settings)
            self.assertIsNone(again.bank)
        book = PlanBook()
        for plan in planned:
            book.set(plan)
        self.assertEqual([p["probe"] for p in book.to_list()], ["Probe 1"])
        self.assertEqual([p["probe"] for p in book.to_list(implants=True)],
                         ["Fiber 1", "Prism 1"])
        again, problems = PlanBook.from_list(book.to_list(), book.to_list(implants=True))
        self.assertEqual(problems, [])
        self.assertEqual(again.plans(), book.plans())
        # An implant plan among the probe plans is refused, not read as a probe.
        _book, problems = PlanBook.from_list(book.to_list(implants=True))
        self.assertEqual(len(problems), 2)
        with self.assertRaises(ValueError):
            ProbePlan("X", [0, 0, 0], kind="laser")


class GeometryTests(unittest.TestCase):
    def test_a_fiber_is_its_axis_and_its_rim(self):
        plan = fiber([0.0, 0.0, -800.0], diameter=400.0, ap_tilt_deg=20.0)
        lines = device_lines(plan)
        self.assertEqual(len(lines), 9)
        direction = plan.direction
        for _name, offset, raised in lines[1:]:
            self.assertAlmostEqual(np.linalg.norm(offset), 200.0)
            self.assertAlmostEqual(float(np.dot(offset, direction)), 0.0)
            self.assertEqual(raised, 0.0)
        self.assertEqual(len(device_lines(plan, outline=True)), 8)

    def test_a_prism_bottom_rises_behind_its_face_at_the_bevel(self):
        plan = prism([0.0, 0.0, -1000.0], roll=90.0)          # face looks right
        np.testing.assert_allclose(plan.normal, [1.0, 0.0, 0.0], atol=1e-12)
        lines = device_lines(plan)
        for _name, offset, raised in lines:
            behind = -float(np.dot(offset, plan.normal))
            self.assertGreaterEqual(behind, -1e-9)
            self.assertLessEqual(behind, 400.0 + 1e-9)
            self.assertAlmostEqual(raised, behind)            # 45°: rises as far as it goes back
        self.assertLess(len(device_lines(plan, outline=True)), len(lines))
        flat = prism([0.0, 0.0, -1000.0], bevel_deg=90.0)
        self.assertTrue(all(raised == 0.0 for _n, _o, raised in device_lines(flat)))

    def test_the_planned_prism_model_has_the_bevel(self):
        plan = prism([0.0, 0.0, -1000.0], roll=90.0)
        model = planned_model(plan, {"entry_um": [0.0, 0.0, 0.0]}, 50.0)
        # Bottom at (0, 0, -20) voxels; the prism lies at ML -8..0, AP -4..4.
        corners = model_segments(model)
        self.assertAlmostEqual(corners[:, 2].min(), -20.0)
        self.assertAlmostEqual(corners[:, 2].max(), -20.0 + 40.0)
        x, y = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])

        def cut(height):
            mask = model_section(model, np.array([-10.0, -10.0, -20.0 + height]), x, y,
                                 (20, 20))
            return 0 if mask is None else int(mask.sum())

        # Two voxels above the bottom only the two columns nearest the face are
        # inside; above the bevel (8 voxels) the whole 8 x 8 footprint is.
        self.assertEqual(cut(2.0), 2 * 8)
        self.assertEqual(cut(9.0), 8 * 8)
        self.assertEqual(cut(41.0), 0)
        fibre = planned_model(fiber([0.0, 0.0, -1000.0]), {"entry_um": [0.0, 0.0, 0.0]}, 50.0)
        self.assertEqual(fibre["type"], "cylinder")
        self.assertAlmostEqual(fibre["radius_vox"], 4.0)


class ReadoutTests(unittest.TestCase):
    def setUp(self):
        self.atlas, _labels, _info = make_atlas()

    def test_the_imaging_face_looks_into_what_is_in_front_of_it(self):
        # Face at ML +0.15 mm looking right, its bottom 1.25 mm deep at AP 0:
        # the view (bottom 0.4 mm, ±0.2 mm, 0.05-0.2 mm out) is three quarters RT.
        plan = prism([150.0, 0.0, -1250.0], roll=90.0)
        height, regions = face_view(plan, self.atlas)
        self.assertAlmostEqual(height, 400.0)
        fractions = {r["acronym"]: r["fraction"] for r in regions}
        self.assertAlmostEqual(fractions["RT"], 0.75)
        self.assertAlmostEqual(fractions["CH"], 0.25)
        readout = plan_readout(plan, self.atlas)
        self.assertEqual(readout["face"], "lateral (the animal's right)")
        self.assertEqual(readout["warnings"], [])
        line = coordinate_line(plan, readout)
        self.assertIn("bottom of the imaging face", line)
        self.assertIn("face looks into RT 75%, CH 25%", line)
        # Looking left, the same face sees only CH.
        left = face_view(prism([150.0, 0.0, -1250.0], roll=270.0), self.atlas)[1]
        self.assertEqual([r["acronym"] for r in left], ["CH"])
        # A flat bottom has no mirror and no view.
        self.assertEqual(face_view(prism([150.0, 0.0, -1250.0], bevel_deg=90.0),
                                   self.atlas), (0.0, []))

    def test_the_imaging_window_must_be_in_the_brain(self):
        # The window is 0.4 x 0.4 mm (45°, 0.4 mm deep): with the face's bottom
        # 0.3 mm deep it reaches 0.1 mm above the surface.
        readout = plan_readout(prism([150.0, 0.0, -300.0]), self.atlas)
        np.testing.assert_allclose(readout["imaging_window_um"], [400.0, 400.0])
        self.assertIn("The imaging window (0.40 × 0.40 mm) reaches 0.10 mm above the brain "
                      "surface: put the bottom of the face at least 0.40 mm deep.",
                      readout["warnings"])
        deep = plan_readout(prism([150.0, 0.0, -1250.0]), self.atlas)
        self.assertFalse(any("imaging window" in w for w in deep["warnings"]))

    def test_a_prism_too_short_for_its_depth(self):
        plan = prism([150.0, 0.0, -1250.0], length_um=1000.0)
        warnings = plan_readout(plan, self.atlas)["warnings"]
        self.assertTrue(any("top would be 0.25 mm below the brain surface" in w
                            for w in warnings), warnings)

    def test_the_rim_and_footprint_are_checked_not_only_the_axis(self):
        # The axis at ML +0.05 mm misses RT (from ML +0.25); the 0.4 mm fiber's rim does not.
        plan = fiber([50.0, 0.0, -1000.0])
        hard, _soft = track_checks(plan, self.atlas, avoid=[30])
        self.assertEqual(hard, ["The fiber passes through RT, which is to be kept out of."])
        probe = ProbePlan("Probe 1", [50.0, 0.0, -1000.0])
        self.assertEqual(track_checks(probe, self.atlas, avoid=[30])[0], [])
        # A 0.3 mm craniotomy around the entry holds the probe, not the prism.
        hole = Craniotomy("c" * 32, "Craniotomy 1", [0.0, 0.0], 300.0)
        self.assertEqual(track_checks(ProbePlan("Probe 1", [0.0, 0.0, -1000.0]),
                                      self.atlas, craniotomy=hole)[0], [])
        hard, _soft = track_checks(prism([0.0, 0.0, -1000.0]), self.atlas, craniotomy=hole)
        self.assertEqual(hard, ["The prism does not fit through Craniotomy 1 (0.30 mm across)."])

    def test_a_gap_is_reported_once_for_the_whole_fiber(self):
        from driftlessmap.probe_plans import PlanAtlas

        _atlas, labels, info = make_atlas()
        labels = labels.copy()
        labels[:, :, 30:32] = 0          # an unlabelled layer, 0.1 mm thick, 0.4 mm deep
        atlas = PlanAtlas(labels, info, 50.0, self.atlas.bregma)
        _hard, soft = track_checks(fiber([0.0, 0.0, -1000.0]), atlas)
        self.assertEqual(soft, ["The fiber crosses up to 0.10 mm outside the atlas's labelled "
                                "brain between the surface and its tip."])

    def test_clearance_is_measured_to_the_fiber_surface(self):
        planned = [fiber([-300.0, 0.0, -1000.0]),
                   ProbePlan("Probe 1", [100.0, 0.0, -1000.0])]
        [pair] = clearances([(plan, plan_readout(plan, self.atlas)) for plan in planned])
        self.assertAlmostEqual(pair["distance_um"], 200.0, places=6)


if __name__ == "__main__":
    unittest.main()
