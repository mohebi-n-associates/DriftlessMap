"""Space out plans that come too close (2.8.8): tilts about the tips,
vertical where possible, ML before AP, the largest tilt as small as possible."""

import math
import unittest
from unittest.mock import patch

import numpy as np

from driftlessmap.probe_plans import ProbePlan, clearances, plan_readout, space_plans
from tests.test_probe_plans import make_atlas


def fiber(name, tip, **keep):
    return ProbePlan(name, tip, kind="fiber",
                     specs={"diameter_um": 200.0, "fiber_length_um": 1500.0,
                            "ferrule_diameter_um": 1250.0, "ferrule_length_um": 6400.0},
                     implant_id=name[-1] * 32, **keep)


class SpacingTests(unittest.TestCase):
    def setUp(self):
        self.atlas, _labels, _info = make_atlas()

    def closest(self, plans):
        return clearances([(p, plan_readout(p, self.atlas)) for p in plans])

    def ferrule_gap(self, a, b):
        """The gap between the two ferrules' surfaces, exactly (axis lines)."""
        def ferrule(plan):
            bottom = np.asarray(plan.tip_um) - plan.direction * plan.specs["fiber_length_um"]
            return bottom, bottom - plan.direction * plan.specs["ferrule_length_um"]

        from driftlessmap.probe_plans import _segment_distance

        distance = _segment_distance(*ferrule(a), *ferrule(b))[0]
        return distance - a.specs["ferrule_diameter_um"]

    def test_search_does_not_compute_anatomical_readouts(self):
        plans = [fiber("Fiber 1", [300, 0, -1200]),
                 fiber("Fiber 2", [500, 200, -1300])]
        with patch("driftlessmap.probe_plans.plan_readout",
                   side_effect=AssertionError("unnecessary anatomical calculation")):
            spaced, report = space_plans(self.atlas, plans, [p.probe for p in plans])
        self.assertTrue(report["moved"])
        self.assertFalse(report["clashes"])
        self.assertGreaterEqual(self.ferrule_gap(*spaced), 300 - 1e-6)

    def test_overlapping_fixed_tips_remain_a_clash(self):
        plans = [fiber("Fiber 1", [0, 0, -1200]),
                 fiber("Fiber 2", [0, 0, -1200])]
        spaced, report = space_plans(self.atlas, plans, [p.probe for p in plans])
        self.assertEqual([p.tip_um for p in spaced], [p.tip_um for p in plans])
        self.assertEqual(len(report["clashes"]), 1)
        self.assertEqual(report["clashes"][0]["distance_um"], 0.0)

    def test_fixed_pair_conflict_is_reported_without_moving_it(self):
        plans = [fiber("Fiber 1", [-800, 0, -1200]),
                 fiber("Fiber 2", [-600, 0, -1200]),
                 fiber("Fiber 3", [900, 900, -1200])]
        spaced, report = space_plans(self.atlas, plans, ["Fiber 3"],
                                     max_ml_deg=0, max_ap_deg=0)
        self.assertEqual(spaced, plans)
        self.assertEqual(report["moved"], [])
        self.assertEqual([p["probes"] for p in report["clashes"]],
                         [("Fiber 1", "Fiber 2")])

    def test_ferrules_that_touch_are_splayed_in_ml_about_fixed_tips(self):
        plans = [fiber("Fiber 1", [300.0, 0.0, -1200.0]),
                 fiber("Fiber 2", [500.0, 200.0, -1300.0])]
        self.assertEqual(self.closest(plans)[0]["distance_um"], 0.0)
        spaced, report = space_plans(self.atlas, plans, ["Fiber 1", "Fiber 2"])
        a, b = spaced
        self.assertEqual(report["clashes"], [])
        self.assertFalse(report["ap_used"])
        self.assertEqual(sorted(report["moved"]), ["Fiber 1", "Fiber 2"])
        for before, after in zip(plans, spaced):
            self.assertEqual(after.tip_um, before.tip_um)           # tips never move
            self.assertEqual(after.ap_tilt_deg, 0.0)
        # Splayed apart (Fiber 1 is to the left: its top goes left), evenly.
        self.assertGreater(a.ml_tilt_deg, 0.0)
        self.assertLess(b.ml_tilt_deg, 0.0)
        self.assertLessEqual(abs(abs(a.ml_tilt_deg) - abs(b.ml_tilt_deg)), 1.0)
        # The ferrules keep the 0.3 mm gap; one degree less on the larger
        # tilt and they would not.
        self.assertGreaterEqual(self.ferrule_gap(a, b), 300.0 - 1e-6)
        larger = a if abs(a.ml_tilt_deg) >= abs(b.ml_tilt_deg) else b
        less = larger.copy(ml_tilt_deg=larger.ml_tilt_deg
                           - math.copysign(1.0, larger.ml_tilt_deg))
        pair = (less, b) if larger is a else (a, less)
        self.assertLess(self.ferrule_gap(*pair), 300.0)

    def test_plans_already_apart_and_fixed_plans_do_not_move(self):
        # 1.8 mm apart: the 1.25 mm ferrules keep 0.55 mm; the second leans
        # out (its top to the right), as the user set it.
        far = [fiber("Fiber 1", [-900.0, 0.0, -1000.0]),
               fiber("Fiber 2", [900.0, 0.0, -1000.0], ml_tilt_deg=-5.0)]
        spaced, report = space_plans(self.atlas, far, ["Fiber 1", "Fiber 2"])
        self.assertEqual(report["moved"], [])
        self.assertEqual(spaced, far)              # a tilt of the user's own stays
        # 1 mm apart, only Fiber 2 may move: it alone leans out (about 22°).
        close = [fiber("Fiber 1", [-500.0, 0.0, -1200.0]),
                 fiber("Fiber 2", [500.0, 0.0, -1200.0])]
        spaced, report = space_plans(self.atlas, close, ["Fiber 2"])
        self.assertEqual(report["moved"], ["Fiber 2"])
        self.assertEqual(spaced[0], close[0])
        self.assertLess(spaced[1].ml_tilt_deg, 0.0)     # away from the fixed one
        self.assertEqual(report["clashes"], [])

    def test_ap_tilts_only_when_ml_cannot_help(self):
        plans = [fiber("Fiber 1", [300.0, 0.0, -1200.0]),
                 fiber("Fiber 2", [300.0, 300.0, -1200.0])]
        spaced, report = space_plans(self.atlas, plans, ["Fiber 1", "Fiber 2"],
                                     max_ml_deg=0.0)
        self.assertTrue(report["ap_used"])
        self.assertEqual(report["clashes"], [])
        self.assertTrue(all(p.ml_tilt_deg == 0.0 for p in spaced))
        # The anterior fiber's top goes anterior: its tip lies posterior of
        # its entry (a negative AP tilt).
        self.assertLess(spaced[1].ap_tilt_deg, 0.0)
        self.assertGreater(spaced[0].ap_tilt_deg, 0.0)
        # ML alone would need about 30.4° each: allowed 35°, ML alone does it;
        # at the default 30°, AP helps.
        spaced, report = space_plans(self.atlas, plans, ["Fiber 1", "Fiber 2"],
                                     max_ml_deg=35.0)
        self.assertFalse(report["ap_used"])
        self.assertEqual(report["clashes"], [])

    def test_when_nothing_within_the_limits_helps_the_clash_is_reported(self):
        plans = [fiber("Fiber 1", [300.0, 0.0, -1200.0]),
                 fiber("Fiber 2", [500.0, 0.0, -1200.0])]
        spaced, report = space_plans(self.atlas, plans, ["Fiber 1", "Fiber 2"],
                                     max_ml_deg=0.0, max_ap_deg=0.0)
        self.assertEqual(report["moved"], [])
        self.assertEqual(spaced, plans)
        [pair] = report["clashes"]
        self.assertEqual(pair["probes"], ("Fiber 1", "Fiber 2"))


if __name__ == "__main__":
    unittest.main()
