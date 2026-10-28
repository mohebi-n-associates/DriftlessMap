# DriftlessMap

Interactive histology registration and brain-atlas mapping.

DriftlessMap is an open-source desktop application for registering histological
images to reference brain atlases, reconstructing probes and other anatomical
objects, and visualizing data in 2D and 3D. The name refers to Wisconsin's
Driftless Area and to the project's focus on dependable spatial mapping.

## Origin and independence

DriftlessMap began as a fork of
[HERBS](https://github.com/Whitlock-Group/HERBS) — Histological E-data
Registration in rodent Brain Spaces — originally created by Jingyi Guo
Fuglstad, Pearl Saldanha, Jacopo Paglia, Jonathan R. Whitlock, and HERBS
contributors.

DriftlessMap is independently maintained. It is not affiliated with or endorsed
by the original HERBS developers. Their foundational work remains credited in
the Git history, [license](LICENSE.txt), [project history](ORIGINS.md),
[contributors](CONTRIBUTORS.md), [authors](AUTHOR.txt), and
[acknowledgements](THANKS.txt).

Current development is led by
[Mohebi & Associates](https://www.mohebi-associates.org/), with
[Ali Mohebi, PhD](https://www.mohebial.com/) as project lead and maintainer
and Esther Lara Gonzalez, PhD as a contributor.

If DriftlessMap contributes to published research, please cite both the software
version used and the original HERBS paper:

> Fuglstad, J. G., Saldanha, P., Paglia, J., & Whitlock, J. R. (2023).
> Histological E-data Registration in rodent Brain Spaces. *eLife*, 12,
> e83496. https://doi.org/10.7554/eLife.83496

See [CITATION.cff](CITATION.cff) for machine-readable citation metadata.

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

## DriftlessMap 2.0 release candidate

**2.0.0rc1** is the release candidate of DriftlessMap 2.0. It opens the
redesigned step-by-step interface by default (Project, Section, Match, Register,
Annotate, Results); the classic interface is still available with
`driftlessmap --classic` or from Help > Open the classic interface. See
[What’s New](WhatsNew.md) for the full list of changes.

The stable release is still **1.6.1**: `pip install driftlessmap` installs 1.6.1
until 2.0.0 is released. To try the release candidate:

```bash
python -m pip install --pre driftlessmap
```

or download the 2.0.0rc1 desktop builds from its
[GitHub pre-release](https://github.com/mohebi-n-associates/DriftlessMap/releases/tag/v2.0.0rc1).
Projects saved by 2.0 cannot be opened by 1.6.1 or earlier; 2.0 opens 1.x and
HERBS projects. Keep a copy of important projects while evaluating it.

## Installation

DriftlessMap is available as a desktop application for end users and as a
Python package for developers. The stable release is 1.6.1; the 2.0 release
candidate is 2.0.0rc1.

### Mode 1: desktop application for end users

No Python or Conda installation is required. Download the asset for your
computer from [GitHub Releases](https://github.com/mohebi-n-associates/DriftlessMap/releases).
For the 2.0 release candidate, use `DriftlessMap-2.0.0rc1-Windows-x64.zip` or
`DriftlessMap-2.0.0rc1-macOS-arm64.dmg` from the
[2.0.0rc1 pre-release](https://github.com/mohebi-n-associates/DriftlessMap/releases/tag/v2.0.0rc1).
For the stable 1.6.1 release:

- **Windows 64-bit:** download `DriftlessMap-1.6.1-Windows-x64.zip`, extract
  the complete folder, and double-click `DriftlessMap.exe`. Do not move the
  executable out of its extracted folder.
- **macOS (Apple Silicon):** download `DriftlessMap-1.6.1-macOS-arm64.dmg`,
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
[official DriftlessMap 1.6.1 release](https://github.com/mohebi-n-associates/DriftlessMap/releases/tag/v1.6.1).
The official macOS DMG has this SHA-256 digest:

```text
aa8ed43826e63cd1e111e3ee53310bb1ac569fd1409862070b847afaeefe7e94
```

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

To use a PyPI package instead of an editable checkout, install the stable
release or, with `--pre`, the 2.0 release candidate:

```bash
python -m pip install driftlessmap
```

```bash
python -m pip install --pre driftlessmap
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

The rebrand is designed not to strand existing research data:

- DriftlessMap reads legacy `.herbs`, `.herbslayer`, `.herbsobj`,
  `.herbsslice`, and `.herbstri` files.
- New files use `.dmap`, `.dmaplayer`, `.dmapobj`, `.dmapslice`, and
  `.dmaptri`.
- DriftlessMap installs only the `driftlessmap` Python package and command. It
  does not overwrite the original HERBS package, so both distributions can be
  installed in the same environment. New code should use `import driftlessmap`.
- Existing `HERBS_CONFIG_DIR` overrides remain supported. New configurations
  should use `DRIFTLESSMAP_CONFIG_DIR`.
- Some persisted coordinate field names retain `herbs` because changing them
  would break existing datasets and downstream analysis scripts.

The original HERBS application may not be able to open files newly written by
DriftlessMap. Keep backups before converting important projects.

## Documentation

Read the [DriftlessMap User Manual](MANUAL.md) for installation, atlas,
registration, reconstruction, persistence, export, and troubleshooting
guidance. The original [HERBS Cookbook](CookBook.pdf) and [tutorials](Tutorial)
remain useful for workflows whose interface has not changed.

The screenshot below is retained from HERBS for historical workflow reference;
its title bar predates the DriftlessMap rebrand.

<img src="./driftlessmap/herbs.png" width="800px" alt="Historical HERBS interface used as the basis for DriftlessMap">

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
