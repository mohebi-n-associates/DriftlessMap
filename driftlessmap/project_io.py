"""GUI-free helpers for assembling and restoring DriftlessMap projects."""

import os
import re

from .provenance import describe_atlas_path, describe_path

from .image_reader import MAX_CHANNELS

# Cell counts: index 0 counts manual cells, index k counts cells found on
# channel k.
CELL_COUNT_SLOTS = MAX_CHANNELS + 1

# Project payload schema. 3 adds the registration-input recipe; projects with
# schema 1 or 2 are read with Legacy registration input.
PROJECT_SCHEMA_VERSION = 3


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
        "cell_count": [0] * CELL_COUNT_SLOTS,
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
        "cell_count": [0] * CELL_COUNT_SLOTS,
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
    merged["cell_count"] = padded_cell_count(merged.get("cell_count"))
    return merged


def padded_cell_count(cell_count):
    """Cell counts with CELL_COUNT_SLOTS entries.

    Projects before 2.0 stored five entries; shorter lists are padded with
    zeros, and anything invalid is reset.
    """
    if not isinstance(cell_count, (list, tuple)) or len(cell_count) > CELL_COUNT_SLOTS:
        return [0] * CELL_COUNT_SLOTS
    try:
        counts = [int(value) for value in cell_count]
    except (TypeError, ValueError):
        return [0] * CELL_COUNT_SLOTS
    return counts + [0] * (CELL_COUNT_SLOTS - len(counts))
