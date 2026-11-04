# Probe planning design: a planned probe is a pose

Status: approved 4 November 2026 for implementation in four phases,
2.8.0 (Phase 1) to 2.11.0 (Phase 4). Builds on the pre-surgical probe
plan (MANUAL Section 11), `probe_utiles.calculate_probe_info`, the named
probes of the V2 Annotate step (`v2/probes.py`) and the undo history
(`phase3_mapping_design.md`).

Background: a comparison with Pinpoint (VirtualBrainLab, v2 Unity app and
the v5 web app at pinpoint.allenneuraldynamics.org) on 4 November 2026.
Pinpoint keeps one pose per probe (tip plus angles) and shows everything the
surgeon needs as the pose changes; DriftlessMap made a plan from two clicks
on one slice, then Add, Build and a separate information window.

## 1. What changes for the user

Before (2.7.0 and earlier):

1. Choose a slice and tilt; the track can only lie in that slice.
2. Mark track, click the entry, click the tip.
3. Add the points to the probe; Build it.
4. Open the Region table to see entry, depth, angles and regions.
5. To change the plan, click again (the plan is replaced) and build again.

After:

1. Add a probe and give it a plan (Annotate, the probe's **Plan** card;
   or Project > Atlas card > **Plan a probe on this atlas…**).
2. Set the plan any way that suits: type the tip (AP, ML, DV from Bregma),
   the AP and ML tilts and the roll; or click the entry and the tip on any
   atlas view; or snap the tip to a region's centre; then nudge it.
3. Every change updates the readout at once (entry on the brain surface,
   depth along the probe, tip, tilts, the regions along the shank and
   their lengths, warnings) and the planned probe in 3D and on the atlas.
   There is no Add or Build step for a plan.
4. Copy the plan as one self-describing line, or export it with the other
   results.

Post-surgical reconstruction (Mark track on sections, Map, Build) does not
change. A probe can have a plan and an observed track; the plan is built as
its own object, `"<probe> plan"`, so the two can be compared.

## 2. The model (GUI-free, `driftlessmap/probe_plans.py`)

### 2.1 Frame

All positions are in the atlas frame DriftlessMap already uses for probes:
Bregma-relative, x = ML (positive is the animal's right), y = AP (positive
is anterior), z = DV (positive is dorsal), stored in micrometres. Atlas
voxels are `um / vox_size_um + origin_3d` (the same convention as
`calculate_probe_info` and the implant models). Bregma is the atlas's
(estimated, for Allen CCFv3) Bregma, as everywhere else.

### 2.2 A plan

```
ProbePlan
  probe            name of the probe it belongs to (the ProbeBook name)
  tip_um           [ML, AP, DV] of the probe tip, from Bregma
  ap_tilt_deg      tilt in the sagittal plane, -80..80;
                   positive: the tip is anterior of the entry
  ml_tilt_deg      tilt in the coronal plane, -80..80;
                   positive: the tip is to the animal's right of the entry
  roll_deg         turn about the shank, 0..360; 0: the contacts face
                   anterior (4-shank probes then spread their shanks along
                   ML); positive turns the face towards the animal's right
                   seen from above
  probe_settings   the probe design (the same dict `.dmapprobe` saves:
                   type, length, tip, sites, multi_shanks)
  shank_offsets_um across-the-face offsets of each shank, or None for one
                   shank (NP2.0 four-shank: -375, -125, 125, 375)
  bank             Phase 2: recording window (bank index or "all")
  targets, avoid   Phase 4: region ids (default empty)
  craniotomy       Phase 3: craniotomy id or None
```

The direction (entry to tip, pointing into the brain) follows from the two
projected tilts: `d = normalise([tan(ml), tan(ap), -1])`. These are the
angles `probe_utiles.get_angles` already reports, with a sign added, so a
built plan's Region table shows the same numbers as the plan.

`PlanBook` holds the plans by probe name, validates them (`from_list` returns
plans and problems, like `ImplantBook`), renames and deletes them with their
probe, and serialises to plain JSON (`to_list`).

### 2.3 What a plan gives (`plan_readout`)

From the label volume (`DriftlessMap._merge_label_volume`), label info and
voxel size:

* **Entry**: the first brain voxel met coming down the line from above the
  brain (the surface the probe touches first), as AP, ML and DV from Bregma.
* **Depth**: distance along the probe from the entry to the tip; this is
  what the manipulator is advanced after zeroing at the brain surface.
* **Tip** and the **tilts** in words (anterior/posterior, medial/lateral,
  using the side of the entry).
* **Regions along the shank**: from the entry to the tip, each region's
  acronym, name, start and end depth and length (sampled every half voxel).
  Phase 2 adds the contacts and the recording window.
* **Warnings**: the tip is outside the brain or above the surface; the line
  never meets the brain; the depth is longer than the shank (the probe
  cannot reach); the line leaves the atlas; the probe crosses the midline.

The readout is cheap (one line through the volume) and is recomputed on
every change. The same function scores Phase 4 proposals, so a proposal and
a hand-made plan are judged the same way.

### 2.4 Building the planned probe

`ProbePlanEngineMixin.build_plan(probe)` turns the plan into the two-point
centre line `[entry, tip]` (and, for several shanks, one line per shank
through `get_center_lines`, with the face normal from the roll) and calls
`calculate_probe_info(..., pre_plan=True)` exactly as a clicked plan did,
so the built object, its reconstruction metadata, exports and Region table
are unchanged. The objects are named `"<probe> plan"` (`"<probe> plan shank
N"`) and carry `plan_of: <probe>` and the plan itself in their data.
Rebuilding replaces them. The plan is rebuilt automatically when an edit is
finished (Enter or leaving a field, a click, a snap), inside
`undoable("Edit <probe> plan")`, so Edit > Undo mapping step takes a plan
change back. The atlas description needed for the reconstruction metadata
is computed once per loaded atlas and reused.

## 3. Persistence

* Project payload: optional `probe_plans` (a list of plan dicts). Absent in
  older projects (no plans); no schema bump, because older readers ignore it
  and keep the built plan objects as ordinary probes. Invalid plans are left
  out with a message, and the project still opens.
* Plans are document state (not section state): they are not in
  `SECTION_FIELDS`.
* Plans are part of the undo transaction state.
* Renaming a probe renames its plan and its plan objects; deleting a probe
  deletes its plan.
* `export_all_results` writes `probe_plans.csv` (one line per plan: atlas,
  frame, entry, tip, depth, tilts, roll, probe type, regions).

## 4. Phases

### Phase 1, 2.8.0: plan by pose

* `probe_plans.py` (model, readout, coordinate line), the engine mixin,
  persistence, undo, rename/delete.
* V2: a **Plan** card for the selected probe in Annotate: numeric fields
  (tip AP/ML/DV in mm, AP and ML tilt, roll), the probe type, **Snap tip to
  region** (the region selected in the Regions tree), **Set from clicks**
  (Mark track: click the entry and then the tip on an atlas view; the two
  points set the tip and tilts), **Show on atlas** (moves the pages to the
  tip), **Copy coordinates**, and the live readout.
* An atlas overlay draws each plan on the three atlas views: the track
  projected onto the slice (dashed), the part within 100 µm of the slice
  solid, the entry and tip marked.
* Plan a probe on this atlas (Project step and Ctrl/Cmd+K) creates a probe
  with a plan at Bregma, 3 mm deep, so the readout is filled from the start.

### Phase 2, 2.9.0: see and steer

* A **shank strip**: the regions along the shank drawn to scale with the
  contacts and the chosen recording window (bank), region names beside
  them; hovering names the region.
* **Probe-plane view**: the atlas sampled in the plane of the probe (the
  plane through the shank containing the face normal), so the whole track is
  seen even when it lies across slices.
* **Keyboard nudging** while the Plan card is active: W/S AP, A/D ML, Q/E DV,
  Z/X depth along the probe, I/K AP tilt, J/L ML tilt, U/O roll; step 10,
  50, 100, 500 µm (degrees 1 or 5) shown and changed with -/+; Shift for the
  largest step.
* **Move to the surface**: put the tip on the brain surface, either along
  the probe or straight down in DV, then set the depth.
* Recording window coverage per region in the readout.

### Phase 3, 2.10.0: surgery

* **Craniotomies**: named circles (AP, ML, diameter) belonging to the
  project; a plan can be tied to one; a warning when the entry lies outside
  it; **Fit craniotomy to plans**; drawn on the horizontal view.
* **Clearance between probes**: the closest approach of every pair of
  planned shanks inside the brain and up to 3 mm above it, with a warning
  below a set clearance (default 300 µm) and the closest pair named.
* **Angle conventions** for display and entry: the AP/ML tilts (default) or
  arm angles (azimuth, the direction the probe leans in from anterior
  towards the animal's right, and elevation from vertical), converted
  exactly both ways.
* **Bregma-Lambda scaling**: the measured distance for the animal scales AP
  (and ML/DV proportionally) for the exported surgical coordinates; the atlas
  coordinates stay as they are; the copied line names the scaling.

### Phase 4, 2.11.0: propose a plan

* Per probe: **Targets** (regions, in order from dorsal to ventral when
  that matters) and **Avoid** (regions, plus a margin from the midline);
  **Use checked regions** fills Targets from the Regions tree.
* Limits: largest AP and ML tilt, fixed tilts (the rig's arm is fixed),
  the craniotomy (Phase 3), the probe's shank length and recording window.
* `propose_plans` (GUI-free) searches candidate lines through the targets
  over the allowed tilts at a reduced resolution, slides the recording
  window to its best depth along each line, scores each line (window inside
  the targets, every target reached, nothing avoided crossed, entry on the
  surface, small tilt preferred) and refines the best at full resolution.
* A dialog lists ranked proposals with entry, tilts, depth, the length in
  each target and warnings; choosing one sets the plan.
* When nothing works it says why: the targets are not on one line within
  the tilt limits (and the tilt that would be needed), the depth needed is
  longer than the shank, every line crosses an avoided region or the
  midline margin, or a target is too small for the window.
* The score uses the atlas only: vessels, the sinus and the skull are not
  in it, and real brains differ from the atlas. The dialog says so.

## 5. Not planned

A full manipulator joint solver (Pinpoint v5's inverse kinematics), gamepad
control, cloud sync, and collisions with rig and headstage models.
