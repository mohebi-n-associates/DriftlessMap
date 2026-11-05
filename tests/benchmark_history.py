"""Measure shared-array history packing; optionally compare a trusted old module.

python tests/benchmark_history.py [--baseline /tmp/old_transactions.py]
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import tracemalloc

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driftlessmap import transactions  # noqa: E402


def measure(module):
    array = np.random.default_rng(42).integers(0, 65536, (2048, 2048), dtype=np.uint16)
    state = {'live': array, 'built': [array], 'source': array}
    tracemalloc.start()
    start = time.perf_counter()
    packed, size = module.pack(state)
    seconds = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    restored = module.unpack(packed)
    np.testing.assert_array_equal(restored['live'], array)
    return {'pack_seconds': seconds, 'retained_bytes': size, 'traced_peak_bytes': peak}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline')
    args = parser.parse_args()
    result = {'current': measure(transactions)}
    if args.baseline:
        spec = importlib.util.spec_from_file_location('history_baseline', args.baseline)
        baseline = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = baseline
        spec.loader.exec_module(baseline)
        result['baseline'] = measure(baseline)
    print(json.dumps(result, indent=2))
