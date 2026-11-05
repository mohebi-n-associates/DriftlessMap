"""Bounded, GUI-free derived planning data owned by one document engine.

Atlas volumes are immutable while installed. A different atlas object clears
all cached results. Plan keys include every serialized scientific field;
callers receive copies so UI annotations cannot mutate cached diagnostics.
"""
import copy
import json
from collections import OrderedDict

from .probe_plans import clearances, plan_readout


class PlanService:
    def __init__(self, capacity=64):
        self.capacity = capacity
        self.atlas = None
        self.readouts = OrderedDict()
        self.pairs = OrderedDict()

    def _select(self, atlas):
        if atlas is not self.atlas:
            self.atlas = atlas
            self.readouts.clear()
            self.pairs.clear()

    @staticmethod
    def key(plan):
        return json.dumps(plan.to_dict(), sort_keys=True)

    def _get(self, cache, key, calculate):
        if key not in cache:
            cache[key] = calculate()
        cache.move_to_end(key)
        while len(cache) > self.capacity:
            cache.popitem(last=False)
        return copy.deepcopy(cache[key])

    def readout(self, plan, atlas):
        self._select(atlas)
        return self._get(self.readouts, self.key(plan), lambda: plan_readout(plan, atlas))

    def clearances(self, plans, atlas):
        self._select(atlas)
        result = []
        for i, a in enumerate(plans):
            for b in plans[i + 1:]:
                key = self.key(a), self.key(b)
                result.extend(self._get(self.pairs, key, lambda a=a, b=b: clearances([
                    (a, self.readout(a, atlas)), (b, self.readout(b, atlas))])))
        return sorted(result, key=lambda pair: pair['distance_um'])
