# DriftlessMap 2.0 release validation

Development preview: **2.0.0a26**, 28 October 2026. Stable release: **1.6.1**.
Passing automated tests does not satisfy the native-installation or user-evaluation
gates. Keep the alpha version until every required gate has recorded evidence.

## Correctness checks added in a26

| Risk | Executable evidence |
| --- | --- |
| Unsaved edits missed by partial summaries | `tests/test_state_digest.py`; V2 shell test `test_saved_work_edits_are_dirty_and_idle_refresh_does_not_rescan` |
| Review survives changed triangle connectivity | `tests/test_registration_review.py` (explicit and implicit topology) |
| Failed open destroys the active document | Project-persistence tests `test_failed_project_restore_rolls_back_unsaved_work_without_sources` and `test_failed_load_into_an_empty_session_stays_empty` |
| Rename breaks probe rebuilding and mapping ownership | Probe-book test `test_renaming_a_build_preserves_mapping_units_and_rebuilds` |
| Implant report appears current after specifications change | Implant-engine test `test_specs_invalidate_build_through_save_reopen_export_and_rebuild` |
| History exceeds its budget or crosses unrecorded edits | Transaction-history tests and implant-engine test `test_unrecordable_mutation_clears_both_history_directions` |

## Reproduce automated validation

Use Python 3.10–3.14 and a dedicated environment, installing `.[test]` from this
checkout. CZI needs the optional dependency and Python 3.10–3.13. The old absolute
HERBS environment path is not a prerequisite.

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[test]"
QT_API=pyqt6 QT_QPA_PLATFORM=offscreen .venv/bin/python tests/run_test_suite.py unittest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
.venv/bin/python -m compileall -q driftlessmap tests
cmp AGENTS.md CLAUDE.md
git diff --check
```

Use the existing Xvfb/XCB workflow for Linux GUI tests. On Windows use the venv's
`Scripts/python` and set Qt environment variables in PowerShell. A mixed Conda/pip
Qt installation may require `QT_QPA_PLATFORM_PLUGIN_PATH` pointing to the active
PyQt6 installation's `Qt6/plugins/platforms`; do not change application imports to
accommodate a broken local Qt setup.

Local validation uses Python 3.13.9, NumPy 2.3.5, pyqtgraph 0.14.0 and SimpleITK
2.5.6 on macOS arm64. It is not evidence for the other CI Python versions or for
a packaged installer.

Recorded a26 result: **377 tests run, 375 passed, 2 skipped** (139 seconds).
Both skips require an externally configured real section/atlas fixture. Ruff,
mypy (31 modules), Python compilation, Qt UI parsing, guide equality and
`git diff --check` passed. Recovery archive creation and reopening, failed-load
rollback, same-name implant rebuild undo/redo, and loaded-document navigation
were exercised by the regression suite.

## Digest performance observation

Run `python tests/benchmark_project_state.py`. It hashes uint16 rasters and 10,000
cell points, with the same raster referenced twice. Results are medians of three
runs; shared arrays are read once per digest. No cache survives between mutable
edits. Measurements on an Apple M3 Max with 48 GiB RAM, macOS 26.1 arm64:

| Raster | Raster memory | Exact digest time |
| --- | ---: | ---: |
| 1024 × 1024 × 3 | 6 MiB | 21 ms |
| 4096 × 4096 × 6 | 192 MiB | 98 ms |

The shell does not rescan these arrays on idle 600 ms refreshes. Close/open
decisions always check the full state. These measurements exclude load, warp,
save/reopen and peak application memory; they are not a complete performance gate.

## Remaining gates for stable 2.0

| Priority | Gate | Required evidence | Status |
| --- | --- | --- | --- |
| 1 | Native Windows and macOS installers | Install on clean machines; launch both interfaces; open → register → map → build → export → save/reopen; record artifact version, OS and results | Pending |
| 1 | Representative migration and numerical agreement | Copied supported 1.x/HERBS projects and brightfield/fluorescence/CZI/OME-TIFF cases; compare coordinates, labels, contacts and exports with declared tolerances; exercise source relocation and embedded recovery | Automated fixtures exist; real-data trials pending |
| 2 | Large-file performance | Record machine, dataset dimensions and peak memory; compare load, warp, save/reopen and interactive latency to 1.6.1; establish budgets | Digest observation above only; full comparison pending |
| 2 | User evaluation | New and experienced users, keyboard access, both themes, small windows; record assistance, anatomical correctness and task times against Section 17 of `version2_redesign.md` | Pending |
| 2 | Tutorials and capability coverage | Execute each documented workflow in the installers and attach the results; include multichannel registration, stale-result recovery and implant/probe rebuilding | Pending |
| 3 | Architecture follow-up | Continue extracting scientific orchestration from `app.py` behind shared services; consider stable probe IDs with legacy-name migration; avoid a broad rewrite before correctness gates pass | Project collection/recovery extracted in a26; further work incremental |

Do not mark a pending gate complete based on synthetic tests, digest timings, or
successful source execution alone. Record concrete artifacts and outcomes here
as those checks are performed.
