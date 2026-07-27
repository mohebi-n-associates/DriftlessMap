# DriftlessMap User Manual

This manual applies to **DriftlessMap 1.1.0**.

DriftlessMap - Histological E-data Registration in Brain Space - is a desktop
application for aligning rodent histology with a reference atlas, reconstructing
experimental objects in atlas space, and inspecting the result in two and three
dimensions. It supports pre-surgical probe planning, post-surgical probe
reconstruction, virus or tracer expression, cell locations, tissue contours,
and user-drawn lines or areas of interest.

The original [HERBS Cookbook](CookBook.pdf) remains useful as an illustrated
introduction. This manual follows its task-oriented approach but describes the
current Python 3.10-3.14, PyQt6, safe-file, mesh-validation, coordinate-reporting,
and CSV-export behavior.

The following historical interface image predates the DriftlessMap rebrand;
the workflows shown remain recognizable.

![Historical HERBS main window](herbs/herbs.png)

## Contents

1. [What DriftlessMap does](#1-what-driftlessmap-does)
2. [Installation and launching](#2-installation-and-launching)
3. [Concepts and coordinate systems](#3-concepts-and-coordinate-systems)
4. [The DriftlessMap interface](#4-the-driftlessmap-interface)
5. [Downloading, processing, and loading atlases](#5-downloading-processing-and-loading-atlases)
6. [Processing a custom volume atlas](#6-processing-a-custom-volume-atlas)
7. [Loading and preparing histological images](#7-loading-and-preparing-histological-images)
8. [Registering histology to an atlas](#8-registering-histology-to-an-atlas)
9. [Working with layers](#9-working-with-layers)
10. [Working with object pieces and merged objects](#10-working-with-object-pieces-and-merged-objects)
11. [Pre-surgical probe planning](#11-pre-surgical-probe-planning)
12. [Post-surgical probe reconstruction](#12-post-surgical-probe-reconstruction)
13. [Virus, tracer, lesion, and expression registration](#13-virus-tracer-lesion-and-expression-registration)
14. [Cell registration and counting](#14-cell-registration-and-counting)
15. [Drawings, regions of interest, contours, and measurements](#15-drawings-regions-of-interest-contours-and-measurements)
16. [External point data](#16-external-point-data)
17. [Using a two-dimensional slice atlas](#17-using-a-two-dimensional-slice-atlas)
18. [Saving, loading, and exporting](#18-saving-loading-and-exporting)
19. [Menu and shortcut reference](#19-menu-and-shortcut-reference)
20. [Troubleshooting](#20-troubleshooting)
21. [Python API and development](#21-python-api-and-development)
22. [Reproducibility checklist](#22-reproducibility-checklist)

## 1. What DriftlessMap does

DriftlessMap combines four related activities in one application:

- **Plan:** select a target in a volume atlas and calculate a prospective probe
  trajectory before surgery.
- **Prepare:** load, orient, crop, recolor, and mask a histological image.
- **Register:** pair landmarks in a histological section and atlas slice, then
  use a validated piecewise-affine mesh to transform images and experimental
  annotations between them.
- **Analyze and visualize:** convert annotations into three-dimensional objects,
  assign atlas regions, inspect measurements, compare probes, and export data.

DriftlessMap includes workflows for the Waxholm Space Sprague Dawley rat atlas and
Allen Mouse CCFv3 2017. It can also process another three-dimensional atlas when
the user supplies an intensity volume, matching segmentation volume, label
table, voxel size, and source-axis directions.

### 1.1 Volume-atlas and slice-atlas workflows

A **volume atlas** is a three-dimensional template and annotation volume. It
supports arbitrary coronal, sagittal, and horizontal sections, limited plane
rotation, atlas-region lookup, three-dimensional meshes, probe reconstruction,
and object analysis.

A **slice atlas** is a calibrated image of one atlas plate. It is useful when a
volume atlas is unavailable, but it does not contain a three-dimensional label
volume. DriftlessMap can register a histological image to it and use its physical
scale, Bregma point, and ruler measurements. Volumetric object reconstruction
and region-aware probe merging are not available in this mode.

### 1.2 Pre-surgical and post-surgical work

The practical distinction is:

- With a volume atlas loaded and no histological image loaded, the Probe Marker
  creates a **pre-surgical plan**. A planned trajectory must contain exactly two
  points.
- With both a volume atlas and histological image loaded, probe points represent
  an observed track. After registration and transfer, DriftlessMap performs a
  **post-surgical reconstruction** from two or more points, potentially collected
  across several sections.

### 1.3 Layers versus objects

This distinction is central to DriftlessMap:

- A **layer** is editable two-dimensional working data in an atlas or histology
  window. Examples are `img-mask`, `img-probe`, `atlas-cells`, and
  `atlas-overlay`.
- An **object piece** is a three-dimensional sample created from the current
  atlas-layer data. It normally represents one section or one part of a longer
  experiment.
- A **merged object** combines related pieces. Merging calculates region
  assignments and the data used by information windows and 3D rendering.

Saving a layer, saving an object, and saving a project therefore serve different
purposes. See [Saving, loading, and exporting](#18-saving-loading-and-exporting).

## 2. Installation and launching

### 2.1 Requirements

DriftlessMap 1.1.0 requires:

- A 64-bit operating system and 64-bit Python 3.10 or newer.
- Python 3.10-3.14 for the core application.
- OpenGL-capable graphics for the 3D view.
- Enough memory for the selected atlas resolution and histology images.

Python 3.14 is recommended for a new core installation. Zeiss CZI support uses
the optional `aicspylibczi` dependency, whose available builds currently limit
the CZI environment to Python 3.10-3.13. Use Python 3.13 when CZI support is
needed.

### 2.2 Recommended Conda installation

DriftlessMap is currently installed from this repository rather than PyPI. Create an
isolated environment so Qt, NumPy, OpenCV, and OpenGL packages do not conflict
with unrelated software:

```bash
conda create --name DriftlessMap python=3.14 -y
conda activate DriftlessMap
python -m pip install --upgrade pip
git clone https://github.com/mohebi-n-associates/DriftlessMap.git
cd DriftlessMap
python -m pip install .
```

Use the following environment instead when opening CZI files is required:

```bash
conda create --name DriftlessMap-CZI python=3.13 -y
conda activate DriftlessMap-CZI
python -m pip install --upgrade pip
git clone https://github.com/mohebi-n-associates/DriftlessMap.git
cd DriftlessMap
python -m pip install ".[czi]"
```

If the repository was downloaded as a ZIP file, unzip it, open a terminal in
the directory containing `pyproject.toml`, and run the same `python -m pip
install .` command.

For source development, use an editable installation:

```bash
python -m pip install -e ".[test]"
```

### 2.3 Confirming the installation

Check that the selected Python and installed DriftlessMap refer to the intended
environment:

```bash
python --version
python -m pip --version
python -c "import driftlessmap; print(driftlessmap.__version__)"
```

The final command should print `1.1.0`.

### 2.4 Launching DriftlessMap

Any of the following launches the same GUI:

```bash
driftlessmap
```

```bash
python -m driftlessmap
```

```python
import driftlessmap

driftlessmap.run()
```

`driftlessmap.run_driftlessmap()` is retained as an alias for `driftlessmap.run()`.

Activate the environment again in each new terminal:

```bash
conda activate DriftlessMap
```

Use `DriftlessMap-CZI` instead if that is the environment you created.

### 2.5 Updating

From the cloned repository:

```bash
conda activate DriftlessMap
git pull
python -m pip install . --upgrade
```

Restart DriftlessMap after updating. Read [What’s New in DriftlessMap](WhatsNew.md) before
resuming an important project, particularly when probe reconstruction or
registration behavior has changed.

## 3. Concepts and coordinate systems

### 3.1 Pixels, voxels, and physical coordinates

- A **pixel** is a location in a two-dimensional image.
- A **voxel** is a location in a three-dimensional atlas.
- Physical distances are reported in micrometres (`um`) or millimetres (`mm`)
  using the atlas voxel size or the calibrated slice dimensions.

Histology clicks begin as pixels. Landmark registration maps them to an atlas
slice, and DriftlessMap then converts the registered two-dimensional location into a
three-dimensional atlas voxel.

### 3.2 DriftlessMap internal axes

DriftlessMap stores atlas-space points using these internal axes:

| Position | Axis | Positive direction |
| --- | --- | --- |
| 1 | LR/ML | Right |
| 2 | AP | Anterior |
| 3 | DV | Superior/dorsal |

Many user-facing reports label these values `(ML, AP, DV)`. Configured
Bregma-relative DV values in the internal data are positive dorsally. Some CSV
columns also provide `configured_DV_ventral_mm`, where the sign is inverted so
positive values point ventrally. Always read the column name rather than
assuming a DV convention.

The atlas viewer rearranges and sometimes reverses axes to display conventional
coronal, sagittal, and horizontal sections. Do not manually reinterpret a
display-window `(x, y)` coordinate as a native-atlas coordinate.

### 3.3 Source-atlas coordinates

Every processed volume atlas includes `atlas_axis_info.pkl`, which describes:

- The source volume shape.
- The transpose from source axes into DriftlessMap axes.
- Which source axes were reversed.
- The inverse transformation back to source-atlas voxels.

This metadata is used for external points, self-contained probe reconstruction,
drawing ROI reports, and CSV exports. If it is missing, reprocess the atlas;
do not guess a conversion.

### 3.4 Allen CCFv3 coordinates and estimated Bregma

Allen CCFv3 source voxels use `(AP, DV, ML)` order. DriftlessMap recognizes the
standard 10, 25, and 50 um CCFv3 2017 volumes from their shape, voxel size, and
axis transform. For recognized volumes, information windows and CSV exports
include:

- Raw Allen source voxels.
- Estimated AP and ML coordinates relative to Bregma.
- Depth measured from the local dorsal brain surface.
- An affine DV estimate that is explicitly marked as unsuitable for targeting.

The estimated transform uses a community-derived CCF Bregma location, sagittal
tilt, and DV scale. It is **not ground truth**. For surgical targeting, use
measured depth from the brain surface and validate the convention against the
experimental protocol.

The Allen downloader pre-fills the nearest source voxel to the current
estimated Bregma:

| Resolution | Estimated source voxel `(AP, DV, ML)` |
| --- | --- |
| 10 um | `(540, 44, 570)` |
| 25 um | `(216, 18, 228)` |
| 50 um | `(108, 9, 114)` |

Changing the resolution updates these defaults. If the fields are edited, record
the values used with the experiment.

### 3.5 Configured Bregma and brain-surface depth

For a non-Allen atlas, DriftlessMap reports coordinates relative to the Bregma voxel
stored during atlas processing. In the custom atlas processor, a zero in a
Bregma coordinate means “unspecified for this axis”; DriftlessMap substitutes the
midpoint of that source axis before applying flips and transposition.

Brain-surface depth is calculated locally from the atlas annotation mask. It is
different from the DV displacement relative to Bregma and from the total length
of an oblique probe.

## 4. The DriftlessMap interface

The application has five main areas:

1. **Menu bar:** file, editing, image, atlas, object, display, and help commands.
2. **Toolbar:** window layouts, drawing and selection tools, registration
   transforms, and context-specific options.
3. **Sidebar:** atlas, segmentation, image, layer, and object controllers.
4. **Plot windows:** atlas sections, histology, slice atlas, and 3D rendering.
5. **Status bar:** current operation, errors, hover coordinates, brain region,
   and coordinate reports.

### 4.1 Plot windows

The View menu and the first toolbar group can show:

- Coronal, sagittal, or horizontal volume-atlas window.
- Histological image only.
- 3D view only.
- Volume atlas plus histology.
- Slice atlas plus histology.
- Four volume-atlas windows: three orthogonal slices and 3D.
- A three-window layout used during atlas/histology/3D work.

The last layout is exposed by the toolbar even though it is not a separate View
menu item.

### 4.2 Sidebar tabs

Use the mouse or `Ctrl+1` through `Ctrl+5`:

#### Ctrl+1 - Atlasing Controller

- Choose coronal, sagittal, or horizontal display.
- Set atlas-label opacity.
- Toggle region boundaries.
- Set horizontal and vertical tilt for each section plane.
- Keep slice angles when changing planes.
- Turn linked crosshair navigation on or off.

Atlas rotation is intended to compensate for an oblique tissue plane. Check all
three views when using rotation; a plausible match in one plane can still be
anatomically wrong in 3D.

#### Ctrl+2 - Segmentation View Controller

- Expand the atlas hierarchy.
- Check a structure to display it and its descendants.
- Change a structure color.
- Reset label colors.
- Show selected structures in 3D.
- Choose `opaque`, `translucent`, or `additive` 3D composition.

#### Ctrl+3 - Image View Controller

- Choose CZI scene and loading scale.
- Load all CZI scenes.
- Move through pages in a grayscale TIFF stack.
- Adjust black and white points, gamma, linear mapping, or spline mapping.
- Enable or disable channels and change their display colors.

At least one image channel remains visible. Grayscale cell selection and
detection require exactly one visible channel.

#### Ctrl+4 - Layer View Controller

- Select one or more working layers.
- Toggle visibility or delete a layer.
- Set opacity.
- Set pixel composition to `Plus`, `Multiply`, `Overlay`, or `SourceOver`.
- Add a placeholder layer or delete the selected layers.

Composition affects blendable pixel layers. It does not change the underlying
scientific values.

#### Ctrl+5 - Object View Controller

- Select, show, recolor, rename, link, or delete object entries.
- Add current atlas annotations as pieces.
- Merge probe, virus, cell, drawing, or contour pieces.
- Unmerge a merged object.
- Open the information window.
- Locate a supported object in 2D.
- Compare linked probes.
- Set merged-object opacity, size/width, and 3D composition.

### 4.3 Toolbar tools

Only one of the main editing tools is active at a time. Selecting a tool reveals
its controls to the right.

| Tool | Purpose and important controls |
| --- | --- |
| Ruler | Two-point length measurement; color and line width. |
| Pencil | Draw an open line or closed area; color, width, and path type. |
| Eraser | Delete points or erase within the current editable layer; color and radius. |
| Polygon Lasso | Select an inside or outside region for cropping or deletion. |
| Magic Wand | Select pixels by tolerance; optionally clean the mask with rectangular, elliptical, or cross-shaped morphology; convert the mask to virus or contour data. |
| Probe Marker | Mark a probe plan or observed track; choose probe type, site face, multi-shank mode, contact display, and color. |
| Triangulation | Add paired registration landmarks; display the mesh, match boundary rectangles, set boundary-point count and color, and inspect mesh quality. |
| Cell Selector | Add cells manually or define a representative cell for blob detection; choose color and inspect counts. |

The transform actions are:

- **Transform to Atlas Slice Window:** warp histology into atlas-slice space.
- **Transform to Histological Image Window:** warp atlas data into histology
  space.
- **Accept and Transfer:** transfer the current probe, virus, cell, drawing, or
  contour annotations through the accepted registration.

Clicking an active transform action again removes its overlay so landmarks can
be edited.

### 4.4 Status bar

Watch the status bar throughout a workflow. It reports more than completion:
invalid inputs, unmatched landmarks, unavailable tools, current pixel
coordinates, atlas voxels, region hierarchy, configured Bregma coordinates,
estimated Allen AP/ML coordinates, and surface depth can all appear there.

## 5. Downloading, processing, and loading atlases

### 5.1 Atlas storage rules

Use one dedicated folder per processed atlas.

Do not:

- Store an atlas inside the DriftlessMap source or installed package directory.
- Put two atlas resolutions or species in the same folder.
- Move, rename, or partially copy a processed atlas folder during a project.
- Edit the generated `.pkl` caches manually.

Atlas processing creates large implementation-specific caches and meshes. Keep
the original downloaded files and processed output together, and back up the
entire folder.

### 5.2 Waxholm rat atlas

1. Select **Atlas > Download Waxholm Rat Atlas**.
2. Click **Download** and choose an empty destination folder.
3. Wait for the label, T2* volume, mask, and annotation downloads to finish.
4. Click **Process**. If DriftlessMap was restarted after downloading, select the
   folder when prompted.
5. Leave the dialog open until processing completes.
6. Load the folder with **File > Load Atlas**.

The dialog estimates 40-60 minutes for processing, but the actual duration
depends on CPU, storage, and memory. The standard workflow uses a voxel size of
39.0625 um and the packaged Waxholm label information.

Downloads are written atomically and use HTTPS. A failed or incomplete download
does not replace an existing valid file.

### 5.3 Allen mouse atlas

1. Select **Atlas > Download Allen Mice Atlas**.
2. Choose 10, 25, or 50 um resolution.
3. Review the estimated Bregma source voxel `(AP, DV, ML)`.
4. Click **Download**, choose a dedicated destination folder, and wait for the
   template and annotation downloads.
5. Click **Download Meshes** and wait for all structure meshes.
6. Click **Process**. If the dialog was reopened, select the folder containing
   the raw volume, annotation, label table, and complete downloaded meshes.
7. Load the processed folder with **File > Load Atlas**.

Resolution trade-offs:

- **10 um:** finest sampling and largest memory/storage cost.
- **25 um:** a practical balance for many workflows.
- **50 um:** fastest and smallest, with coarser spatial sampling.

Processing must complete for the selected resolution. Do not combine a 25 um
annotation with a 10 um template or meshes from another folder.

### 5.4 Loading and navigating a processed volume atlas

Use **File > Load Atlas** and select the folder, not an individual file. The
toolbar’s atlas icon loads the previously selected folder from user
preferences. If that folder was moved, DriftlessMap asks for a new location.

After loading:

1. Choose the section plane in the Atlasing Controller.
2. Use the page slider or its slow/fast arrow buttons.
3. When a slice window has keyboard focus, the Left and Right arrow keys move
   by one page.
4. Adjust atlas intensity with the vertical LUT control beside the image.
5. Toggle **Show Boundary** for label outlines.
6. Select structures in the Segmentation View Controller.
7. Use **Navigation** in the four-window layout to link the orthogonal
   crosshairs.
8. Use the View menu for the 3D mesh and plane/axis controls.

Programmatic page changes update immediately; rapid dragging coalesces
intermediate renders and shows the latest selected page.

### 5.5 Expected processed-atlas files

A complete folder normally contains at least:

| File | Purpose |
| --- | --- |
| `atlas_pre_made.pkl` | Normalized intensity volume and atlas metadata. |
| `segment_pre_made.pkl` | Integer annotation volume and unique labels. |
| `atlas_labels.pkl` | Region IDs, names, acronyms, hierarchy, and colors. |
| `atlas_meshdata.pkl` | Whole-brain mesh. |
| `atlas_small_meshdata.pkl` | Per-region meshes. |
| `atlas_axis_info.pkl` | Invertible source-to-DriftlessMap axis transform. |

Processed atlases may also contain orientation-specific boundary caches and
raw source files. DriftlessMap can load the core volumes without eagerly loading the
large boundary caches, but meshes are required for the normal 3D workflow.

## 6. Processing a custom volume atlas

Select **Atlas > Atlas Processor**.

### 6.1 Required source data

| Input | Requirement |
| --- | --- |
| Volume | A non-empty 3D NIfTI (`.nii`, including compressed NIfTI accepted by nibabel) or NRRD (`.nrrd`) intensity volume. |
| Segmentation | A 3D NIfTI or NRRD integer-label volume with exactly the same shape. |
| Mask | Optional 3D mask, or a 4D mask with one trailing singleton channel, with the same spatial shape. |
| Label information | CSV or Excel `.xlsx` table. Only the first Excel sheet is read. |
| Voxel size | Positive finite value in micrometres. |
| Axis directions | One non-duplicated anatomical direction for each source x, y, and z axis. |

All source files selected in one processor session should be in the same
folder. The processed files are written into that folder.

### 6.2 Label table

Column names are case-insensitive. These columns are required:

| Column | Meaning |
| --- | --- |
| `id` | Integer value stored in the segmentation volume. |
| `name` | Full structure name. |
| `acronym` | Short structure label. |
| `parent_id` | Parent structure ID; use a negative value for a root. |
| `structure_id_path` | Slash-delimited hierarchy such as `/997/8/567/`. |

`color_hex_triplet` is optional. If it is absent, DriftlessMap assigns random colors.
For reproducibility, provide six-digit hexadecimal colors and keep the label
table with the source atlas.

Every nonzero label used by the segmentation should have a corresponding table
row. Label `0` is conventionally background.

### 6.3 Bregma, axis directions, and mesh factor

Enter Bregma as three **source-volume voxel coordinates** before any DriftlessMap axis
conversion. A zero component is treated as unspecified and replaced by that
source axis’s midpoint.

For each source dimension, choose one of:

- Left hemisphere to right hemisphere.
- Right hemisphere to left hemisphere.
- Posterior to anterior.
- Anterior to posterior.
- Superior to inferior.
- Inferior to superior.

Each anatomical axis group must be used exactly once. DriftlessMap applies the same
flips and transpose to intensity data, segmentation, and Bregma, then writes
the inverse mapping to `atlas_axis_info.pkl`.

The **Factor** controls mesh downsampling. It must be an integer of at least 2
and cannot exceed any volume dimension. Larger values reduce mesh detail and
processing cost. Start with 2 unless the volume is too large to process
practically.

The dialog includes Lambda fields for forward compatibility; current custom
atlas processing and coordinate reports use the configured Bregma.

### 6.4 Processing sequence and validation

1. Select the intensity, segmentation, optional mask, and label files.
2. Enter Bregma, voxel size, factor, and all source-axis directions.
3. Click **Start Process**.
4. Keep the dialog open until it reaches 100% and closes.
5. Load the output folder and visually check all three planes, region labels,
   Bregma location, and 3D mesh.

Processing stops if volume shapes differ, the label table is incomplete, the
factor is invalid, or a file cannot be read. Do not use an atlas merely because
its intensity image looks correctly oriented; confirm segmentation and Bregma
alignment as well.

## 7. Loading and preparing histological images

### 7.1 Supported image types

Use **File > Load Image** or the histology-image toolbar button.

| Type | Current behavior |
| --- | --- |
| TIFF `.tif`, `.tiff` | 8- or 16-bit grayscale, RGB, channel-last/channel-described data, or a grayscale page stack. Multi-series and unsupported layouts are rejected. |
| CZI `.czi` | Optional dependency; grayscale or RGB, scene selection, mosaics/non-mosaics, and scaled loading. |
| JPEG `.jpg`, `.jpeg` | Loaded as 8-bit RGB. |
| PNG `.png` | Loaded as 8-bit RGB. |
| BMP `.bmp` | Loaded as 8-bit RGB. |

DriftlessMap supports at most four non-RGB image channels. An RGB image has three
display channels but is treated as one RGB cell-count category.

### 7.2 CZI scenes and scale

Before loading a CZI file:

- Set **Scale** to the percentage needed for registration.
- Enable **Load ALL Scenes** only if all scenes are required immediately.

If all scenes are not loaded, use the Scene slider later; DriftlessMap reads a scene
when first selected. Changing the scale rereads the current CZI scene. Begin
with a modest scale for landmark placement, then increase it if cell or boundary
work needs more detail. Higher scale increases time and memory use.

### 7.3 TIFF pages and channels

A grayscale TIFF page stack shows page navigation under the image. RGB TIFF,
multi-channel TIFF, and page-stack TIFF are intentionally distinct:

- RGB samples display as three color channels.
- A channel axis displays up to four independent grayscale channels.
- A page axis displays one grayscale section at a time.

If a TIFF is rejected, inspect its axes, series count, sample type, and channel
count in the exporting microscopy software.

### 7.4 Display adjustments

In the Image View Controller:

1. Toggle channels to isolate the anatomy or signal of interest.
2. Change a channel’s display color if needed.
3. Adjust Black and White to set the displayed intensity interval.
4. Use Gamma for nonlinear brightness adjustment.
5. Choose `linear` or `spline` for manual curve control.
6. Use **Reset** to restore the mapping.

These controls change the display lookup table. When scientific intensity
values matter, preserve the original source image and document display
settings rather than treating a screenshot as quantitative data.

### 7.5 Orientation and cropping

The Image menu provides 180-degree, 90-degree, and one-degree rotations plus
horizontal and vertical flips. A reliable sequence is:

1. Load the image.
2. Use large rotations or flips to establish orientation.
3. Turn on View grids if helpful.
4. Use one-degree rotations for fine adjustment.
5. Select a closed Polygon Lasso around the retained region.
6. Choose **Image > Crop**.

Crop uses the lasso’s rectangular bounding box. It does not create an arbitrary
non-rectangular image boundary.

### 7.6 Creating a process layer and removing background

Choose **Image > Process** to make the current image editable as an
`img-process` layer.

To remove a color/intensity-selected background:

1. Activate Magic Wand.
2. Choose a visible selection color and a tolerance.
3. Click the background. Hold Shift while clicking to union additional
   selections.
4. Optionally select a morphology kernel and size to remove small islands and
   close small gaps.
5. Select the `img-process` layer.
6. Press Delete or Backspace to remove the current mask from the process image.
7. Repeat, or use Eraser for local cleanup.

To limit deletion geometrically, close a Polygon Lasso, select whether to keep
inside or outside, activate the target `img-process` or `img-mask` layer, and
press Delete/Backspace.

Use **Image > Reset** to discard processed-image changes and return to the
loaded image state.

## 8. Registering histology to an atlas

Registration creates a shared triangle mesh from paired atlas and histology
landmarks. That same topology is used for both image-warp directions and for
probe, virus, cell, contour, and drawing transfer.

### 8.1 Prepare the two views

1. Load and orient the volume or slice atlas.
2. Select the correct section and, for a volume atlas, the correct plane tilt.
3. Load and prepare the corresponding histological image.
4. Show **Volume + Histology** or **Slice + Histology**.
5. Avoid resizing or rotating the source image after placing landmarks.

### 8.2 Place paired landmarks

1. Activate Triangulation.
2. Choose a point color visible in both windows.
3. Leave **Points Number** at 2 initially unless more automatic boundary
   anchors are needed. It must be at least 2.
4. Click an anatomical landmark in the atlas.
5. Click the corresponding landmark in histology.
6. Continue in the same order.

Interior landmarks are numbered. The atlas and histology must contain the same
number of points, and point `n` must identify the same anatomy in both.

Good landmarks are:

- Distributed around the section rather than clustered in one area.
- At recognizable outer extrema and internal structures.
- Away from tears, folds, missing tissue, glare, and uncertain borders.
- Sufficient to describe local shape without creating very narrow triangles.

Ten to twenty carefully distributed pairs is a useful starting range for many
whole-section registrations, but image complexity matters more than count.

Landmarks can be dragged. With Eraser active, clicking a numbered landmark
deletes the corresponding point in both windows and renumbers the remaining
pairs.

### 8.3 Match boundary rectangles

The automatically generated outer points define the warp domain. After
interior points are placed, use **Match Boundaries** when the atlas and
histology bounding rectangles differ substantially. This updates the boundary
anchors while retaining the paired interior anatomy.

For a volume atlas, boundary matching can derive the atlas extent from the
nonzero label area. A slice atlas requires interior landmarks in both images.

### 8.4 Evaluate mesh quality

The Triangulation controls report:

- **Good / green:** no detected fold or strong-shape warning.
- **Review / yellow:** a narrow or highly stretched triangle needs inspection.
- **Invalid / red:** duplicate, collapsed, folded, out-of-image, or otherwise
  unsafe geometry.

Enable triangle display and hover the quality label for details. Folded or
collapsed triangles block transfer. A yellow mesh can transfer, but it should
be reviewed against known anatomy.

To repair a mesh:

- Move a landmark away from its neighbor.
- Delete an uncertain pair.
- Add a pair in a large unsupported region.
- Reduce local stretching.
- Confirm that pair order has not been confused.
- Recheck the atlas slice and tilt.

### 8.5 Create and refine an overlay

To overlay histology onto the atlas:

1. Click **Transform to Atlas Slice Window**.
2. Inspect internal structures and the outer boundary.
3. In the Layer View Controller, change the `atlas-overlay` opacity or use
   `Plus`/`Overlay` composition.
4. Click the transform action again to remove the overlay if refinement is
   needed.
5. Move, add, or delete paired points and transform again.

To overlay atlas data onto histology, use **Transform to Histological Image
Window** instead. Only one transform direction is active at a time.

During landmark dragging, DriftlessMap rewarps the original overlay instead of
repeatedly warping an already transformed preview, preventing accumulated blur.
Atlas labels and masks use nearest-neighbor mapping where discrete values must
be preserved; histology display uses smooth interpolation.

### 8.6 Transfer annotations

Once the registration is accepted:

1. Create a probe, virus, cell, drawing, or contour annotation in the
   histology window.
2. Click **Accept and Transfer**.
3. Confirm that the corresponding `atlas-*` layer appears.
4. Read the status bar for points that fell outside the mesh.
5. Add the atlas-layer data as an object piece in the Object View Controller.

Points outside the registration mesh cannot be assigned a valid atlas
coordinate. DriftlessMap preserves or rejects them according to the data type and
reports the count; do not silently treat them as registered.

### 8.7 Save registration landmarks

Use:

- **Atlas > Save Triangulation Points** to write `.dmaptri`.
- **Atlas > Load Triangulation Points** to restore them.

Current files include paired landmarks and shared triangle connectivity.
Legacy `.pkl` landmark files can be loaded with the restricted legacy reader.
A landmark file is meaningful only for the corresponding atlas slice,
orientation, and image geometry.

## 9. Working with layers

### 9.1 Common layer names

| Histology layer | Atlas layer | Meaning |
| --- | --- | --- |
| `img-process` | `atlas-slice` | Editable base image or processed slice. |
| `img-overlay` | `atlas-overlay` | Transformed image overlay. |
| `img-mask` | `atlas-mask` | Magic-wand selection. |
| `img-probe` | `atlas-probe` | Probe track points. |
| `img-virus` | `atlas-virus` | Expression/tracer pixels or transferred points. |
| `img-cells` | `atlas-cells` | Cell centers and metadata. |
| `img-drawing` | `atlas-drawing` | Open line or closed area. |
| `img-contour` | `atlas-contour` | Tissue boundary. |

Not every layer has a useful counterpart in every workflow.

### 9.2 Selecting and editing

Click a layer to make it current. Some operations require exactly one selected
layer; DriftlessMap reports an error when none or multiple are selected.

Use the eye to toggle display and the trash icon to delete. Deleting a
scientific layer clears the associated working data. Deleting an overlay also
resets the corresponding transfer state.

### 9.3 Translation and rotation

The Edit menu can translate or rotate compatible selected layers:

1. Choose **Edit > Translation > Distance Setting** to set the movement step.
2. Use Up, Down, Left, or Right.
3. Choose **Edit > Rotation > Angle Setting** to set the rotation step.
4. Use Clockwise or Counter Clockwise.

Transformations are applied only to valid layer types and are recorded in the
recent undo history. DriftlessMap retains a bounded history of the six most recent
recorded actions, so project saves are the durable recovery mechanism.

Shortcuts:

- `Ctrl+Z`: Undo.
- `Ctrl+Shift+Z`: Redo.

**Edit > Clear** clears working layers while preserving the loaded base image
or atlas slice where appropriate. Save the project before using it.

### 9.4 Opacity and composition

Opacity affects display only. Pixel composition modes are:

- `Plus`: additive display, useful for bright boundaries or fluorescence.
- `Multiply`: emphasizes shared dark structure.
- `Overlay`: contrast-preserving overlay and the default for new layers.
- `SourceOver`: conventional alpha compositing.

Choose a mode that makes anatomical mismatch visible; do not use blending to
hide a poor registration.

## 10. Working with object pieces and merged objects

### 10.1 Creating a piece

After registered data appear in an atlas layer:

1. Open the Object View Controller (`Ctrl+5`).
2. Click **Add Object Piece**.
3. DriftlessMap converts all eligible current atlas annotations into one or more
   three-dimensional pieces and clears their temporary atlas-layer data.

The four-window layout cannot create or merge pieces. Switch to a single atlas
slice or atlas-plus-histology layout first.

### 10.2 Naming and grouping

DriftlessMap groups pieces during merge using the text before the first hyphen. The
default name `probe - piece`, for example, belongs to the group `probe`.

To keep two experiments separate, rename their pieces before merging:

```text
left probe - section 01
left probe - section 02
right probe - section 01
right probe - section 02
```

This produces `left probe` and `right probe` merged objects. Use consistent,
descriptive prefixes and keep at least one hyphen in the piece name.

### 10.3 Merging and unmerging

Use the type-specific bottom button to merge all available pieces of that type.
Merging removes the source pieces and adds calculated merged objects. Probe
merging additionally fits the trajectory, finds the brain-surface entry,
models contacts, samples region labels, and embeds coordinate metadata.

Select a merged object and click **Unmerge** to recover its named pieces.
Re-merge after changing piece membership, probe settings, or atlas metadata.

### 10.4 Object controls

For a selected merged object:

- Eye: toggle 3D visibility.
- Color swatch: choose display color.
- Link: include the object in comparison.
- Information: open region and measurement details.
- 2D locate: currently supported for a selected merged probe.
- Opacity, size/width, composition: adjust 3D rendering.
- Trash: delete the object.

Probe comparison requires at least two linked merged probes. Other object-type
comparisons are not currently implemented.

## 11. Pre-surgical probe planning

### 11.1 Standard single-shank plan

1. Load a processed volume atlas. Do not load histology.
2. Choose the target plane, slice, and tilt.
3. Activate Probe Marker.
4. Choose `Neuropixel 1.0`, `Neuropixel 2.0`, `Linear-silicon`, or `Tetrode`.
5. Choose the site-face direction:
   - `Out`: contacts face the viewer.
   - `In`: contacts face away from the viewer.
   - `Left` or `Right`: contacts face the corresponding screen direction.
6. Click the intended surface/insertion point.
7. Click the intended tip/target point.
8. Add the probe piece in the Object View Controller.
9. Merge probe pieces.
10. Open the Probe Information Window and inspect trajectory, coordinates,
    regions, contacts, and mapping quality.

A pre-surgical planned probe must be one two-point piece. If a group contains
multiple pieces, DriftlessMap refuses to merge it as a plan.

### 11.2 Neuropixels 2.0 four-shank plan

Choose `Neuropixel 2.0` and enable the Multi-shanks switch. The built-in model
uses four shank offsets. One two-point center trajectory generates the planned
shank pieces. Add and merge them as above.

### 11.3 Custom linear silicon probe

1. Choose `Linear-silicon`.
2. Open the Linear Silicon Designer.
3. Enter:
   - Overall probe length.
   - Probe thickness.
   - Tip length.
   - Contact height and width.
   - Number of contact columns.
   - Contacts per column.
   - Contact spacing.
   - X and Y bias for each column.
4. Confirm the design.
5. Save it with **Objects > Save Probe Setting** if it will be reused.

Tip length must lie within the probe length. Contact height and width must be
nonzero before a valid plan can be made.

Load a saved design with **Objects > Load Probe Setting** and verify every
field before merging.

### 11.4 Multi-probe planning

Use **Objects > Multi-Probe Planning** to define several probes or shanks by:

- X offset in micrometres.
- Y offset in micrometres.
- Face direction for each probe.

The positive out-of-plane convention depends on the planned orientation. The
dialog’s preview and face fields are the authoritative setup; inspect the
result in 3D before accepting surgical coordinates.

### 11.5 Interpreting a planned probe

The Probe Information Window distinguishes:

- AP and ML tilt from the dorsoventral axis.
- Insertion-to-tip track length.
- Vertical DV change.
- Insertion and tip relative to configured Bregma.
- Source-atlas voxels.
- Modeled physical contacts per region.
- Fitted centerline path length per region.

For recognized Allen CCFv3, AP and ML Bregma values are estimated. Surface
depth, not affine transformed DV, is the targeting-relevant depth measure.

## 12. Post-surgical probe reconstruction

### 12.1 Single-section trajectory

1. Load the volume atlas and histological section.
2. Register the image to the correct atlas slice.
3. Activate Probe Marker and select the physical probe type.
4. Choose the after-surgery site face (`Up`, `Down`, `Left`, or `Right`) based
   on how the probe was held.
5. Click at least two points along the visible track. More points can describe a
   noisy trace, but they should represent one straight probe.
6. Click **Accept and Transfer**.
7. Confirm `atlas-probe` and add an object piece.
8. Merge the probe.
9. Inspect the fit-quality section before export.

For a generic electrode or injection trajectory without modeled contacts,
`Tetrode` can be used as a simple linear trajectory type.

### 12.2 Multi-section trajectory

For a probe visible in several sections:

1. Register the first section.
2. Mark and transfer its visible probe segment.
3. Add a probe piece.
4. Rename it using a stable group prefix, such as
   `probe A - section 01`.
5. Load and register the next section.
6. Repeat with `probe A - section 02`, and so on.
7. Merge after all sections are represented.

All pieces with the same prefix are fit together in 3D.

### 12.3 Reconstructing a multi-shank probe after surgery

Do not treat the built-in multi-shank pre-plan as a substitute for observed
tracks. Trace each visible shank independently in each relevant section:

```text
shank 0 - section 01
shank 0 - section 02
shank 1 - section 01
shank 1 - section 02
```

Merging creates one reconstructed probe per unique prefix.

### 12.4 Robust fit and mapping diagnostics

DriftlessMap uses an outlier-resistant orthogonal 3D line fit. It reports:

- Total and retained point count.
- RMS deviation of retained points.
- Maximum deviation across all points.
- Straight-line explained fraction.
- Method used to find the insertion at the 3D atlas brain-mask surface.

Quality is classified relative to atlas voxel size:

- Good: retained RMS at most 1.5 voxels.
- Review: retained RMS above 1.5 and at most 3 voxels.
- Poor: retained RMS above 3 voxels.

The robust fit can reject an isolated misplaced point, but it cannot fix a
wrong atlas section, reversed image, confused shank identity, or systematic
curvature. Review the reconstructed track in all views.

### 12.5 Contact and region interpretation

Contacts are physical modeled recording sites, not acquisition-channel IDs.
The embedded contact table is column-major; within each column, index zero is
nearest the geometric tip in the DriftlessMap model.

`Merge sites` changes the schematic display of contacts at the same depth. It
does not remove contacts from the self-contained reconstruction table.

Region summaries distinguish:

- **Contacts:** modeled physical sites assigned to the structure.
- **Path:** fitted probe centerline length within the structure.

### 12.6 Probe CSV export

Open a merged probe’s information window and click **Export probe CSV files**.
Choosing one base name creates:

- `*_contacts.csv`: one row per physical contact, deepest first.
- `*_trajectory.csv`: one row containing insertion, tip, angles, length, fit
  quality, atlas identity, and coordinate-system metadata.
- `*_regions.csv`: one row per traversed region with contact count and path
  length.

Important contact columns:

- `axial_distance_up_from_tip_um`: smallest at the deepest contact and
  increases toward the surface.
- `axial_depth_from_insertion_um`: increases from insertion toward the tip.
- `site_index`, `column_index`, `index_in_column`: stable model indexes.

Probe objects created by older versions may lack the `reconstruction` block.
Load their original project with the same atlas, unmerge/re-merge the probe,
and save a new `.dmapobj` before exporting CSV.

## 13. Virus, tracer, lesion, and expression registration

The virus workflow is appropriate for pixel-defined regions such as viral
expression, tracer spread, lesions, or degeneration. It estimates occupied
atlas voxels rather than individual labeled cells.

For each section:

1. Register histology to the atlas.
2. Activate Magic Wand.
3. Set a contrasting selection color and a tolerance.
4. Click the signal. Hold Shift and click to union disconnected components.
5. Optionally use a morphology kernel to clean speckle or small gaps.
6. Use Polygon Lasso and Delete/Backspace to remove false-positive areas.
7. Click the Magic Wand **virus registration** button to create `img-virus`.
8. Click **Accept and Transfer** to create `atlas-virus`.
9. Add a virus object piece.
10. Rename it with a shared experimental prefix.

Repeat for every section, then click **Merge Virus**. The information window
reports each affected atlas region, sampled volume in stack voxels, and
proportion of the merged expression.

Magic Wand is intensity/tolerance based. Results depend on image scaling,
channel visibility, background correction, and morphology. Keep the source
images and document the settings used.

## 14. Cell registration and counting

### 14.1 Manual selection

1. Register histology to the atlas.
2. Activate Cell Selector.
3. Choose a display color.
4. Enable manual selection.
5. For a grayscale/multichannel image, leave exactly one channel visible.
6. Click each cell center.
7. Erase mistaken cell points with the Eraser tool.
8. Click **Accept and Transfer**.
9. Add a cell piece and rename it.
10. Repeat for other sections or channels, then click **Merge Cells**.

RGB images use one total cell category. Non-RGB images retain a separate
category for each selected channel.

### 14.2 Similar-cell blob detection

DriftlessMap includes an interactive detector seeded from a representative cell:

1. Activate Cell Selector.
2. For multichannel data, leave exactly one channel visible.
3. Enable the target/aim control.
4. Click around the boundary of one representative cell to define its shape
   and intensity range.
5. Click the radar control to search the current image for similar blobs.
6. Inspect every detected point and erase false positives.

The detector derives area, circularity, threshold, convexity, and inertia
settings from the sample. It is a convenience tool, not a validated universal
cell classifier. Uneven illumination, overlapping cells, changing scale, and
mixed phenotypes can materially affect its output.

### 14.3 Cell information

A merged cell object reports counts by atlas structure. Counts outside the
atlas or outside a valid registration mesh should be reviewed rather than
assigned to a nearby structure.

External points can enter the same object-piece and merge workflow; see
[External point data](#16-external-point-data).

## 15. Drawings, regions of interest, contours, and measurements

### 15.1 Open line and closed area drawings

1. Register histology.
2. Activate Pencil.
3. Choose color, width, and open/closed path mode.
4. Click to start, move along the desired path, and click to stop.
5. Click **Accept and Transfer**.
6. Add a drawing piece.
7. Repeat across sections and merge if needed.

An open drawing is analyzed as a line. A closed drawing is filled and analyzed
as a sampled area.

### 15.2 Drawing ROI information and CSV

Select either a drawing piece or merged drawing and click Information. For a
loaded volume atlas, the report includes:

- Sampled point count.
- Line length or sampled area.
- Coordinate basis.
- AP/ML centroid and range.
- Configured DV where meaningful.
- Local dorsal surface-depth summary.
- Distribution across atlas structures.

Click **Export coordinates as CSV** for one row per sampled coordinate. The
file includes piece and point indexes, Bregma-relative DriftlessMap voxels, configured
coordinates, surface depth, and anatomical assignment. Recognized Allen CCFv3
adds source voxels, estimated AP/ML, and clearly labeled non-targeting affine
DV.

Out-of-bounds samples are exported as structure `0`, “Outside atlas /
unlabeled,” rather than being wrapped to the opposite side of an array.

### 15.3 Tissue contours

1. Use Magic Wand to select the tissue region.
2. Choose a tolerance high enough to cover the intended tissue but not
   background.
3. Click the contour-registration control to create `img-contour`.
4. Transfer to `atlas-contour`.
5. Add one contour piece per section.
6. Merge contours for 3D display.

Contour merging creates a 3D line representation. It is not a watertight
surface-reconstruction pipeline.

### 15.4 Ruler

Activate Ruler and click two endpoints. In a calibrated slice atlas, the
reported length uses the registered width and height. In histology, the ruler
uses available image scaling metadata. Confirm the active view and units before
recording a value.

For a 2D book atlas, the ruler is the recommended way to measure how much of a
planned path lies in a manually identified region.

## 16. External point data

Use **File > Load External Data > Cells** to load cell or point coordinates
generated by another program.

Requirements:

- A volume atlas must already be loaded.
- The atlas folder must contain valid `atlas_axis_info.pkl`.
- The file must be `.npy`; legacy inert `.pkl` is also accepted.
- The payload must be a non-empty numeric NumPy array with shape `(N, 3)`.
- Coordinates must be in the **source atlas’s native voxel order and
  directions**, not DriftlessMap display-window coordinates.
- Values should fall within the source atlas shape.

DriftlessMap applies the saved flips and transpose, subtracts configured Bregma, and
adds the data as a `cells piece` named `loaded point data`. Rename and merge it
as needed.

For integer voxel indices, valid coordinates satisfy `0 <= coordinate <
axis_size`. A value equal to an axis size is outside the volume.

## 17. Using a two-dimensional slice atlas

Use this workflow only when you have the right to use the atlas image.

### 17.1 Load and register the plate

1. Choose **Atlas > Load Slice**.
2. Select JPEG, PNG, `.dmapslice`, or a legacy slice `.pkl`.
3. For a raw image, choose **Atlas > Register Slice Info**.
4. Enter:
   - Plane: coronal, sagittal, or horizontal.
   - Physical width in mm.
   - Physical height in mm.
   - Signed distance from Bregma in mm.
5. Choose **Atlas > Bregma Picker** and click the 2D Bregma location.
6. If the image has a margin, close a Polygon Lasso around the useful plate and
   choose **Atlas > Crop**.
7. Choose **Atlas > Create Slice Layer**.
8. Save the calibrated result with **Atlas > Save Processed Slice**.

Width and height must be positive finite values. Distance can be positive,
negative, or exactly zero. Bregma must be a finite two-coordinate point.

### 17.2 Register histology

Show **Slice + Histology**, place paired landmarks, evaluate the mesh, and
create the desired overlay just as for a volume-atlas slice.

### 17.3 Limitations

The slice atlas has no volumetric label array or per-region 3D meshes:

- The volume-atlas controller and segmentation tree are disabled.
- Object-piece creation and region-aware probe merging are disabled.
- Multiple slice merging is currently unavailable.
- Use the ruler and known printed labels for regional path measurements.

If both volume and slice atlases have been loaded, **Atlas > Switch Atlas**
changes the active atlas type.

## 18. Saving, loading, and exporting

### 18.1 DriftlessMap file formats

| Extension | Payload | Portability and dependencies |
| --- | --- | --- |
| `.dmap` | Complete working project state. | Stores atlas and source-image paths; keep those resources at their original locations. |
| `.dmaplayer` | One 2D layer. | Must match the target image dimensions and required layer metadata. |
| `.dmapobj` | One object or merged object. | Load an appropriate atlas first. Current merged probes embed self-contained reconstruction metadata. |
| `.dmapslice` | Calibrated 2D atlas slice. | Contains image, plane, physical dimensions, distance, and Bregma point. |
| `.dmaptri` | Paired registration landmarks and topology. | Reuse only with matching atlas slice and histology geometry. |

These are versioned ZIP-based DriftlessMap archives containing a JSON manifest and
NumPy arrays written with pickling disabled. Saves are atomic: DriftlessMap writes a
temporary archive and replaces the destination only after a complete save.

Legacy `.pkl` files are read with a restricted unpickler that accepts the inert
built-in and NumPy structures used by older HERBS releases and rejects
executable or unsupported globals. After opening an important legacy file,
save it in the current DriftlessMap format.

DriftlessMap also reads the safe HERBS extensions `.herbs`, `.herbslayer`,
`.herbsobj`, `.herbsslice`, and `.herbstri`. New saves use the DriftlessMap
extensions in the table above and identify their manifest format as
`DriftlessMap`.

Internal processed-atlas `.pkl` files are a separate implementation detail.
Only use caches created by DriftlessMap or obtained from a trusted atlas source.

### 18.2 Saving and loading a project

Use **File > Save Project** frequently. A project records:

- Atlas and histology paths.
- Current atlas type, slice, plane, and tilt.
- Histology scene, scale, channels, and display controls.
- Processed images and current layers.
- Paired landmarks and registration topology.
- Tool settings.
- Probe design.
- Object pieces and merged objects.
- Current layout and related state.

Projects are not fully self-contained datasets. On load, DriftlessMap reloads the
atlas folder and source histological image from the recorded paths. Moving or
renaming them can prevent restoration. Preserve a stable project directory or
document any relocation.

When loading another project over active work, DriftlessMap asks whether to save the
current project first.

### 18.3 Saving and loading layers

Use **File > Save Layer > Current Layer** when exactly one layer is selected, or
**All Layers** to write every layer using a chosen base name. DriftlessMap appends the
layer name to create separate `.dmaplayer` files. Some pixel layers also
produce a JPEG preview/export beside the DriftlessMap file.

Use **File > Load Layers** after loading the matching image or atlas. Pixel
layers must match the current dimensions; process layers also require valid
size, level, and data metadata. Invalid files are rejected instead of being
partially displayed.

### 18.4 Saving and loading objects

Use:

- **File > Save Object > Current** for the selected entry.
- A type-specific Save Object command to save every merged object of that type
  into a selected folder.
- **File > Load Objects** to select one or more `.dmapobj` files.

Load the intended atlas first and use a single atlas-slice layout. DriftlessMap checks
that object coordinates fit the loaded atlas. A file from another atlas or
resolution can be rejected as nonmatching.

### 18.5 Information-window exports

Current structured CSV exports are:

- Three companion probe CSVs from Probe Information.
- One drawing-coordinate CSV from Drawing ROI Information.

Virus and cell information is available in their dialogs and saved objects,
but there is no equivalent dedicated CSV action in their current information
windows.

### 18.6 Configuration file

The last atlas folder is stored in:

- Windows: `%APPDATA%\DriftlessMap\settings.json`
- macOS: `~/Library/Application Support/DriftlessMap/settings.json`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/DriftlessMap/settings.json`

Set `DRIFTLESSMAP_CONFIG_DIR` before launching to use another configuration directory.
The preference file is written atomically. If it is corrupt, DriftlessMap ignores it
and asks for an atlas folder.

For compatibility, `HERBS_CONFIG_DIR` and an existing HERBS settings file are
still read when a DriftlessMap setting has not been created.

## 19. Menu and shortcut reference

### 19.1 File

| Command | Function |
| --- | --- |
| Load Atlas | Select a processed volume-atlas folder. |
| Load Image | Select a supported histological image. |
| Save Project / Load Project | Write or restore `.dmap` project state. |
| Save Layer > Current Layer / All Layers | Write `.dmaplayer` files. |
| Save Object > Current | Write the selected `.dmapobj`. |
| Save Object > Probes/Virus/Cells/Contours/Drawings | Save all merged objects of that type to a folder. |
| Load Layers / Load Objects | Restore matching saved layers or objects. |
| Load External Data > Cells | Import source-atlas `(N, 3)` point data. |

### 19.2 Edit

| Command | Function |
| --- | --- |
| Undo / Redo | Move through recent recorded actions. |
| Translation > Up/Down/Left/Right | Move compatible selected layers by the configured distance. |
| Translation > Distance Setting | Set movement step. |
| Rotation > Clockwise/Counter Clockwise | Rotate compatible selected layers. |
| Rotation > Angle Setting | Set rotation step. |
| Clear | Clear working layers. |

### 19.3 Image

| Command | Function |
| --- | --- |
| 180 / 90 Clockwise / 90 Counter Clockwise | Coarse image rotation. |
| 1 Clockwise / 1 Counter Clockwise | Fine image rotation. |
| Flip Horizontal / Flip Vertical | Mirror image. |
| Hide | Toggle loaded image display. |
| Process | Create editable `img-process`. |
| Crop | Crop to the closed lasso bounding rectangle. |
| Reset | Restore loaded image state. |

### 19.4 Atlas

| Command | Function |
| --- | --- |
| Download Waxholm Rat Atlas | Download/process standard rat atlas. |
| Download Allen Mice Atlas | Download/process Allen 10, 25, or 50 um atlas. |
| Atlas Processor | Process a custom volume atlas. |
| Save/Load Triangulation Points | Write/read `.dmaptri`. |
| Load Slice | Load a raw or processed 2D atlas plate. |
| Register Slice Info | Set plane, dimensions, and Bregma distance. |
| Create Slice Layer | Make the calibrated plate active. |
| Crop | Crop the slice atlas with a lasso. |
| Bregma Picker | Select the 2D Bregma point. |
| Save Processed Slice | Write `.dmapslice`. |
| Merge Slices | Disabled in the current release. |
| Switch Atlas | Switch between loaded volume and slice atlases. |

### 19.5 Objects

| Command | Function |
| --- | --- |
| Save Probe Setting | Save the current probe geometry. |
| Load Probe Setting | Restore a saved probe geometry. |
| Multi-Probe Planning | Configure multi-probe offsets and faces. |

### 19.6 View

Commands select individual atlas, histology, and 3D windows; volume-plus-
histology or slice-plus-histology layouts; and the four-window layout. Display
commands switch 2D/3D dark or light mode, atlas planes, 3D axes, and 2D grids.
The menu text changes to show the resulting on/off state.

### 19.7 Help

**About DriftlessMap** displays the current version and project information.

### 19.8 Keyboard and mouse reference

| Input | Action |
| --- | --- |
| `Ctrl+1` ... `Ctrl+5` | Select the five sidebar controllers. |
| `Ctrl+Z` | Undo. |
| `Ctrl+Shift+Z` | Redo. |
| Left/Right Arrow | Move a focused volume-atlas plane one page. |
| Delete or Backspace | Delete using the active layer/tool context. |
| Shift+Magic Wand click | Union another pixel selection into the mask. |
| Click-drag | Pan where supported or move a movable registration point. |
| Mouse wheel | Zoom in plot windows. |

## 20. Troubleshooting

### DriftlessMap imports in one terminal but not another

Activate the same Conda environment and verify:

```bash
conda activate DriftlessMap
which python
python -m pip --version
python -c "import driftlessmap; print(driftlessmap.__version__)"
```

On Windows use `where python` instead of `which python`.

### CZI support is not installed

Use Python 3.13 or earlier and install the optional extra:

```bash
python -m pip install ".[czi]"
```

Do not add PyQt5 to the environment; DriftlessMap is a PyQt6 application.

### The application starts but the 3D window is blank or OpenGL fails

- Update the graphics driver.
- Confirm that OpenGL is available to the desktop session.
- Avoid launching through a remote session without OpenGL forwarding.
- On Linux, confirm the required system OpenGL libraries are installed.
- Test with a smaller atlas resolution to separate graphics from memory issues.

### Atlas loading says a core file or mesh is missing

Select the processed atlas folder, not the raw download folder or an individual
file. If `atlas_pre_made.pkl`, `segment_pre_made.pkl`,
`atlas_meshdata.pkl`, or `atlas_small_meshdata.pkl` is absent or corrupt,
rerun the correct downloader’s Process step or the custom Atlas Processor.

### The wrong atlas loads from the toolbar

Use **File > Load Atlas** and select the correct folder. DriftlessMap updates the
remembered path. Delete or relocate the user `settings.json` only if the
preference itself is corrupt.

### A 10 um Allen atlas is slow or uses too much memory

Close other memory-intensive applications, avoid loading unnecessary high-
resolution CZI scenes, or process/load the 25 or 50 um atlas in a separate
folder.

### An image is rejected

Check:

- Supported extension and readable file.
- TIFF uses `uint8` or `uint16`.
- TIFF has one series.
- It is a supported RGB, grayscale, channel, or page-stack layout.
- It contains no more than four non-RGB channels.
- CZI support is installed and the CZI has a supported pixel type.

Re-export from the microscopy application as a conventional TIFF when needed.

### Magic Wand selects too much or too little

- Isolate the relevant channel.
- Adjust black/white only for visibility; adjust Magic Wand tolerance for the
  actual selection.
- Click without Shift to replace the selection.
- Hold Shift to add regions.
- Use morphology carefully; large kernels can remove real signal.
- Clean the result with lasso and eraser before transfer.

### Registration says the mesh is invalid

- Ensure the landmark counts match.
- Confirm pair order.
- Separate duplicate or near-duplicate points.
- Move points inside their images.
- Remove crossings/folds.
- Add support in a large empty area.
- Revisit the atlas plane and tilt.

Do not bypass an invalid mesh; transfer is blocked to prevent corrupt
coordinates.

### A transferred object is incomplete

Some source points were probably outside the triangle mesh. Expand boundary
coverage, add suitable landmarks, rebuild the transform, and repeat the
transfer. Check the status-bar count.

### Probe merging fails

Check:

- A volume atlas, not only a slice atlas, is active.
- `atlas_axis_info.pkl` exists.
- The current layout is not the four-window view.
- A pre-plan has exactly one two-point piece per group.
- A reconstruction has at least two points.
- Piece prefixes group the intended sections/shanks.
- Custom probe contact dimensions are nonzero.
- Points remain within atlas bounds.

### Probe CSV export says to re-merge

The object predates self-contained reconstruction metadata. Load the original
project with the same atlas, unmerge and re-merge it in DriftlessMap 1.1.0, then save a
new object.

### A project cannot find its image or atlas

Projects retain resource paths. Restore the files to their original paths or
recreate the project after loading them from the new locations. A saved project
is not a substitute for archiving source images and the entire processed atlas
folder.

### A saved layer or object does not match

Load the same source image dimensions and atlas/resolution used when it was
created. DriftlessMap intentionally rejects out-of-range objects and incompatible
pixel layers.

### Reporting a problem

Open an issue at
<https://github.com/mohebi-n-associates/DriftlessMap/issues> and include:

- DriftlessMap version.
- Python version and operating system.
- Installation command.
- Atlas species and resolution.
- Image type, bit depth, axes/series/channel information.
- Exact steps.
- Full error text and a screenshot.
- Whether the problem reproduces in a new project.

Do not attach confidential or unpublished experimental data unless it is safe
to share.

## 21. Python API and development

### 21.1 Supported public package surface

DriftlessMap is primarily a GUI application. The small public package surface is:

```python
import driftlessmap

print(driftlessmap.__version__)
driftlessmap.run()
driftlessmap.run_driftlessmap()  # alias
```

`CZIReader` is lazily available when the CZI extra is installed:

```python
from driftlessmap import CZIReader

reader = CZIReader("section.czi")
reader.read_data(scale=0.1, scene_index=0)
```

Importing `driftlessmap` does not eagerly import the complete GUI or optional
CZI stack. The legacy `herbs` package remains available for existing scripts.
Internal modules provide testable atlas, triangulation, persistence, probe, and
ROI helpers, but they are not currently declared as a stable public API. Pin a
DriftlessMap version if external code imports them.

### 21.2 Running the test suite

Install the test extra, then run:

```bash
python -m pytest
python -m ruff check .
```

The regression suite covers packaging, resource paths, image contracts, atlas
transforms and loading, safe persistence, layers, slice validation,
triangulation, probe mapping/reconstruction/CSV export, cell detection, and
drawing ROI analysis.

### 21.3 Package resources and working directory

DriftlessMap resolves icons, UI files, QSS styles, and packaged label data relative to
the installed package. Launching it does not change the process working
directory. This matters when embedding the launcher in a notebook or another
Python program.

## 22. Reproducibility checklist

Before acquiring or analyzing experimental data:

- Record DriftlessMap and Python versions.
- Record atlas name, release, resolution, folder, and source files.
- Record Bregma source voxel and axis directions.
- Keep `atlas_axis_info.pkl` with the processed atlas.
- Keep raw histology unchanged.
- Record CZI scene and loading scale.
- Save triangulation points and the complete project.
- Inspect mesh quality and registration in more than one anatomical feature.
- Use stable piece names before merging.
- Inspect probe fit diagnostics and 3D position.
- Export structured CSVs, not only screenshots.
- Preserve source image, atlas folder, project, objects, and exports together.
- For Allen coordinates, label AP/ML as estimates and do not use affine DV for
  surgical targeting.

For a new analysis, a practical archive layout is:

```text
experiment/
├── atlas-reference.txt
├── histology/
├── projects/
├── triangulation/
├── objects/
├── csv/
└── notes/
```

The processed atlas itself can remain in a shared read-only location, provided
its absolute path remains stable and the experiment records exactly which atlas
folder was used.
