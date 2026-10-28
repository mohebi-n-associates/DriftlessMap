"""Reproducible exact-state digest benchmark; does not require the GUI.

Run: python tests/benchmark_project_state.py
This measures digest cost, not full application performance or release readiness.
"""

import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from driftlessmap.state_digest import state_digest


def main():
    results = []
    for shape in ((1024, 1024, 3), (4096, 4096, 6)):
        image = np.zeros(shape, dtype=np.uint16)
        image[::17] = 45000
        payload = {"image": image, "same_image": image,
                   "cells": [[float(i), float(i % 1000)] for i in range(10000)]}
        samples = []
        for _ in range(3):
            started = time.perf_counter()
            state_digest(payload)
            samples.append(time.perf_counter() - started)
        results.append({"shape": shape, "image_mib": image.nbytes / 1024**2,
                        "median_seconds": float(np.median(samples))})
    print(json.dumps({"machine": platform.machine(), "platform": platform.platform(),
                      "python": platform.python_version(), "numpy": np.__version__,
                      "results": results}, indent=2))


if __name__ == "__main__":
    main()
