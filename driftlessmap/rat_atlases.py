"""Downloadable rat atlases and the preparation of their files (GUI-free).

Two atlases share the Waxholm Space (WHS) of the Sprague Dawley rat brain,
39.0625 um voxels, 512 x 1024 x 512, axes as stored in the WHS NIfTI files
(right, anterior, superior):

* :data:`WAXHOLM`: the WHS MRI (T2*) template with the v4.01 annotation
  (Kleven et al. 2023) from NITRC.
* :data:`SWC_FEMALE_RAT`: the Sainsbury Wellcome Centre female rat template
  (serial two-photon microscopy) registered to WHS, with the same v4.01
  annotation, as packaged by BrainGlobe (``whs_sd_swc_female_rat_39um``).

Both are processed by the shared volume-atlas processing; this module only
turns the downloaded files into the template, annotation, mask and
``atlas_labels.pkl`` that processing reads. Every download is pinned by
SHA-256, so a changed upstream file is refused rather than processed.
"""

import json
import os
import tarfile
import xml.etree.ElementTree as ElementTree
import zipfile
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .persistence import write_cache_pickle

# Bregma and Lambda of WHS in voxels of the WHS volume (as used since HERBS).
WHS_BREGMA = (246, 653, 440)
WHS_LAMBDA = (244, 442, 464)
WHS_VOXEL_UM = 39.0625
WHS_SHAPE = (512, 1024, 512)
# The parent of top-level regions in ``atlas_labels.pkl``.
NO_PARENT = np.iinfo(np.int64).min

NITRC = "https://www.nitrc.org/frs/"
# NITRC serves the v4.01 release only to users who accept its terms.
AGREE = "/?i_agree=1&download_now=1"


@dataclass(frozen=True)
class AtlasFile:
    role: str           # shown to the user
    url: str
    local: str          # file name in the atlas folder
    sha256: str
    size: int


@dataclass(frozen=True)
class RatAtlas:
    key: str
    title: str
    summary: str
    files: tuple
    template: str       # files processing reads, in the atlas folder
    annotation: str
    mask: Optional[str]  # brain mask file, or None when the annotation is masked already
    agreement: str      # terms the user accepts before downloading, or ""
    citation: str

    @property
    def download_size(self):
        return sum(item.size for item in self.files)


WAXHOLM = RatAtlas(
    key="waxholm",
    title="Waxholm Space rat brain atlas (v4.01)",
    summary=("Sprague Dawley rat: MRI (T2*) template and 224-region annotation, version "
             "4.01 (2023), at 39 µm. From NITRC."),
    files=(
        AtlasFile("Region annotation and hierarchy (v4.01)",
                  NITRC + "download.php/13400/MBAT_WHS_SD_rat_atlas_v4.01.zip" + AGREE,
                  "MBAT_WHS_SD_rat_atlas_v4.01.zip",
                  "2adeffb6816ee1ace68c1c0383cd484f9eccf436375ebd502890990e26621ae1",
                  3372092),
        AtlasFile("MRI template (T2*, v1.01)",
                  NITRC + "downloadlink.php/9423",
                  "WHS_SD_rat_T2star_v1.01.nii.gz",
                  "5369827d136c7f1cca637a41b7bb322a54c731018db7897325535c39bd10a050",
                  943246294),
        AtlasFile("Brain mask (v1.01)",
                  NITRC + "downloadlink.php/9425",
                  "WHS_SD_rat_brainmask_v1.01.nii.gz",
                  "13068f2e7ce7cc096ad93fd737bdd1dc2472867fb3f17664e02cec3f23d347f1",
                  5372137),
    ),
    template="WHS_SD_rat_T2star_v1.01.nii.gz",
    annotation="WHS_SD_rat_atlas_v4.01.nii.gz",
    mask="WHS_SD_rat_brainmask_v1.01.nii.gz",
    agreement=("By downloading the atlas you agree to NITRC's terms: the atlas is freely "
               "available under the CC BY 4.0 license; cite it according to the citation "
               "policy at https://www.nitrc.org/citation/?group_id=1081."),
    citation="Kleven et al. 2023, Nature Methods, https://doi.org/10.1038/s41592-023-02034-3",
)

SWC_FEMALE_RAT = RatAtlas(
    key="swc_female_rat",
    title="SWC female rat brain atlas (in Waxholm Space)",
    summary=("Lister Hooded female rats: a serial two-photon microscopy template from the "
             "Sainsbury Wellcome Centre, registered to Waxholm Space at 39 µm, with the "
             "Waxholm v4.01 regions. From BrainGlobe."),
    files=(
        AtlasFile("Template and region annotation",
                  "https://gin.g-node.org/brainglobe/atlases/raw/master/"
                  "whs_sd_swc_female_rat_39um_v1.0.tar.gz",
                  "whs_sd_swc_female_rat_39um_v1.0.tar.gz",
                  "9cbf25654aa6568b035c0f61960863cb8fe920f054b84752a8cd56ce380a5793",
                  203458580),
    ),
    template="swc_female_rat_template.nii.gz",
    annotation="swc_female_rat_annotation.nii.gz",
    mask=None,
    agreement="",
    citation=("Sainsbury Wellcome Centre female rat template (BrainGlobe "
              "whs_sd_swc_female_rat_39um v1.0); regions: Kleven et al. 2023, "
              "https://doi.org/10.1038/s41592-023-02034-3"),
)

RAT_ATLASES = {atlas.key: atlas for atlas in (WAXHOLM, SWC_FEMALE_RAT)}


# --------------------------------------------------------------- regions
def _colour(value):
    text = (value or "#ffffff").lstrip("#")
    if len(text) != 6:
        raise ValueError("Invalid region colour {!r}.".format(value))
    return [int(text[i:i + 2], 16) for i in (0, 2, 4)]


def label_info_from_ilf(path):
    """``atlas_labels.pkl`` contents from a WHS ``.ilf`` region hierarchy.

    Regions are listed depth first in file order, as in the label file
    shipped with HERBS.
    """
    root = ElementTree.parse(path).getroot().find("structure")
    if root is None:
        raise ValueError("The region hierarchy has no structure.")
    rows = []

    def visit(element, parent, level):
        for child in element.findall("label"):
            rows.append((int(child.get("id")), _colour(child.get("color")),
                         child.get("name", "").strip(), child.get("abbreviation", "").strip(),
                         parent, level))
            visit(child, int(child.get("id")), level + 1)

    visit(root, NO_PARENT, 0)
    return _label_info(rows)


def label_info_from_brainglobe(structures):
    """``atlas_labels.pkl`` contents from a BrainGlobe ``structures.json``
    list, leaving out its added root."""
    by_id = {int(s["id"]): s for s in structures}
    roots = {int(s["id"]) for s in structures if len(s["structure_id_path"]) == 1}
    children = {}
    for s in structures:
        path = [int(v) for v in s["structure_id_path"]]
        if len(path) > 1:
            children.setdefault(path[-2], []).append(path[-1])
    rows = []

    def visit(parent, level):
        for child in children.get(parent, []):
            s = by_id[child]
            rows.append((child, [int(v) for v in s["rgb_triplet"]], s["name"].strip(),
                         s["acronym"].strip(), NO_PARENT if parent in roots else parent, level))
            visit(child, level + 1)

    for root in sorted(roots):
        visit(root, 0)
    return _label_info(rows)


def _label_info(rows):
    if not rows:
        raise ValueError("The region hierarchy lists no regions.")
    ids = [row[0] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("The region hierarchy repeats a region.")
    return {
        "index": np.array(ids, dtype=np.int64),
        "color": np.array([row[1] for row in rows], dtype=np.int64),
        "label": [row[2] for row in rows],
        "abbrev": np.array([row[3] for row in rows]),
        "parent": np.array([row[4] for row in rows], dtype=np.int64),
        "level_indicator": np.array([row[5] for row in rows], dtype=np.int64),
    }


# ----------------------------------------------------------- preparation
def _members(names, wanted):
    """Map each wanted base name to the one archive member that ends with it."""
    found = {}
    for name in names:
        base = name.replace("\\", "/").rsplit("/", 1)[-1]
        if base in wanted:
            if base in found:
                raise ValueError("The archive holds {} twice.".format(base))
            found[base] = name
    missing = sorted(set(wanted) - set(found))
    if missing:
        raise ValueError("The archive lacks {}.".format(", ".join(missing)))
    return found


def prepare_waxholm(folder):
    """Unpack the WHS annotation and write ``atlas_labels.pkl`` from its hierarchy."""
    archive = os.path.join(folder, WAXHOLM.files[0].local)
    nii, ilf = WAXHOLM.annotation, "WHS_SD_rat_atlas_v4.01_labels.ilf"
    with zipfile.ZipFile(archive) as bundle:
        members = _members(bundle.namelist(), {nii, ilf})
        for base, name in members.items():
            _write_atomically(os.path.join(folder, base), bundle.read(name))
    write_cache_pickle(os.path.join(folder, "atlas_labels.pkl"),
                       label_info_from_ilf(os.path.join(folder, ilf)))


def brainglobe_to_whs(volume, whs_shape=None):
    """A BrainGlobe ``asr`` volume of WHS (1024 x 512 x 512) in WHS file order.

    BrainGlobe stores the axes anterior-to-posterior, superior-to-inferior,
    right-to-left; WHS files store x towards the right, y towards anterior
    and z towards superior (RAS). Verified on the v4.01
    annotation: the converted SWC annotation equals the WHS one wherever it
    is labelled.
    """
    x, y, z = whs_shape or WHS_SHAPE
    volume = np.asarray(volume)
    if volume.shape != (y, z, x):
        raise ValueError("Expected a {} x {} x {} volume, got {}.".format(
            y, z, x, " x ".join(map(str, volume.shape))))
    return np.ascontiguousarray(np.transpose(volume, (2, 0, 1))[:, ::-1, ::-1])


def prepare_swc_female_rat(folder):
    """Convert the BrainGlobe package into WHS-ordered NIfTI files and labels."""
    import nibabel as nib
    import tifffile

    archive = os.path.join(folder, SWC_FEMALE_RAT.files[0].local)
    wanted = {"reference.tiff", "annotation.tiff", "structures.json", "metadata.json"}
    with tarfile.open(archive, "r:gz") as bundle:
        regular = [m for m in bundle.getmembers() if m.isfile()]
        members = _members([m.name for m in regular], wanted)

        def read(base):
            return bundle.extractfile(members[base]).read()

        metadata = json.loads(read("metadata.json"))
        if metadata.get("orientation") != "asr" or \
                [float(v) for v in metadata.get("resolution", [])] != [39.0] * 3:
            raise ValueError("The SWC package is not the 39 um Waxholm Space version.")
        structures = json.loads(read("structures.json"))
        template = brainglobe_to_whs(tifffile.imread(_bytes_file(read("reference.tiff"))))
        annotation = brainglobe_to_whs(tifffile.imread(_bytes_file(read("annotation.tiff"))))
    affine = np.diag([WHS_VOXEL_UM / 1000.0] * 3 + [1.0])
    for name, data, dtype in ((SWC_FEMALE_RAT.template, template, np.uint16),
                              (SWC_FEMALE_RAT.annotation, annotation, np.uint16)):
        if data.max() > np.iinfo(dtype).max:
            raise ValueError("Values in {} exceed the stored range.".format(name))
        path = os.path.join(folder, name)
        temporary = path + ".partial.nii.gz"
        nib.save(nib.Nifti1Image(data.astype(dtype), affine), temporary)
        os.replace(temporary, path)
    write_cache_pickle(os.path.join(folder, "atlas_labels.pkl"),
                       label_info_from_brainglobe(structures))


PREPARE = {"waxholm": prepare_waxholm, "swc_female_rat": prepare_swc_female_rat}


def _bytes_file(data):
    import io

    return io.BytesIO(data)


def _write_atomically(path, data):
    temporary = path + ".partial"
    with open(temporary, "wb") as stream:
        stream.write(data)
    os.replace(temporary, path)
