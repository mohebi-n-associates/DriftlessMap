import itertools
import unittest
import numpy as np
from driftlessmap.solid_geometry import ConvexSolid
from driftlessmap.probe_plans import ProbePlan, clearances, plan_readout
from tests.test_probe_plans import make_atlas


class SolidTests(unittest.TestCase):
    def test_segments_inside_crossing_and_outside(self):
        solid = ConvexSolid(list(itertools.product((-1, 1), repeat=3)))
        for start, end in (([0, 0, 0], [.5, 0, 0]), ([-2, 0, 0], [2, 0, 0])):
            self.assertEqual(solid.segment_distance(start, end)[0], 0)
        self.assertAlmostEqual(solid.segment_distance([2, 0, 0], [3, 0, 0])[0], 1)
        self.assertAlmostEqual(solid.segment_distance([2, 2, 0], [2, 2, .5])[0], np.sqrt(2))

    def test_contained_and_separated_solids(self):
        vertices = np.array(list(itertools.product((-1, 1), repeat=3)))
        solid = ConvexSolid(vertices)
        self.assertEqual(solid.distance(ConvexSolid(vertices * .5))[0], 0)
        self.assertAlmostEqual(solid.distance(ConvexSolid(vertices + [3, 0, 0]))[0], 1)

    def test_fiber_inside_prism_reports_intersection(self):
        atlas, _, _ = make_atlas()
        prism = ProbePlan('Prism', [500, -500, -1400], kind='prism', implant_id='a'*32,
                          roll_deg=90, specs={'width_um': 1000, 'depth_um': 1000,
                                             'length_um': 3000, 'bevel_deg': 90})
        fiber = ProbePlan('Fiber', [0, 0, -500], kind='fiber', implant_id='b'*32,
                          specs={'diameter_um': 100, 'fiber_length_um': 10000})
        result = clearances([(p, plan_readout(p, atlas)) for p in (prism, fiber)])
        self.assertEqual(result[0]['distance_um'], 0)
