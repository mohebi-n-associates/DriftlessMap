# What’s New in HERBS

This cumulative release history is maintained as a single document. New
releases are added at the top; earlier release notes remain below them.

## HERBS 1.0.3

Release date: 25 July 2026

HERBS 1.0.3 adds estimated stereotaxic reporting for recognized Allen CCFv3
atlases and fixes atlas interaction at exact image boundaries.

### Highlights

- Shows a concise live report with estimated Bregma AP/ML and depth from the
  visible brain surface.
- Prefills the Allen downloader with the nearest estimated Bregma voxel for
  the selected 10, 25, or 50 µm resolution.
- Keeps the raw Allen voxel and affine DV estimate out of the live status line
  while preserving them in reconstruction exports.
- Uses Left and Right Arrow to move one slice backward or forward in the
  focused coronal, sagittal, or horizontal atlas view.
- Adds the estimated coordinates and transform metadata to probe
  reconstruction exports without replacing existing coordinate fields.
- Prevents hover and click events at the right or bottom image edge from
  producing an out-of-bounds `IndexError`.
- Corrects horizontal slice index conversion at the volume boundary.

### Estimated Allen stereotaxic coordinates

For recognized Allen CCFv3 2017 volumes, HERBS centers the source coordinates
at `(5400, 440, 5700)` µm in `(AP, DV, ML)`, applies a 5° AP–DV rotation with
the anterior CCF tilted ventrally, scales the rotated DV coordinate by
`0.9434`, and negates AP so positive AP means anterior.

The conversion is deliberately labeled **estimated**. The
[Allen community discussion](https://community.brain-map.org/t/how-to-transform-ccf-x-y-z-coordinates-into-stereotactic-coordinates/1858)
states that the Bregma position, tilt, and scale are estimates with biological
variance. Allen also explains that the
[CCF has no single ground-truth Bregma](https://community.brain-map.org/t/why-doesnt-the-3d-mouse-brain-atlas-have-bregma-coordinates/158)
because it is an ex-cranio average of many fixed brains.

Interactive reports now show only estimated Bregma AP, estimated Bregma ML,
and positive depth measured from the brain surface. The raw Allen voxel and
affine DV estimate are omitted from the live status line to keep it readable.
Probe reconstruction exports retain the original HERBS and Allen CCF
coordinates, add `estimated_stereotaxic_bregma_mm`, and embed the transform
parameters and targeting caveat. Custom atlases continue using their configured
Bregma without the Allen-specific conversion.

### Allen downloader defaults

The downloader labels its three Bregma fields as `(AP, DV, ML)` and fills them
with the nearest source-atlas voxel to the estimated CCF location:

| Resolution | AP | DV | ML |
| --- | ---: | ---: | ---: |
| 10 µm | 540 | 44 | 570 |
| 25 µm | 216 | 18 | 228 |
| 50 µm | 108 | 9 | 114 |

Changing the selected resolution updates all three defaults. The 25 and 50 µm
DV values are rounded to the nearest available voxel.

These defaults establish the coordinate origin in the processed HERBS atlas.
They do not replace the estimated stereotaxic transform, which additionally
applies the 5° AP–DV rotation and `0.9434` DV scale.

### Atlas keyboard navigation

After clicking a coronal, sagittal, or horizontal atlas image, press Left Arrow
for the previous slice or Right Arrow for the next slice. In the four-window
layout, the shortcut advances only the atlas plane that has focus. Arrow-key
editing in text and numeric fields is unaffected.

### Atlas boundary handling

Mouse hover and click positions are checked against the displayed slice before
HERBS reads atlas intensity or label data. Qt may report the exact right or
bottom boundary during pointer movement; those coordinates lie outside
NumPy’s valid zero-based index range and are now ignored.

The horizontal view now consistently uses `size - 1 - index` when translating
between displayed slices and volume coordinates, avoiding an off-by-one result
at the edge of the atlas.

### Upgrade notes

Install or update HERBS from the repository:

```bash
conda activate HERBS
git pull
python -m pip install . --upgrade
```

Restart HERBS after upgrading so the new package version and coordinate
reporting code are loaded.

---

## HERBS 1.0.2

Release date: 25 July 2026

HERBS 1.0.2 is a maintenance release focused on reliable Allen Mouse Brain
Atlas setup, particularly for the 10 µm CCFv3 2017 atlas.

### Highlights

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

### Allen mesh downloads

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

### 10 µm atlas performance

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

### Allen label hierarchy

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

### Interface defaults

The histology image dialog now opens with TIFF (`.tif` and `.tiff`) as its
default file filter. CZI, JPEG, PNG, and BMP remain available.

New layers now use the **Overlay** composition mode by default. Composition
modes restored from saved projects remain unchanged.

### Python launcher

The documented Python API is now:

```python
import herbs
herbs.run()
```

The `herbs` terminal command and `python -m herbs` use the same launcher.
Existing scripts that call `herbs.run_herbs()` continue to work because the old
name remains an alias.

### Upgrade notes

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

---

## HERBS 1.0.1

Release date: 25 July 2026

HERBS 1.0.1 is a maintenance release focused on reliable Allen Mouse Brain
Atlas setup, particularly for the 10 µm CCFv3 2017 atlas.

### Highlights

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

### Allen mesh downloads

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

### Allen label hierarchy

The Allen root structure has no parent, so its `parent_structure_id` field is
empty in the structure table. HERBS now maps that one missing parent to `0`
before converting the parent column to integers. This removes the following
warning without changing the hierarchy:

```text
RuntimeWarning: invalid value encountered in cast
```

### Upgrade notes

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

---

## HERBS 1.0.0

HERBS 1.0 moves the desktop application to the current Python and Qt
ecosystem.

### Highlights

- Supports Python 3.10 through Python 3.14.
- Migrates the user interface from PyQt5 to PyQt6.
- Updates pyqtgraph to 0.14 and supports NumPy 2 and OpenCV 5.
- Replaces the unmaintained QtRangeSlider package with the Python 3.14-ready
  `superqt` range slider.
- Uses modern `pyproject.toml` package metadata and declares a `herbs` command.
- Keeps application imports lightweight so importing `herbs` does not start or
  eagerly load the GUI.

### CZI support

Zeiss CZI reading is now an optional installation extra:

```bash
python -m pip install ".[czi]"
```

The upstream `aicspylibczi` project currently provides wheels through Python
3.13. Use Python 3.13 when CZI support is required; the rest of HERBS supports
Python 3.14.

### Upgrade notes

Create a fresh environment for HERBS 1.0. Environments containing PyQt5 or
pyqtgraph 0.12 should not be upgraded in place because Qt binding selection can
be affected by packages already imported into a Python process.

---

## HERBS 0.2.8.1

Release date: 18 July 2026

HERBS 0.2.8.1 is a reliability, security, and maintainability release. It does not intentionally change the core registration workflow. Instead, it corrects coordinate-processing errors, prevents several GUI crashes, makes file and network operations safer, improves installation behavior, and adds automated regression coverage.

### Highlights

- Correct and consistent atlas, segmentation, boundary, Bregma, and probe coordinates.
- Self-contained merged-probe exports with complete atlas and contact-coordinate metadata.
- A safe, versioned HERBS archive format for user-created project and data files.
- Deterministic image and atlas loading with clearer failure handling.
- Atomic, HTTPS-only atlas downloads that do not replace valid files with partial data.
- Fixed label, layer, cell-detection, probe-eraser, and slice-registration behavior.
- Supported packaging for Python 3.8.10 through 3.11, including a console launcher.
- Package resources and preferences no longer depend on or modify the process working directory.
- 58 regression tests plus continuous integration across all supported Python versions.

### Atlas and Coordinate Correctness

### Custom-atlas transforms

Custom atlas intensity data, segmentation labels, and Bregma coordinates now receive the same axis flips and transposition. Previously, an atlas could appear correctly oriented while its labels or Bregma remained in a different coordinate system, producing incorrect region and probe results.

An unspecified Bregma coordinate is now converted to the midpoint of the original source volume before the volume transform is applied. This preserves the intended anatomical location after axes are reordered or reversed.

### Probe-coordinate bounds

Probe insertion points, shank columns, and recording sites are now validated against every atlas dimension. Negative coordinates and coordinates equal to an axis size are rejected instead of being accepted by NumPy as wrapped or out-of-range indexes.

This prevents probes near an atlas edge from silently sampling the wrong anatomy or raising an indexing exception later in the calculation.

### Self-contained probe reconstruction

New merged-probe objects contain a versioned `reconstruction` block so the probe can be analyzed later without reopening the original HERBS project. It records:

- HERBS version, probe settings, site face, and contact-order definition.
- Atlas identifier, voxel resolution, HERBS and source-atlas shapes, the selected Bregma, and the complete invertible axis transform.
- The atlas label lookup used during reconstruction.
- Insertion and geometric-tip positions in HERBS voxels, Bregma-relative micrometres, source-atlas voxels, and source-atlas micrometres.
- An always-unmerged contact table with stable flat indexes, column and within-column indexes, probe-local positions, distance from the geometric tip and insertion point, anatomical structure IDs and names, and both HERBS and source-atlas coordinates.

For a standard Allen CCFv3 2017 atlas, the source coordinate fields are also exposed explicitly as `allen_ccf_vox` and `allen_ccf_um` in `[AP, DV, LR]` order. Contact ordering is column-major, and `index_in_column == 0` identifies the contact nearest the geometric tip. This ordering describes the HERBS geometric model; it intentionally does not claim to be a Neuropixels acquisition-channel or physical-electrode ID.

The reconstruction table retains every modeled contact even when the display option to merge sites at the same depth is enabled. The full atlas intensity and annotation volumes are not duplicated into every probe file; the exact coordinate transform, label lookup, and annotation sampled at every contact are included because those are sufficient to reconstruct the exported probe coordinates and regions.

### Allen atlas boundaries

Processed sagittal, coronal, and horizontal Allen boundary volumes are now returned under the keys expected by the atlas viewer. A shape check ensures the three boundary volumes remain aligned.

### Atlas loading and processing

Atlas loaders now have deterministic success and failure contracts:

- Data fields are initialized before reading begins.
- Core file failures cannot be overwritten by a later successful optional-boundary read.
- Raw-processing functions always return the documented six-item result.
- Atlas, segmentation, mask, and boundary shapes are validated.
- Both three-dimensional masks and four-dimensional masks with one trailing channel are supported.
- Constant-valued atlas volumes normalize to zero without producing `NaN` values.
- A failed worker remains in a failure state and reports the actual error.

Custom-atlas mesh downsampling factors must now be integers of at least 2 and must fit all three volume dimensions. Processing stops after reporting an invalid factor rather than continuing with bad state. The factor input also no longer connects a no-argument Qt signal to a slot that requires text.

### Atlas slices at Bregma

A registered slice at `0 mm` from Bregma is now considered valid. The previous readiness check treated zero as missing data, which prevented processing of the anatomically central slice. Width, height, distance, and the two-dimensional Bregma point are now validated independently, with positive dimensions and finite coordinates required.

### Safer HERBS Files

### New archive format

New user-created files are saved as versioned HERBS archives instead of general-purpose Python pickles. The following formats use the new archive implementation:

- Projects: `.herbs`
- Layers: `.herbslayer`
- Objects: `.herbsobj`
- Atlas slices: `.herbsslice`
- Triangulation data: `.herbstri`

Each archive contains a JSON manifest and NumPy arrays written with pickling disabled. The loader verifies the format name, schema version, payload kind, required fields, referenced array entries, duplicate archive members, manifest size, and total expanded size.

Writes are atomic: HERBS writes a temporary file beside the destination and replaces the destination only after the complete archive has been created. A failed save therefore does not destroy the last valid file.

### Legacy-file compatibility

Legacy `.pkl` files can still be opened when they contain the inert built-in and NumPy data types used by older HERBS saves. They are read with a restricted unpickler that rejects executable or unsupported Python globals.

The restricted reader recognizes the inert `_frombuffer` array constructor used by NumPy 2 highest-protocol pickles, under both the historical `numpy.core` and current `numpy._core` module names. Atlas label caches created with NumPy 2 therefore remain readable on NumPy 1 as well as NumPy 2, without weakening the rejection of executable pickle globals.

After opening a legacy file, save it again in the corresponding new HERBS format. Some legacy files containing arbitrary custom Python or Qt objects will now be rejected intentionally rather than executed.

The safe archive format applies to user-created project, layer, object, slice, and triangulation files. Internal atlas preprocessing caches remain implementation-specific and should only be obtained from trusted atlas processing or download sources.

### Consistent loading results

Invalid, missing, corrupt, or unsupported HERBS files now return the same `(data, error)` result shape. Callers can report a useful error without failing while unpacking a different return type.

### Image Loading

Image readers now expose a consistent data and metadata contract:

- An 8-bit grayscale TIFF is treated as one grayscale channel, not RGB.
- RGB TIFF data and multi-page grayscale stacks are distinguished using TIFF axes.
- Channel-axis TIFF data is moved into the channel position expected by the viewer.
- Images with more than four channels are rejected before fixed-size GUI channel controls are indexed.
- Multi-series or unsupported TIFF data returns a defined error state.
- Folder-based image scenes are filtered and sorted deterministically.
- Folder readers populate scene count, scale, channel, pixel-type, and filename metadata.
- CZI `gray8` and non-mosaic images use the same normalized contracts.
- Image-stack opacity is applied consistently.

These changes prevent silent channel swaps, incorrect color controls, uninitialized attributes, and failures that depended on filesystem ordering.

### GUI and Tool Fixes

### Labels

- Label-tree construction uses the supported PyQt5 header-resize API.
- Label colors retain the `#` required for current pyqtgraph color parsing.
- Default colors are stored as `QColor` values, so Reset Colors no longer passes an incompatible string to the color setter.
- Lookup-table size is based on the largest label ID, including label tables whose ordering or parent structure is unusual.
- Empty label tables fail with a clear error.

### Layers

- Saved non-contiguous selections are restored using their actual indexes rather than selecting the first *n* layers.
- Empty saved layer lists no longer index a missing final widget.
- Saved property-list lengths and unique layer links are validated.
- Add Layer supplies the required color argument.
- The toolbar Delete button removes the selected layers instead of treating its Qt `checked` boolean as a layer ID.
- Add and Delete controls are included in the layer-control layout.
- Opacity and blend controls are restored for a single selected layer.

### Cell detector and probe eraser

Cell detection no longer references an undefined mode variable. Grayscale and RGB inputs select a defined detection channel, contour data is normalized safely, and 16-bit inputs are handled without overflowing the expected processing range.

The probe eraser now returns its result consistently instead of reaching a path with no return value.

### Restored layer validation

Loaded pixel layers must match the current image dimensions and include all required metadata. Negative or out-of-range processing levels and mismatched declared sizes are rejected before display. Invalid layers abort the operation instead of partially modifying the image view.

### Atlas Downloads

Atlas downloads now share one hardened implementation:

- Only HTTPS URLs and HTTPS redirects are accepted.
- Requests have connection and read timeouts.
- HTTP error statuses are reported.
- Content length is checked when the server provides it.
- SHA-256 verification is performed when an expected digest is supplied.
- Empty, cancelled, incomplete, or failed downloads are removed.
- Existing destination files are replaced atomically only after verification.
- Progress reaches 100% only after the final file is in place.

Downloader worker threads are retained for their full lifetime, errors propagate back to the dialog, and the GUI no longer performs a blocking preliminary `HEAD` request. This prevents partial atlas files, silent background-thread failures, and avoidable interface freezes.

### Installation and Runtime Behavior

### Supported versions and dependencies

Package metadata now consistently supports Python `>=3.8.10,<3.12`, and PyQt5 5.15.5 or newer is installed for every supported Python version, including Python 3.11.

NumPy is constrained below version 2 while HERBS remains on PyQtGraph 0.12.3. That PyQtGraph release calls the deprecated `np.product` alias during affine atlas slicing; NumPy 2 removed the alias, causing every atlas-rotation update to fail. OpenCV is correspondingly constrained below 4.12 because OpenCV 4.12 and later require NumPy 2 on supported HERBS Python versions. These compatible bounds allow the installer to select NumPy 1.26 and OpenCV 4.11 instead of producing an internally inconsistent environment.

The unused `h5py` and `tables` dependencies were removed. HERBS did not import either library, while `tables` could force an unnecessary native HDF5 build and prevent installation on otherwise supported systems.

The package, installer metadata, and About dialog now obtain `0.2.8.1` from one canonical version value. Project and issue links point to the current `mohebi-n-associates/HERBS` repository.

### Launch options

HERBS can be launched using any of the following:

```bash
herbs
python -m herbs
```

```python
import herbs
herbs.run_herbs()
```

Importing `herbs` no longer imports the complete GUI and CZI stack immediately. The heavier GUI imports occur when the application is launched or the CZI reader is requested.

### Resources and preferences

Icons, stylesheets, UI files, and bundled data now resolve relative to the installed HERBS package. The launcher no longer changes the caller’s process-wide working directory, so relative paths in notebooks, scripts, and embedding applications continue to work normally.

Relative `url(icons/...)` references embedded inside Qt stylesheets are now rewritten to absolute package-resource paths when each stylesheet is loaded. This prevents missing spinbox arrows, splitter dots, tree icons, and combo-box icons when HERBS is launched from a home directory, notebook, or another working directory.

The last selected atlas path is stored atomically in the user configuration directory instead of `herbs/data/atlas_path.txt` inside the installation:

- Windows: `%APPDATA%\HERBS\settings.json`
- macOS: `~/Library/Application Support/HERBS/settings.json`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/HERBS/settings.json`

`HERBS_CONFIG_DIR` can override the configuration directory. Because the old package-local preference was removed, HERBS may ask you to select the atlas folder once after upgrading.

### Maintainability and Verification

Focused modules were extracted for atlas transforms, coordinate checks, slice and layer validation, persistence, download handling, cell-channel selection, package resources, and user settings. This reduces the amount of safety-critical logic embedded directly in the main GUI controller and makes it independently testable.

Version 0.2.8.1 includes:

- 58 automated regression tests.
- Headless GUI construction and resource-path smoke testing.
- Python source compilation checks.
- Targeted Ruff checks for syntax errors and undefined names.
- Wheel-build and package-content verification.
- GitHub Actions coverage for Python 3.8, 3.9, 3.10, and 3.11.

### Upgrade Notes

1. Pull the latest source and reinstall HERBS:

   ```bash
   git pull
   python -m pip install . --upgrade
   ```

2. If prompted, select your atlas folder once so it can be saved in the new user configuration file.

3. Open important legacy `.pkl` project or data files and save them in the new HERBS format.

   A previously merged probe does not contain the new atlas reconstruction metadata. Load its project with the same atlas and merge the probe pieces again before exporting a new `.herbsobj`.

4. If you automate HERBS file handling, update filters and scripts to recognize the new extensions listed above.

5. Use Python 3.8.10 through 3.11. Python 3.12 and later are not declared supported by this release.

### Implementation References

The changes were kept as separate issue-level commits:

| Commit | Change |
| --- | --- |
| `3241b11` | Fix custom atlas coordinate transforms |
| `879b17f` | Reject probe coordinates outside atlas bounds |
| `4583fab` | Expose processed Allen atlas boundaries |
| `4f54836` | Validate restored image layers before display |
| `4071edd` | Return consistent errors for invalid HERBS files |
| `01fb3ba` | Replace executable user files with safe archives |
| `01e56a2` | Make atlas loading failures deterministic |
| `4bc5a66` | Normalize image reader contracts and channel handling |
| `8fe7c3a` | Prevent cell detector and probe eraser crashes |
| `b2ecbaf` | Make atlas downloads atomic and failure-aware |
| `56994ec` | Fix label color reset state |
| `3912cc5` | Restore saved layer selections exactly |
| `cb1765e` | Allow atlas slices at Bregma |
| `db374d4` | Validate custom atlas downsampling factors |
| `9d2f8e7` | Align Python and PyQt package metadata |
| `4828645` | Keep runtime state outside the package tree |
| `99886a2` | Use one canonical HERBS version |
| `c0bc2d9` | Add regression test CI |
| `f6d20ff` | Remove unused HDF5 runtime dependencies |
| `00b5368` | Bump HERBS version to 0.2.8.1 |
