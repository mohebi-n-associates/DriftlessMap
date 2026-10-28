# DriftlessMap Agent Guide

This is the concise working map for automated contributors. Read this file
before exploring the repository. Use `rg` to open only the files relevant to
the task. `AGENTS.md` and `CLAUDE.md` must remain identical; update both in the
same change whenever architecture, behavior, commands, formats, dependencies,
or important workflows change.

## Project identity

- Current stable release: DriftlessMap 1.6.1. `main` carries DriftlessMap 2.0,
  published as the release candidate 2.0.0rc1 (after the 2.0.0aN previews).
  Fixes before the final release become 2.0.0rcN (currently 2.0.0rc11). Plain 2.0.0 is reserved for
  the release that passes the gates in `release_validation.md`. Never give V2
  work 1.x numbers. A published GitHub release runs `release.yml` (PyPI, trusted
  publishing) and `desktop-builds.yml` (Windows ZIP and macOS DMG attached to
  the release).
- Desktop application for histology registration, atlas mapping, probe
  reconstruction, anatomical annotation, and data export.
- Python package: `driftlessmap`; GUI: PyQt6 + pyqtgraph/OpenGL.
- Supported Python: 3.10-3.14. CZI support currently requires 3.10-3.13.
- OpenCV uses the headless wheel because PyQt6 owns the GUI and Qt plugin
  runtime; do not reintroduce the GUI OpenCV wheel.
- DriftlessMap is an independently maintained continuation of HERBS. Preserve
  legacy HERBS file compatibility and coordinate field names where documented.

## Fast architecture map

- `driftlessmap/app.py`: main window, workflow orchestration, menu handlers,
  project/layer/object persistence, atlas and histology loading.
- `driftlessmap/project_io.py`: GUI-free project helpers (default working
  data, merging older payloads, input pre-fingerprinting, export file names).
  Atlas kind, path and load fingerprint are committed only through
  `DriftlessMap._commit_atlas`; per-view display updates go through
  `DriftlessMap._atlas_view_items`.
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
  Pyramidal single-plane TIFFs (`has_levels`) are read at a stored level
  chosen by the Scale slider, recorded through the saved `image_scale`. `czi_reader.py` handles optional CZI input.
- `driftlessmap/image_view.py`: image scene/page/channel/LUT state. Channel
  `ImageItem`s (`image_stacks.py`) use `autoDownsample` and additive blending
  for all 16 channels.
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
  tilt, image size and triangle connectivity; any change makes it lapse. Fingerprint
  content version 2 (2.0.0a26) deliberately invalidates older review fingerprints;
  old results remain loadable. Mapping records of the loaded section whose stored
  fingerprint is the pre-a26 one for the unchanged registration are restamped on
  load (`_migrate_mapping_fingerprints`), so they stay current. Unusable saved probe
  planning warns and the project still opens. Pre-schema-3 work is
  "not recorded", never "reviewed". Saved as `registration_review`.
- `driftlessmap/auto_registration.py`: SimpleITK registration (moment-based
  affine on silhouettes, then a B-spline on intensities with Mattes MI over
  every masked pixel, smoothed at each level by `BSPLINE_SMOOTHING`; random
  sampling made results seed- and platform-dependent; sections are analysed on
  a copy of at most `ANALYSIS_MAX_SIDE` pixels, `_analysis_copy`, with
  physical space kept in section pixels) that
  proposes atlas-to-histology landmark pairs in DriftlessMap pixel-edge
  coordinates. The B-spline is kept only if it improves the intensity match
  without degrading the outline. Up to 10 landmarks are suggested:
  outline tips/notches (skipping image-edge cuts and label-only outline) and
  internal edges scored by local agreement between atlas and resampled
  section edges, so single-image edges are never chosen.
- `driftlessmap/atlas_loader.py`, `atlas_view.py`, `atlas_transform.py`:
  processed atlas loading, display, coordinate transforms.
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
  undo transactions. V2: `v2/implant_card.py` and `v2/outline_editor.py`
  (draw, Propose by flood fill inside the brain envelope, tip/bottom point).
  Probes are listed in the same Implants card but stay on the named-probe
  path: selecting one shows `v2/probe_card.ProbeControls`. The implant table
  adds a summary row per built probe (`probe_csv_row`). `implant_build_status` compares
  the retained report specs to the current implant specs; mismatches are out of date
  in the UI and exports until rebuilt. The implant CSV includes a `status` column.
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
- `driftlessmap/landmarks.py`: `LandmarkModel` owns paired landmark lists,
  topology, the cached registration and label items (the `DriftlessMap`
  attributes of the same names delegate to it), plus `.dmaptri` validation.
- `driftlessmap/probe_utiles.py`, `probe_reconstruction.py`, `probe_csv.py`:
  probe geometry, mapping, reconstruction schema, and exports.
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
- Archive format version is currently 1. Project payload schema is version 3
  (`project_io.PROJECT_SCHEMA_VERSION`); schema 3 adds `registration_input`,
  `registration_review` and `mapping_review_state`, and up to 16 channels.
  The optional `interface_state` (where the user left off) needs no schema
  bump: it is absent in older files and dropped when unusable.
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
