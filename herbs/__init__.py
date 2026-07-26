"""
``HERBS Code``
================

Functions present in herbs are listed below.


For Image Processing
--------------------------

   ...
   ...

For Atlas
--------------

   ...

For Others
------------------

   ...


"""

from .run_herbs import run, run_herbs
from .version import __version__

__all__ = ["run", "run_herbs", "CZIReader", "__version__"]


def __getattr__(name):
    if name == "CZIReader":
        from .czi_reader import CZIReader

        return CZIReader
    raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
