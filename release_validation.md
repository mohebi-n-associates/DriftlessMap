# DriftlessMap 2.0 release validation

Stable release: **2.0.0**, 29 October 2026 (PyPI, and a GitHub release with
Windows and macOS builds), after release candidates 2.0.0rc1 (published) to
2.0.0rc16. Current release: 2.9.3, 5 November 2026 (multi-step Undo and object state from 2.9.2, with the 2.9.3 Undo fixes); previously 2.9.0, the same day (service extraction and performance); 2.8.8, 4 November 2026 (Space out: tilting plans that come too close; 2.8.7, the same day, put a prism's tip at its imaging face's bottom left corner; 2.8.6, the same day, published probe planning, Phases 1-4, the fixes from `reviews/2.8.3`, planned fibers and prisms, and probe hardware with 2.8.0-2.8.5; 2.7.0, 3 November 2026, was the one before); the waiver below
applies to it as well. Passing automated tests does not satisfy the native-installation or
user-evaluation gates.

## Gates waived for 2.0.0

On 29 October 2026 the project owner chose to release 2.0.0 while every gate in
"Remaining gates for stable 2.0" below was still pending, after being told which
ones lacked evidence. No installer was tried on a clean machine (the only
Windows build tried, 2.0.0rc1, could not save; the cause was fixed in rc7 but not
retried on Windows), no real 1.x/HERBS project or real-data numerical comparison
was recorded, and no performance or user evaluation was done. These gates are
**waived, not passed**: record evidence for them against 2.0.x as it is
gathered, and fix what they find in 2.0.N releases.

Recorded 2.0.0 automated result (macOS arm64, Python 3.13.9): 412 tests run,
410 passed, 2 skipped; ruff, mypy, UI parsing and guide equality passed; CI on
Python 3.10-3.14 passed for the release commit.

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
2.6.3 on macOS arm64. It is not evidence for the other CI Python versions or for
a packaged installer.

Recorded 2.0.0rc1 result: **378 tests run, 376 passed, 2 skipped** (122 seconds).
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

## TIFF pages as sections (2.6.3)

Run `QT_QPA_PLATFORM=offscreen python tests/benchmark_tiff_pages.py PAGES SIDE`.
It writes a PAGES × SIDE × SIDE uint16 ZYX stack, adds every page as a section
(`add_sections(..., pages_as_sections=True)`), and reports full-stack decodes,
elapsed time, the traced (tracemalloc) allocation peak and the process's
resident peak; one run per process. Apple M3 Max, 48 GiB RAM, macOS 26.1
arm64, Python 3.13.9, NumPy 2.5.4, tifffile 2026.10.15, offscreen:

| Stack | Version | Full-stack decodes | Time | Traced peak | Resident peak |
| --- | --- | ---: | ---: | ---: | ---: |
| 40 × 1024², 80 MiB | 2.6.2 | 40 | 2.2 s | 362 MiB | 1,112 MiB |
| 60 × 2048², 480 MiB | 2.6.2 | 60 | 11.4 s | 1,811 MiB | 3,506 MiB |
| 60 × 2048², 480 MiB | 2.6.3 | 1 | 5.0 s | 952 MiB | 2,438 MiB |

2.6.3 reads the stack once and lets the sections share it read-only. Synthetic
data on one machine; not a measurement of real-data registration or saving.

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

## 2.9.0 refactoring validation

See `reviews/2.9.0/IMPLEMENTATION.md` for changed boundaries, regression
coverage and measured synthetic performance. Ruff and mypy (36 modules) pass
with PyQt6 6.11.0. The 6.12.0 stubs have invalid parameter ordering and that
version is excluded. Existing real-data/native installation gates stay pending.

## 2.9.2 source-only refactoring

2.9.2 was not released on its own; it was published with 2.9.3. See
`reviews/2.9.2/IMPLEMENTATION.md` for the object model, stable identity payload
fields, extracted export workflow, undo memory comparison and remaining work.
Synthetic benchmarks do not close real-data or clean-install gates.

## 2.9.3 Undo fixes

Fixes three regressions found reviewing 2.9.2, each reproduced in the real
engine before and covered by tests after: a per-tool stroke blocked Undo from
reaching points and mapping steps; a point click snapshotted the whole document
(375 ms with a 40 MB object, now about 1 ms); point clicks pushed mapping steps
out of the 10-step history. Real-data trials remain pending as above.
