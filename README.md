# DriftlessMap

Interactive histology registration and brain-atlas mapping.

DriftlessMap is an open-source desktop application for registering histological
images to reference brain atlases, reconstructing probes and other anatomical
objects, and visualizing data in 2D and 3D. The name refers to Wisconsin's
Driftless Area and to the project's focus on dependable spatial mapping.

## Authors

DriftlessMap is developed by
[Mohebi & Associates](https://www.mohebi-associates.org/), with
[Ali Mohebi, PhD](https://www.mohebial.com/) as project lead and maintainer
and Esther Lara Gonzalez, PhD as a contributor. See
[contributors](CONTRIBUTORS.md).

If DriftlessMap contributes to published research, please cite the software
version you used; see [CITATION.cff](CITATION.cff).

## Acknowledgements

DriftlessMap grew out of [HERBS](https://github.com/Whitlock-Group/HERBS), now
a legacy project, created by Jingyi Guo Fuglstad, Pearl Saldanha, Jacopo
Paglia and Jonathan R. Whitlock. DriftlessMap is independently developed and
not affiliated with or endorsed by the HERBS developers. The
[HERBS legacy note](ORIGINS.md) records the connection, the HERBS publication,
licensing, and what is kept for compatibility with HERBS data; earlier
acknowledgements are in [THANKS.txt](THANKS.txt).

## Features

- 2D and 3D visualization of volumetric brain atlases and arbitrary slices.
- Interactive histology-to-atlas registration with local elastic deformation.
- Automatic suggestions for the matching atlas section and starting landmarks,
  including brightfield sections.
- Direct multichannel microscopy input (up to 16 channels, TIFF hyperstacks,
  series and CZI) with registration on explicitly chosen channels.
- Probe planning, reconstruction, contact mapping, and CSV export.
- Optical fiber and microprism reconstruction (tip, bottom, laterality and
  regions) alongside probes.
- Drawing, cell, virus-expression, and user-defined object workflows.
- Registration review, out-of-date tracking and undo for mapped results.
- Safe, versioned project and object archives that reopen where you left off.
- Support for custom compatible atlases.

## DriftlessMap 2.0

**2.0.0** is the current release. It opens the
redesigned step-by-step interface by default (Project, Section, Match, Register,
Annotate, Results); the classic interface is still available with
`driftlessmap --classic` or from Help > Open the classic interface. See
[What’s New](WhatsNew.md) for the full list of changes.

Projects saved by 2.0 cannot be opened by 1.6.1 or earlier; 2.0 opens 1.x and
HERBS projects. Keep a copy of important projects before opening them in 2.0.
DriftlessMap 1.6.1 remains available from its
[release page](https://github.com/mohebi-n-associates/DriftlessMap/releases/tag/v1.6.1)
and with `pip install "driftlessmap==1.6.1"`.

## Installation

DriftlessMap is available as a desktop application for end users and as a
Python package for developers. The current release is 2.0.0.

### Mode 1: desktop application for end users

No Python or Conda installation is required. Download the asset for your
computer from [GitHub Releases](https://github.com/mohebi-n-associates/DriftlessMap/releases).
From the [2.0.0 release](https://github.com/mohebi-n-associates/DriftlessMap/releases/tag/v2.0.0):

- **Windows 64-bit:** download `DriftlessMap-2.0.0-Windows-x64.zip`, extract
  the complete folder, and double-click `DriftlessMap.exe`. Do not move the
  executable out of its extracted folder.
- **macOS (Apple Silicon):** download `DriftlessMap-2.0.0-macOS-arm64.dmg`,
  open it, and drag `DriftlessMap.app` to Applications. The application bundle
  includes the DriftlessMap icon and all Python dependencies. Intel Macs are
  not covered by the desktop build; use the Conda/pip installation below.

Release builds are currently unsigned. If Windows SmartScreen or macOS
Gatekeeper displays a warning, verify that the file came from the official
release page before bypassing the warning. Code signing and notarization are
planned for a future release.

If macOS reports that Apple could not verify that DriftlessMap is free of
malware:

1. Click **Done**; do not move the application to the Trash.
2. Drag `DriftlessMap.app` from the DMG into **Applications**.
3. In Finder, Control-click `DriftlessMap.app`, choose **Open**, and confirm
   **Open** if macOS offers that option.
4. If the same warning remains, open **System Settings**, select **Privacy &
   Security**, scroll to **Security**, and click **Open Anyway** beside the
   DriftlessMap message.
5. Authenticate when prompted and confirm **Open**. This approval is normally
   required only for the first launch.

Only use **Open Anyway** for a copy downloaded from the
[official DriftlessMap releases](https://github.com/mohebi-n-associates/DriftlessMap/releases).
Each release page lists the SHA-256 digest of its downloads; compare it with
`shasum -a 256` on the downloaded file.

### Mode 2: Conda and pip for developers

DriftlessMap supports Python 3.10–3.14 and Qt 6 through PyQt6. Python 3.14 is
recommended for core development:

```bash
conda create --name DriftlessMap python=3.14 -y
conda activate DriftlessMap
python -m pip install --upgrade pip
git clone https://github.com/mohebi-n-associates/DriftlessMap.git
cd DriftlessMap
python -m pip install -e ".[test]"
```

Launch the editable installation with `driftlessmap` or
`python -m driftlessmap`; both open the 2.0 interface, and `--classic` opens the
classic one. Library users can call `driftlessmap.run()`.

To use a PyPI package instead of an editable checkout:

```bash
python -m pip install driftlessmap
```

#### Check your version and upgrade

Check the installed version:

```bash
python -m driftlessmap --version
```

Compare it against the latest stable release on
[PyPI](https://pypi.org/project/driftlessmap/):

```bash
pip index versions driftlessmap
```

Upgrade to the latest stable release:

```bash
python -m pip install --upgrade driftlessmap
```

#### Zeiss CZI files

CZI support uses the optional `aicspylibczi` package, whose prebuilt packages
currently support Python through 3.13:

```bash
conda create --name DriftlessMap-CZI python=3.13 -y
conda activate DriftlessMap-CZI
python -m pip install --upgrade pip
python -m pip install "driftlessmap[czi]"
```

#### Building the desktop applications

Native applications must be built on their target operating system. The
release workflow builds both platforms automatically; maintainers can also run
`packaging/build_windows.ps1` on Windows or `packaging/build_macos.sh` on
macOS. Outputs are written to `dist/` as a Windows ZIP and a macOS DMG.

## Compatibility with HERBS

DriftlessMap opens legacy HERBS files (`.herbs`, `.herbslayer`, `.herbsobj`,
`.herbsslice`, `.herbstri`) and can be installed alongside HERBS; new files use
the `.dmap*` extensions, which HERBS cannot open. Details are in the
[HERBS legacy note](ORIGINS.md#compatibility-with-herbs-data).

## Documentation

Read the [DriftlessMap User Manual](MANUAL.md) for installation, atlas,
registration, reconstruction, persistence, export, and troubleshooting
guidance, and the [tutorials](Tutorial) for worked examples.

Do not store downloaded atlases inside the source or installed package
directory. Keep each atlas in its own external folder.

See [What’s New in DriftlessMap](WhatsNew.md) for release history and migration
notes.

## License

DriftlessMap is distributed under the MIT License. The original HERBS copyright
and permission notice are preserved, and a separate copyright notice covers
subsequent DriftlessMap modifications. See [LICENSE.txt](LICENSE.txt) and
[ORIGINS.md](ORIGINS.md).

Please report issues or start discussions at
<https://github.com/mohebi-n-associates/DriftlessMap>.
