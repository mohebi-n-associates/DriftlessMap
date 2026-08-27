# DriftlessMap Agent Guide

This is the concise working map for automated contributors. Read this file
before exploring the repository. Use `rg` to open only the files relevant to
the task. `AGENTS.md` and `CLAUDE.md` must remain identical; update both in the
same change whenever architecture, behavior, commands, formats, dependencies,
or important workflows change.

## Project identity

- Current release: DriftlessMap 1.4.0.
- Desktop application for histology registration, atlas mapping, probe
  reconstruction, anatomical annotation, and data export.
- Python package: `driftlessmap`; GUI: PyQt6 + pyqtgraph/OpenGL.
- Supported Python: 3.10-3.14. CZI support currently requires 3.10-3.13.
- DriftlessMap is an independently maintained continuation of HERBS. Preserve
  legacy HERBS file compatibility and coordinate field names where documented.

## Fast architecture map

- `driftlessmap/app.py`: main window, workflow orchestration, menu handlers,
  project/layer/object persistence, atlas and histology loading.
- `driftlessmap/persistence.py`: safe versioned ZIP format, JSON manifest,
  NumPy arrays with pickling disabled, streamed portable attachments, and
  restricted legacy-pickle reader.
- `driftlessmap/provenance.py`: SHA-256 input identity, relative/absolute path
  hints, relocation and verification, portable source packing/extraction.
- `driftlessmap/image_reader.py`: conventional, TIFF, folder, and embedded
  active-raster readers. `czi_reader.py` handles optional CZI input.
- `driftlessmap/image_view.py`: image scene/page/channel/LUT state.
- `driftlessmap/atlas_loader.py`, `atlas_view.py`, `atlas_transform.py`:
  processed atlas loading, display, coordinate transforms.
- `driftlessmap/triangulation.py`: deterministic piecewise-affine registration,
  topology, validation, transforms, and warping.
- `driftlessmap/probe_utiles.py`, `probe_reconstruction.py`, `probe_csv.py`:
  probe geometry, mapping, reconstruction schema, and exports.
- `driftlessmap/object_control.py`: object pieces/merged objects, visualization,
  and information dialogs.
- `driftlessmap/layers_control.py`: layer metadata and UI state.
- `driftlessmap/main_window.ui`: Qt menu/action definitions.
- `driftlessmap/icons/app/`: canonical PNG plus native Windows ICO and macOS
  ICNS application artwork.
- `packaging/DriftlessMap.spec` and `packaging/build_*`: native PyInstaller
  application bundles and release artifacts for Windows and macOS.
- `.github/workflows/desktop-builds.yml`: builds both native desktop artifacts
  and attaches them to published GitHub releases.
- `MANUAL.md`, `WhatsNew.md`, `UpdateLog.md`: user behavior and release history.
- `tests/`: unittest-compatible test suite; CI also invokes it through pytest.

## Persistence contract

- New files are never executable pickle payloads. They are atomic ZIP archives
  containing `manifest.json`, `.npy` arrays, and optional streamed attachments.
- Archive format version is currently 1. Project payload schema is version 2.
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
  user files. Processed-atlas pickle caches are trusted internal inputs.

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
- Saves must stay atomic: write a temporary archive, then `os.replace`.

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

Full suite in the known local GUI-capable environment:

```bash
QT_QPA_PLATFORM=offscreen /Users/ali/miniconda/envs/HERBS/bin/python \
  -m unittest discover -s tests -p 'test_*.py' -q
```

The default local Python may lack `superqt`, `pytest`, or `tomli`; do not treat
that environment-only absence as a product regression. The full HERBS Conda
environment currently runs the complete suite. Offscreen OpenGL warnings are
expected in local headless tests. Linux CI must install `libgl1`, `libegl1`,
`libxcb-cursor0`, `xvfb`, and `xauth`, then run GUI tests under `xvfb-run` with
the Qt `xcb` platform and software OpenGL; Qt's offscreen plugin is not stable
for `QOpenGLWidget` teardown across the Linux version matrix.

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
