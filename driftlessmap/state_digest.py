"""Exact, bounded-memory digests of saved state (no lossy array summaries)."""

import hashlib

import numpy as np


def state_digest(value):
    """Hash every value; deduplicate shared arrays within this call only.

    Mutable arrays must be read again on the next call. Chunked iteration
    avoids allocating a second full raster for non-contiguous image views.
    """
    arrays = {}

    def digest(item):
        h = hashlib.sha256()
        if isinstance(item, np.generic):
            item = item.item()
        h.update(type(item).__name__.encode())
        if isinstance(item, np.ndarray):
            if id(item) in arrays:
                return arrays[id(item)]
            h.update(repr((item.shape, item.dtype.str, item.dtype.descr)).encode())
            if item.dtype.hasobject:
                h.update(digest(item.tolist()))
            elif item.size:
                with np.nditer(item, flags=["external_loop", "buffered"],
                               order="C", buffersize=65536) as chunks:
                    for chunk in chunks:
                        h.update(chunk.tobytes())
            arrays[id(item)] = h.digest()
        elif isinstance(item, dict):
            for key in sorted(item, key=repr):
                h.update(digest(key))
                h.update(digest(item[key]))
        elif isinstance(item, (tuple, list)):
            for child in item:
                h.update(digest(child))
        elif item is None or isinstance(item, (str, int, float, bool, bytes)):
            h.update(repr(item).encode())
        elif hasattr(item, "getRgb"):
            h.update(digest(item.getRgb()))
        else:
            raise TypeError("Unsupported saved-state value: {}".format(type(item).__name__))
        return h.digest()

    return digest(value).hex()
