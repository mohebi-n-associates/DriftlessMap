"""Atlas region colours that keep neighbouring regions apart (GUI-free).

Atlas ontologies colour related regions alike: in the Allen atlas the
prelimbic (PL) and infralimbic (ILA) areas, which touch, are both green.
`distinct_region_colors` finds which regions touch in the label volume and
moves the colour of a region that is too close to a neighbour's to the
nearest colour that is far enough from all of them, so most regions keep
their atlas colour and changed ones stay close to it.

Regions are recoloured as areas: a region and its descendants that share its
colour (an area's layers) form one area and keep one colour.
"""

import numpy as np

# Smallest CIE76 colour difference between touching areas.
MIN_DIFFERENCE = 30.0
# Touching is found on a copy of the label volume sampled every STEP voxels
# along each axis (40 um for the 10 um Allen atlas).
STEP = 4
_HUE_STEPS = (0, 20, -20, 40, -40, 60, -60, 90, -90, 120, -120, 150, -150, 180)
_LIGHTNESS_STEPS = (0, 10, -10, 20, -20, 30, -30)
_CHROMA_STEPS = (0, 25, 50)


def srgb_to_lab(rgb):
    """CIE L*a*b* (D65) of 8-bit sRGB colours, shape (..., 3)."""
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193],
                        [0.3576, 0.7152, 0.1192],
                        [0.1805, 0.0722, 0.9505]])
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]),
                     200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb(lab):
    """8-bit sRGB of CIE L*a*b* colours, clipped to the gamut, shape (..., 3)."""
    lab = np.asarray(lab, dtype=float)
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29))
    xyz = xyz * np.array([0.95047, 1.0, 1.08883])
    c = xyz @ np.array([[3.2406, -0.9689, 0.0557],
                        [-1.5372, 1.8758, -0.2040],
                        [-0.4986, 0.0415, 1.0570]])
    c = np.clip(c, 0.0, 1.0)
    c = np.where(c > 0.0031308, 1.055 * c ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.round(c * 255).astype(int)


def color_areas(index, parent, color):
    """Area root of each label: the label itself, or its highest ancestor
    reached through parents of exactly the same colour."""
    index = [int(i) for i in np.ravel(index)]
    color = np.asarray(color).reshape(len(index), -1)[:, :3]
    row = {label: i for i, label in enumerate(index)}
    parent_of = {label: int(p) for label, p in zip(index, np.ravel(parent))}
    roots = []
    for i, label in enumerate(index):
        root, seen = label, {label}
        while True:
            up = parent_of.get(root)
            if up not in row or up in seen or not np.array_equal(color[row[up]], color[i]):
                break
            root = up
            seen.add(up)
        roots.append(root)
    return roots


def touching_pairs(volume, labels, step=STEP):
    """Pairs of positions in ``labels`` (sorted label IDs) whose regions touch
    along an axis of the sampled volume; background (0) and unknown IDs are
    ignored. Returns an (N, 2) int array with the smaller position first."""
    labels = np.asarray(labels, dtype=np.int64)
    sample = np.asarray(volume[::step, ::step, ::step])
    found = np.searchsorted(labels, sample)
    found = np.minimum(found, len(labels) - 1)
    known = labels[found] == sample
    codes = np.where(known & (sample != 0), found, -1)
    pairs = []
    for axis in range(3):
        a = np.moveaxis(codes, axis, 0)
        first, second = a[:-1].ravel(), a[1:].ravel()
        keep = (first != second) & (first >= 0) & (second >= 0)
        low = np.minimum(first[keep], second[keep])
        high = np.maximum(first[keep], second[keep])
        pairs.append(np.unique(low.astype(np.int64) * len(labels) + high))
    if not pairs:
        return np.zeros((0, 2), dtype=np.int64)
    code = np.unique(np.concatenate(pairs))
    return np.stack([code // len(labels), code % len(labels)], axis=1)


def _candidates(lab):
    """Colours near ``lab`` in lightness, hue and chroma, nearest first."""
    lightness, a, b = lab
    chroma, hue = np.hypot(a, b), np.arctan2(b, a)
    found = []
    for dc in _CHROMA_STEPS:
        for dl in _LIGHTNESS_STEPS:
            for dh in _HUE_STEPS:
                c = chroma + dc
                h = hue + np.radians(dh)
                found.append((np.clip(lightness + dl, 15, 95), c * np.cos(h), c * np.sin(h)))
    found = srgb_to_lab(lab_to_srgb(np.array(found)))   # what can be shown
    order = np.argsort(np.linalg.norm(found - lab, axis=1), kind="stable")
    return found[order]


def distinct_region_colors(label_info, volume, min_difference=MIN_DIFFERENCE, step=STEP):
    """``label_info`` with colours changed so touching areas differ by at
    least ``min_difference`` (CIE76) where possible.

    Returns a new dict (the input is not modified) whose ``color`` holds the
    new colours and ``atlas_color`` the atlas's own; and the number of areas
    whose colour changed. Larger areas keep their colour first.
    """
    index = np.asarray(label_info["index"], dtype=np.int64)
    color = np.asarray(label_info["color"]).reshape(len(index), -1)[:, :3].astype(int)
    roots = color_areas(index, label_info["parent"], color)
    area_ids = sorted(set(roots))
    area_of_root = {root: k for k, root in enumerate(area_ids)}
    area = np.array([area_of_root[r] for r in roots], dtype=np.int64)

    order = np.argsort(index, kind="stable")
    sorted_ids = index[order]
    pairs = touching_pairs(volume, sorted_ids, step)
    pairs = area[order][pairs] if len(pairs) else pairs.reshape(0, 2)
    pairs = pairs[pairs[:, 0] != pairs[:, 1]]
    neighbours = [set() for _ in area_ids]
    for first, second in pairs:
        neighbours[first].add(int(second))
        neighbours[second].add(int(first))

    # Size of each area in the sampled volume decides who keeps its colour.
    sample = np.asarray(volume[::step, ::step, ::step]).ravel()
    ids, counts = np.unique(sample, return_counts=True)
    found = np.minimum(np.searchsorted(sorted_ids, ids), len(sorted_ids) - 1)
    size = np.zeros(len(area_ids))
    known = sorted_ids[found] == ids
    np.add.at(size, area[order][found[known]], counts[known])

    root_row = {int(label): i for i, label in enumerate(index)}
    lab = srgb_to_lab(np.array([color[root_row[root]] for root in area_ids]))
    new_lab = lab.copy()
    done = np.zeros(len(area_ids), dtype=bool)
    changed = 0
    for k in sorted(range(len(area_ids)), key=lambda k: (-size[k], area_ids[k])):
        placed = [n for n in neighbours[k] if done[n]]
        done[k] = True
        if not placed:
            continue
        others = new_lab[placed]
        if np.min(np.linalg.norm(others - lab[k], axis=1)) >= min_difference:
            continue
        options = _candidates(lab[k])
        gap = np.min(np.linalg.norm(options[:, None, :] - others[None], axis=2), axis=1)
        good = np.flatnonzero(gap >= min_difference)
        new_lab[k] = options[good[0]] if len(good) else options[int(np.argmax(gap))]
        changed += 1

    new_rgb = lab_to_srgb(new_lab)
    result = dict(label_info)
    result["atlas_color"] = color.copy()
    unchanged = np.all(new_lab == lab, axis=1)
    result["color"] = np.array([color[i] if unchanged[area[i]] else new_rgb[area[i]]
                                for i in range(len(index))], dtype=color.dtype)
    return result, changed
