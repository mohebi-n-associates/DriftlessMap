# Implant workflow design: Neuropixels, optical fibers and microprisms

Status: implemented in 2.0.0a13–2.0.0a15 (approved 27 October 2026). Builds on
the Phase 3 mapping records and undo (`phase3_mapping_design.md`).

Decisions taken on 27 October 2026:

1. Map both the drawn boundaries and a fitted device model; the outlines
   are the evidence, the fit gives the reported coordinates.
2. The fiber light-cone estimate (illuminated regions from NA and diameter)
   comes later. Fiber NA is stored now so it can be added without new input.
3. Microprisms are 1.5 x 1.5 mm by default but sized per implant. Required
   results: the bottom (DV) and laterality (ML).
4. Sections can be coronal or sagittal (horizontal works the same way but is
   not a target case).

## 1. One workflow, three implant types

V2 should be organised around what the experimenter implanted. The three
cases share one workflow and differ only in the device shape and the report:

1. **Add an implant**: choose its type and give it a name and its specs.
2. **Draw on each section**: outline what the implant left in the tissue.
3. **Map**: carry the outlines to the atlas with the section's registration.
4. **Build**: fit the device shape to all mapped outlines and report it.

| | Neuropixels (exists) | Optical fiber | Microprism |
| --- | --- | --- | --- |
| Specs | Probe model, shanks | Diameter (µm, default 200), NA (default 0.39; stored for later) | Width x depth (µm, default 1500 x 1500), imaging face (medial, lateral, anterior or posterior) |
| Drawn per section | Track points | Closed outline of the track cavity; optional tip click | Closed outline of the footprint; optional bottom-edge click |
| Fitted model | Line through all marks | Cylinder: axis and tip | Rectangular block: insertion axis, bottom edge, face plane |
| Main results | Contacts and their regions | **Tip** AP/ML/DV and region; entry point; angle | **Bottom DV**; **ML** of the medial edge, lateral edge, centre and imaging face; AP extent; angle |

Neuropixels keeps its present path unchanged; it becomes one type in the
same Implants list so all three are added, mapped, built and reported in the
same place.

## 2. What the example section shows

The example (`pfc-2.tif`, coronal frontal section, brightfield) has the
fiber track as a white slot just right of the midline, from the dorsal surface
to mid-depth. Two features matter for the design:

- **Tears look like tracks** (the V-shaped gap in the left hemisphere), and
  bubbles appear as dark rings. Outlines are therefore always drawn or
  confirmed by the user. The magic wand may propose the bright cavity as a
  starting outline, never as a result.
- **One section shows a chord of the fiber**, not its full diameter, unless
  it passes through the axis. A coronal section through a vertical fiber
  shows a slot narrower than the diameter when off-centre; the AP centre is
  where the slot is widest. The tip is the deepest point over all sections.

## 3. Data model

**Implant definitions** (new, saved in the project as `implants`):

| Field | Meaning |
| --- | --- |
| `implant_id` | Random 32-hex identifier |
| `name` | User name, unique in the project ("Fiber L", "Prism 1") |
| `type` | `neuropixels`, `fiber` or `prism` |
| `specs` | Fiber: `diameter_um`, `na`. Prism: `width_um`, `depth_um`, `face`. Validated ranges; unknown keys rejected |
| `colour` | Display colour |

Renaming an implant renames its parts and built object; identity is the
`implant_id`, not the name.

**Outlines.** An outline is a closed polygon of section pixel vertices
(not a filled mask, so it stays small and editable), plus the optional tip or
bottom-edge point. The live outlines of the loaded section are working data,
as cells and drawings are today.

**Mapping records.** `fiber` and `prism` become mapping kinds. The unit key
is `(section_id, kind, implant_id)`; the record's kept source is the polygon
and optional point. Everything from Phase 3 then applies unchanged: one
record per section and implant, re-mapping replaces it, out-of-date labels,
Update mapping, Edit marks and undo. (The record field now called `probe`
holds the implant identifier for these kinds; Neuropixels records keep the
probe name, so existing preview projects still load.)

**Mapping an outline.** Before transfer, each polygon edge is resampled to at
most 2 section pixels between points, because the piecewise-affine
registration bends straight edges. The resampled points are transferred like
contour points and placed in 3D with `get_3d_data_from_2d_view`, so coronal,
sagittal and tilted slices all work. A part ("Fiber L - piece") holds one
section's mapped outline; mapping makes it at once (there is no separate Make
parts step for implants).

## 4. Building

All fitting runs on the mapped 3D outline points in atlas voxels, so it does
not depend on the cutting plane. It is GUI-free (`driftlessmap/implants.py`)
and deterministic.

**Fiber.**

1. Fill each mapped outline in its own section plane and sample its
   interior.
2. Axis: robust line fit (`robust_probe_line_fit`) through all interior
   samples. With one section only, the axis is the outline's long axis in
   that plane, and the report says the out-of-plane angle is unknown.
3. Tip: the deepest outline point along the axis, projected onto the axis;
   a user tip click, when given, is used instead and the difference is
   reported.
4. Entry: where the axis meets the brain surface
   (`find_probe_surface_entry`), giving depth below the surface.
5. Checks: the widest mapped chord against the specified diameter. Wider than
   1.5 x the diameter warns of tissue damage or a tear in the outline;
   every chord much narrower warns that no section passed near the axis.

**Microprism.**

1. Insertion axis: line fit through all outline points (one section: the
   outline's long axis, as for fibers).
2. Bottom: the deepest outline points along the axis define the bottom edge;
   bottom DV is reported for the edge centre and both corners.
3. Laterality: ML of the medial edge, the lateral edge, the centre and the
   imaging-face plane. Coronal sections show ML directly. A sagittal section
   shows AP and DV only; ML then comes from the series of sagittal sections
   that contain the prism and is limited by section spacing, which the report
   states.
4. AP extent from the outlines (sagittal) or the first and last sections that
   contain the prism (coronal; again limited by spacing).
5. Checks: outline width and depth against the specified size, warning
   beyond 20 % (shrinkage, or a section not through the full prism).

**Coordinates and regions.** As probes do today: atlas voxel and physical
coordinates, estimated bregma coordinates for the Allen CCF
(`allen_ccf_to_estimated_bregma_mm`, labelled as an estimate), and the region
at each reported point. For prisms, also the regions along the imaging face
from the bottom edge up to the surface.

**Built objects** (`merged fiber`, `merged prism`) are self-contained like
merged probes: specs, fitted model, results, mapped outlines, atlas transform
and provenance, and their mapping origin. They draw in 3D as a cylinder or a
block with the mapped outlines, export to `.dmapobj`, and add rows to a new
implant CSV (one row per implant: type, name, results, region names,
warnings). Building replaces the implant's earlier built object.

## 5. Interface (V2)

The Annotate step gains an **Implants** card above the generic marks:

- A list of implants with type icon, colour and status (parts, built, out of
  date). **Add implant** asks type, name and specs.
- With an implant selected: **Draw outline** (click vertices; double-click
  or click the first vertex to close; drag a vertex to edit), **Propose
  outline** (magic wand on the bright cavity, then edit), and **Mark tip** /
  **Mark bottom edge**.
- **Map** maps the selected implant's outline; **Build** fits it.

The Results step shows each implant's report card and the 3D view; Export
writes the implant CSV and objects.

## 6. Persistence

Payload schema stays 3: `implants` and the new mapping kinds are optional and
absent in older files.

| Field | Default when absent |
| --- | --- |
| `implants` | No fibers or prisms (Neuropixels stay named probes and are listed from them) |
| Mapping records of kind `fiber` / `prism` | None |

Loading validates specs, identifiers, polygons (finite, at least 3
vertices) and implant references; an invalid implant or record is dropped
with a message rather than failing the project.

## 7. Delivery

As delivered: 2.0.0a13, the GUI-free model, fiber and prism fits and reports;
2.0.0a14, the engine (mapping, parts, building, undo, projects, 3D display,
`.dmapobj` and the implant CSV); 2.0.0a15, the V2 Implants card and outline
editor. Later: fiber light-cone regions from NA and diameter.

## 8. Tests

- Specs and implant validation; save and reopen; older projects open.
- Outline resampling and mapping on coronal, sagittal and tilted slices.
- Fiber fit on synthetic cylinders cut coronally and sagittally (vertical
  and angled): tip within half a voxel; one-section fallback; diameter
  warnings.
- Prism fit on synthetic blocks: bottom DV, edge and face ML; sagittal-only
  ML limited by spacing; size warnings.
- Mapping records, out of date, Update and undo for both kinds.
- V2: adding implants, drawing, mapping, building and the report.

## 9. Points to confirm

1. Default fiber diameter 200 µm and NA 0.39; other common values offered in
   a list (100, 105, 200, 400 µm; 0.22, 0.37, 0.39, 0.50 NA).
2. Prism face choices: medial, lateral, anterior, posterior.
3. DV reported both from estimated bregma and as depth below the brain
   surface along the insertion axis.
4. Fiber and prism outlines are polygons drawn on the section; no
   automatic detection beyond the editable magic-wand proposal.
