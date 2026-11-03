## Create an environment with Anaconda or Miniconda

DriftlessMap needs its own Python environment, so its Qt, NumPy, OpenCV and
OpenGL packages do not conflict with other software. Most users do not need
this: the Windows and macOS desktop builds on the
[Releases page](https://github.com/mohebi-n-associates/DriftlessMap/releases)
include Python and everything else. Use an environment when you install the
Python package, for scripting or development.

In a terminal (on Windows, the *Anaconda Prompt*):

```bash
conda create --name DriftlessMap python=3.14 -y
conda activate DriftlessMap
python -m pip install --upgrade pip
python -m pip install driftlessmap
driftlessmap
```

The last command starts DriftlessMap in the 2.0 interface;
`driftlessmap --classic` starts the classic interface.

To open Zeiss CZI files, use Python 3.13 (the CZI reader has no builds for
newer Python yet):

```bash
conda create --name DriftlessMap-CZI python=3.13 -y
conda activate DriftlessMap-CZI
python -m pip install --upgrade pip
python -m pip install "driftlessmap[czi]"
```

Check that the environment is the one you meant:

```bash
python -c "import driftlessmap; print(driftlessmap.__version__)"
```

It prints the installed version, for example `2.5.0`.

**With Anaconda Navigator** (the graphical interface): open *Environments*,
click *Create*, name the environment `DriftlessMap` and choose Python 3.14 (or
3.13 for CZI). Then click the triangle next to the new environment, choose
*Open Terminal*, and run the two `python -m pip install` commands above. The
packages DriftlessMap needs come from PyPI through pip, not from the Navigator
package list.

The [User Manual, Section 2](../MANUAL.md#2-installation-and-launching) covers
installation in full.
