# Reproduction and evidence

Source: commit `e2956d748798d8b82d236c0df7b8f6930d99be52` (2.8.8), reviewed 5 November 2026. The source was exported to an isolated temporary directory. Application source was not edited.

Environment: macOS 26.1 arm64, Python 3.14.10, NumPy 2.5.4; dedicated DriftlessMap Conda environment, Qt offscreen. Diagnostic scripts import `tests.settings_isolation`. They use small generated atlas fixtures, not private histology or animal data.

From a checkout of the reviewed commit, with its dependencies installed:

```bash
export DMAP_REVIEW_ROOT="$PWD"
python /absolute/path/to/reviews/2.8.8/evidence/audit.py containment
python /absolute/path/to/reviews/2.8.8/evidence/audit.py fixed
python /absolute/path/to/reviews/2.8.8/evidence/audit.py overlap
python /absolute/path/to/reviews/2.8.8/evidence/audit.py pure_perf
python /absolute/path/to/reviews/2.8.8/evidence/audit.py gui_perf
QT_API=pyqt6 QT_QPA_PLATFORM=offscreen python tests/run_test_suite.py unittest
python tests/benchmark_project_state.py
```

The audit script is a standalone diagnostic, not an imported unit test. After flushing its results it exits with `os._exit(0)` to avoid offscreen Qt teardown; success means it ran, not that a reported geometry case passed an assertion. Inspect the `REVIEW_RESULT` values. Each mode must be run separately. The full suite uses the repository's own result-preserving runner.

Files:

- `dmap288-containment.txt`: overlapping fiber/prism, positive reported gap.
- `dmap288-fixed.txt`: omitted fixed/fixed clash.
- `dmap288-overlap.txt`: overlapping coincident tips with empty spacing clash report.
- `dmap288-pure_perf.txt`: readout samples and cProfile spacing breakdown.
- `dmap288-gui_perf.txt`: unchanged shell/overlay refresh measurements and cProfile call counts.
- `dmap288-digest.json`: existing exact-state digest benchmark output.
- `dmap288-inventory.json`: AST inventory of all package Python files; counts include physical blank/comment lines and nested functions. Per-class method counts include directly declared methods only.
- `dmap288-static.txt`: Ruff, mypy blocker, compilation/UI/guide checks. The shell continued after mypy failed; the report does not count it as passing.
- `full-suite.txt`: complete unittest output, 584 run, two skipped, no failures.

Profiles are diagnostic observations with instrumentation overhead, not benchmark guarantees. Some ran concurrently with the suite. Offscreen OpenGL/font warnings are retained; they do not validate native rendering. No screenshots or external datasets are required for the reproduced geometry findings.
