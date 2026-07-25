# What’s New in HERBS 1.0.0

HERBS 1.0 moves the desktop application to the current Python and Qt
ecosystem.

## Highlights

- Supports Python 3.10 through Python 3.14.
- Migrates the user interface from PyQt5 to PyQt6.
- Updates pyqtgraph to 0.14 and supports NumPy 2 and OpenCV 5.
- Replaces the unmaintained QtRangeSlider package with the Python 3.14-ready
  `superqt` range slider.
- Uses modern `pyproject.toml` package metadata and declares a `herbs` command.
- Keeps application imports lightweight so importing `herbs` does not start or
  eagerly load the GUI.

## CZI support

Zeiss CZI reading is now an optional installation extra:

```bash
python -m pip install ".[czi]"
```

The upstream `aicspylibczi` project currently provides wheels through Python
3.13. Use Python 3.13 when CZI support is required; the rest of HERBS supports
Python 3.14.

## Upgrade notes

Create a fresh environment for HERBS 1.0. Environments containing PyQt5 or
pyqtgraph 0.12 should not be upgraded in place because Qt binding selection can
be affected by packages already imported into a Python process.
