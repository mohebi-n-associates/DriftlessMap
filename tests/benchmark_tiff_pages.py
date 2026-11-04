"""Benchmark adding every page of a large TIFF stack as its own section.

Run: QT_QPA_PLATFORM=offscreen python tests/benchmark_tiff_pages.py [pages] [side]

Writes a ``pages`` x ``side`` x ``side`` uint16 ZYX stack to a temporary
folder, adds its pages as sections through ``DriftlessMap.add_sections`` (as
File > Add sections with "Each page a section" does), and reports the number
of full-stack decodes (``TiffPageSeries.asarray`` calls), the elapsed time,
and the peak memory: traced NumPy/Python allocations during the import
(``tracemalloc``) and the process's peak resident size. One run per process,
so the resident peak belongs to this import only. It measures the import, not
full application performance or release readiness (review F7 of 2.6.0).
"""

import json
import os
from pathlib import Path
import platform
import resource
import sys
import tempfile
import time
import tracemalloc
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tests.settings_isolation  # noqa: E402,F401  (before the app reads settings)
import numpy as np  # noqa: E402
import tifffile  # noqa: E402


def peak_resident_mib():
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Bytes on macOS, kibibytes on Linux.
    return peak / 1024 ** 2 if sys.platform == "darwin" else peak / 1024


def main(pages=40, side=1024):
    from PyQt6.QtWidgets import QApplication

    from driftlessmap.app import DriftlessMap
    from tests.atlas_fixture import make_processed_atlas

    application = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        stack = root / "stack.tif"
        rng = np.random.default_rng(0)
        tifffile.imwrite(stack, rng.integers(0, 4096, (pages, side, side), dtype=np.uint16),
                         metadata={"axes": "ZYX"}, photometric="minisblack")
        window = DriftlessMap()
        window.load_volume_atlas(str(make_processed_atlas(root / "atlas")))
        decodes = []
        original = tifffile.TiffPageSeries.asarray

        def counted(series, *args, **kwargs):
            decodes.append(tuple(series.shape))
            return original(series, *args, **kwargs)

        resident_before = peak_resident_mib()
        tracemalloc.start()
        started = time.perf_counter()
        with patch.object(tifffile.TiffPageSeries, "asarray", counted):
            added = window.add_sections([str(stack)], pages_as_sections=True)
        elapsed = time.perf_counter() - started
        traced_peak = tracemalloc.get_traced_memory()[1] / 1024 ** 2
        tracemalloc.stop()
        result = {
            "pages": pages, "side": side,
            "stack_mib": round(pages * side * side * 2 / 1024 ** 2, 1),
            "sections_added": added,
            "full_stack_decodes": sum(1 for shape in decodes if shape[0] == pages),
            "decodes": len(decodes),
            "seconds": round(elapsed, 2),
            "traced_peak_mib": round(traced_peak, 1),
            "resident_peak_mib": round(peak_resident_mib(), 1),
            "resident_peak_before_mib": round(resident_before, 1),
        }
        window.close()
        window.deleteLater()
        application.processEvents()
    print(json.dumps({"machine": platform.machine(), "platform": platform.platform(),
                      "python": platform.python_version(), "numpy": np.__version__,
                      "tifffile": tifffile.__version__, "result": result}, indent=2))


if __name__ == "__main__":
    main(*(int(value) for value in sys.argv[1:3]))
