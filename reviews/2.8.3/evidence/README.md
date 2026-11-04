# 2.8.3 review evidence

Reviewed commit: `e7f85634e577247f5cbd7b696ddd7ee0e53d9948`.
All application tests ran in an isolated archive of this revision. The review
does not modify application code or the user's settings/data.

## Existing checks

- Full unittest suite: **545 run, 543 passed, 2 skipped**, 278.418 seconds.
- Both skips require externally configured real section/atlas fixtures.
- Ruff, Python compilation, Qt UI compilation (`loadUiType`), and
  `AGENTS.md`/`CLAUDE.md` equality passed.
- Mypy was inconclusive: installed PyQt6 stubs produced 16 syntax errors
  before checking could finish. This is not a claim of 16 application errors.
- See `unittest-output.txt`, `ruff-output.txt`, `mypy-output.txt`, and
  `environment.txt` for logs/context.

To rerun from the isolated source directory in a dedicated environment:

```sh
QT_API=pyqt6 QT_QPA_PLATFORM=offscreen python tests/run_test_suite.py unittest
python -m ruff check .
python -m mypy
python -m compileall -q driftlessmap tests
cmp AGENTS.md CLAUDE.md
```

## New diagnostic cases

Set `DMAP_REVIEW_ROOT` to an extracted `git archive` of the reviewed commit.
Run each case in its own process, using the environment with the project's
test dependencies:

```sh
python /absolute/path/to/probe_planning.py multi
python /absolute/path/to/probe_planning.py pending_save
python /absolute/path/to/probe_planning.py pending_new
python /absolute/path/to/probe_planning.py pending_undo
python /absolute/path/to/probe_planning.py lambda
python /absolute/path/to/probe_planning.py conflict
python /absolute/path/to/probe_planning.py gap
python /absolute/path/to/probe_planning.py hierarchy
python /absolute/path/to/probe_planning.py dialog_stale
python /absolute/path/to/probe_planning.py steering
```

For screenshots, also set `DMAP_REVIEW_SCREENSHOTS` to a writable output
directory and run `ui`. `observations.txt` contains the final runs.

The script sets offscreen rendering, uses the repository's settings isolation,
and constructs disposable synthetic inputs. GUI cases use existing test
helpers and terminate without fragile OpenGL interpreter teardown. Exit 0
means the observation completed, not that the observed behavior is correct.

Specific qualifications:

- `multi` uses Neuropixels 2.0 settings and the four supported offsets. It
  compares accepted center-line proposals with the physical shank paths.
  The synthetic target/exclusion/opening arrangement is intentionally demanding.
- `pending_new` executes the actual `project.new` command and clicks Keep the
  atlas through the test helper. `pending_save` uses the shell's save method.
  `pending_undo` invokes the engine's undo action while a steering edit is pending.
- `lambda` supplies a known Lambda to the loaded fixture view and exercises a
  failed project open with an empty raster. It checks the automatic rollback;
  no real rat atlas is downloaded or modified.
- `hierarchy` directly exercises the line scorer and target readout with the
  same line and reordered targets; it is not a full-search timing experiment.
- `steering` delivers a Qt key event after navigating away from Annotate.
- The readout has warnings for the gap case; the finding concerns proposal
  validity and disclosure before acceptance, not absence of every later warning.

## Earlier findings

`probe_prior_findings.py` reruns the seven 2.6.0 scenarios. Its only substantive
adaptation records the expected export refusal after an atlas changes, rather
than aborting on that exception. Run it with `atlas`, `legacy`, `checker`,
`repair`, `multi_repair`, `review`, or `batch`. Results are in
`prior-findings.txt`; all seven original scenarios behave as intended.

The old `checker` output field `saved_matches_checker` compares the original
overlay item. In the fixed implementation, the checkerboard is on a separate
presentation item; that field's name no longer describes the rendered comparison.
`changed_values: 0` and the reopen comparison establish canonical persistence.

## Limits

Screenshots are offscreen macOS layouts of synthetic fixtures. Expected
QOpenGLWidget warnings mean this does not validate native 3D rendering.
The review did not certify installers, real-atlas numerical accuracy,
representative search performance, or user-study outcomes.
