# Update Log

### 28th October 2026
##### DriftlessMap 2.0.0a26

Shared project collection and transactional replacement in `project_session.py`;
recovery borrows the previous atlas/raster arrays and restores mutable metadata,
original image reader and history. `state_digest.py` hashes complete saved values
with chunked array reads; V2 schedules status checks after input/commands, with
unconditional checks before closing/replacing work and conservative error handling.
Registration fingerprints version their content and include canonical triangle
connectivity; on load, `_migrate_mapping_fingerprints` restamps the loaded
section's records whose stored fingerprint equals the pre-a26 one
(`registration_fingerprint(..., simplices=legacy)`, `MappingLedger.restamp`), so
unchanged mappings stay current while reviews still lapse. Unusable probe planning
again only warns on load instead of rolling the open back. Probe rename updates stored part names and ledger owners without
changing unit IDs or revisions. Implant build status compares stored report specs
with current specs and propagates to the UI, object files and implant CSV. Undo/redo
share a bounded budget and unrecordable edits clear history. Content signatures
record same-name rebuilds; exceptions roll back retained transactions. A failed
widget recovery preserves a recovery archive and blocks partial-session saves.
Regression coverage
and a reproducible digest benchmark were added; see `release_validation.md` for
remaining native-installation, user-evaluation and performance gates.

### 28th October 2026
##### DriftlessMap 2.0.0a25

Projects store `interface_state` (optional, plain JSON via `clean_interface_state`, no schema bump) from `interface_state_provider`; `on_project_loaded` hands it to V2 `resume` (step, view, implant selection, `ProbeBook.state`, Mark track, outline draft). Unmapped probes count in the unsaved-change digest. Point layers use `layer_points` / `plot_points`: empty layers saved as `[None, None]` made `load_project` fail part-way; they now load, and empty layers save as [].

### 28th October 2026
##### DriftlessMap 2.0.0a24

Region boundaries drawn as an RGBA overlay in `BOUNDARY_COLOUR` (`slice_stacks.boundary_rgba`) instead of an additive white image, which vanished over brightfield overlays; V2 View > Show region boundaries (`view.boundaries`, B) drives `show_boundary_btn`.

### 27th October 2026
##### DriftlessMap 2.0.0a23

V2: probes merged into the Implants card (`ProbeControls`); probe summary rows in the implant table (`probe_csv_row`); `export_all_results` with Results > Export all results (project copy via `save_project_called(path=, as_copy=True)`, objects, probe CSVs, implant table, layers); Add implant dialog widths.

### 27th October 2026
##### DriftlessMap 2.0.0a22

pyqtgraph `useNumba` is set only when numba is importable, removing a UserWarning on every image drawn without numba (e.g. Python 3.14).

### 27th October 2026
##### DriftlessMap 2.0.0a21

Atlas page slider: throttled drag updates (40 ms) instead of a debounce that withheld every page during a continuous drag; coronal pages are copied contiguously before display (10 µm: preview 108 → 4 ms, full page 260 → 25 ms).

### 27th October 2026
##### DriftlessMap 2.0.0a20

Suggest Atlas Section keeps sections upright and unflipped unless clearly better otherwise, and shows the orientation it applies.

### 27th October 2026
##### DriftlessMap 2.0.0a19

Find atlas section ranks depth in two passes and compares close orientations on sampled pages; checked on the Allen 25 µm atlas.

### 27th October 2026
##### DriftlessMap 2.0.0a18

Find atlas section prefers upright orientations and compares close ones by anatomy; the coronal atlas slider previews pages while dragging.

### 27th October 2026
##### DriftlessMap 2.0.0a17

Find atlas section and Suggest landmarks handle brightfield sections (inverted, illumination flattened, black background); hole filling fixed for tissue touching two edges.

### 27th October 2026
##### DriftlessMap 2.0.0a16

Find atlas section searches fine atlases on a sampled copy and refines the pages at full resolution (about 8x faster at 10 µm).

### 27th October 2026
##### DriftlessMap 2.0.0a15

Implants card in the 2.0 preview: outline (draw or propose), mark the tip or bottom, map, build and report fibers and microprisms.

### 27th October 2026
##### DriftlessMap 2.0.0a14

Implants in the engine: map outlines, build, undo, save in projects, 3D display, object import/export and the implant CSV.

### 27th October 2026
##### DriftlessMap 2.0.0a13

Implant model: fibers and microprisms are fitted to mapped section outlines (fiber tip; prism bottom DV and ML edges), with warnings.

### 27th October 2026
##### DriftlessMap 2.0.0a12

Map, Update mapping, Make parts and Build can be undone and redone as whole steps (Ctrl+Alt+Z / Ctrl+Alt+Shift+Z).

### 27th October 2026
##### DriftlessMap 2.0.0a11

Update mapping and Edit marks for kept marks; rebuilding leaves out replaced parts; Edit parts works for built contours.

### 27th October 2026
##### DriftlessMap 2.0.0a10

Mappings, parts and built objects are labelled out of date when the registration changes or the marks are mapped again; object exports record the status.

### 27th October 2026
##### DriftlessMap 2.0.0a9

Mapping keeps the section's marks in mapping records; mapping or making parts again replaces earlier results instead of duplicating them.

### 27th October 2026
##### DriftlessMap 2.0.0a8

Projects save mapping records and each object's mapping origin (groundwork for keeping section marks after mapping).

### 27th October 2026
##### DriftlessMap 2.0.0a7

Pyramidal TIFFs can be read at a stored lower resolution with the Scale slider; the level is saved and restored with the project.

### 27th October 2026
##### DriftlessMap 2.0.0a6

The desktop application can open the 2.0 preview (Help > Open the 2.0 Preview, or `--v2`), and the preview can open the classic interface.

### 27th October 2026
##### DriftlessMap 2.0.0a5

The 2.0 preview's light and dark themes now restyle the 1.x tool options, atlas controller and region tree.

### 27th October 2026
##### DriftlessMap 2.0.0a4

Choose which time point (or other further axis plane) of a TIFF to read; the choice is saved in the project.

### 27th October 2026
##### DriftlessMap 2.0.0a3

Channels named in a file without stored colours get conventional colours (DAPI blue, GFP green, tdTomato red, Cy5 magenta).

### 27th October 2026
##### DriftlessMap 2.0.0a2

**Suggest Atlas Section** names the anatomical side: where the animal's right is in the section, or the Right or Left hemisphere for sagittal sections.

### 27th October 2026
##### DriftlessMap 2.0.0a1

In the 2.0 preview, actions that cannot run yet are greyed out with the reason in their tooltip, Match and Register show what to load first, and empty views and side panels are replaced by short guidance.

### 28th September 2026
##### DriftlessMap 1.6.1

Fixes **Show Boundary**, which drew atlas region boundaries almost black and therefore invisibly. **Propose Landmarks** now suggests up to 10 landmarks on features both images show (outline tips and notches, shared internal edges) instead of about 36. Adds a tutorial for the automatic section and landmark suggestions.

### 27th September 2026
##### DriftlessMap 1.6.0

Adds **Atlas > Suggest Atlas Section...**, which suggests the atlas plane, section, tilt and histology orientation for a loaded section. Also adds **Atlas > Propose Landmarks**, which fits the shown atlas slice to the histology and fills in registration landmarks for review. SimpleITK is now a required dependency.

### 27th September 2026
##### DriftlessMap 1.5.0

Review release: corrects probe site faces, source-voxel mirroring, brain-entry detection, region path lengths, image scale, pixel-centre warps, voxel flooring and surface depth; closes a mesh-cache code-execution hole and an allocation bomb; stops several ways of losing work; fixes many crashes; and runs long operations in the background. See the "re-export if…" list in [What’s New](WhatsNew.md) before reusing results from earlier versions.

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
