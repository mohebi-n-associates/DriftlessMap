# Contributing to DriftlessMap

Thank you for helping improve DriftlessMap. This guide covers what you need to
change the code safely. Read `AGENTS.md` (identical to `CLAUDE.md`) for the
architecture map and the persistence contract before larger changes.

## Set up

Use Python 3.10–3.14 (3.13 or earlier if you need CZI support):

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --editable ".[test]"
```

## Check your change

Run all three before opening a pull request; CI runs the same checks:

```bash
python -m pytest
python -m ruff check .
python -m mypy
```

GUI tests need a display. On a headless Linux machine, run them under
`xvfb-run` with `QT_QPA_PLATFORM=xcb`; on macOS and Windows the offscreen
platform works: `QT_QPA_PLATFORM=offscreen python -m pytest`. Offscreen OpenGL
warnings are expected.

## Ground rules

- **Never load user files with unrestricted `pickle`.** Use the restricted
  readers in `driftlessmap/persistence.py`; new files are written as safe ZIP
  archives.
- **Identify inputs by content, not by path.** Use the SHA-256 references in
  `driftlessmap/provenance.py`.
- **New persisted state** needs validation, a default for older files, a
  round-trip test, and documentation in `MANUAL.md`.
- **Keep older files readable.** DriftlessMap and legacy HERBS files must
  keep opening.
- **Scientific changes** that alter reported numbers need a test that pins
  the corrected behaviour, and a release note saying which outputs to
  regenerate.
- **Keep long work off the GUI thread.** Use `run_in_background` in
  `driftlessmap/background.py` for hashing, large writes or warps. Never touch
  widgets from that work.
- **Do not commit large binaries** (videos, PDFs, sample datasets). Attach
  them to a GitHub release and link to them instead.
- **Keep `AGENTS.md` and `CLAUDE.md` identical.** CI compares them.

## Releases

Every release updates the version in `driftlessmap/version.py`,
`CITATION.cff`, `tests/test_version.py`, `README.md`, `MANUAL.md`, `AGENTS.md`
and `CLAUDE.md`. It also adds an entry at the top of `WhatsNew.md` and
`UpdateLog.md`. Publishing a GitHub release runs the test suite, then builds
the PyPI distributions and the Windows and macOS desktop bundles.
