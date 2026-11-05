# DriftlessMap Agent Guide

This is the concise working map for automated contributors. Read this file
before exploring the repository. Use `rg` to open only the files relevant to
the task. `AGENTS.md` and `CLAUDE.md` must remain identical; update both in the
same change whenever architecture, behavior, commands, formats, dependencies,
or important workflows change.

## Project identity

- Source version: **2.9.3, unpublished** (fixes to 2.9.2's Undo). Do not tag or publish this version
  without a new owner instruction. Current published release: DriftlessMap 2.9.0 (5 November 2026; planning services,
  solid clearance, responsive jobs and direct pyramid loading). 2.8.8
  (4 November 2026; Space out). 2.8.7
  (a prism's tip at its imaging face's bottom left corner). 2.8.6 (4 November 2026; probe planning,
  `probe_planning_design.md` Phases 1-4, `reviews/2.8.3` R1-R8, planned
  fibers and prisms (its section 6) and probe hardware (section 7); the owner
  numbers the probe-planning phases 2.8.0-2.8.3, one feature), published on
  PyPI and GitHub with 2.8.0-2.8.5. Before it: 2.7.0 (3 November 2026; the
  first release since 2.0.0, including 2.0.1-2.3.0 and multi-section
  projects). 2.0.0
  (29 October 2026) followed the 2.0.0aN previews and 2.0.0rc1-rc16. The owner released it with the
  `release_validation.md` gates still pending (recorded there as waived); keep
  recording evidence for them. Later fixes become 2.0.N, features 2.N.0.
  Never give V2 work 1.x numbers. A published GitHub release runs `release.yml` (PyPI, trusted
  publishing) and `desktop-builds.yml` (Windows ZIP and macOS DMG attached to
  the release).
- Desktop application for histology registration, atlas mapping, probe
  reconstruction, anatomical annotation, and data export.
- Python package: `driftlessmap`; GUI: PyQt6 + pyqtgraph/OpenGL.
- Supported Python: 3.10-3.14. CZI support currently requires 3.10-3.13.
- OpenCV uses the headless wheel because PyQt6 owns the GUI and Qt plugin
  runtime; do not reintroduce the GUI OpenCV wheel.
- DriftlessMap grew out of HERBS, now a legacy project. `ORIGINS.md` (the
  HERBS legacy note) is the one place describing the connection; HERBS
  developers are credited as acknowledgements, not authors (package metadata,
  `CITATION.cff`, `AUTHOR.txt`, `CONTRIBUTORS.md`, About dialog). Keep the
  HERBS copyright notice in `LICENSE.txt` (MIT condition), and preserve legacy
  HERBS file compatibility and coordinate field names where documented.

## Undo (2.9.2, fixed in 2.9.3)

The top Undo button and Ctrl/Cmd+Z (`undo_called`) take back the newest of three
histories' next steps; Ctrl/Cmd+Shift+Z (`redo_called`) the oldest undone. Every
step gets a number from `_next_edit_seq`; `next_undo`/`next_redo` compare them
and name the step (V2 button tooltips).
- Mapping steps: `TransactionHistory` (10 steps, 500 MB; `Transaction.seq`) via
  `undoable`. Recording or undoing one clears the per-tool list.
- Point edits: `transactions.PointHistory` (200 steps) via the `point_action`
  decorator on probe/cell/contour click and erase handlers. It keeps only
  `_point_state` (the point lists, never objects or masks): a whole-document
  snapshot per click (2.9.2) cost ~0.4 s with a 40 MB object and pushed Build
  out of the 10 mapping steps. Point steps older than a mapping step that left
  its history are dropped (`TransactionHistory.horizon`, `barrier`;
  `_drop_points_past_horizon`).
- Per-tool edits: `action_list`/`action_id` (pencil, eraser, lasso, wand; six
  post-edit states, entries carry `seq`). `save_current_action` is skipped inside
  a mapping step or point step. `forget_layer_actions` resets the position only
  when it removed entries.
A new edit of any kind clears every redo branch. Section/document transitions
clear all histories (`_forget_point_history` with each reset). This is not a
universal undo for view, registration, file or display settings.

## Fast architecture map

- `driftlessmap/app.py`: main window, workflow orchestration, menu handlers,
  project/layer/object persistence, atlas and histology loading.
- `driftlessmap/project_io.py`: GUI-free project helpers (default working
  data, merging older payloads, input pre-fingerprinting, export file names).
  Atlas kind, path and load fingerprint are committed only through
  `DriftlessMap._commit_atlas`; per-view display updates go through
  `DriftlessMap._atlas_view_items`. `load_volume_atlas` refuses a different
  atlas while the document has results (`atlas_replacement_problem`: same
  folder unchanged, or identical content elsewhere, is allowed, and only while
  the loaded folder still matches its load-time signature); project
  loading passes `replacing_document=True`. V2 File > New window starts a
  fresh process (`open_new_window`). Save (`project.save`) writes to
  `current_project_path` without a dialog; `project.save_as` asks; the
  portable copy is written `as_copy`. Every shell message is kept in
  `activity` (warnings/errors counted on `activity_button`, `show_activity`).
  Below `COMPACT_WIDTH` the inspector folds away (`resizeEvent`); step panels
  must fit the 1100 px minimum window (test). Below `COMPACT_RAIL_WIDTH`
  the step rail shows numbers (`set_rail_compact`). 2.6.0 usability (review
  U items): `v2/section_bar.SectionBar` above the canvas switches sections in
  place (`section.previous/next`); `v2.state.annotation_pipeline` drives
  Annotate's one next-step button; Results repairs a stale object
  (`object_contributions`, `repair_plan`: changed sections are remapped one by
  one in section order, then one build; `stale_contribution` follows it; the
  object stays selected by `obj_id`, `ObjectControl.select_object`); Register
  gates Mark review complete on a checklist, also for the `register.review`
  command (`needs_review_checks`), and offers Blink/Checkerboard
  (`checkerboard`), drawn on `RegisterPanel.compare_item`, never on the
  overlay item that saves and exports read; leaving the step ends them; the Section table has All/None per column (`tick_all`);
  Edit > Mapping history (`TransactionHistory.labels`); `add_sections` adds
  files in natural order or TIFF pages as sections (the stack is decoded once:
  later pages get `TIFFReader.shared()` through `tiff_reader=`, and
  `ImageView.volume_img` is a read-only view of the reader's stack, never
  written in place; `progress(done, total, name)` returning False stops between
  sections; `tests/benchmark_tiff_pages.py`); the empty canvas offers
  three starts (`start_probe_plan`; after an atlas is loaded, the Project
  step's Atlas card and the `probe.plan` command). 2.7.0: New project in the
  same window (`project.new`, `ProjectSessionMixin.start_new_project`, from
  the start-up `ProjectSnapshot` kept by `remember_empty_document`; a kept
  volume atlas stays in memory and gets its frame from
  `reset_tri_points_atlas`); Steps/Objects buttons at the ends of the view
  bar (`view.task_column`, `view.inspector`); `v2/channel_strip.ChannelStrip`
  above the histology image (one brightness slider per channel through
  `channel_display`); brightness sliders are brighter to the right
  (`slider_brightness`).
- `driftlessmap/probe_plans.py` (GUI-free) and `probe_plan_engine.py`:
  planned probes as poses (`probe_planning_design.md`; Phase 1 in 2.8.0).
  `ProbePlan` holds the tip (Bregma-relative um: ML right +, AP anterior +,
  DV dorsal +), `ap_tilt_deg`/`ml_tilt_deg` (signed projected tilts, the
  angles `get_angles` reports unsigned), `roll_deg` (0: contacts face
  anterior; `face_normal`), probe settings and shank offsets. `PlanBook`
  keys plans by probe name (`from_list` returns plans and problems).
  `plan_readout` (entry: exact crossing into the first brain voxel coming
  down the line, `surface_entry`; depth along the probe; `regions_along`;
  warnings) is cheap and drives the live readout; `region_centre` (strided,
  one hemisphere) backs Snap tip to region. `ProbePlanEngineMixin.set_probe_plan`
  stores and builds a plan in one `undoable` step: `calculate_probe_info`
  (pre-plan, face normal from the roll) on `shank_lines`, giving merged-probe
  objects `"<probe> plan"` (`"<probe> plan shank N"`) with `plan_of` and the
  plan in their data; `plan_build_status` gives CURRENT or BUILD_CHANGED.
  `ProbeBook` leaves plan objects out of a probe's parts/built and renames
  and deletes plans with their probe. Plans are document state saved as the
  optional payload key `probe_plans` (no schema bump), part of undo
  transactions, and exported as `probe_plans.csv`. `plan_overlay.PlanOverlay`
  projects each plan (and `plan_previews`, the plan being edited) onto the
  atlas views. V2: `v2/plan_editor.PlanEditor` (the Plan section of
  `ProbeControls`; edits preview at once and commit after `BUILD_DELAY_MS`).
  2.8.1 (Phase 2): `ProbePlan.bank` (recording window, 384 channels counted
  from the tip; None for every site; absent in 2.8.0 plans means 0);
  `site_offsets_um`, `recording_sites`, `window_coverage` and the readout's
  `contacts_um`/`window_um`/`window_regions`; `column_surface`,
  `plan_from_surface` (Edit by: Entry and depth; tilts turn about the
  entry) and `tip_to_surface`; `probe_plane` (labels in the plane of the
  shank's face) drawn by `v2/shank_view.ShankView` with the shank strip;
  keyboard steering (`plan_editor.KEYS`, `steered`, an application event
  filter installed only while Steer with keys is on, ignoring text inputs
  and other windows).
  2.8.2 (Phase 3): `ProbePlan.craniotomy` (an id; absent means None);
  `Craniotomy`/`CraniotomyBook` (centre ML/AP and diameter in um),
  `craniotomy_warning`, `fit_craniotomy` (exact smallest enclosing circle
  plus margin); `clearances`/`clearance_warning` (segment-to-segment
  distances from `CLEARANCE_ABOVE_UM` above each entry, per shank);
  `arm_from_tilts`/`tilts_from_arm` (azimuth from anterior towards the
  right, elevation from vertical; exact inverses); `bregma_lambda_scale`,
  `validated_surgery_settings`. The engine's `probe_plan_readout` adds
  `arm`, `craniotomy`, `closest` (other plans, previews included) and
  `scale`; `atlas_bregma_lambda_um` uses `AtlasView.atlas_lambda` (the
  processed atlas's Lambda, None when absent, as for the Allen atlas).
  Payload keys `craniotomies` and `surgery_settings` (optional, document
  state, undoable; plans whose craniotomy is missing lose the link with a
  message). `PlanOverlay` draws craniotomies on the horizontal view.
  `PlanEditor`: Angles (QSettings `plan/angles`), Craniotomy list, Surgery
  menu (`craniotomy_dialog`, `bregma_lambda_dialog`).
  2.8.3 (Phase 4): `ProbePlan.targets`/`avoid` (region ids; absent means
  none); `ProposalRequest` and `propose_plans` (screen lines per tilt on a
  strided copy by projecting target voxels across each direction,
  `_screen_lines`; evaluate them at full resolution with `_LineScorer`,
  sliding the recording window by cumulative sums and stopping before
  avoided regions, the midline margin, the other side, the shank's end or
  leaving the brain; refine the best by 1° and rank with `_key`/`_rank`:
  reached, window coverage less `PROPOSAL_TILT_PENALTY_UM_PER_DEG` per
  degree, shallowest; best per tilt band kept); `_reasons` explains failures
  from the scorer's counts and `_line_spans_targets`. `target_coverage`
  feeds the readout's `targets`. Engine `propose_probe_plans` (worker
  thread). V2 `v2/proposal_dialog.ProposalDialog` (Record/Keep out of lists,
  `checked_regions`, side, midline, tilt limits, craniotomy, results table,
  reasons) from Propose… in `PlanEditor`.
  2.8.4 (`reviews/2.8.3/RESOLUTION.md`): proposals check every shank at the
  plan's roll (`_LineScorer` samples each shank; tips only in tissue on every
  shank; coverage summed over shanks, ranking by the union) and final
  candidates pass `track_checks` (exact voxel walk, `traverse`), whose
  messages the readout shows too (plan.avoid, gaps); membership is per target
  (`region_ids`, `_members`); `ProposalRequest.check` refuses a target equal
  to or inside an avoided region; `propose_plans(progress=)` may stop
  (`SearchStopped`). Staged plan edits live in the engine
  (`stage_probe_plan`, `plan_previews`, `PLAN_SETTLE_MS`): counted by
  `state.scientific_digest`, flushed by `flush_plan_edits` before save,
  export, undo/redo, any `undoable` action and section switches, dropped by
  `discard_plan_edits` in `_restore_project_payload`; never keep pose edits
  only in the editor. `plan_candidates` (display only) draws a proposal
  under inspection. `ProjectSnapshot` keeps the atlas Lambda;
  `surgery_scale` is None (unavailable) when the animal distance is set but
  the atlas's is unknown. Steering ends when the Plan section is hidden.
  2.8.5: `ProbePlan.kind` (`probe`/`fiber`/`prism`) with `specs` and
  `implant_id` (written only for implant plans; kept under the implant's
  name; probe and implant names exclude each other); `device_lines` (shanks,
  fiber axis and rim, prism footprint grid with the bevel's `prism_rise`)
  drive `track_checks`, `clearances` and the craniotomy fit; `planned_model`
  (cylinder, new `prism` model type in `implants.model_section`),
  `face_view` (what a prism's imaging face looks into), prism length check.
  Prism specs gain `length_um` (3000) and `bevel_deg` (45); `FIT_SPECS` are
  the settings fits use (others never put a built implant out of date).
  Engine `implant_plan`, `default_implant_plan`, `_build_implant_plan`
  (`merged fiber`/`merged prism` `"<name> plan"`, `plan_of`, no
  `implant_id`); rename/settings/delete of an implant carry its plan.
  `PlanEditor` gets its device from its owner (`plan_colour`, `use_colour`,
  `plan_kind`, `default_plan`, `plan_removed`): `ProbeControls`, and the
  Implants card for fibers and prisms. The start screen's Plan a probe/fiber/
  prism (`start_probe_plan(kind)`, commands `probe.plan`, `fiber.plan`,
  `prism.plan`) ask for the atlas folder when none is loaded. A prism's
  imaging window (`imaging_window_um`: width × depth / tan(bevel)) is drawn
  in the Imaging face view and must lie in the brain. Regions: the Regions
  tree has a Find box (`LabelTree.filter_labels`, `show_labels` checks
  regions so the atlas and 3D show them); `v2/region_picker.pick_region`
  for Snap tip to region and Propose's Add…, whose regions are shown.
  Fibers and prisms are filled in 3D (`implants.model_mesh`,
  `obj_items.ImplantItem`, which takes `setData(color=, width=)`);
  `set_region_opacity` (Regions tab slider) makes region meshes translucent.
  Fibers have a ferrule (`fiber_length_um`, `ferrule_diameter_um`,
  `ferrule_length_um`; model part `ferrule`, `model_parts`); `plan_segments`
  carries radii and `clearances` subtracts them.
  2.8.6: `probe_hardware.py` (`PARTS`, `DOVETAIL`, `hardware_boxes`,
  `hardware_model` of type `boxes`, `hardware_segments`) draws a planned
  NP1.0/NP2.0 probe's shank, base, flex, connector/headstage and dovetail
  (gray child of the 3D track, `PlanOverlay`) and adds them to
  `plan_segments`; `show_probe_hardware`/`set_probe_hardware_shown`
  (Hardware: `SHOWN` none, probe only (`PROBE_PARTS`, track child
  `hardware`) or with the backend (child `backend`); `show_hardware_of`). Pinpoint's GPL models were measured, never copied.
  `region_meshes.region_surface` builds one smooth surface per checked
  region (with sub-regions) in the segmentation frame (`atlas_label`
  reordered back); `sync_region_meshes` draws it instead of the parts'
  meshes.
  2.8.7: a prism's tip is its imaging face's bottom left corner as you face
  it (`PRISM_TIP_AT`, saved as `tip_at`; `from_dict` moves older plans' tip
  from the edge's middle, `prism_corner_from_middle`; `face_middle_um` for
  the model, face view, focus, default plan and snapping); prisms face
  posterior by default.
  2.8.8: `space_plans` (tilts movable plans about their tips so all keep a
  gap: ML before AP, smallest largest tilt, back towards the start; `moved`,
  `clashes`, `ap_used`), engine `space_out_plans` (one undoable step),
  `v2/spacing_dialog.SpacingDialog`, Space out… and command `plan.space`.
- 2.9.0: spacing trials calculate only surface entry and geometry;
  anatomical readouts remain in build/display. Fixed-device conflicts and
  overlapping fixed tips remain visible in the spacing report.
- `plan_service.PlanService` owns bounded copied readouts and pair results keyed
  by the complete plan payload and installed immutable PlanAtlas identity.
  `solid_geometry` checks convex prism solids, including containment, against
  other prisms and device capsules. `object_export.write_objects` writes captured
  object payloads without widgets. Background jobs optionally take a cancellation
  Event; spacing checks it between trials and rejects changed inputs on completion.
  TIFFReader accepts an initial scale, selecting single-plane pyramid levels
  before decoding. Region surfaces are calculated in a worker, installed in Qt
  on the GUI thread. PyQt6 6.12.0 is excluded for malformed typing stubs.
- `driftlessmap/project_session.py`: `ProjectSessionMixin.project_payload` is the
  shared saved-state collector. `load_project` snapshots the active document and
  restores it on failure, including its original reader, in-memory atlas and undo
  history; `ProjectSnapshot` borrows arrays and copies mutable metadata, so rollback
  never requires the old source files. If restoring widgets also fails, a recovery
  `.dmap` is written to a reported temporary folder and partial-session saves are
  disabled until a document is successfully opened. `_restore_project_payload` is the low-level
  installer; do not call it directly outside loading/recovery.
- `driftlessmap/state_digest.py`: exact recursive saved-state hashing, reading arrays
  in chunks and deduplicating shared arrays within each call (never across mutable
  edits). V2 checks after user input/commands instead of rescanning on idle timer
  ticks; destructive transitions always check, and check failures count as dirty.
- `driftlessmap/persistence.py`: safe versioned ZIP format, JSON manifest,
  NumPy arrays with pickling disabled, streamed portable attachments, and
  restricted legacy-pickle reader.
- `driftlessmap/provenance.py`: SHA-256 input identity, relative/absolute path
  hints, relocation and verification, portable source packing/extraction.
- `driftlessmap/image_reader.py`: conventional, TIFF, folder, and embedded
  active-raster readers. TIFF axes beyond C and the paged axis are read at
  the plane in `plane_selection` (saved in `img_ctrl_data`; default first
  plane); `DriftlessMap.select_image_planes` re-reads the section.
  Unnamed channels whose colours the file stores (ImageJ LUTs, OME Color)
  are named after those colours (`channel_names_from_colors`); otherwise the
  1.x positional names apply.
  Pyramidal single-plane TIFFs (`has_levels`) are read at a stored level
  chosen by the Scale slider, recorded through the saved `image_scale`. `czi_reader.py` handles optional CZI input.
  Pixel size: readers set `scaling_val` (um per full-resolution pixel; TIFF via
  `tiff_pixel_size_um`: OME, ImageJ unit, centimetre tags, inch only below
  20 um; `valid_pixel_size` bounds it). `ImageView.pixel_size_um()` divides the
  file's or user-entered size (`pixel_size_override`, saved as optional
  `img_ctrl_data["pixel_size_um"]`, `DriftlessMap.ask_pixel_size`,
  `pixel_size_dialog.py`, Image > Pixel Size) by the read scale; the ruler and
  `scale_bar.ScaleBar` (histology, atlas views by `vox_size_um`, slice atlas by
  its calibrated width) use it.
- `driftlessmap/image_view.py`: image scene/page/channel/LUT state. Channel
  `ImageItem`s (`image_stacks.py`) use `autoDownsample` and additive blending
  for all 16 channels. In the V2 Section step the brightness, contrast, Min,
  Max, Gamma, Auto and Reset controls act on the rows ticked under Adjust,
  which follow Show until the user ticks them (reset for a new section).
  `V2Window` re-evens the view splitter (`_balance_views`, deferred one
  event-loop pass) whenever the set of visible view frames changes, including
  layouts the engine switches itself (loading an atlas or a section).
  Focus mode (`view.focus`, Ctrl+Shift+F, header Focus button,
  `V2Window.toggle_focus`) hides both side columns through the View menu's
  Show task column / Show objects and layers items.
- `driftlessmap/atlas_matching.py`: GUI-free suggestion of the atlas plane,
  orientation and slice that match a histology section (silhouette search on
  slices exactly as `AtlasView` displays them). Coronal/horizontal matches are
  ambiguous up to a left-right mirror; the user chooses the side, which the
  dialog names anatomically (`animal_right_edge`, `sagittal_side`; positive
  ML is the animal's right). The user names the section plane
  (`planes=`, `planes_for`, `plane_from_name`; `DriftlessMap.ask_section_plane`,
  V2 Match step Section plane): outlines are compared without physical size, so
  planes are confused. `suggest_sections` searches a copy sampled by
  `search_factor` (at most `SEARCH_MAX_SIDE` voxels per side) and refines
  each suggested page at full resolution (`_refine_page`); suggested and
  candidate indexes are always full-resolution pages. `tissue_mask` and
  `histology_gray` detect brightfield sections (`bright_background`),
  flatten their illumination (`_absorbance`) and present tissue bright on
  black, as the atlas template is; auto-registration shares them.
  Coronal/sagittal sections stay upright unless another orientation's outline
  is better by `UPRIGHT_OUTLINE_MARGIN`; mirror pairs resolve to the
  unflipped form (`preferred_form`); `plane_candidates[0]` carries the chosen
  orientation, which the dialog shows and applies. Otherwise orientations
  within `ORIENTATION_MARGIN` of the best outline are compared
  by internal anatomy (`orientation_contenders`, `choose_orientation`) on
  every few pages, with a preference for upright ones; depth is ranked in two
  passes (`DEPTH_PAGES` pages, then page by page around the best
  `DEPTH_NEIGHBOURHOODS`). While the coronal page slider is dragged,
  `AtlasView` draws a sampled preview page (`PREVIEW_MAX_SIDE`) at most every
  `DRAG_UPDATE_DELAY_MS` (a throttle, not a debounce) and the full page on
  release (`PageController.sig_page_settled`); coronal pages are strided in
  memory, so each is copied out of the volume once before display.
  With `voxel_um` (the app passes the atlas voxel size and
  `ImageView.pixel_size_um()`), depth, tilt and page refinement place the
  section inside each slice (`PhysicalSection.place`: physical size up to
  `FIT_LIMITS` shrinkage/flattening, capped outline distance
  `OUTLINE_REACH_UM`, `OUTSIDE_WEIGHT`; coarse grid then coordinate
  refinement), which copes with partial sections; without a pixel size it is
  sized to each slice's width (`UNKNOWN_*`, `report.size_known` False caps
  confidence at medium). Without `voxel_um` the old `NormalisedSection`
  (outlines scaled to fill one box) is used. `Suggestion.fit_scale` is atlas /
  section size. The app asks for a missing pixel size first
  (`ImageView.pixel_size_declined` after "I don't know").
  `confidence(suggestion, report, voxel_um)` rates each candidate high/medium/low
  from template-edge agreement (`CONFIDENT_ANATOMY`/`FAIR_ANATOMY`), the span of
  near-equal depths (`report.depth_span`, `DEPTH_TIE`) and the plane margin;
  thresholds come from atlas-cut sections, not yet real ones.
  `confidence_points` gives the same judgement as 0-100 (each criterion's
  fair threshold 50, confident 80; the weakest wins). `PhysicalSection.measure`
  weights the anatomy agreements by the share of the section's tissue inside
  the slice's brain, so edge slices holding a sliver of brain cannot win.
  V2 Match step: `state.sagittal_hemisphere` (side and mm from the midline,
  `origin_3d[0]`), `MatchPanel.show_other_hemisphere` (`mirrored_index`), and
  a warning when `hemisphere_from_name` disagrees with the page shown.
  `section_suggestion_dialog.py` shows ranked candidates for confirmation and
  `DriftlessMap.apply_section_suggestion` sets the view, page, tilt and
  histology orientation. Tilted matches use `tilted_slice`, which must stay
  identical to `AtlasView.rotate_*_current_slice`.
- `driftlessmap/registration_input.py`: GUI-free registration-input recipe
  (Legacy = unchanged raw image, 1.6 behaviour; or explicit channels, each
  percentile-normalised (percentiles from a grid sample of
  `PERCENTILE_SAMPLE` pixels) and averaged into one analysis plane). Display
  settings never enter it. `DriftlessMap.registration_section()` applies it
  for Suggest Atlas Section and Propose Landmarks; a new multichannel image
  has no recipe until the user chooses (`registration_channels_dialog.py`).
- `driftlessmap/registration_review.py`: human review of the current
  registration, tied to a fingerprint of landmarks, frame points, plane, page,
  tilt, image size, triangle connectivity and, for multi-page/scene/plane
  files only, the shown part (`image_reader.source_selection`, carried by
  `EmbeddedImageReader` when the original is missing); any change makes it lapse. Fingerprint
  content version 2 (2.0.0a26) deliberately invalidates older review fingerprints;
  old results remain loadable. Mapping records of the loaded section whose stored
  fingerprint is the pre-a26 one for the unchanged registration are restamped on
  load (`_migrate_mapping_fingerprints`), so they stay current. Unusable saved probe
  planning warns and the project still opens. Pre-schema-3 work is
  "not recorded", never "reviewed". Saved as `registration_review`.
- `driftlessmap/auto_registration.py`: SimpleITK registration (moment-based
  affine on silhouettes, then a B-spline on intensities with Mattes MI over
  every masked pixel, smoothed at each level by `BSPLINE_SMOOTHING`; random
  sampling made results seed- and platform-dependent, and multithreaded ITK
  made them run-dependent, so the fits run on one ITK thread
  (`_single_itk_thread`; running them in parallel threads was not exact);
  sections are analysed on
  a copy of at most `ANALYSIS_MAX_SIDE` pixels, `_analysis_copy`, with
  physical space kept in section pixels) that
  proposes atlas-to-histology landmark pairs in DriftlessMap pixel-edge
  coordinates. The B-spline is fitted once per `BSPLINE_SAMPLINGS` grid of the
  section; each control point keeps the mean displacement, scaled down to
  zero as the fits disagree by `BSPLINE_AGREEMENT` of the control spacing (a
  single fit moved up to 0.8 mm with the analysis size). It is kept only if
  it improves the intensity match without degrading the outline. Up to 10 landmarks are suggested:
  outline tips/notches (skipping image-edge cuts and label-only outline) and
  internal edges scored by local agreement between atlas and resampled
  section edges, so single-image edges are never chosen.
- `driftlessmap/atlas_loader.py`, `atlas_view.py`, `atlas_transform.py`:
  processed atlas loading, display, coordinate transforms.
- `driftlessmap/rat_atlases.py` (GUI-free): the downloadable rat atlases,
  `WAXHOLM` (NITRC v4.01 annotation zip with its `.ilf` hierarchy, T2* and
  mask v1.01; NITRC needs `i_agree`, which the dialog asks the user for) and
  `SWC_FEMALE_RAT` (BrainGlobe `whs_sd_swc_female_rat_39um`, converted from
  `asr` to WHS RAS order by `brainglobe_to_whs`; its annotation equals WHS
  v4.01 where labelled). Both share WHS grid, Bregma/Lambda and region IDs.
  Files are pinned by SHA-256. `PREPARE[key]` writes the template,
  annotation and `atlas_labels.pkl` (`label_info_from_ilf` /
  `label_info_from_brainglobe`) before the shared processing; the worker
  then writes `atlas_axis_info.pkl` (`waxholm_axis_info`: identity, as the
  Atlas Processor gives for RAS), which probe builds and cell points need.
  `atlas_downloader.AtlasDownloader(atlas=...)` is the 1.x dialog;
  `v2/rat_download_dialog.RatAtlasDownloadDialog` rebuilds its layout.
  `download_utils` serialises manifest writes (parallel downloads).
- `driftlessmap/region_colors.py` (GUI-free): `AtlasView.set_data` passes
  `label_info` through `distinct_region_colors`, which finds touching areas in
  the label volume (sampled every `STEP` voxels) and moves an area whose colour
  is within `MIN_DIFFERENCE` (CIE76) of a touching one to the nearest colour
  clear of all of them, larger areas first. Areas are a label plus descendants
  of the same colour (layers). `label_info["atlas_color"]` keeps the atlas's
  own colours; `color` (label tree defaults, LUTs, meshes, probe exports) holds
  the new ones. Landmark dots default to red (`toolbox.LANDMARK_COLOR`; saved
  old gray defaults open red).
- `driftlessmap/triangulation.py`: deterministic piecewise-affine registration,
  topology, validation, transforms, and warping.
- `driftlessmap/mapping_records.py` and `transactions.py`: Phase 3 (see
  `phase3_mapping_design.md`). `MappingLedger` keeps one record per mapped
  unit (section, kind, probe) with the kept section marks and the
  registration fingerprint. `DriftlessMap.transform_accept(probe=...)`
  records each mapped kind; `make_pieces_of(kind)` gives parts their
  `(unit, revision)` origin (object control `obj_derivation`) and replaces
  earlier parts of the same unit; `atlas_mark_origin` ties atlas marks to
  their record until they are edited. `update_mapping(unit)` re-maps one
  unit's kept marks without touching other live marks; `edit_mapped_marks`
  returns them to the section; merges call `_drop_superseded_pieces`.
  `remove_mapping(unit)` forgets a record and deletes its parts and unmade
  atlas marks, first taking apart built objects that contain one
  (`_delete_results_of`, so a rebuild cannot bring the part back); mapping
  marks that were returned for editing and then all deleted
  (`cleared_edit`) removes the mapping the same way, also from
  `map_implant` and `ProbeBook.add_section`.
  `TransactionHistory` (10 steps, 500 MB, compressed masks) backs
  `DriftlessMap.undoable(label)`, which records only the outermost action
  (wrap new mapping, part or build entry points in it), and
  `undo_mapping_step` / `redo_mapping_step`. Undo and redo share the memory budget;
  unrecordable mutations clear both stacks as a history barrier. Transaction
  signatures hash actual object/source contents, so rebuilding under the same
  name is undoable; the packer borrows state and copies it once.
- `driftlessmap/implants.py` (GUI-free) and `implant_engine.py`: optical
  fibers and microprisms (`implants_design.md`). `ImplantBook` holds the
  implants (id, name, kind, validated specs, colour); `fit_fiber` /
  `fit_prism` fit a cylinder / block to mapped outlines (Bregma-relative
  voxels: ML right, AP anterior, DV dorsal) and return a report (fiber tip;
  prism bottom DV and medial, lateral, centre and face ML; regions;
  stereotaxic estimate; warnings). `ImplantEngineMixin` (mixed into
  `DriftlessMap`) keeps `implant_outlines` for the loaded section;
  `map_implant` resamples the polygon, maps it, records it as kind
  `fiber`/`prism` (the record's `probe` field holds the implant id) and makes
  the section's part at once (`"<name> - piece"`, data carries
  `implant_id`); `build_implant` fits all parts into `merged fiber` /
  `merged prism`. Implants and live outlines are saved in the project and in
  undo transactions. `implant_overlay.ImplantOverlay` (created by the engine)
  outlines each visible built fiber/prism on the atlas views where the shown
  slice cuts its fitted model (`implants.model_section`, slices mapped with
  `AtlasView.get_*_3d`); `show_implant_on_atlas` moves the pages to the tip.
  V2: `v2/implant_card.py` and `v2/outline_editor.py`
  (draw, Propose by flood fill inside the brain envelope, tip/bottom point).
  Unfinished outlines belong to their section (`OutlineEditor.follow_section`
  parks them in `drafts`; saved in `interface_state` with their section id).
  Undo help: `v2/widgets.undo_help()` (native shortcut text via `keys`) is
  the tooltip text for Mark track, Map this section, Build and Delete; only
  ways verified by tests are named (Ctrl+Z removes the last probe point).
  Probes are listed in the same Implants card but stay on the named-probe
  path: selecting one shows `v2/probe_card.ProbeControls`. The implant table
  adds a summary row per built probe (`probe_csv_row`). `implant_build_status` compares
  the retained report specs to the current implant specs; mismatches are out of date
  in the UI and exports until rebuilt. The implant CSV includes a `status` column.
  `DriftlessMap.out_of_date_reason(index)` names why an object is out of date
  (changed implant settings; the section, by name, mapped again or whose
  registration changed) and the fix; export messages and the V2 Results
  status use it (`out_of_date_lines`).
  `DriftlessMap.export_all_results(folder)` (Results > Export all results)
  writes a project copy (`save_project_called(path=, as_copy=True)` leaves
  the current project file and references alone), every built object, probe
  localisation CSVs, the implant table and layers into one folder.
  Projects reopen where the user left off: the engine saves
  `interface_state` (`project_io.clean_interface_state`; plain JSON, optional,
  `{}` for older files) from `interface_state_provider` and hands it to
  `on_project_loaded`; V2 fills it with `V2Window.leave_state` / `resume`
  (step, view, `ImplantCard.leave_state`: selection, `ProbeBook.state`,
  Mark track, an outline being drawn). Point layers are read through
  `project_io.layer_points` / `plot_points`, so an empty layer (formerly
  saved as `[None, None]`) saves and reopens.
- `driftlessmap/sections.py` (GUI-free) and `section_engine.py`: multi-section
  projects (`multi_section_design.md`, released in 2.4.0). V2 Project step **Sections** card
  (`ProjectPanel.refresh_sections`), classic File > Sections…
  (`sections_dialog.py`); `export_sections` writes each section's working
  TIFF, landmark CSV and `sections.json` for Export all results.
  `SECTION_FIELDS` / `section_fields` split the payload into document and
  section fields (`atlas_control` is a section's only with a volume atlas).
  `SectionBook` lists the sections in order; the open one lives in the engine
  (`sections.active_id` follows `section_id`, `sync_sections`), the others are
  `SectionEntry`s whose large arrays `SpillCache` keeps as content-addressed
  copy-on-write `.npy` memmaps. `load_image` adds a section
  (`begin_new_section` / `finish_new_section`); direct `load_single_image_file`
  calls re-read the open one. `switch_section` installs document fields plus
  the target's fields through `ProjectSnapshot.restore` (rollback on failure)
  with `keep_atlas` (the volume is not re-set) and restores the section's own
  `section_id`; a missing or changed source opens its embedded raster.
  `remove_section(delete_results=)`. Saving writes every section
  (`sections_for_save`, fingerprints and packing off the GUI thread); opening
  rebuilds the book (`restore_sections`: invalid stored sections are left out
  and named) and finds a stored section's source through its provenance, or
  its packed portable source, when it is opened. `sections_index` (cached
  per-entry digests) is the payload's `sections` for change detection.
  `sections_without_image` lists mapped sections with no stored section.
  A stored section's `summary["registration"]` is its registration
  fingerprint when put away (`section_summary`); `stored_registrations` feeds
  it to `MappingRecord.status` / `derivation_status`, so a section changed
  after mapping stays out of date while another section is open. A stored
  section without one (saved before 2.5.3, or invalid) gives UNVERIFIED ("not
  verified"; `unverified_reason`, Results, exports), never current; sections
  no longer in the project stay OTHER_SECTION.
- `driftlessmap/landmarks.py`: `LandmarkModel` owns paired landmark lists,
  topology, the cached registration and label items (the `DriftlessMap`
  attributes of the same names delegate to it), plus `.dmaptri` validation.
  `fit_frame` places the frame (corner and side points) from a per-axis
  scale/offset fit of the pairs, inside both images (`FRAME_MIN_PAIRS`,
  `FRAME_MIN_SPREAD`); `DriftlessMap.fit_frame_to_landmarks` applies it after
  landmarks are proposed, added, moved or deleted and for Match Boundaries,
  never on load (a saved frame is part of the registration fingerprint).
- `driftlessmap/probe_utiles.py`, `probe_reconstruction.py`, `probe_csv.py`:
  probe geometry, mapping, reconstruction schema, and exports. Planned shank
  offsets are probe-frame x (across the probe) and y (face normal);
  `get_center_lines` turns them by the site face, and the preview uses the
  same mapping (`shank_plane_offsets`); never swap x and y for a face.
- `document_state.DocumentState.objects` is the canonical GUI-free ObjectState.
  It owns object columns, creation/deletion, selection, IDs and the next-ID counter.
  ObjectControl's old attributes delegate to it; project collection and history
  read the model. Optional obj_id/obj_count payload fields preserve identities;
  legacy/invalid IDs keep generated identities. Arrays are borrowed in payloads.
  Transaction signatures exclude identity bookkeeping; unchanged rebuilds restore
  their original IDs/counter so they neither add an undo step nor dirty the model.
  `export_workflow.export_all_results` owns export orchestration through the
  engine's application operations; the main-window method is an adapter.
  History pack/unpack deduplicate array identity within each call, never across
  snapshots; budget accounting counts each retained array once.
- `driftlessmap/object_control.py`: object pieces/merged objects, visualization,
  and information dialogs.
- `driftlessmap/layers_control.py`: layer metadata and UI state.
- `driftlessmap/background.py`: `run_in_background` runs GUI-free work
  (hashing, archive writes, reference verification, image warps, registration
  input preparation) on a worker thread behind a modal progress dialog shown
  after 150 ms. Never touch widgets from that work. V2 buttons go through
  `v2/widgets.respond` (busy cursor at once; the shell's event filter drops
  input whose timestamp falls inside an action that held the window).
- `driftlessmap/file_dialogs.py`: every open/save/folder dialog goes through it;
  dialogs that would start at home (or nowhere) start in the last chosen folder
  (`user_settings` `last_folder`, kept with `last_atlas_path`). Tests import
  `tests/settings_isolation.py` so they never write the user's settings.
- `driftlessmap/layer_geometry.py`: pure shift/rotate helpers shared by point
  and raster layers.
- `driftlessmap/utils.py`: shared image, label and geometry helpers (formerly
  `uuuuuu.py`).
- `driftlessmap/v2/`: the 2.0 interface, the default on launch since
  2.0.0a27 (`driftlessmap`, `driftlessmap-v2`, `python -m driftlessmap.v2`
  and the desktop bundle). `--classic` or `DRIFTLESSMAP_INTERFACE=classic`
  starts the 1.x interface; a flag wins over the environment. See
  `interfaces.py`, which also starts one interface from the other in a
  separate process (the classic restart passes `--classic`).
  `shell.V2Window` hosts a hidden `DriftlessMap` as its engine: it moves the engine's view splitter,
  toolbar (tool options only), object/layer panels and label tree into its
  own layout and calls engine methods and QActions for every operation. The
  shell must never hold its own copy of scientific state. Panels per step
  (`*_panel.py`), `commands.py` (registry and Ctrl/Cmd+K palette; every 1.x
  QAction is registered under its old name), `state.py` (read-only status and
  the unsaved-change digest, which ignores navigation), `channel_display.py`
  (per-channel display range/gamma written into the 1.x curve state so saves
  restore it), `theme.py` (design tokens and stylesheet, set on the V2 window,
  never on the application: an application stylesheet restyles every hidden
  widget; separate windows get it when shown) and `adopted.py`
  (restyles the adopted 1.x toolbar, atlas controller and label tree from
  the tokens and recolours their white icons; call it on theme changes). Preview
  preferences use a separate QSettings namespace. V2 dialogs subclass the
  1.x ones and only rebuild the layout (`allen_download_dialog.py`), so
  download, validation and processing code stays shared. `probes.py` manages
  named probes on top of the engine's name-prefix grouping of probe pieces
  (`"<probe> - piece"`, `"<probe> shank N - piece"`); `merge_probes(only=...)`
  builds selected groups only. `ProbeBook.rename` updates retained `pieces_names`
  and `MappingLedger.rename_probe` rekeys owners without changing unit IDs or
  revisions. Do not rename only the visible rows.
- `driftlessmap/main_window.ui`: Qt menu/action definitions.
- `driftlessmap/icons/app/`: canonical PNG plus native Windows ICO and macOS
  ICNS application artwork.
- `packaging/DriftlessMap.spec` and `packaging/build_*`: native PyInstaller
  application bundles and release artifacts for Windows and macOS.
- `.github/workflows/ci.yml`: the single test and lint workflow; release and
  desktop-build workflows call it and build only after it passes. Actions are
  pinned to commit SHAs (Dependabot proposes updates).
- `.github/workflows/desktop-builds.yml`: builds both native desktop artifacts
  with `packaging/constraints-desktop.txt`, signs them when signing secrets are
  configured, and attaches them to published GitHub releases from a separate
  write-permitted job.
- `MANUAL.md`, `WhatsNew.md`, `UpdateLog.md`: user behavior and release history.
- `tests/`: unittest-compatible test suite; CI also invokes it through pytest.

## Persistence contract

- New files are never executable pickle payloads. They are atomic ZIP archives
  containing `manifest.json`, `.npy` arrays, and optional streamed attachments.
- Archive format version is currently 1. Project payload schema is version 4
  (`project_io.PROJECT_SCHEMA_VERSION`); schema 3 adds `registration_input`,
  `registration_review` and `mapping_review_state`, and up to 16 channels;
  schema 4 adds `sections`: the open section stays at the top level as before,
  and `sections.stored` holds every other section's fields (`SECTION_FIELDS`,
  each with its own embedded working raster and histology provenance), plus
  `order`, `names` and `active_section_id`. Every section's working raster is
  embedded (linking originals was rejected: the raster is the working one,
  after rotations, flips and crops). Schemas 1-3 open as one section. Portable copies pack stored
  sections' sources under `portable_sources.sections`.
  The optional `interface_state` (where the user left off) needs no schema
  bump: it is absent in older files and dropped when unusable.
  The optional `probe_plans` (2.8.0), `craniotomies` and `surgery_settings`
  (2.8.2) and `implant_plans` (2.8.5: fiber and prism plans, kept apart so
  older versions do not read them as probes), all document state, need none
  either:
  absent means no plans; invalid plans are left out with a message; older
  versions ignore it and keep the built plan objects as ordinary probes.
  Schemas 1 and 2 load with Legacy registration input.
  Do not bump either without a backward-compatible reader/migration path.
- Supported primary extensions:
  - `.dmap`: project.
  - `.dmaplayer`: layer.
  - `.dmapobj`: exported object.
  - `.dmapslice`: calibrated slice atlas.
  - `.dmaptri`: registration landmarks/topology.
  - `.dmapprobe`: complete probe-planning settings.
- Legacy `.herbs*` and inert `.pkl` files remain readable through the
  restricted unpickler. Never replace this with unrestricted `pickle.load` for
  user files. Processed-atlas caches, including mesh caches, are also read
  through restricted unpicklers (`load_legacy_pickle`, `load_mesh_file`),
  because atlas folders can arrive alongside shared projects.

### Project behavior

- **Save Project** is canonical and includes all user-created scientific work:
  registration landmarks/topology, warp direction/method, atlas slice/tilt,
  current histology raster and display controls, processed pixels, layers,
  object pieces and merged objects, probe geometry/planning/face/multi-probe
  state, tool state, and layout.
- Every project embeds the exact lossless active histology raster. If the
  original source is missing or mismatched, loading falls back to that raster.
- A normal project links the original histology and processed volume atlas.
  References contain project-relative and absolute hints plus SHA-256 identity.
- **Save Portable Project** additionally streams the original histology source
  into the archive. Large CZI files must remain streaming attachments; do not
  turn them into in-memory byte arrays.
- Processed volume atlases are deliberately not embedded. Atlas identity covers
  recognized cache files, voxel size/shape, axis metadata, and known provider
  version. Loading rejects mismatched atlas content and allows verified
  relocation.
- Slice-atlas pixels are embedded.
- If source files change after being loaded, do not silently associate the
  in-memory work with the changed bytes. Atlas changes block saving until
  reload; normal histology saves retain the embedded raster without linking the
  changed source; portable histology saves require reload.
- Repeated references to the same NumPy array are stored once per archive.
- Saves must stay atomic: write a temporary archive, then `os.replace`. Flush it
  through a writable handle (Windows rejects `os.fsync` on read-only handles);
  flushing is best effort.

### Objects and probes

- Projects already contain all objects. Standalone object actions are named
  Export/Import because `.dmapobj` is for sharing, reuse, and downstream work.
- New object exports include software/schema, coordinate frame, and checksummed
  atlas provenance. Import verifies atlas content; legacy objects fall back to
  coordinate-bounds validation.
- Merged probes embed self-contained reconstruction metadata: atlas transform,
  labels, voxel coordinates, physical coordinates, contacts, fitted track,
  source atlas metadata, probe settings, and face.
- `.dmapprobe` saves and restores geometry, face, multi-probe offsets/faces,
  validity flags, and merge-sites choice.

## Change rules

1. Preserve backward loading of valid DriftlessMap v1 archives and supported
   HERBS files unless a task explicitly requires a breaking migration.
2. New persisted scientific state needs validation, a default for old files,
   round-trip tests, and documentation.
3. Never identify an atlas or source by basename/path alone. Use provenance
   content identity and coordinate-frame metadata.
4. Do not embed the processed volume atlas in normal or portable projects.
5. Do not require separately exported layers/objects to restore a project.
6. Keep large file handling streaming and ZIP64-compatible.
7. Update `MANUAL.md` for user-visible behavior and `WhatsNew.md`/`UpdateLog.md`
   for release behavior. Keep version references synchronized across
   `driftlessmap/version.py`, `CITATION.cff`, tests, and docs.
8. Update both `AGENTS.md` and `CLAUDE.md` in the same commit. They should be
   byte-for-byte identical so guidance cannot drift.
9. Preserve unrelated user changes in a dirty worktree.
10. Desktop builds are native: use the PowerShell builder on Windows and the
    shell builder on macOS. Keep the canonical version, PyInstaller bundle
    metadata, release filenames, GUI display, and installation docs in sync.

## Testing and validation

Fast targeted tests:

```bash
python -m unittest tests.test_persistence tests.test_provenance \
  tests.test_image_reader tests.test_probe_mapping
```

Use a dedicated environment with the declared dependencies (the historical
`/Users/ali/miniconda/envs/HERBS` path may not exist):

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
QT_API=pyqt6 QT_QPA_PLATFORM=offscreen .venv/bin/python tests/run_test_suite.py unittest
```

On Windows use `.venv\Scripts\python` and set the environment variables in
PowerShell. Do not run against an unrelated HERBS environment with pyqtgraph 0.12
or missing SimpleITK; the application requires the versions in `pyproject.toml`.
`tests/benchmark_project_state.py` measures exact digest cost; remaining platform,
migration, usability and performance gates are tracked in `release_validation.md`.
Offscreen OpenGL warnings are
expected in local headless tests. Linux CI must install `libgl1`, `libegl1`,
the Qt XCB runtime libraries listed in the workflows, `xvfb`, and `xauth`, then
run GUI tests under `xvfb-run` with the Qt `xcb` platform and software OpenGL;
Qt's offscreen plugin is not stable for `QOpenGLWidget` teardown across the
Linux version matrix. CI invokes `tests/run_test_suite.py`, which preserves the
real unittest/pytest result and skips only the unstable interpreter-shutdown
destructor path after the suite has finished.

Before handoff:

```bash
python -m py_compile driftlessmap/*.py
python - <<'PY'
from PyQt6.uic import loadUiType
loadUiType('driftlessmap/main_window.ui')
print('UI valid')
PY
cmp AGENTS.md CLAUDE.md
git diff --check
```

Persistence changes should cover at least: safe round trip, legacy read,
wrong-kind rejection, duplicate-array storage, streamed attachment extraction,
relative relocation, checksum mismatch, embedded-raster fallback, portable
source restoration, and complete probe-planning round trip.
