"""A planned Neuropixels probe's hardware (2.8.6): parts, placement, clearances."""

import unittest

import numpy as np

from driftlessmap.implants import model_mesh, model_section
from driftlessmap.probe_hardware import (
    box_corners,
    hardware_boxes,
    hardware_kind,
    hardware_model,
    hardware_segments,
)
from driftlessmap.probe_plans import ProbePlan, clearances, plan_readout
from driftlessmap.probe_utiles import Probe
from tests.test_probe_plans import make_atlas

NP2_SHANKS = [-375.0, -125.0, 125.0, 375.0]


def settings(kind):
    probe = Probe()
    probe.set_np1() if kind == 1 else probe.set_np2()
    return probe.get_settings()


def np1(tip, **keep):
    return ProbePlan("Probe 1", tip, probe_settings=settings(1), **keep)


def np2(tip, name="Probe 2", **keep):
    return ProbePlan(name, tip, probe_settings=settings(2), shank_offsets_um=NP2_SHANKS, **keep)


class PartsTests(unittest.TestCase):
    def test_which_probes_have_hardware(self):
        self.assertEqual(hardware_kind(np1([0, 0, -1000])), "NP1.0")
        self.assertEqual(hardware_kind(np2([0, 0, -1000])), "NP2.0")
        self.assertIsNone(hardware_kind(ProbePlan("Probe 3", [0, 0, -1000])))
        fiber = ProbePlan("Fiber 1", [0, 0, -1000], kind="fiber", implant_id="f" * 32)
        self.assertIsNone(hardware_kind(fiber))
        self.assertEqual(hardware_boxes(fiber), [])
        self.assertIsNone(hardware_model(fiber, 50.0))

    def test_a_vertical_np1_base_starts_where_its_shank_ends_behind_the_face(self):
        boxes = {box["name"]: box for box in hardware_boxes(np1([0.0, 0.0, -1000.0]))}
        self.assertEqual(set(boxes), {"Shank", "Probe base", "Flex cable", "Connector board",
                                      "Dovetail adapter"})
        base = box_corners(boxes["Probe base"])
        # 10 mm shank: the base from DV +9 mm (tip -1 mm) for 10.7 mm.
        self.assertAlmostEqual(base[:, 2].min(), 9000.0)
        self.assertAlmostEqual(base[:, 2].max(), 19700.0)
        # Roll 0: the contacts face anterior, the 1.2 mm base lies behind them.
        self.assertAlmostEqual(base[:, 1].max(), 0.0)
        self.assertAlmostEqual(base[:, 1].min(), -1200.0)
        self.assertAlmostEqual(np.ptp(base[:, 0]), 6200.0)
        flex = box_corners(boxes["Flex cable"])
        self.assertAlmostEqual(flex[:, 2].min(), 19700.0)
        dovetail = box_corners(boxes["Dovetail adapter"])
        self.assertLess(dovetail[:, 1].max(), base[:, 1].min())   # behind the base
        shank = box_corners(boxes["Shank"])
        self.assertAlmostEqual(shank[:, 2].min(), -1000.0)
        self.assertAlmostEqual(shank[:, 2].max(), 9000.0)

    def test_np2_parts_turn_and_tilt_with_the_probe(self):
        plan = np2([200.0, 0.0, -1000.0], ap_tilt_deg=20.0, roll_deg=90.0)
        boxes = hardware_boxes(plan)
        self.assertEqual(sum(b["name"] == "Shank" for b in boxes), 4)
        headstage = [b for b in boxes if b["name"] == "Headstage"][0]
        self.assertEqual(headstage["half"], [7000.0, 5000.0, 1850.0])
        up = -plan.direction
        for box in boxes:
            np.testing.assert_allclose(box["axes"][0], up, atol=1e-12)
            np.testing.assert_allclose(box["axes"][2], plan.normal, atol=1e-12)
        # The base is centred on the shank row, 10 mm up the probe from the tip.
        base = [b for b in boxes if b["name"] == "Probe base"][0]
        start = np.asarray(base["centre"]) - up * base["half"][0] \
            + plan.normal * base["half"][2]
        np.testing.assert_allclose(start, np.asarray(plan.tip_um) + up * 10000.0, atol=1e-6)

    def test_the_drawn_model_is_closed_and_cut_by_slices(self):
        model = hardware_model(np1([0.0, 0.0, -1000.0]), 50.0)
        vertices, faces = model_mesh(model)
        self.assertEqual(len(vertices), 8 * 5)
        edges = {}
        for face in faces:
            for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                key = (min(a, b), max(a, b))
                edges[key] = edges.get(key, 0) + 1
        self.assertEqual(set(edges.values()), {2})
        # A horizontal slice 1 mm into the base (DV +10 mm = 200 voxels) cuts
        # the base, 124 x 24 voxels, and the dovetail beside it.
        mask = model_section(model, np.array([-100.0, -300.0, 200.0]), np.array([1.0, 0, 0]),
                             np.array([0, 1.0, 0]), (400, 200))
        self.assertIsNotNone(mask)
        self.assertAlmostEqual(mask.sum(), 124 * 24 + 160 * 160, delta=400)


class ClearanceTests(unittest.TestCase):
    def setUp(self):
        self.atlas, _labels, _info = make_atlas()

    def test_hardware_collides_above_the_brain(self):
        # Shanks 0.6 mm apart: their 6.2 mm bases overlap 10 mm above the tips.
        planned = [np1([-300.0, 0.0, -1000.0]),
                   np1([300.0, 0.0, -1000.0]).copy(probe="Probe 2")]
        [pair] = clearances([(p, plan_readout(p, self.atlas)) for p in planned])
        self.assertEqual(pair["distance_um"], 0.0)
        self.assertLess(pair["depth_um"], -5000.0)
        # Without hardware (a custom design) the shanks keep their 0.6 mm.
        bare = [p.copy(probe_settings=None) for p in planned]
        [pair] = clearances([(p, plan_readout(p, self.atlas)) for p in bare])
        self.assertAlmostEqual(pair["distance_um"], 600.0)

    def test_segments_cover_each_part(self):
        segments = hardware_segments(np1([0.0, 0.0, -1000.0]))
        radii = sorted({round(r, 3) for _a, _b, r in segments})
        self.assertEqual(radii, [40.0, 500.0, 600.0, 4000.0])   # flex, board, base, dovetail


if __name__ == "__main__":
    unittest.main()
