"""Public API for DriftlessMap."""

from .run_driftlessmap import run
from .version import __version__

run_driftlessmap = run

__all__ = ["run", "run_driftlessmap", "CZIReader", "__version__"]


def __getattr__(name):
    if name == "CZIReader":
        from .czi_reader import CZIReader

        return CZIReader
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
