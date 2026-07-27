# Project origins and attribution

## Relationship to HERBS

DriftlessMap is an independent open-source continuation of HERBS (Histological
E-data Registration in rodent Brain Spaces). It retains substantial portions of
the original HERBS code and therefore remains a derivative work under the MIT
License.

- Original project: <https://github.com/Whitlock-Group/HERBS>
- Original license: MIT
- Recorded upstream base commit: `7a181097a57d9f34b189f233a484a0f0c228c5da`
- Independent project: <https://github.com/mohebi-n-associates/DriftlessMap>

DriftlessMap is not affiliated with or endorsed by the original HERBS
developers or the Whitlock Group.

## Original authors and publication

The original HERBS research software and publication were created by:

- Jingyi Guo Fuglstad
- Pearl Saldanha
- Jacopo Paglia
- Jonathan R. Whitlock
- Additional HERBS code, testing, documentation, and research contributors
  recorded in the repository history and `THANKS.txt`

Original publication:

Fuglstad JG, Saldanha P, Paglia J, Whitlock JR. Histological E-data
Registration in rodent Brain Spaces. *eLife*. 2023;12:e83496.
<https://doi.org/10.7554/eLife.83496>

The original software is also identified as RRID:SCR_022776.

## Independent development

Independent work after the upstream base includes platform modernization,
current Python and Qt support, safer persistence, validation and security
hardening, automated regression tests, atlas-coordinate corrections, probe
reconstruction and CSV export, ROI analysis, and expanded documentation.
The Git history is intentionally preserved so individual contributions remain
auditable.

DriftlessMap development is led by
[Mohebi & Associates](https://www.mohebi-associates.org/) and
[Ali Mohebi](https://www.mohebial.com/). See `CONTRIBUTORS.md` for the current
and original contributor groups.

## Licensing and notices

The complete project remains licensed under the MIT License:

- The original `Copyright (c) 2022 HERBS Developers` notice is preserved
  verbatim in `LICENSE.txt`.
- `Copyright (c) 2026 Ali Mohebi and DriftlessMap contributors` covers
  subsequent modifications.
- Neither the new project name nor this attribution statement changes the
  license governing the original HERBS code.

When redistributing DriftlessMap or a substantial portion of its source, retain
`LICENSE.txt`. Preserving this file is a condition of the MIT License.

## Compatibility names

Names such as `.herbs*` legacy file extensions, `HERBS_CONFIG_DIR`, and
persisted `herbs_vox` coordinate fields are retained only where needed for data
compatibility. DriftlessMap does not install a top-level `herbs` Python package
or a `herbs` command. These compatibility names do not indicate affiliation
with or endorsement by the original HERBS developers.
