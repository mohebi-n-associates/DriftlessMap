# Update Log

### 29th October 2026
##### DriftlessMap 2.0.0

Stable release of 2.0.0rc16 with no code changes: version 2.0.0 in `version.py`, `CITATION.cff` (dated 2026-10-29) and tests; README, MANUAL, guides and `release_validation.md` describe 2.0.0 as current and install without `--pre`. The automatic-matching tutorial describes the 2.0 steps (section plane, registration channels, pixel size, real-size placement, confidence, side choice); its screenshots are still from 1.6. The manual's step table and suggestion-dialog description mention pixel size and tissue size. Released at the owner's request with all `release_validation.md` gates pending; the waiver is recorded there.

### 29th October 2026
##### DriftlessMap 2.0.0rc16

`atlas_matching.PhysicalSection` (section resampled to the search voxel size, or sized to each slice's width without a pixel size) and `place`: coarse grid of `FIT_SCALES` × `FIT_STRETCHES` at half resolution (outline distance capped at `COARSE_REACH_UM` 450 µm), then coordinate refinement within `FIT_LIMITS` (scale 0.9–1.5, stretch 0.8–1.3, ±10°); translation by `cv2.matchTemplate` of the capped distance to the atlas outline (`OUTLINE_REACH_UM` 180 µm) per outline pixel plus `OUTSIDE_WEIGHT` 3 × tissue share outside the brain. Outline agreement = 1 − cost. `NormalisedSection` wraps the old comparison; `rank_depths`/`refine_tilt`/`_refine_page` take `section=` (pass 2 and page refinement refined; tilts keep the depth's fit and re-place only). `suggest_sections(voxel_um=, pixel_um=)`; `Suggestion.fit_scale`, `SuggestionReport.size_known` (False caps confidence at medium). App asks for a missing pixel size (`ImageView.pixel_size_declined`). Whole pipeline on Allen 10 µm coronal pages 500/800/1100 cut from the atlas, DAPI-like random-region stain, tissue at 100 % and 80 %, 0 or 35 % ventral removed: known size ≤ 110 µm, unknown size ≤ 40 µm, old ≤ 5240 µm (35 % cut: 140–5240). Time 14–27 s (old 5–7 s). Confidence was mostly low/medium on these re-stained sections because template agreement is low by construction. User's IM-1109 sections need ~1.3× enlargement (about 24 % shrinkage) to fit; 01 fits no page closely (outline cost ≈ 0.73).

### 29th October 2026
##### DriftlessMap 2.0.0rc15

`image_reader.tiff_pixel_size_um` reads OME `PhysicalSizeX` (+unit), ImageJ resolution with its `unit`, centimetre resolution, and inch resolution only below 20 µm (`PIXEL_SIZE_RANGE_UM` 0.01–1000 via `valid_pixel_size`); `TIFFReader` and TIFF folders set `scaling_val`. `ImageView.pixel_size_override` (optional `img_ctrl_data['pixel_size_um']`, None in older files), `full_resolution_pixel_size()`, `pixel_size_um()` (÷ read scale), `set_pixel_size`. `scale_bar.ScaleBar` (pyqtgraph ScaleBar picking 1/2/5×10ⁿ µm ≈ 1/5 of the view width) on `ImageStacks`, `SliceStacks` and `SliceStack`. New `actionPixel_Size`, `DriftlessMap.ask_pixel_size`, `pixel_size_dialog.PixelSizeDialog`, `user_settings.load/save_last_pixel_size`; V2 Section step pixel-size row. The user's IM-1109/IM_1112 TIFFs read 1.634 µm. Ruler uses `pixel_size_um()`.

### 28th October 2026
##### DriftlessMap 2.0.0rc14

`atlas_matching.confidence(suggestion, report, voxel_um)` returns (level, reasons): the minimum of template-edge agreement (`CONFIDENT_ANATOMY` 0.5, `FAIR_ANATOMY` 0.3), the span of depths within `DEPTH_TIE` (1.0 z) of the best in the every-few-pages pass (`SuggestionReport.depth_span`, ≤ 500 µm high, ≤ 1000 µm medium) and the plane margin when the plane was detected. `Suggestion.template_edges` and `SuggestionReport.depth_span` are new (defaulted). Thresholds measured on Allen 10 µm coronal pages 450–1100 cut from the atlas (flattened 15 %, noise): agreement 0.60–0.95, span ≤ 360 µm, depth error ≤ 60 µm; the user's two fluorescence sections: 0.09–0.19, rated low. The dialog no longer calls a plane the user chose "clear".

### 28th October 2026
##### DriftlessMap 2.0.0rc13

`auto_registration._bspline_on_intensities` fits the B-spline once per `BSPLINE_SAMPLINGS` (1.0, 0.9, 1.12: the moving image linearly resampled, `_resampled`) and combines the fits per control point: mean displacement × clip(1 − spread / (`BSPLINE_AGREEMENT` 0.05 × control spacing)), spread = largest distance of a fit from the mean. The keep test (MI improved, Dice drop ≤ 0.03) applies to the combined transform. A single fit's optimum moved with the analysis size: over `ANALYSIS_MAX_SIDE` 1700–2500 (10 sizes) a grid of atlas points on the user's sagittal section spread by up to 982 section pixels (median 339); now 7 (median 5). Coronal IM-1109 04: 4 → 4; 01: 5 → 56 at one size (2300), ≤ 18 elsewhere, as the keep decision now has little effect. Synthetic warp, 8 seeds: median error 2.42 px mean, 2.91 worst (was 2.74 / 2.82). Two fits left one coronal section unstable (up to 691 px); a 7 % tolerance gave up to 198 px. B-spline time roughly triples (sagittal action 3 s → 7.5 s).

### 28th October 2026
##### DriftlessMap 2.0.0rc12

`LayersControl.add_layer` gave every new layer `DEFAULT_BLEND_MODE` (Overlay) and emitted it; for `img-process` `layers_blend_mode_changed` applies the mode to the histology channel items, and Overlay over the black base layer renders black (inherited from HERBS). `CHANNEL_LAYERS` now starts `img-process` in Plus. Blend modes are not saved in projects, so no migration. Reproduced and verified on the user's 3-channel IM-1109 TIFF (view grab black before, section visible after) for crop and Process Image.

### 28th October 2026
##### DriftlessMap 2.0.0rc11

Channel `ImageItem`s in `image_stacks.ImageStacks` use `setAutoDownsample(True)`: `makeARGB` LUT application on the full 24.8 Mpx raster dominated each display change (0.57 s → 0.055 s per brightness step, measured through `SectionPanel.brightness` on the user's IM-1109 TIFF). Channels 5–16 now also use `CompositionMode_Plus` (only 1–4 did).

### 28th October 2026
##### DriftlessMap 2.0.0rc10

New `file_dialogs` module wraps `QFileDialog.getOpenFileName(s)`, `getSaveFileName` and `getExistingDirectory` for all 32 call sites: a start directory that is empty, the home folder or missing is replaced by the last chosen folder (a suggested file name is kept), and every choice is remembered. `user_settings.update_settings` merges keys (`save_last_atlas_path` used to overwrite the file), with `load_last_folder`/`save_last_folder`; settings schema stays 1. Tests use `tests/settings_isolation.py` (temporary `DRIFTLESSMAP_CONFIG_DIR`).

### 28th October 2026
##### DriftlessMap 2.0.0rc9

`sig_label_changed`'s mesh logic is replaced by `sync_region_meshes`: mesh keys are strings and the tree's checked ids ints, so the second pass never matched; regions checked before enabling were not shown and disabling hid nothing. `show_small_area_in_3d(visible)` takes the button state and syncs. V2 had no control for `show_child_mesh` (default False), so checked regions never appeared in 3D; the Regions tab has a "Show checked regions in 3D" check box, on by default.

### 28th October 2026
##### DriftlessMap 2.0.0rc8

`persistence._fsync_file` opened the temporary archive read-only before `os.fsync`; Windows' `_commit` rejects read-only handles with EBADF, so every `save_driftlessmap_file` (projects, layers, objects, Export all results) failed on Windows since atomic saves gained the flush. It now opens the file `r+b` and treats a failing flush as best effort (some network/removable drives cannot flush; `os.replace` stays atomic). `switch_3d_display_mode` referred to `actionMode_Dark` instead of `action3D_Mode_Dark` (AttributeError on every 3D mode switch).

### 28th October 2026
##### DriftlessMap 2.0.0rc7

Mark displays now follow their data: `_transform_accept` redraws each mapped kind with `_show_section_marks` (the 1.x transfer cleared `working_img_data` but left the plot items and layer thumbnails), `_make_pieces_of` calls `_show_atlas_marks` after the maker cleared the atlas marks, and `_show_section_marks` clears the item/layer (`_clear_section_item`) and the probe trajectory when a kind is empty. New `clear_live_marks(kind)`; `ProbeControls.delete_probe` uses it for the selected probe's unmapped marks.

### 28th October 2026
##### DriftlessMap 2.0.0rc6

`auto_registration.propose_landmarks` analyses sections larger than `ANALYSIS_MAX_SIDE` (2048) on an INTER_AREA copy (`_analysis_copy`); the moving images keep physical space in section pixels (spacing × factor), outline contours and mask lookups are scaled, and `_section_in_atlas` takes the factor. Affine results agree with full-resolution analysis within 8.5 section pixels on the user's sagittal section; small sections are unchanged. `registration_input.prepare` takes percentiles from an evenly spaced grid of about `PERCENTILE_SAMPLE` (4 M) pixels and averages channels in place. Whole action on an 11520×5990×3 section: 5.8 s → 2.2 s (macOS), peak memory several GB lower. Known: the B-spline stage on real sections is sensitive to small input changes (its keep/reject decision flips); not changed here.

### 28th October 2026
##### DriftlessMap 2.0.0rc5

`registration_section` runs `registration_input.prepare` (per-channel percentiles of the full raster, several seconds on an 11520×5990×3 section) through `run_in_background` instead of on the GUI thread before the progress dialog. `run_in_background` shows its dialog after 150 ms (was 400). V2 `widgets.button` handlers go through `widgets.respond`: wait cursor and repaint before the handler, re-entrant clicks ignored until a modal window opens (`window_shown`, called from the shell's Show hook); when a handler held the window > 0.2 s without a modal window, press/release/key events stamped within it are dropped by the shell event filter (`respond.seen`, `PRESS_EVENTS`).

### 28th October 2026
##### DriftlessMap 2.0.0rc4

`atlas_matching.suggest_sections(..., planes=)` restricts `search_planes`; `PLANE_CHOICES`, `planes_for(choice)` and `plane_from_name(path)` (one unambiguous plane word in the file name). `DriftlessMap.suggest_atlas_section(plane=None)` asks with `ask_section_plane` (QInputDialog, preselected from `section_plane` or the file name) when no plane is given and remembers `section_plane` for the session. V2 Match step: Section plane combo (`MatchPanel.chosen_plane`), and `match.find` passes it. On the user's IM-1109 coronal DAPI/DiI/DiO section the unconstrained search preferred a lateral sagittal page (outline 0.763 vs 0.769, scale-free); constrained to coronal it returns frontal coronal pages.

### 28th October 2026
##### DriftlessMap 2.0.0rc3

Lasso closing: the image lasso compared a squared distance with 5 % of the image size (a few image pixels on large images) and the slice lasso used a squared distance < 5; both now close within `LASSO_CLOSE_PIXELS` (12) screen pixels via `layer_geometry.lasso_tolerance(view_box)`/`lasso_closes`. `lasso_points_clicked` read the slot arguments as (points, ev) and tested only `ev[0]`; pyqtgraph lists points last first, so clicking the first point of a closed or overlapping lasso hit the duplicate last point and called `inactive_lasso`. It now closes only when any clicked point has index 0 (`lasso_point_closes`) and otherwise does nothing. `cut_image`/`crop_slice` close an open lasso of ≥3 points (`close_image_lasso`/`close_slice_window_lasso`) and report when there is none.

### 28th October 2026
##### DriftlessMap 2.0.0rc2

V2 theme stylesheet is set on `V2Window` instead of `QApplication` (an application stylesheet repolished all ~2,000 widgets, including ~940 hidden menu, colour-dialog and view-menu widgets); top-level windows outside the V2 window get it on `Show` via `_theme_window` (marked `v2_theme`) and follow `apply_theme`. The application event filter compares against a precomputed `EDIT_EVENTS` set and no longer calls the base filter. Toggle time 0.50 s → 0.10 s offscreen on macOS.

### 28th October 2026
##### DriftlessMap 2.0.0rc1

Release candidate of 2.0 (previews 2.0.0a1–a27). Auto-registration's B-spline now evaluates Mattes MI on every masked pixel instead of a seeded 30 % random sample and smooths every level (`BSPLINE_SMOOTHING` = 6, 3, 1.5 px): its accuracy had depended on the sample by up to 2 section pixels, which failed Linux CI from 2.0.0a17 on (median error 4.17 vs 3.41 px on macOS). Over eight noise realisations of the synthetic warp the median error is now 2.71 px mean, 2.79 px worst (was 3.56 / 4.55). Version, citation, PyPI classifier (4 - Beta), README, manual installation (`pip install --pre`, release-candidate downloads) and release-validation status updated; no other code changes since 2.0.0a27.

### 28th October 2026
##### DriftlessMap 2.0.0a27

`interfaces.requested_interface` defaults to the 2.0 interface; `--classic` and `DRIFTLESSMAP_INTERFACE=classic` select the classic one, flags before the environment. `interface_command("classic")` passes `--classic` (bundle and `-m driftlessmap`), and `run` strips interface flags before Qt sees them.

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
