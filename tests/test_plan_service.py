import unittest
from unittest.mock import patch

from driftlessmap.plan_service import PlanService
from driftlessmap.probe_plans import plan_readout, space_plans, SearchStopped
from tests.test_probe_plans import make_atlas
from tests.test_plan_spacing import fiber


class PlanServiceTests(unittest.TestCase):
    def test_cached_readout_is_isolated_and_invalidated_by_pose_and_atlas(self):
        atlas, _, _ = make_atlas()
        plan = fiber('Fiber 1', [0, 0, -1200])
        service = PlanService(capacity=2)
        with patch('driftlessmap.plan_service.plan_readout', wraps=plan_readout) as read:
            first = service.readout(plan, atlas)
            first['warnings'].append('not cached')
            self.assertNotIn('not cached', service.readout(plan, atlas)['warnings'])
            self.assertEqual(read.call_count, 1)
            service.readout(plan.copy(ml_tilt_deg=1), atlas)
            self.assertEqual(read.call_count, 2)
            other, _, _ = make_atlas()
            service.readout(plan, other)
            self.assertEqual(read.call_count, 3)
            self.assertEqual(len(service.readouts), 1)

    def test_cancel_does_not_mutate_input(self):
        atlas, _, _ = make_atlas()
        plans = [fiber('Fiber 1', [300, 0, -1200]), fiber('Fiber 2', [500, 200, -1300])]
        before = [p.to_dict() for p in plans]
        with self.assertRaises(SearchStopped):
            space_plans(atlas, plans, [p.probe for p in plans], progress=lambda: False)
        self.assertEqual(before, [p.to_dict() for p in plans])
