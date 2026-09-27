# Update Log

### 27th September 2026
##### DriftlessMap 1.4.23

Settings safety: Slice Settings opens with the current calibration and can be cancelled, layer shift and rotate settings can be cancelled and no longer clamp above 99, and loaded probe planning is validated before it changes the session without discarding unaccepted probe points.

### 27th September 2026
##### DriftlessMap 1.4.22

Atlas download and processing workers now report unexpected failures instead of leaving their dialogs stuck or aborting DriftlessMap, and closing a dialog after a finished background step no longer raises an error.

### 27th September 2026
##### DriftlessMap 1.4.21

Undo and redo are more reliable: history snapshots are independent copies, history for deleted layers is discarded instead of crashing, and atlas mask, slice and probe edits can be undone.

### 27th September 2026
##### DriftlessMap 1.4.20

Image display fixes: masks and nearly black images load again, hidden channels stay hidden after project load, flips, rotations and page or scene changes, histogram colours no longer carry over between images, and colour swatches no longer accumulate on every project load.

### 27th September 2026
##### DriftlessMap 1.4.19

Object import checks coordinates against the loaded volume atlas correctly and no longer crashes with a slice atlas; bulk object export writes safe, unique file names and confirms completion.

### 27th September 2026
##### DriftlessMap 1.4.18

Probe reconstruction no longer crashes on tracks too short to hold a recording site, on atlas labels missing from the ontology, or on horizontal probe directions; each case now produces a clear message or a labelled result.

### 27th September 2026
##### DriftlessMap 1.4.17

Editing-tool fixes: the histology eraser no longer crashes on overlay or empty layers, the magic wand selects a two-sided intensity band that works on 16-bit images, and clearing a size or tolerance field no longer raises errors.

### 27th September 2026
##### DriftlessMap 1.4.16

Layer shift and rotate fixes: rotating point layers no longer crashes and turns in the same direction as image layers about the correct centre, and shifting image layers on non-square slices keeps them aligned.

### 27th September 2026
##### DriftlessMap 1.4.15

Fixes crashes with slice atlases and the pencil: virus registration, Accept and Transfer and Edit > Clear now work with a slice atlas, erasing or lasso-deleting the slice layer edits the saved slice pixels, and changing pencil colour or size no longer fails.

### 27th September 2026
##### DriftlessMap 1.4.14

Changing a brain-region colour no longer crashes DriftlessMap on atlases with sparse structure IDs such as the Allen CCF, and the 3D region mesh receives the colour that was chosen.

### 27th September 2026
##### DriftlessMap 1.4.13

Scientific fix: Make Pieces now builds every piece type from atlas-frame annotations only; histology-frame virus pixels are no longer transposed or placed without registration, histology cells are no longer silently dropped, and contour pieces no longer crash.

### 27th September 2026
##### DriftlessMap 1.4.12

Provenance fix: after falling back to the embedded histology raster, or restoring a slice atlas from a project, saving no longer fingerprints a changed or unverified file on disk as the source of that work.

### 27th September 2026
##### DriftlessMap 1.4.11

Atlas provenance fixes: Switch Atlas now records the atlas actually shown, and downloaded Waxholm and Allen atlases are opened through the verified loader so their path and fingerprint are recorded.

### 27th September 2026
##### DriftlessMap 1.4.10

Scientific fix: exported source-atlas voxels (including Allen DV and AP) now contain the voxel whose label was reported, instead of lying one voxel away on flipped axes; imported integer point files are accepted and bounds-checked.

### 27th September 2026
##### DriftlessMap 1.4.9

Scientific fix: ruler lengths are correct after reopening a project and for non-mosaic CZI images; projects now store the raster's true scale and embedded rasters keep it.

### 27th September 2026
##### DriftlessMap 1.4.8

Scientific fix: recording-site positions for site faces "In" (1) and "Right" (3) on tilted after-surgery probes are now correct; affected merged probes should be re-merged and re-exported.

### 27th September 2026
##### DriftlessMap 1.4.7

Probe geometry dialogs: Cancel now discards edits, added linear-silicon columns put site count and spacing in the right rows, OK reflects every field, saved multi-probe faces display correctly, and geometry validity is re-evaluated on every accept.

### 27th September 2026
##### DriftlessMap 1.4.6

Loading triangulation points no longer wipes the loaded landmarks when the file was saved in a different atlas view; files are validated against the current atlas, and landmark labels are numbered consistently.

### 27th September 2026
##### DriftlessMap 1.4.5

Volume and slice atlas loads now validate everything before changing the session, so a failed load no longer corrupts atlas provenance or deletes atlas layers; slice atlases can be loaded from images again.

### 27th September 2026
##### DriftlessMap 1.4.4

Merging probe, virus, cell, drawing and contour pieces no longer deletes the pieces when the merge fails; all merged objects are computed first and pieces are removed only when every one succeeds.

### 27th September 2026
##### DriftlessMap 1.4.3

Load Project no longer deletes the current objects before a replacement project has been chosen and verified, and its save prompt now offers Cancel.

### 27th September 2026
##### DriftlessMap 1.4.2

Security fix: array sizes declared inside project, layer and object archives are checked against the stored data before memory is allocated, so a small crafted file can no longer exhaust memory.

### 27th September 2026
##### DriftlessMap 1.4.1

Security fix: processed-atlas mesh caches are now read with a restricted, non-executable reader, closing a code-execution path through shared atlas folders.

### 27th August 2026
##### DriftlessMap 1.4.0

Adds native Windows and macOS desktop release builds, a new application icon,
visible GUI version information, and separate end-user and developer
installation instructions.

### 27th August 2026
##### DriftlessMap 1.3.0

Adds reproducible project archives with checksummed, relocatable atlas and
histology references; lossless embedded working histology; optional portable
histology sources; complete probe-planning persistence; and atlas-bound object
provenance. Standalone probe-setting save/load is now implemented.

### 27th July 2026
##### DriftlessMap 1.2.0

Adds a versioned four-file probe-localization export with a labeled centerline
track suitable for assigning continuous unit depths to Allen CCF coordinates
and brain structures. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 27th July 2026
##### DriftlessMap 1.1.0

Establishes DriftlessMap as an independently maintained continuation of HERBS,
with complete upstream attribution, a distinct package and application identity,
new DriftlessMap archive extensions, and compatibility for existing HERBS data
and scripts. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 25th July 2026
##### HERBS 1.0.4

Improves manual atlas registration with one reproducible triangulation mesh,
live quality feedback, safer landmark editing, and smoother seam-free warping.
See the cumulative [What’s New in DriftlessMap](WhatsNew.md) history for details.

### 25th July 2026
##### HERBS 1.0.3

Adds estimated Allen CCFv3 stereotaxic coordinate reporting and fixes atlas
hover handling at image boundaries. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 18th July 2026
##### HERBS 0.2.8.1

Reliability, security, packaging, and maintainability release. See the
cumulative [What’s New in DriftlessMap](WhatsNew.md) history for the complete change
details, reasons, compatibility notes, and upgrade instructions.

### 1st May 2023
##### Bug fix!
Fix the bugs that reported in the issue page. 
1. Bug when changing color or size of the uploaded probe obj.
2. Bug when saving projects that contain virus layers/obj.




### 23rd Dec. 2022
##### Minor update!
Feature: Keep slice angles when page number changed for volume atlas.

### 20th Dec. 2022
##### Major update!
1. Re-design probe sites visualisation.
2. Add linear silicon probe design.
3. Add multi-shanks probe design.
4. Support uploading external cell points.
5. Support un-merging merged object.

### 04th Nov. 2022
##### Minor debug.
Fix the valid values for the text input of on side points.

### 29th Oct. 2022
##### Minor update!
Fix the atlas rotation slider value changed issue.

### 28th Oct. 2022
##### Major update! 
support for displaying merged object in 2D atlas view. Only merged probe is finished implementation at the moment. 

<p align="center">
<img src="image/update_log_281022.png" width="50%">
</p>


- By clicking **2D button**, the current activated merged objects will be displayed in the 2D atlas view. 
For probe objects, all three planes will be translated to the corresponding according to the insertion voxels,
and Coronal and Sagittal plane will be rotated according to the AP and ML angle respectively. 
The probe will be shown in both Coronal and Sagittal 2D atlas view.


- By clicking **info button**, the information window of the current activated object will pop up. 
The previous way to read the information by double clicking the object is no longer supported. 
