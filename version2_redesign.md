# DriftlessMap 2.0: Interface Redesign

Status: revised proposal for discussion. This document describes intended
behavior and release gates; it does not describe implemented features.

The goal is to make scientific work easier to understand, perform and check.
A consistent appearance supports that goal, but looking different from 1.x
is not a success criterion. Preserve existing scientific capabilities and
file loading while making state, dependencies and the next useful action
visible. V2 also makes direct multichannel microscopy input a core workflow:
open a native 16-bit TIFF, choose what to display, adjust its appearance and
register using an explicitly selected channel such as DAPI, without an
intermediate flattened export from ImageJ.

Development takes place on a separate `v2-redesign` branch. The stable branch
continues serving 1.x until V2 satisfies the release gates. This document records
the branch strategy; it does not itself create or switch Git branches.

The first implementation target is one complete workflow: **open → match →
register → annotate → inspect → export → save/reopen**. Expand only after
that workflow works through the new shell with representative data. A new
shell does not authorize silent changes to scientific results.

## Implementation status (first preview, `v2-redesign` branch)

Done, with tests:

- Registration-input recipe (Legacy exactly as 1.6, or chosen channels) used
  by both automatic stages; chosen in the Section step or Atlas > Registration
  Channels…; saved in payload schema 3.
- Up to 16 channels at native 8/16-bit depth; 1.x four-element display lists
  and five-entry cell counts padded on load.
- TIFF hyperstacks (Z browsed as pages, further axes fixed and reported),
  several series as scenes read on demand, OME/ImageJ channel names and
  colours, readable errors and an alpha-channel note.
- Human registration review tied to a fingerprint of landmarks, frame points,
  plane, page, tilt and image size; mapping records whether it was reviewed.
- The V2 shell: step rail with concrete status, Compare/Atlas/Section/3D/
  Multi-plane views, tool options, objects/layers/regions column, status line
  with navigation-proof unsaved-change detection, light and dark themes,
  command palette covering every 1.x menu command, single-key shortcuts that
  never fire while typing.
- Section step: per-channel rows, brightness/contrast, gamma, Auto, registration
  input preview; Register step: landmark list by kind, mesh check, review and
  warp preview; Annotate and Results steps wrapping the 1.x operations.
- End-to-end check on a 16-bit DAPI/GFP/tracer OME-TIFF: DAPI-only match and
  landmarks, review, warp, probe mapping, build, save and reopen.

Not yet done (see Sections 3, 6 and 15): source retention and staleness,
undo for mapping and building, named anatomical sides for the hemisphere
choice, series/Z/T selectors beyond the page slider, pyramid levels, a fully
themed restyle of adopted 1.x controls, and a desktop bundle that starts the
preview.

## Contents

1. [Scope and priorities](#1-scope-and-priorities)
2. [Problems and assumptions to validate](#2-problems-and-assumptions-to-validate)
3. [State and interaction contract](#3-state-and-interaction-contract)
4. [The window and workspace](#4-the-window-and-workspace)
5. [Start screen and projects](#5-start-screen-and-projects)
6. [The workflow steps](#6-the-workflow-steps)
7. [Canvas, views and navigation](#7-canvas-views-and-navigation)
8. [Inspector and outline](#8-inspector-and-outline)
9. [Tools, commands and shortcuts](#9-tools-commands-and-shortcuts)
10. [Capability migration inventory](#10-capability-migration-inventory)
11. [Simplification without capability loss](#11-simplification-without-capability-loss)
12. [Feedback, undo and background work](#12-feedback-undo-and-background-work)
13. [Visual design and accessibility](#13-visual-design-and-accessibility)
14. [Architecture and persistence](#14-architecture-and-persistence)
15. [Migration and release gates](#15-migration-and-release-gates)
16. [Risks and decisions still required](#16-risks-and-decisions-still-required)
17. [Validation and acceptance](#17-validation-and-acceptance)

---

## 1. Scope and priorities

### Required for the redesign

- Organize controls around work: preparing a section, finding a plane,
  reviewing registration, making annotations and checking results.
- Preserve a fast manual path alongside automation. Suggestions are useful
  starting points; the interface must communicate their limitations.
- Show the active atlas, image, coordinate frame, registration state and save
  state. Distinguish source data, previews and derived results.
- Preserve valid DriftlessMap and supported HERBS loading, provenance checks,
  safe archives, embedded active rasters and atomic saves.
- Preserve scientific algorithms, coordinate conventions and export meanings.
  Explicit registration-channel selection is a deliberate input change; validate
  and record its preprocessing without silently changing legacy behavior.
- Support native 16-bit multichannel TIFF input, independent display and
  registration-channel selection, and non-destructive brightness/contrast controls.
- Keep PyQt6 widgets, pyqtgraph and OpenGL. Extract application logic in small
  increments on the V2 branch, with shared services wherever both interfaces remain.
- Preserve all current workflows before merging V2 into the stable branch.
  Development builds may cover fewer workflows and must identify their limits;
  users can continue using the stable 1.x release.

### First preview

One active histology section with native multichannel 16-bit TIFF input, a volume
atlas, per-channel display controls, explicit registration-channel selection,
manual and suggested matching, paired landmarks, warp review, probe annotations,
explicit reconstruction, exports and complete project saving/reopening. Existing
dialogs may be reused. Persistence of the new state (channels, display settings,
registration input, review) is part of this scope, not later polish. This is an
opt-in V2 development build, not a staged migration of stable 1.x users.

The first preview keeps the current mapping and merge semantics: mapping moves
section marks to the atlas, and building a 3D object replaces its parts, which
Edit parts restores. The shell labels these consequences plainly before the user
acts. Retaining source marks after mapping, dependency and stale-result tracking,
and undo for mapping and building are Phase 3 work (Section 15). The contract in
Section 3 is the target they must meet; the first preview must not contradict it,
but it does not implement all of it.

### Deferred unless separately justified

- Multiple independently editable sections in one project.
- Automatic reconstruction when visiting Results.
- A persistent image-processing recipe or adjustment stack.
- Algorithmic per-landmark confidence or automatic anatomical error detection.
- Global history navigation, background autosave and nonmodal scientific jobs.
- A new atlas library, replacement atlas-processing wizards, minimaps,
  transform gizmos and decorative animation.

Deferral of a new interaction does not remove an existing capability. Keep
its current control or dialog until a replacement has passed validation.

---

## 2. Problems and assumptions to validate

The existing menus, toolbar and five sidebar tabs expose many operations
without explaining their relationships. Image warping, annotation mapping,
object-piece creation and reconstruction are particularly easy to confuse.
Some feedback is transient, and undo covers only a limited set of edits.

The redesign should address these problems without assuming that every
technical control is clutter. Exact depth, tilt, levels, frame-point count,
coordinate readouts and layer composition can be essential scientific
controls. Their location and explanation may need improvement; their
precision must remain available.

Validate these assumptions with both new and experienced users:

- Task-oriented panels reduce uncertainty without imposing a rigid sequence.
- Frequent operations remain fast when controls move into context.
- Compare and Overlay cover common registration tasks while single-view and
  Multi-plane layouts remain easy to reach.
- A shared outline is usable with many objects and a large atlas region tree.
- New users understand suggestions, manual review and stale results.

Measure current task times and failure modes before implementation. Menu
counts and fewer clicks alone do not establish a usability problem or a fix.

---

## 3. State and interaction contract

These rules precede visual design. The implementation must make them explicit
in the model and commands, rather than infer them from which panel is open.
They are the target contract. The first preview implements the review rules
and the display/analysis separation, and labels the current mapping and merge
behaviour; source retention and staleness tracking arrive in Phase 3.

### Source, preview and result

| State | Meaning | Allowed changes |
| --- | --- | --- |
| Source section and annotations | Current histology raster, its geometry, and marks in that image's coordinate frame | Explicit editing commands; original raster remains recoverable under the existing project contract |
| Registration | Atlas content/frame, chosen slice and tilt, image geometry, landmarks and topology | Explicit apply/edit commands; numerical validity and user review are separate |
| Warp preview | An image resampled with a particular registration and direction | Replaceable display result; creating or removing it does not transfer annotations |
| Mapped annotation | Coordinates derived from source marks and a particular registration | Explicit Map/Update command; preserve source marks for the current section |
| Reconstruction | Object built from identified parts, atlas data and type-specific settings | Explicit Build/Update command; entering Results is read-only |
| Historical or imported object | Stored result whose original editable image/registration may be unavailable | Inspect/export with known provenance; never imply that it can be recomputed from the current section |

Existing mapping clears some source annotation lists, and existing merge
operations replace pieces with merged objects. Retaining sources and tracking
derivation are deliberate orchestration changes, requiring persistence and
transaction tests. They are not achieved by renaming the existing handlers.

### Revision and invalidation rules

Every derived result records its dependencies. In-memory revisions detect
changes during a session; persisted dependency metadata must also allow
staleness to be determined after reopening. Do not use file paths as identity.

| Change | Required effect |
| --- | --- |
| Select/hover a candidate, change view, zoom, select a row | Preview or navigation only; no scientific mutation or dirty flag |
| Apply a different atlas plane/depth/tilt or edit landmarks/topology | Invalidate dependent previews and mappings; retain source marks and previous results, clearly labeled stale |
| Edit source annotations | Mark their mapped results and dependent reconstructions stale; other annotations remain unaffected |
| Change probe geometry, face, merge-sites choice or contributing parts | Mark the dependent reconstruction stale |
| Change brightness/contrast, LUT, channel visibility/colour, opacity or interface theme | Display only: never change raw samples, registration input or coordinates; saved appearance changes dirty project display state, while an application theme preference does not |
| Change registration channels or registration preprocessing | Invalidate pending/cached proposals; retain the committed transform and results with their original input recipe. Label them as built with the previous recipe until a new proposal is explicitly applied and reviewed |
| Apply cleanup that changes pixels but preserves geometry | Invalidate affected proposal jobs/previews; retain coordinates, clear anatomical review and require review of the changed image |
| Crop, rotate, flip, change scene/page or read scale | Treat as an image-geometry/source change; apply a tested coordinate transformation to affected data or explicitly reset/archive it before committing |
| Replace the current section | Resolve unsaved working annotations; preserve stored objects as historical results, then start a fresh registration for the new image |
| Change atlas content or coordinate frame | Reject reuse of incompatible mappings; offer a new project or explicit reset of dependent work, preserving the original project |

A stale result remains inspectable with its original context. It cannot be
exported as a current result. Offer Update when its dependencies are available;
otherwise offer an explicitly labeled export of the stored historical result.
Never silently discard work or present old results on a new plane as current.

A successful Map/Update replaces the derivation for the same source annotation;
it does not append duplicate parts. Failure leaves the last committed state
intact. Undo restores sources, derived results and validity flags together.

### Review is a human action

- **Mesh valid / review / invalid** describes geometry and numerical checks.
  It does not certify anatomical correspondence.
- **Not reviewed / reviewed by user** describes an explicit review of the
  current registration. Point-level review, if implemented, follows the same
  rule. Dragging a point is an edit, not a review action.
- Editing reviewed inputs clears affected review states. Imported legacy work
  has review state **not recorded**, never automatically **reviewed**.
- No invented confidence percentages or automatic “Check this point” labels.
  Such features require separate algorithm outputs and validation.

Navigation never confirms a suggestion, maps marks, builds an object or changes
the saved scientific result. Necessary actions have explicit controls.

---

## 4. The window and workspace

The shell has a task rail, central canvas, task controls, an inspector/outline,
and a persistent status line. Keep the native title and menu bars. The exact
placement of task controls is subject to a Qt prototype with real images.

```text
┌ DriftlessMap — Mouse_S12.dmap • ───────────────────────────────────┐
│ File   Edit   View   Help                         Search commands  │
├──────────┬───────────────────────────────────────┬─────────────────┤
│ Project  │ Compare  Overlay  3D  Multi-plane      │ Inspector       │
│ Section  │ Coronal · depth … mm · tilt … / …      │ Landmark 4      │
│ Match    ├───────────────────┬───────────────────┤ Atlas x,y       │
│ Register │ Atlas             │ Current section   │ Section x,y     │
│ Annotate │                   │                   │ Review: pending │
│ Results  │                   │                   ├─────────────────┤
│          ├───────────────────┴───────────────────┤ Outline         │
│          │ Add point  Measure  Suggest landmarks │ Landmarks       │
│          │ Mesh valid · Anatomical review pending│ Working marks   │
│          │ Preview warp   Mark review complete   │ Stored objects  │
├──────────┴───────────────────────────────────────┴─────────────────┤
│ Unsaved changes · Allen mouse 25 µm · Current section: S12         │
└───────────────────────────────────────────────────────────────────┘
```

Task navigation remains free. Missing inputs disable the relevant action with
an explanation and a link to obtain them; they do not lock entire panels.
Avoid progress ticks that imply scientific correctness. Show concrete states
such as “image loaded,” “review pending” or “results stale.”

The rail and inspector can collapse, task controls can compact, and either
image can be maximized. Frequent tools have visible labels. A floating toolbar
is optional only if testing shows that it does not obscure useful image area.

---

## 5. Start screen and projects

Start with **Open project**, **New project** and recent projects. A recent path
is a convenience, not verified identity. Missing sources use existing locate,
verification and embedded-raster recovery behavior.

A new project can start with **Histology mapping** or **Probe planning**.
These choose initial panels; they do not restrict later commands. More specific
templates are optional after the common workflows have been validated.

The Project panel shows:

- The chosen atlas, type, resolution and verification state; Load/Change atlas.
- **Current section**, with its thumbnail, source, scene/page and load scale.
- **Load section** when empty and **Replace section** when one is loaded.
- Existing atlas download, processing and slice-calibration tools.

There is no multi-section list or “N sections registered” counter in 2.0.
Replacing the active section does not promise a return to its editable image
and registration. Before replacement, offer to save the current project and
resolve unmapped work. Stored pieces and objects remain available with their
known source context. Do not manufacture missing provenance for legacy parts.

Use **Save Project** for a complete project and **Save Portable Copy** when the
original histology source must travel with it. A portable project still does
not embed the processed volume atlas.

---

## 6. The workflow steps

The rail describes common activities, not a mandatory wizard. Annotation can
start before registration; atlas mapping waits until its prerequisites exist.
The primary action follows the current state instead of always promoting
another automation run.

### 6.1 Project

Choose or locate the atlas and current image, inspect provenance, and open or
save the project. Atlas changes follow Section 3. Reuse current atlas tools
initially. A future slice-atlas wizard must preserve calibration, recropping,
Bregma selection, slice-layer creation and processed-slice export, including
editing an existing slice atlas.

### 6.2 Section: native multichannel images

The required workflow is **open the original image → inspect and adjust channels
→ choose registration input → register → annotate**. A user must not need ImageJ
merely to select DAPI, make the tissue visible or flatten a composite for import.
This is a focused microscopy workflow, not a promise to reproduce every ImageJ
filter, measurement or plugin.

#### Existing foundation and gaps

`TIFFReader` already preserves uint8/uint16 data for supported grayscale, RGB,
channel and page layouts. `ImageView` already exposes channel visibility, colour,
levels, LUT curves and gamma, including saved display state. The current reader
accepts only one TIFF series and a limited set of axis layouts, and the view has
a four-channel limit. Matching and landmark proposal currently receive the active
image array without an explicit user-selected registration channel.

Reuse and test these components. Do not describe native bit depth or channel
visibility as entirely new, or mistake existing partial support for a complete
microscopy import workflow.

#### Loading and interpreting TIFF data

- Accept 8-bit and 16-bit unsigned grayscale and multichannel TIFF, including
  common OME-TIFF and ImageJ TIFF layouts. Preserve original sample values and
  dtype; never require flattening to RGB or conversion to 8-bit for storage.
- Use metadata to distinguish channels (C), depth (Z), time (T), series/scenes
  and RGB samples. A three-plane grayscale stack is not automatically RGB or
  three channels. Ask for dimension interpretation when metadata is ambiguous,
  show a preview, and retain the user's interpretation in the project.
- Provide explicit series, Z and T selectors for supported multidimensional
  files, loading one active 2D section with all its channels. This does not create
  a multi-section project or imply volumetric registration. Projections are a
  separate feature; never silently collapse Z or T.
- Read channel names, colours and spatial calibration where available; allow
  missing labels/calibration to be entered without guessing biological identity
  from a colour or wavelength. Preserve original channel identity separately
  from an editable display name such as “DAPI.”
- Replace fixed four-channel UI/state arrays with metadata-driven channel lists.
  Validate at least 1-, 3-, 4- and 6-channel fixtures; establish documented
  resource limits from measured workloads. Never silently drop excess channels.
- Avoid decoding an entire Z/T stack merely to display one plane when the reader
  permits selective access. Use display-resolution previews and bounded caches;
  preserve full-resolution samples for the active raster at its stated read scale.
- Unsupported encodings/layouts receive a precise error before changing the
  project. Document supported cases with fixtures; do not claim every TIFF is
  supported because it has a `.tif` extension.
- RGBA TIFFs currently lose their alpha channel silently on load. V2 either
  keeps alpha as a named channel or drops it with a visible note; it never
  discards it silently.
- CZI input has the same four-channel limit (`czi_reader.py`). The channel
  workflow applies to CZI too: dynamic channel lists, names from metadata and
  registration-channel selection. CZI Z/T selection follows the same rules as
  TIFF.
- Large images (tiled or pyramidal OME-TIFF, whole-slide sizes) dominate memory
  and loading time. Read a pyramid level appropriate to the stated read scale
  where the file provides one, and record the level used; never load a full
  resolution plane only to downsample it when a pyramid exists.

#### Channel controls and brightness/contrast

Each channel row has a name, colour swatch, **Show** toggle and a distinct
**Use for registration** control. Selecting a channel for editing its display
settings is independent of both toggles. Offer composite view and a quick solo
view; an all-hidden display has a clear hint and Show all action.

```text
Channel          Show     Register     Display range        Gamma
DAPI              ✓          ✓          250 … 8000           1.0
GFP               ✓          —          100 … 4500           1.2
Probe tracer      —          —            0 … 6000           1.0

Registration input: DAPI · raw intensities    [Preview input]
```

For the selected channel provide:

- A histogram with exact black/min and white/max values in native intensity
  units (0–65535 for uint16), plus draggable range handles.
- Familiar brightness and contrast sliders adjusting that display window.
- Auto contrast with a documented percentile/clipping policy; show the resulting
  limits and provide Reset. Do not claim display clipping changes raw intensity.
- Gamma and existing LUT/curve controls under an accessible disclosure, colour
  selection and reset for one channel or all channels.

Changes affect display only and do not overwrite raw pixels. Pixel readouts and
future quantitative intensity operations use source values unless explicitly
labeled otherwise. Existing colour-detection tools must declare whether they
consume raw intensities or a rendered display; brightness changes never silently
rerun them. Persist appearance settings in the project, including hidden channels.
Reset display must not reset registration-channel selection or delete annotations.

#### Registration input is independent of display

Use one explicit input recipe for **Find atlas section** and **Suggest landmarks**.
Show the selected channels in both panels and provide a grayscale input preview.
A hidden channel can still be used for registration; showing another channel does
not add it to the registration input. Annotation can use a different visible
channel, with all co-located channels sharing the same spatial transform.

For a single selected channel, pass its native intensity plane to the existing
registration preprocessing. DAPI-only selection must exclude tracer and other
channels from both tissue-mask extraction and intensity matching. Never infer
DAPI from its display colour. Validate a selection before starting; no selected
channels or an unusable constant/empty input produces an actionable message,
not a silent fallback to every channel.

For multiple selected microscopy channels, define a reproducible initial recipe:
normalize each selected channel using the same documented robust percentile
bounds, clamp to [0, 1], and use their unweighted mean as a single analysis plane.
Both search and landmark proposal consume that plane through their existing
preprocessing. Record the bounds, channel identities and recipe version. Validate
this new recipe on representative stains before release; do not describe it as
identical to legacy averaging. Weighted blends and separate mask/intensity channel
selectors are deferred unless a demonstrated workflow needs them.

Display brightness, gamma and LUT colours never enter this recipe. A future
**Use adjusted intensities for registration** option would require a separate,
explicitly recorded analysis transform; it is not implied by making the image
look brighter. The input preview shows the analysis data, not the coloured overlay.

New multichannel imports ask the user to choose registration input before the
first automated run. Single-channel input can select its sole channel. RGB images
use a clearly labeled luminance/legacy mode, not guessed biological channels.
Older projects keep an explicit **Legacy input** mode reproducing prior behavior
until the user chooses a new recipe. Missing recorded channels on relocation or
reload require resolution rather than substitution by name or array position.

**Legacy input** is defined by what 1.6 does, because the two automatic stages
reduce channels differently:

- The **tissue mask** min–max normalises every channel separately to 0–255 and
  takes the per-pixel maximum over all channels, including hidden ones.
- The **intensity image** takes the unweighted mean of the first three raw
  channels (a fourth channel is ignored), min–max normalises it to 8 bits and
  applies CLAHE.

Legacy mode must reproduce both. The new channel recipe instead builds one
analysis plane and gives it to both stages, so the tissue mask changes too;
this is deliberate and must be documented with the release.

Changing the input recipe does not move existing landmarks. It invalidates pending
proposals; applying a new proposal triggers the registration invalidation rules
in Section 3. The committed fit retains the recipe actually used to produce it.
DAPI may be useful for anatomical structure, but selecting it never certifies that
a particular registration is accurate.

#### Geometry, cleanup and exports

Keep 1° nudges alongside 90° and 180° rotations and flips. Exact angle entry
for image rotation does not exist in 1.x; it is a new control and needs the same
geometry tests. Geometry changes apply consistently to all channels and affected
annotations. A crop box
may supplement lasso cropping; do not remove the latter before establishing
equivalent behavior.

Group Process, Mask Maker and cleanup uses of Magic Wand under **Clean up**.
Retain explicit Apply/Reset, processed raster export and known channel provenance.
A processed copy with reset is distinct from the deferred editable recipe stack.
Registration uses source channels by default; use of processed pixels must be
explicit and recorded. Apply the geometry/state transition rules in Section 3.

Keep **Export rendered image** (visible channels and their display settings)
distinct from **Export channel data** (native intensity arrays and dtype).
Rendered exports show their chosen output bit depth; they do not replace the
project's native multichannel raster. Save Project embeds every channel of the
active plane losslessly, including channels hidden or excluded from registration.
This workflow remains usable after embedded-raster fallback without the original
TIFF file. Navigating other Z/T planes still requires that source.

### 6.3 Match

Keep plane, depth, tilt and exact numeric entry visible beside **Find atlas
section**. Show units and the coordinate reference (Bregma or midline), with
orientation markers. Manual matching is a first-class path. Display the active
registration recipe (for example “DAPI only”) next to Find atlas section, with a
link to its input preview and channel controls.

Suggested candidates appear in a list or filmstrip if the layout permits.
Selecting or hovering previews a candidate with a **Preview** label; **Apply
candidate** commits it. Closing the preview restores the committed state.
Preserve any options controlling histology orientation and application of tilt.

For coronal/horizontal mirror ambiguity, present both orientations with explicit
anatomical left/right markers and show which image side maps to each side.
Require an explicit choice when applying an ambiguous suggestion. A sagittal
hemisphere choice uses named left/right sides. Never replace those distinctions
with “As suggested / Other” or claim a best-ranked match proves laterality.

Keep **Keep tilt while changing depth** and **Reset tilt** accessible. In 1.x
this toggle (Keep Slice Angles) is off by default, so changing depth resets the
tilt to zero. Preserve that default; a different default needs usability
evidence and documentation.
Exploring a plane is a preview until applied when existing registration work
would otherwise be invalidated.

### 6.4 Register

Place, edit and review paired landmarks, then inspect the warped image.
Show the same registration-channel recipe used by Match beside Suggest landmarks;
warp display can independently show all desired channels.

- **Suggest landmarks** produces a reviewable proposal. Replacing an existing
  set is an explicit undoable operation; it never silently erases manual work.
- The list shows pair number, coordinates, known origin/kind and review state.
  Unknown legacy kinds stay unknown. Selecting a row highlights both points.
  Centering the views is available without forcibly changing zoom on every click.
- **Add point** creates a pair in a clear atlas-then-section sequence. Escape
  cancels an incomplete pair. Any predicted correspondence is labeled as an
  estimate and hidden when no valid fit exists.
- **Mesh valid / review / invalid** opens geometric diagnostics. **Mark review
  complete** records the user's anatomical assessment separately.
- **Preview warp** supports section → atlas and atlas → section. It creates an
  overlay without consuming or mapping annotations. Remove preview is explicit.
- Frame points, Match Boundaries and landmark import/export remain accessible.

A valid mesh allows preview and mapping. **Mark review complete** sits beside
**Map annotations to atlas** as a single click; mapping without it is allowed,
and the mapped results are labelled **not reviewed** until the registration they
used is reviewed. This keeps review a human decision without adding a mandatory
step to expert work. Review does not promise correctness; the interface should
prompt inspection of internal anatomy as well as the outline. Tests must cover
manual and suggested registration.

### 6.5 Annotate

Create marks on the current section or directly in a supported atlas view.
The active coordinate frame is always labeled. Section marks are retained as
sources; **Map annotations to atlas** creates or updates their mapped result.
Marks added after registration can be mapped immediately using the same reviewed
registration. Marks edited later become stale until explicitly updated.

| Type | Existing capabilities to preserve |
| --- | --- |
| Probe | Track points, supported probe types/designers, face, multi-shank settings and merge-sites choice |
| Expression | Virus/tracer marks, colour detection with tolerance, painting, erasing and lasso operations |
| Cells | Manual points, selection, detection of similar cells, counts and external imports |
| Contour | Colour-based outline detection, drawing and editing |
| Drawing / ROI | Pencil, lasso, polygon and open/closed path behavior |

Use understandable names for **Working marks**, **Stored parts** and **Built
objects**. Group related parts under a name where their relationship is known.
A group is not an independently editable multi-section dataset.

**Build 3D / Update result** is explicit. Show the contributing parts and the
settings used. A successful build preserves recoverable inputs; a failed build
leaves the previous object and pieces intact. **Edit parts** exposes the existing
unmerge operation with its consequences and undo behavior. Do not disguise it
as a harmless view switch.

Automatically rebuilding on navigation and a continuously editable annotation
hierarchy are deferred. The initial shell may wrap current piece/merge semantics,
provided it clearly distinguishes source marks, stored parts and built results.

### 6.6 Results

Inspect region tables, probe details, object information and 3D views using
existing calculations. Each result shows whether it is current, stale or a
stored historical/imported result, along with the available atlas/source context.
Entering this panel changes no scientific state.

- Build/Update is available when inputs permit it.
- Compare, Show on plane and current object information actions remain available.
- Export lists the selected objects, formats and files to be written; preserve
  existing CSV, table, object and layer exports before adding new formats.
- Stale and historical export follows Section 3. An exported stored result keeps
  its original provenance; current inputs must not be substituted into it.

### 6.7 Planning mode

Planning uses the same shell with atlas planes, 3D, existing placement controls,
precise depth/angle entry, probe geometry and multi-probe settings. Preserve
cross-plane navigation and type-specific reconstruction settings. Direct handles
may be added only alongside exact numeric controls.

Label `.dmapprobe` actions **Save/Load probe settings**. These restore settings;
do not advertise them as a substitute for the complete project, atlas and placed
objects. **Save Project** remains the complete-plan action.

---

## 7. Canvas, views and navigation

| View | Purpose |
| --- | --- |
| Compare | Atlas and current section side by side, with independently usable views |
| Overlay | Warp review in either direction; opacity available initially, swipe/flicker optional |
| 3D | Atlas, selected plane and scientific objects |
| Multi-plane | Coronal, sagittal, horizontal and 3D for planning and inspection |

Preserve section-only and atlas-only focus as well as existing layout tasks.
Multi-plane remains reachable during histology work. Show depth, units, plane
and tilt without requiring the Match panel to be open.

Two linked-cursor behaviors are distinct:

- **Compare correspondence:** use the current valid registration to show a
  matching location in the other image. Hide correspondence outside supported
  mapping bounds or while registration is invalid/stale.
- **Follow cursor across atlas planes:** preserve Navigation's behavior of
  updating orthogonal slices and crosshairs in Multi-plane. In 1.x this follows
  the hovering cursor, not clicks: while Navigation is on, moving the mouse over
  one plane changes the pages of the others. Keep that behaviour and an explicit
  toggle so browsing does not unexpectedly move other planes; clicking to pin a
  location may be added. Inspection slices do not change the committed
  registration plane until explicitly applied.

A minimap does not replace either function and is deferred. Preserve existing
navigation initially; changes to pan/zoom/fit gestures need collision checks with
annotation tools. Double-click must not both add a point and fit the view.

Hover readouts show region and coordinates in a named frame. Boundary, grid,
axes and colour-bar controls remain reachable. Hidden axes require a visible
scale/reference where measurements are shown. Interface themes must not alter
image LUTs, channel colours or scientific rendering modes.

---

## 8. Inspector and outline

The inspector shows properties of the selected pair, marks, part, object or
layer. Its heading names the target. Tool settings have a separate labeled area
so changing selection cannot silently redirect a tool operation.

The outline separates Landmarks, Working marks, Stored parts/objects and Layers.
Rows show status and provenance where available. Historical parts do not imply
that their original section can be reopened from the project.

The searchable atlas **Regions** tree can share the panel but must be pinnable
or independently expanded; a large tree must not crowd out object work. Keep
current region selection, colour and visibility behavior, plus the hover readout.

Only show meaningful actions for each row type. Visibility, rename, delete,
opacity, composition, point size and other existing controls retain their
semantics. Locking, arbitrary reordering and duplication are not universal
capabilities; add them only with explicit model support and tests.

---

## 9. Tools, commands and shortcuts

Keep frequent task tools visible with text labels. Measure remains accessible
where currently supported, even outside the main task panel. Tool settings
stay near the tool or in the labeled inspector area.

Layer translation and rotation retain exact entry, direction controls and
arrow-key nudges. Nudge distance and rotation step are editable in that context;
Preferences supplies defaults. Handles are optional enhancements.

**Ctrl/Cmd+K** searches commands and legacy synonyms such as “merge” and
“triangulation.” Each command exposes availability and a reason when disabled.
The palette supplements menus and controls; it is not the only path for frequent
or unfamiliar work.

Keep File, Edit, View and Help menus on supported desktop platforms, with
platform-standard placement of Preferences/About. File retains project actions
and imports/exports; View retains layouts and panel visibility. Existing
specialist dialogs can remain in task menus while migration proceeds.

Proposed shortcuts, subject to platform and focus testing:

| Shortcut | Action and scope |
| --- | --- |
| Ctrl/Cmd+K | Command palette |
| Ctrl/Cmd+S | Save Project |
| Ctrl/Cmd+Z; standard platform redo binding | Undo/redo with the action name |
| V, P, M, C | Select, Add point, Measure, Crop when the canvas has focus |
| Delete / Backspace | Delete the selected landmark pair or mark when the canvas or list has focus |
| Escape | Cancel preview or incomplete interaction without committing |
| F | Fit the focused canvas |
| O | Switch Compare/Overlay when available |
| Enter | Activate the focused explicit action; never approve a suggestion globally |

Use normal Tab/Shift+Tab focus navigation. Landmark navigation gets separate
controls/shortcuts. Single-key shortcuts never fire while editing text or
numbers. A shortcut sheet is available from Help; retain or alias familiar 1.x
shortcuts where practical and document changed bindings.

---

## 10. Capability migration inventory

This is a starting inventory of destinations, not proof of full coverage.
Before retiring a control, audit its handlers and representative uses. Each
row needs a linked automated test or scripted check recording prerequisites,
inputs, resulting state, save/reopen behavior and an expert interaction path.
Split grouped rows when their operations have different semantics. Record
any omissions found in the audit here; palette access alone does not pass.

Existing dialogs may remain reachable from the new shell until their
replacements pass those checks. Commands also appear in the palette.

### File menu

| 1.x | 2.0 |
| --- | --- |
| Load Atlas… | Project step atlas card; recent atlas locations are hints, verified on use |
| Load Image… | Project step: Load section / Replace section (drag and drop too) |
| Save Project | File > Save (Ctrl/Cmd+S); unsaved-changes marker in the window title and status line |
| Save Portable Project | File > Save portable copy |
| Save Layer > Current Layer / All Layers | Export… > Layers, preserving Current / All selection and supported formats; project saving still includes layers |
| Export Object > Current / Probes / Virus / Cells / Contours / Drawings | Export… dialog presets; inspector action on an annotation |
| Load Project | File > Open; start screen |
| Load Layers | Import… > Layers |
| Import Objects | Import… > Annotations |
| Load External Data > Cells | Import… > Cell points |

### Edit menu

| 1.x | 2.0 |
| --- | --- |
| Undo / Redo | Edit > Undo/Redo with action names; broader History panel deferred until transaction coverage exists |
| Translation > Up/Down/Left/Right | Selected-layer direction controls and arrow-key nudge; drag handles optional (deferred) |
| Translation > Distance Setting | Selected-layer transform controls > Nudge step; Preferences supplies the default |
| Rotation > Clockwise / Counter Clockwise | Selected-layer clockwise/counterclockwise actions and exact angle; rotate handle optional (deferred); palette |
| Rotation > Angle Setting | Selected-layer transform controls > Rotation step; Preferences supplies the default |
| Clear | Outline row menu > Remove; palette "Clear working layers" |

### Image menu

| 1.x | 2.0 |
| --- | --- |
| 180, 90 Clockwise, 90 Counter Clockwise | Section step: Orientation buttons |
| 1 Clockwise, 1 Counter Clockwise | Section step: 1° nudge controls; exact angle entry is new; dial optional |
| Flip Horizontal / Flip Vertical | Section step: Orientation buttons |
| Hide | Outline: eye icon on the section image |
| Process | Section step: Clean up card with explicit Apply and Reset; existing processed raster retained |
| Crop | Section step: Crop tool (C); retain lasso crop until equivalent behavior is verified |
| Reset | Section step: Reset image |

### Atlas menu

| 1.x | 2.0 |
| --- | --- |
| Download Waxholm Rat Atlas… / Download Allen Mice Atlas… | Project > Atlas tools > existing downloaders; unified library deferred |
| Atlas Processor | Project > Atlas tools > existing processor; library/wizard redesign deferred |
| Suggest Atlas Section… | Match step: Find atlas section (primary) |
| Propose Landmarks | Register step: Suggest landmarks (primary) |
| Save / Load Triangulation Points… | Register step > Export / Import landmarks; preserve validation and topology |
| Load Slice…, Register Slice Info…, Create Slice Layer, Crop, Bregma Picker, Save Processed Slice… | Project > Slice atlas tools: all existing operations; wizard only after calibration/editing parity |
| Switch Atlas: Volume | Project step atlas card, when both a volume and a slice atlas are loaded |

### Objects menu

| 1.x | 2.0 |
| --- | --- |
| Save / Load Probe Setting… | Planning and Annotate > Probe: Save / Load probe settings (.dmapprobe); Save Project for the complete plan |
| Multi-Probe Planning | Planning mode panel |

### View menu

| 1.x | 2.0 |
| --- | --- |
| Coronal / Sagittal / Horizontal Window | Plane selector plus independently focusable atlas views |
| 3D Window | 3D view |
| Image Window | Compare view (section side), with section-only focus |
| 2 Windows > Volume + Histology / Slice + Histology | Compare view |
| 4 Windows | Multi-plane view |
| 3D Mode: Dark, Planes: On, Axes: On | 3D view settings popover; preserve rendering modes independently of interface theme |
| 2D Mode: Dark | Image-view background setting; interface theme is separate |
| Grids: Off | View settings popover |

### Help menu

| 1.x | 2.0 |
| --- | --- |
| About DriftlessMap | Help > About; version also in the status line |

### Toolbar

| 1.x | 2.0 |
| --- | --- |
| Layout buttons | View switcher and focus/maximize actions, checked against every existing layout |
| Ruler | Measure tool (M) wherever 1.x supports the ruler |
| Pencil / Eraser / Polygon Lasso | Annotate tools for Expression, Contour, Drawing |
| Magic Wand | Section > Clean up; Annotate > Expression and Contour "Detect by colour" |
| Mask Maker | Section > Clean up |
| Probe Marker | Annotate > Probe |
| Triangulation | Register step (the step itself); Add point tool |
| Cell Selector | Annotate > Cells |
| Transform to Atlas / Transform to Histology | Register step: Preview warp with direction and Remove preview actions |
| Accept and Transfer | Annotate/Register: Map annotations to atlas; distinct from image preview |
| Points Number | Register > Advanced > Frame points |
| Mesh status label | Register step: Mesh valid / review / invalid; separate anatomical review state |
| Tool colour / size / tolerance / kernel / path type | Inspector when the tool is active |

### Sidebar tabs

| 1.x | 2.0 |
| --- | --- |
| Atlasing Controller: plane radios, opacity, Show Boundary, tilts, Keep Slice Angles, Navigation | Match controls; plane/depth selector; overlay opacity; Keep tilt toggle retained; Follow cursor across atlas planes in Multi-plane |
| Segmentation View Controller | Searchable Regions panel with pin option; hover readout supplements it |
| Image View Controller: scenes, scale, channels, LUT | Section step: native TIFF dimensions, dynamic channel rows, brightness/contrast and LUT controls; registration selection is separate |
| Layer View Controller: composition, opacity | Inspector for the selected layer |
| Object View Controller: add piece, merge buttons, un-merge, info, compare, 2D plane, delete, composition, opacity, size | Annotate step and inspector; explicit Build 3D / Edit parts with original type-specific settings (Section 6.5) |

### Required behavior checks beyond command placement

| Workflow | Evidence required before replacing the old controls |
| --- | --- |
| Warp then annotate; annotate then warp | Image preview and annotation mapping stay distinct; both orders produce equivalent mapped coordinates |
| Edit a landmark after mapping | Sources survive; dependent results become stale; Update replaces rather than duplicates; undo restores a consistent state |
| Move between sections | Save/replace preserves stored objects and provenance without promising editable section history |
| Navigate the volume | Follow cursor moves orthogonal slices; toggling it off stops updates; inspection leaves committed registration intact |
| Build and edit objects | All object types retain contributing parts, settings, comparisons, information and export behavior; failure loses no pieces |
| Use a slice atlas | Calibration, crop, Bregma, processing, export and switching to volume preserve coordinate semantics |
| Save/load probe settings | Geometry, face, multi-probe offsets/faces, validity and merge-sites choice round-trip; project saving preserves the complete plan |
| Work with layers | Current/all layer exports, composition, opacity and precise transforms retain supported behavior |
| Reopen shared work | Legacy imports, relocated/mismatched sources, embedded raster and portable extraction follow the persistence contract |
| Register a multichannel 16-bit section | Display tracer/GFP while registering on DAPI only; both automatic stages exclude unselected channels; every channel retains native samples through save/reopen |
| Adjust an image without ImageJ | Per-channel histogram, brightness/contrast, auto/reset, colour and gamma work without changing registration inputs; data and rendered exports have explicit semantics |

---

## 11. Simplification without capability loss

| Proposed simplification | Boundary |
| --- | --- |
| Group image-processing controls under Clean up | Keep processed pixels, reset and exports; no promised recipe stack |
| Group transform controls | Retain exact values, directions and in-context step settings |
| Replace separate warp buttons with direction + Preview warp | Keep annotation mapping as its own action; retain preview removal |
| Label Merge as Build 3D and Unmerge as Edit parts | Preserve type-specific behavior and make mutations explicit |
| Move layer sharing to Export | Preserve current/all-layer selection and every supported export format |
| Compact view chrome | Keep units, scale, orientation and accessible depth/tilt controls |
| Group atlas tasks in Project | Existing download/process/calibration dialogs remain until replacements pass |

Do not remove Keep tilt, cross-plane Navigation or precise controls on the
assumption that a default, a minimap or a drag handle is equivalent. Do not
replace “technical” concepts with names that hide consequential distinctions.

---

## 12. Feedback, undo and background work

### Feedback and save state

Use persistent inline status for prerequisites, invalid/stale state and failures.
Transient success notices may supplement it; warnings and recovery actions remain
available until resolved. An operation must explain what failed and what state
was preserved. Hover readouts must not overwrite important errors.

Show the dirty flag and last successful save. “Saved” refers to the last committed
project revision; a view switch does not dirty scientific state. Capture a
consistent snapshot for save and mark only that revision saved. Preserve current
atomic and provenance behavior.

### Undo is a transaction feature

The current short layer-snapshot history is not project-wide undo. A command
registry is not an undo implementation. Define for each migrated mutation:

- Inputs and preconditions; which state changes together.
- Reversal data, memory cost and behavior after subsequent edits.
- Whether repeated drag/nudge events coalesce into one user action.
- Which dependency and review flags are restored.

The first workflow requires coherent undo for paired-landmark edits and working
annotation edits. Undo for mapping and build/update arrives with source
retention in Phase 3; until then the shell warns before these actions and names
the recovery path (Edit parts for builds). Source replacement, atlas changes
and other operations without affordable reversal need a clear boundary and a
save/cancel path before discarding work. Do not show them as undoable.

Name the next Undo/Redo action and retain a bounded memory budget. Branching
edits clear redo appropriately. Opening a project starts a fresh history; saved
scientific state does not depend on retaining undo snapshots. A clickable global
History panel waits until all included operations can be reversed consistently.

### Background work

Keep `run_in_background` modal initially. Inline progress is not worth accepting
results computed from obsolete inputs. Before enabling nonmodal jobs, require:

- Immutable input snapshots and a project/input revision token.
- A completion check that rejects results if inputs changed or the project closed.
- One atomic commit on the GUI thread; workers never access widgets.
- Cooperative cancellation where supported, with no partial mutation. Cancellation
  is not promised for operations that cannot stop safely.
- Explicit policy for conflicting jobs, shutdown, failures and resource limits.

Test replacing an image, editing landmarks and closing the project while a job
runs. Modal jobs also need failure tests and consistent commit boundaries.

### Recovery copies

Autosave is a separate, deferred feature. Its design must specify consistent
snapshots, frequency, disk quota, retention, recovery after interruption, source
verification and memory/I/O budgets for large rasters and streamed attachments.
A recovery copy never overwrites the user's file or marks it saved. Ordinary
Save Project and embedded-raster recovery remain required throughout migration.

---

## 13. Visual design and accessibility

Use neutral surfaces, one icon family, a small typography/spacing system and
consistent focus and status treatments. Preserve the native window controls.
Favor readable labels and image area over decorative spacing or animation.

- Support light and dark themes with identical functionality; initially follow
  the system preference and let users choose. Theme changes do not alter images.
- Use platform fonts and scalable logical sizes. Validate enlarged text instead
  of relying on a fixed pixel-only mock-up.
- Use distinguishable annotation colours, with user choice. Status always has
  text or an icon in addition to colour.
- Target text contrast of at least 4.5:1; provide visible keyboard focus and
  meaningful accessible names for custom controls.
- Preserve keyboard access to every action and normal focus traversal. Provide
  precise numeric alternatives to dragging.
- Do not animate the scientific canvas. Panel motion is optional and deferred.

Prototype at 1280 × 800 logical pixels and on a larger desktop, with system
scaling and enlarged text. Include long region names, multiple channels, many
annotations and realistic images. No required action may be clipped or become
reachable only by shrinking text. Compare docked and compact task controls before
committing to a floating toolbar or always-open combined outline.

An HTML mock-up can test information organization. A Qt prototype with pyqtgraph
and real data is required to validate layout, focus, image interaction and speed.

---

## 14. Architecture and persistence

### Incremental extraction

Keep PyQt6 widgets and the existing rendering stack. A new GUI framework would
add a separate migration without resolving state ownership.

Extract only what the next complete workflow needs. Where the classic shell is
retained as a development reference, share commands and state; avoid
maintaining two scientific implementations. Do not make extracting all of
`app.py` a prerequisite for a usable development build.

`app.py` is also the file that most stable fixes touch, so a long-lived branch
that restructures it will conflict with nearly every stable fix. Prefer landing
behaviour-neutral extractions of services and model code on the stable branch
in small PRs, with no UI change, and keep only the new shell on the V2 branch.
Core changes that do not depend on the shell, such as the registration-input
recipe and the channel-count limit, should also land on stable first (for
example in 1.7), so that V2 inherits tested code.

Target responsibilities, with module boundaries introduced as needed:

| Responsibility | Owns | Must not own |
| --- | --- | --- |
| Project/domain model | Scientific state, native channel metadata/data, registration input recipes, stable identities, dependencies and validation | Widgets, scene items or menu state |
| Image reader and input preparation | Validated TIFF axes/selection, native samples, explicit analysis-plane construction | Inferring analysis input from display visibility, colour or LUT state |
| Application commands/services | Preconditions, transitions, undo transactions, calls into scientific modules | Rendering or alternate scientific algorithms |
| Persistence adapter | Validated payload conversion, migrations and defaults | Reading arbitrary widget properties as scientific truth |
| Qt presentation layer | Task panels, canvas items, selections and view bindings | Independent copies of mutable scientific state |
| Job runner | Snapshots, progress and guarded result delivery | Direct widget access from workers |

`LandmarkModel` demonstrates useful ownership of related state, but currently
also holds on-screen text items. Move those into presentation before treating
it as a widget-free model. Organize services around domain operations rather
than forcing one controller per visual step; both Register and Annotate use
registration and mapping services.

The command registry supplies stable IDs, names, synonyms, shortcuts, availability
and handlers. Undoable commands additionally implement transactions. Menus,
toolbars and palette call the same actions; registry entries do not themselves
supply reversal or validation.

### Persistence invariants

Preserve safe ZIP/JSON/NumPy storage, restricted legacy readers, atomic writes,
ZIP64 and streaming attachments, array deduplication, content-based provenance,
embedded exact active rasters and exclusion of processed volume atlases. The
current archive format is version 1 and project payload schema is version 2;
application version 2.0 does not dictate either number.

New persistent scientific state requires validation, old-file defaults,
round-trip tests and documentation. Do not freeze the payload schema to disguise
new semantics. This proposal does not authorize breaking backward loading.

**Decision: V2 writes project payload schema 3.** Channel metadata beyond four
channels, display state, registration-input recipes and review state are new
semantics. V2 reads schema 1–3, migrating older payloads to schema 3 with
explicit defaults (Legacy input, review not recorded), and always writes schema
3. The archive format stays at version 1. 1.x already refuses payload schemas
above 2 with a clear message, so a V2 project fails explicitly in 1.x instead of
opening with silently discarded state.

| Proposed state | Storage decision |
| --- | --- |
| Native active-plane channels, dtype, axes/series/Z/T selection and calibration | Persist exact samples plus validated metadata; embed hidden and unused channels too |
| Per-channel display state | Persist names/colours, visibility, min/max, gamma and supported LUT settings independently of analysis input |
| Registration input recipe | Persist source channel identities, raw/processed source choice, combination/normalization parameters and version; legacy default reproduces existing input behavior |
| Source marks, mapped derivation identity and dependency metadata | Persistent, required for retained-source editing and stale-result detection |
| User review state and the inputs reviewed | Persistent if offered as a saved scientific status; legacy default is not recorded |
| Part/source relationships and build settings | Persist known relationships; validate identity, avoid guessed links for legacy objects |
| Warp image preview | Recomputable; preserve existing saved overlay behavior where needed for compatibility |
| Selection, candidate hover and pending jobs | Transient; never restored as committed work |
| Panel layout/theme and shortcut preferences | UI preferences or existing layout fields; never required to interpret scientific data |
| Undo stack, cleanup recipe, multiple-section dataset | No new persistent representation in the initial scope |

Before implementing these fields, specify a concrete payload mapping and
migration fixtures. Source marks and mapped results must remain distinguishable
to avoid double-counting in exports or reconstruction. Existing object formats
and coordinate field meanings remain intact.

### Compatibility commitments

| Direction | Commitment |
| --- | --- |
| Supported 1.x/HERBS → 2.0 | Required: load valid work with defaults for new state and preserve existing results/provenance |
| 2.0 → 2.0 | Required: complete scientific round trip, including review/dependency state and embedded-raster fallback |
| 2.0 → 1.x | Not supported: 1.x refuses payload schema 3. Independently, 1.x cannot open embedded rasters with more than four channels (`MAX_CHANNELS = 4`), so no downgrade export can include them |
| 2.0 → 1.x → save → 2.0 | Separately test any claimed support; an older writer may discard new fields even if it can open the file |

Normal Save Project always preserves the complete 2.0 state. It must not silently
flatten or omit new state for older readers. A future **Export 1.x-compatible
copy** would require a defined downgrade projection, a reviewable loss report and
its own tests; it is not required for the first preview. Users retain their
original 1.x file when first saving migrated work as a new project copy.

Stable 1.x and V2 development builds may have different payload capabilities.
Test V2 on copies of existing projects and save migrated work to a new path;
never imply that switching back to the stable application can preserve V2-only
metadata. If the V2 build retains both shells, they must share validated state
or prevent unsupported mutations. A classic UI switch is optional, not a release
requirement, and must not silently strip new metadata.

---

## 15. Migration and release gates

### Branch strategy

Develop V2 on a dedicated `v2-redesign` branch, preferably in a separate worktree
so stable fixes and V2 experiments have independent working directories. Keep the
stable branch and published 1.x application usable until V2 is ready. Do not ship
intermediate redesign phases to all users or assign them mandatory 1.x release
numbers.

- Use small, reviewable commits and run CI on the V2 branch and its integration
  PRs. Keep a draft integration PR or equivalent review record for the overall diff.
- Make independent fixes on stable first when practical, then regularly bring
  them into V2. Record intentional divergence, especially reader, persistence and
  coordinate changes. Use one consistent integration approach to avoid duplicate
  cherry-picked changes and recurring conflicts.
- Produce opt-in development builds from V2 with an unmistakable development
  version label. Keep preference namespaces separate and use copied projects;
  installing/testing V2 must not require overwriting the stable application.
- Preserve native desktop packaging and verify both supported desktop platforms
  before merging. A branch that runs only from a developer environment is not ready.
- Review state contracts and complete workflows incrementally on the branch.
  Branch isolation protects stable users; it does not make a large unreviewed
  rewrite or late integration safe.

“Everything looks good” means the behavior, scientific output, persistence,
performance and usability gates below all pass, as well as visual review. The
merge/default switch happens once those conditions are met, not after a fixed
number of preview releases.

### Delivery gates within the V2 branch

| Phase | Deliverable | Exit gate |
| --- | --- | --- |
| 0. Baseline and contracts | Representative tasks and image fixtures, audited capability inventory, transition rules, concrete persistence mapping | Agree outputs, channel-input semantics and compatibility policy; exercise difficult cases on paper |
| 1. Interaction prototype | Multichannel Section, Match/Register mock-up plus Qt canvas with real data; chosen design tokens (colours, type scale, spacing) and icon family | Users distinguish display from registration channels and preview from apply; laptop, keyboard and exact-entry checks pass; the visual direction is approved as clearly distinct from 1.x |
| 2. First complete workflow | Native 16-bit TIFF → channel display/selection → match/register → probe annotation → inspect/export → save/reopen | Scientific outputs agree for equivalent inputs; DAPI-only isolation, review state and schema-3 persistence pass; current mapping and merge consequences are labelled |
| 3. Coverage expansion | Source retention, dependency/stale tracking and undo for mapping and building; other annotations, planning, slice atlases, layer/object operations and documented TIFF layouts | Every inventory task has evidence; source-retention, invalidation and undo tests pass; large-file and multichannel checks pass; unsupported cases fail clearly |
| 4. Release candidate | Installable V2 builds, tutorials/manual, copied-project migration trials and user evaluation | Section 17 passes on supported platforms; no unresolved data-loss, numerical or capability blockers |
| 5. Merge and release | Reviewed integration into stable, V2 becomes the default | Maintainer accepts the release-candidate evidence; stable fixes are integrated; old projects remain loadable |

The V2 branch may retain the classic shell for comparison during development.
Shipping two interfaces is not required. Remove the classic implementation only
when its workflows are independently covered and verified; preserve the stable
1.x release/tag as the reference. Reusing mature dialogs is acceptable and does
not count as an incomplete redesign when the resulting workflow is coherent.

Documentation follows implemented behavior on the branch: update `MANUAL.md`,
tutorials, `WhatsNew.md` and `UpdateLog.md` for the intended V2 release. Update
`AGENTS.md` and `CLAUDE.md` together, byte-for-byte identically, when actual
architecture or workflows change. This proposal alone does not change the current
release, create a branch, or alter the user manual.

---

## 16. Risks and decisions still required

| Risk or decision | Required resolution |
| --- | --- |
| New metadata versus older readers | Concrete fields, schema decision, legacy defaults and downgrade policy before persistence changes |
| Source geometry changes | Enumerate each crop/rotate/flip/scene/scale transition and prove coordinate transformation or require an explicit reset/archive path |
| Repeated image replacement | Define how stored parts retain known source context without pretending old image/registration state is still editable |
| Annotation identity | Define stable identities across mapping, grouping, unmerge and legacy imports; never use display names alone |
| Undo memory | Choose and measure a budget with large rasters; define history barriers before claiming broad undo |
| Long-lived V2 branch | Regular stable integration, CI and native development builds; review small changes before final integration |
| `app.py` conflicts between branches | Land behaviour-neutral extractions and shell-independent core changes on stable; keep branch-only edits to `app.py` small and mechanical |
| Multichannel image dimensions | Fixture-backed TIFF axis interpretation, explicit selection and documented resource limits; no dropped channels or accidental Z-as-C interpretation |
| Display versus analysis input | Independent controls and saved recipes; DAPI-only tests exclude every other channel from both automatic stages |
| Expert speed | Validate repeated manual matching, precise adjustment, cross-plane browsing and export, not just the first tutorial |
| Canvas space and performance | Qt prototype and recorded limits on a specified machine before optional overlays or new controls are accepted |
| Scientific review UX | Test whether users distinguish mesh validity, review, stale state and genuine anatomical agreement |

Planning remains a mode in the same shell unless testing demonstrates a concrete
need for a separate window. Multiple editable sections require a separate design
covering image storage, per-section registration, part identity, memory and
migration; no placeholder list ships ahead of that model.

---

## 17. Validation and acceptance

### Scientific and state correctness

Keep existing scientific tests. Add meaningful integration tests for the new
orchestration rather than relying on unchanged unit tests as proof of parity.
For equivalent committed inputs, compare coordinates, labels, contacts, region
statistics and exported values with current behavior using declared tolerances.

Required scenarios include:

- Native uint16 TIFF values above 255, 1/3/4/6 channels, grayscale stacks versus
  channel stacks, RGB samples, supported OME/ImageJ metadata, series/Z/T selection,
  ambiguous axes, constant channels and unsupported-layout failures.
- DAPI-only matching and landmark proposal while tracer/GFP channels are visible;
  changing unselected channels or display brightness/contrast/gamma/visibility
  leaves the analysis plane and algorithm inputs unchanged.
- Multiple selected channels follow the recorded combination recipe, including
  normalization bounds; with the new recipe neither stage ignores selected
  channels beyond the first three. Legacy mode retains its documented original
  behavior, including the intensity image's use of the first three channels.
- Native sample arrays remain unchanged after appearance edits and data export;
  rendered export matches chosen display settings. Save/reopen and embedded-raster
  fallback preserve all channel data, display state and registration recipes.
- Manual and suggested matching, mirror ambiguity, invalid meshes and inaccurate
  but geometrically valid fits.
- Annotation before and after registration, landmark edits after mapping,
  idempotent update, source replacement and stale-result export handling.
- Build failure, edit-parts behavior and undo/redo across dependent state.
- Imported legacy objects with incomplete source context; no fabricated review
  or derivation metadata.
- Ordinary and portable saving, embedded raster recovery, atlas/source relocation
  and mismatch, complete probe settings, wrong-kind rejection and safe legacy reads.
- A 1.x fixture opened and saved as 2.0, then reopened with complete new state;
  use actual supported older readers/writers for any claimed downgrade path.

Test domain transitions without widgets, then test shell bindings, command
availability and focus with Qt. Add a small set of stable screenshots for layout
and theme regressions; screenshots do not establish scientific correctness.
The repository's required checks and existing suite remain release gates.

### Usability

Use both new and experienced users, with brightfield and fluorescence examples,
CZI/TIFF scene or page changes, a native 16-bit DAPI/GFP/tracer section,
incomplete tissue, mirror ambiguity, planning and a slice atlas. Include data beyond the tutorial and record assistance needed.

- **No ImageJ detour:** open a representative original multichannel TIFF, adjust
  channels for inspection, register on DAPI alone, annotate on a different channel
  and save/reopen without flattening or exporting an intermediate image elsewhere.
- **First correct result:** aim for a new user to register and place a probe in
  under 15 minutes on a prepared representative case, without the manual. Score
  anatomical correctness and review behavior independently of completion time.
- **Repeated expert work:** compare median task time and errors to a recorded 1.x
  baseline. Target no more than a 10% slowdown on frequent tasks; investigate and
  resolve material regressions before the default switch.
- **Recovery:** users can identify a stale result, correct an erroneous landmark,
  undo a mistake and recover a project with a missing image source without losing
  unrelated work.
- **Capability coverage:** every inventory task has an executable test or a
  recorded scripted check covering inputs, outputs and persistence.
- **Accessibility:** complete the core workflow by keyboard, with visible focus
  and enlarged text, in both themes and at the minimum tested window size.

### Performance and release decision

Record dataset sizes and machine specifications. Compare peak memory, loading,
warping, save/reopen time and interactive responsiveness against the existing
application. Set numeric budgets from that baseline before implementing optional
nonmodal jobs or overlays; throttling alone is not an acceptance criterion.

A release cannot pass solely on survey preference or click counts. The default
switch requires correct outputs, recoverable state, demonstrated task coverage,
acceptable expert speed and an interface users understand. Outstanding failures
remain explicit blockers or documented preview limitations.
