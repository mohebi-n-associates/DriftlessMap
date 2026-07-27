"""Public API for DriftlessMap.

The implementation remains in the ``herbs`` package during the compatibility
period so existing scripts and saved research workflows continue to work.
"""

from herbs.run_herbs import run
from .version import __version__

run_driftlessmap = run

__all__ = ["run", "run_driftlessmap", "CZIReader", "__version__"]


def __getattr__(name):
    if name == "CZIReader":
        from herbs.czi_reader import CZIReader

        return CZIReader
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
