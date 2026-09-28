"""GUI-free helpers for assembling and restoring DriftlessMap projects."""

import os
import re

from .provenance import describe_atlas_path, describe_path


def prefingerprint_inputs(atlas_path, histology_path):
    """Warm the provenance checksum cache for the inputs a save will link."""
    for path, describe in (
        (atlas_path, describe_atlas_path),
        (histology_path, describe_path),
    ):
        if not path or not os.path.exists(path):
            continue
        try:
            describe(path)
        except (OSError, ValueError):
            # The provenance step reports the problem on the GUI thread.
            pass


def object_file_names(names):
    """Return unique, filesystem-safe file stems for object names."""
    stems = []
    used = set()
    for name in names:
        stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", str(name)).strip(" .")
        stem = stem or "object"
        candidate = stem
        counter = 2
        while candidate.lower() in used:
            candidate = "{} ({})".format(stem, counter)
            counter += 1
        used.add(candidate.lower())
        stems.append(candidate)
    return stems


def default_working_img_data():
    return {
        "img-overlay": None,
        "img-mask": None,
        "img-probe": [],
        "img-cells": [],
        "img-contour": [],
        "img-virus": None,
        "img-drawing": [],
        "img-blob": [],
        "cell_count": [0 for i in range(5)],
        "cell_size": [],
        "cell_symbol": [],
        "cell_layer_index": [],
        "lasso_path": [],
        "ruler_path": [],
    }


def default_working_atlas_data():
    return {
        "atlas-overlay": None,
        "atlas-mask": None,
        "atlas-probe": [],
        "atlas-cells": [],
        "atlas-contour": [],
        "atlas-virus": [],
        "atlas-drawing": [],
        "cell_count": [0 for i in range(5)],
        "cell_size": [],
        "cell_symbol": [],
        "cell_layer_index": [],
        "lasso_path": [],
        "ruler_path": [],
    }


def with_defaults(defaults, saved):
    """Overlay saved working data on defaults, keeping only known keys."""
    merged = dict(defaults)
    if isinstance(saved, dict):
        for key in defaults:
            if key in saved:
                merged[key] = saved[key]
    cell_count = merged.get("cell_count")
    if not isinstance(cell_count, (list, tuple)) or len(cell_count) != 5:
        merged["cell_count"] = [0 for _ in range(5)]
    return merged
