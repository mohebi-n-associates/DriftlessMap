# Follow-up review evidence

Reviewed source: `ce419db8c73d7df518f254995106a21b5a76c895` (2.6.0).
Tests and probes ran against an isolated `git archive` of that commit, not the
changing working checkout. All probe input files and QSettings are temporary.
Application code was not modified.

## Reproduce

Use a dedicated environment with the project's test dependencies. Extract the
reviewed commit to a temporary directory and set `DMAP_REVIEW_ROOT` to that
directory. Run each probe in a separate process:

```sh
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py atlas
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py legacy
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py checker
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py repair
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py multi_repair
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py review
python /absolute/path/to/reviews/2.6.0/evidence/probe_followup.py batch
```

For `ui`, also set `DMAP_REVIEW_SCREENSHOTS` to an output directory. The script
sets `QT_QPA_PLATFORM=offscreen` and imports the repository's settings isolation
before constructing windows. It uses the existing synthetic atlas/test helpers.
It exits without Qt/OpenGL interpreter teardown, following the test runner's
approach. A successful exit means the observation completed, not that the
observed application behavior passed an acceptance criterion.

The `legacy` probe omits the optional stored-section registration fingerprint
to reproduce the pre-2.5.3 summary shape. It saves/reopens that fixture and
compares status before and after visiting the changed section. It is not a
real historical user project. The `batch` probe counts full-series reads; it
does not measure large-stack performance or assert a memory failure.

From the isolated source directory, run the standard checks:

```sh
QT_API=pyqt6 QT_QPA_PLATFORM=offscreen python tests/run_test_suite.py unittest
python -m ruff check .
python -m mypy
python -m compileall -q driftlessmap tests
cmp AGENTS.md CLAUDE.md
```

`environment.txt` records the actual interpreter and libraries. Ruff,
compilation, UI XML parsing, and guide equality passed. Mypy stopped in installed
PyQt6 stubs with 16 syntax errors, so local type checking is inconclusive.
The full regression result is in `unittest-output.txt`.

## Artifacts

- `observations.txt`: final successful diagnostic runs, including layout measurements.
- `probe_followup.py`: all targeted reproductions and screenshot generation.
- `unittest-output.txt`: complete existing-suite output.
- `ruff-output.txt`, `mypy-output.txt`, `environment.txt`: check/environment evidence.
- `annotate-1280.png`, `section-light-1100.png`: inspected offscreen layouts.

The warning that QOpenGLWidget is unsupported on the offscreen platform limits
3D validation. The images are synthetic layout fixtures. Installer behavior,
real-anatomy agreement, user studies, production downloads, and large-file
performance were not validated here.
