"""Legacy HERBS compatibility API for DriftlessMap.

New integrations should use ``import driftlessmap``. The old import remains
available so existing HERBS scripts continue to run during the transition.
"""

from .run_herbs import run, run_herbs
from .version import __version__

__all__ = ["run", "run_herbs", "CZIReader", "__version__"]


def __getattr__(name):
    if name == "CZIReader":
        from .czi_reader import CZIReader

        return CZIReader
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
