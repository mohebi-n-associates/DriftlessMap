# Validation and reproduction evidence

The report reviews commit `5305b1d78efcf1077dc2333e87d04aceabac3e18`, extracted with `git archive` into an isolated temporary directory. Uncommitted changes in the working checkout were excluded. The scripts here are diagnostic evidence, not fixes or new production tests. They print observations of the release's behavior; a zero exit code does **not** mean the observed behavior is correct.

## Environment and existing checks

- macOS 26.1, arm64.
- Python 3.14.10 in `/Users/ali/anaconda3/envs/DriftlessMap`.
- NumPy 2.5.4, pyqtgraph 0.14.0, SimpleITK 2.5.6, PyQt6/Qt 6.12.0.
- Qt platform: `offscreen`; test settings isolated using `tests.settings_isolation`.
- CZI integration was not exercised on this Python version.

| Check on the isolated release | Result |
| --- | --- |
| `QT_API=pyqt6 QT_QPA_PLATFORM=offscreen python tests/run_test_suite.py unittest` | 471 run, 469 passed, 2 skipped, 201.428 seconds |
| `python -m ruff check .` | All checks passed |
| `python -m compileall -q driftlessmap tests` | Passed |
| `PyQt6.uic.loadUiType('driftlessmap/main_window.ui')` | Passed |
| `cmp AGENTS.md CLAUDE.md` | Passed |
| `python -m mypy` | Inconclusive: 16 parse errors in the installed `PyQt6/QtGui.pyi`; not attributed to application code |
| `python tests/benchmark_project_state.py` | Approximately 23 ms / 6 MiB and 102 ms / 192 MiB; digest only |

Skipped cases: `test_atlas_matching.RealSectionTests.test_sagittal_section_is_recognised` and `test_auto_registration.RealSectionTests.test_real_section_registers`, both because the sample section/atlas was not configured. Offscreen OpenGL warnings in the log are not counted as application defects.

The report's additional probes use small synthetic images and the repository's processed-atlas fixture. They establish state transitions and UI behavior, not biological accuracy. The download tests simulate cached-file corruption and the active-operation predicate; the processing metadata test substitutes small arrays and a mesh stub for expensive processing. No live remote download, clean installer trial, screen-reader trial, or user study was performed.

## Running the additional probes

Use a dedicated environment satisfying the release's dependencies. Point `DRIFTLESSMAP_REVIEW_SOURCE` at an extracted **release** tree, not the dirty development checkout. For example, from the repository root:

```sh
review_source=$(mktemp -d)
git archive 5305b1d78efcf1077dc2333e87d04aceabac3e18 | tar -x -C "$review_source"
export DRIFTLESSMAP_REVIEW_SOURCE="$review_source"
export QT_API=pyqt6
export QT_QPA_PLATFORM=offscreen

python reviews/2.5.0/evidence/probe_sections.py stale
python reviews/2.5.0/evidence/probe_sections.py atlas
python reviews/2.5.0/evidence/probe_sections.py remove
python reviews/2.5.0/evidence/probe_sections.py portable
python reviews/2.5.0/evidence/probe_sections.py tiff
python reviews/2.5.0/evidence/probe_downloads.py
python reviews/2.5.0/evidence/probe_ui.py
```

Each process creates its own temporary fixture folders and isolates user settings. `probe_ui.py` creates screenshots in its temporary fixture folder. The scripts use the suite's immediate-exit convention to avoid unrelated Qt interpreter-shutdown teardown; temporary fixture folders may remain and can be removed afterward.

| Probe | Report finding | Key observation |
| --- | --- | --- |
| `probe_sections.py stale` | B1 | `registration changed` becomes `current` after switching; export notes are empty |
| `probe_sections.py atlas` | B2 | Old merged fiber remains current; current export provenance identifies the replacement 50 µm atlas |
| `probe_downloads.py` processing observation | B3 | Successful worker path does not write axis metadata |
| `probe_ui.py` | B4 | Unfinished vertices remain in draw mode after switching and commit to the newly active section |
| `probe_sections.py tiff` | B5 | Pixel values/page change, but fingerprint, reviewed status, and current mapping remain |
| `probe_sections.py remove` | B6 | Shared build removal leaves no parts; remaining mapping cannot be built without remapping |
| `probe_downloads.py` verification observation | B7 | An altered file with an unchanged checksum manifest is accepted as verified |
| `probe_sections.py portable` | B8 | Save succeeds, changed inactive source is absent from portable attachments |
| `probe_downloads.py` Escape observation | B9 | Dialog becomes hidden/Rejected while the active-download predicate is true |
| `probe_ui.py` layout observations/screenshots | B10 | Accepted 1280 × 800 window clips task content and header text |

## Retained outputs

- [Observed probe output](observations.txt).
- [Full unittest output](unittest-output.txt).
- [Mypy environment errors](mypy-output.txt).
- [Digest benchmark metadata and measurements](digest-benchmark.json).
- [Section screenshot](section-1280.png) and [Annotate screenshot](annotate-1280.png).

Fixture paths and randomly generated identifiers in `observations.txt` describe the review run. They are not paths to the user's data or stable expected values. Source citations in the report point at the immutable reviewed commit so subsequent fixes do not change the cited evidence.
