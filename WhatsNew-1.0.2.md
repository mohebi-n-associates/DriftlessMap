# What’s New in HERBS 1.0.2

Release date: 25 July 2026

HERBS 1.0.2 is a maintenance release focused on reliable Allen Mouse Brain
Atlas setup, particularly for the 10 µm CCFv3 2017 atlas.

## Highlights

- Prevents the 10 µm mesh downloader from appearing frozen while it discovers
  atlas structure IDs.
- Scans compressed annotation data in bounded chunks instead of loading and
  sorting the entire 1.2-billion-voxel volume for label discovery.
- Reports progress while scanning the annotation and while downloading each
  mesh.
- Displays the current processing phase and item counts during mesh conversion,
  large cache writes, fallback mesh generation, and boundary construction.
- Resumes mesh setup by preserving and skipping mesh files that were already
  downloaded successfully.
- Handles the Allen hierarchy root's intentionally missing parent ID without a
  NumPy invalid-cast warning.
- Loads atlas label caches created with pandas 3 string arrays while preserving
  the restricted legacy-file security boundary.
- Makes TIFF the default histology image type in the open dialog.
- Makes Overlay the default composition mode for newly created layers.
- Adds `herbs.run()` as the primary Python launcher while retaining
  `herbs.run_herbs()` as a compatibility alias.
- Makes 10 µm slice navigation responsive by compacting atlas volumes,
  replacing sparse Allen-ID color tables with a compact display map, and
  coalescing rapid slider updates.

## Allen mesh downloads

The previous mesh-download worker loaded the complete annotation volume and
called `numpy.unique` before creating the mesh folder or updating the progress
bar. At 10 µm resolution, the annotation contains 1,203,840,000 voxels. The
operation could consume several gigabytes of memory and spend a long time
sorting while the user interface continued to show 0%.

HERBS now scans the compressed NRRD annotation incrementally. Only a small
chunk is decompressed and inspected at a time, while the set of discovered
structure IDs remains in memory. The same bounded scan is used during Allen
atlas processing to avoid the previous whole-volume sort.

The mesh progress bar now covers both phases:

1. Scanning atlas structure IDs.
2. Downloading the required structure meshes.

The status area also displays the current mesh number and Allen structure ID.
If setup is restarted, existing non-empty `.obj` files are retained and
skipped. Atlas intensity and annotation files do not need to be downloaded
again.

During processing, the status area now names long-running operations instead of
leaving the percentage as the only feedback. Mesh conversion and packing show
item counts, fallback mesh generation reports its internal phase, and sagittal,
coronal, and horizontal boundary construction report their current slice.
Large cache writes are identified explicitly because their underlying pickle
operation does not expose byte-level progress.

## 10 µm atlas performance

The Allen atlas uses sparse structure IDs, including IDs as large as
614,454,277. The previous label display allocated color tables up to the
largest ID, even though the atlas contains only about 1,300 described
structures. Those dense tables could consume more than 11 GB by themselves.

HERBS now maps original Allen IDs to compact display-only indexes. Original
structure IDs remain unchanged for region descriptions, probe reconstruction,
and 3D meshes.

Atlas intensities now use `float32`, segmentation IDs use `int32`, and boundary
data uses one-byte values. Existing caches are converted to these runtime
formats while they load; newly processed caches are saved in the compact
formats. The GUI also avoids loading the three full boundary volumes and
computes the currently displayed boundary only when **Show Boundary** is
enabled.

While a slice slider is dragged, rapid intermediate positions are coalesced
over a short interval. The page number follows the pointer immediately and the
latest requested slice is always rendered when dragging pauses or ends.
Single-step buttons and programmatic page changes remain immediate.

## Allen label hierarchy

The Allen root structure has no parent, so its `parent_structure_id` field is
empty in the structure table. HERBS now maps that one missing parent to `0`
before converting the parent column to integers. This removes the following
warning without changing the hierarchy:

```text
RuntimeWarning: invalid value encountered in cast
```

New Allen and custom-atlas label caches now store label, abbreviation, color,
and structure-path fields as plain NumPy arrays. This prevents internal pandas
array implementations from leaking into the cache format.

Atlas label caches already created with pandas 3 may contain serialized
`StringArray` fields. The restricted legacy loader now recognizes only the
specific pandas string-array reconstruction records required by those caches,
maps them to inert local stand-ins, validates their state, and returns plain
NumPy string arrays. It does not invoke pandas' serialized reconstruction
function or permit arbitrary pandas globals.

## Interface defaults

The histology image dialog now opens with TIFF (`.tif` and `.tiff`) as its
default file filter. CZI, JPEG, PNG, and BMP remain available.

New layers now use the **Overlay** composition mode by default. Composition
modes restored from saved projects remain unchanged.

## Python launcher

The documented Python API is now:

```python
import herbs
herbs.run()
```

The `herbs` terminal command and `python -m herbs` use the same launcher.
Existing scripts that call `herbs.run_herbs()` continue to work because the old
name remains an alias.

## Upgrade notes

Install or update HERBS from the repository:

```bash
conda activate HERBS
git pull
python -m pip install . --upgrade
```

An interrupted atlas setup can reuse its existing folder. Open the Allen atlas
downloader, choose **Download Meshes**, and select the folder containing
`average_template_10.nrrd` and `annotation_10.nrrd`. HERBS will scan the
annotation and continue with any missing meshes.
