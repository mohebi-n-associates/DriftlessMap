# Tutorials

Step-by-step guides with screenshots of the 2.0 interface of DriftlessMap 2.5
(the default; `driftlessmap --classic` opens the classic interface, and each
tutorial names its classic menu commands). The
[User Manual](../MANUAL.md) is the full reference.

## Installation

- [Create an environment with Anaconda or Miniconda](create_enviroment_in_Anaconda.md)
- [Work on DriftlessMap in PyCharm](install_through_pycharm.md) (developers)

## Atlases

- [Downloading the rat atlases](Atlas_Related/download_rat_atlases.md):
  Waxholm Space v4.01 and the SWC female rat atlas.
- [Upload and process user defined atlases](upload_and_process_user_defined_atlases.md):
  the Atlas Processor for your own volume atlas.
- [Upload a slice atlas](Atlas_Related/upload_slice_atlas.md): a 2D atlas plate.
- [About atlas coordinates](Atlas_Related/about_atlas_through_herbs.md)

## Registration

- [Automatic section matching and landmark proposal](Registration_Related/automatic_section_and_landmarks.md)

## Probes

1. [Important things to know before you start](Probe_Related/1-Important_to_know_before_you_start.md)
2. [Pre-plan a Neuropixels 1.0 probe](Probe_Related/2-Pre-Plan_NP1.md)
3. [Pre-plan Neuropixels 2.0 single and four-shank probes](Probe_Related/3-Pre-Plan_NP2.md)
4. [Design a linear silicon probe](Probe_Related/4-Design_Linear_Silicon_Probe.md)
5. [Design multi-shank probes](Probe_Related/5-Design_multi_shanks_Probes.md)

## External data

- [Important to know before you upload external data](External_Related/important_to_know_before_you_start.md)
- [Upload external cell points](External_Related/upload_external_cell_points.md)

## Coming from HERBS

DriftlessMap grew out of HERBS (see the [HERBS legacy note](../ORIGINS.md)).
Launch `driftlessmap` instead of `herbs` and use `import driftlessmap` in new
Python code. New files use the `.dmap*` extensions; HERBS files and scripts
remain supported.
