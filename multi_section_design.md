# Multi-section projects (design, proposed for 2.4.0)

Status: design agreed on 2 November 2026 (see Decisions). Phase 1 (engine) is
implemented; phases 2-4 are not.

## Problem

A project holds one section at a time. Loading another section (Project >
Replace section) starts a new registration and discards the previous one:

| Kept for earlier sections | Lost when the next section is loaded |
| --- | --- |
| Mapping records with the marks/outline in section pixels | The histology image (only the loaded section's raster is embedded) |
| Mapped parts and built objects in atlas space | Landmarks, frame points, mesh, review |
| Implants and their reports | Atlas plane, page and tilt the section was matched to |
| | Image display, registration channels, pixel size, orientation, crop/clean-up |
| | Section marks still on the section, image layers |
| | Undo history (cleared on every load) |

Each load also gets a new random `section_id`, so reloading the same image
cannot reach its earlier mapping: **Edit marks** and **Update mapping** list
only the loaded section's records, and mapping it again adds a second part
instead of replacing the first.

Goal: one project keeps **every** section with its image, registration and
marks; the user can switch to any section, change it, map it again (replacing
its earlier part), and build implants, probes and other objects from all of
them.

## Model

A project has **document** state (one per project) and **section** state (one
per section). The split follows the current payload:

| Document (unchanged, top level) | Section (one entry per section) |
| --- | --- |
| atlas path, provenance, atlas layout | `section_id`, name, created/modified times |
| objects (parts, built objects), 3D list | histology provenance and `img_path` |
| `mapping_records` (all sections) | `img_ctrl_data` (embedded raster, display, channels, plane selection, scale, pixel size) |
| implants and their specs/colours | `processing_img`, `overlay_img` |
| probe settings and planning | `registration_input`, `registration_review`, `mapping_review_state` |
| session state, layout, theme | `setting_data` (landmarks, frame points, mesh, warp method) and `np_onside` |
| `interface_state` (V2 step/view) | `atlas_control` (plane, page, tilt the section is matched to) |
| | `working_img_data`, `working_atlas_data`, `atlas_mark_origin` |
| | image and atlas layers, `implant_outlines` (unmapped outlines) |

`project_io.SECTION_FIELDS` will name the section keys, so saving, switching,
the change digest and migration share one list (as `project_payload` already
does for the whole document).

GUI-free module `sections.py`:

- `SectionEntry`: `section_id`, `name` (default: file name, unique), `order`,
  `state` (the section fields) and `summary` (landmark pairs, review state,
  mapped records, for listing without loading arrays).
- `SectionBook`: ordered entries, `active_id`, add / rename / remove / reorder,
  `to_list` / `from_list` with validation.

## Switching sections

`DriftlessMap.switch_section(section_id)`:

1. Collect the active section's fields from `project_payload()` into its entry
   (arrays borrowed, then spilled; see Memory).
2. Build a payload of the current document fields plus the target's section
   fields, and install it with the existing atomic `load_project` path
   (snapshot, rollback on failure, recovery file). Reusing the tested path
   avoids a second restore implementation.
3. Restore `section_id` from the entry, so the target's mapping records are
   *current* again (or *out of date* if its registration has changed), and
   **Edit marks**, **Update mapping** and mapping again (which replaces its own
   earlier part) work as for the section that was never unloaded.

Undo history is cleared on a switch, as loading a section clears it today:
transactions describe the marks of the section they were recorded on. The
switch itself is not an undo step.

Loading a new image **adds** a section (it no longer discards the active
one). **Remove section…** deletes an entry; it asks whether to keep or delete
that section's parts and mapping records (default keep: built objects may
depend on them).

## Memory

Rasters can be large (the reported TIFF: 11520 × 5990 × 4 channels, 276 MB
uint8). Inactive sections must not stay in RAM:

- On switch-away, the section's large arrays (`current_img`,
  `processing_img`, `overlay_img`, raster layers) are written once to a
  session cache folder as `.npy` and reopened with `mmap_mode="r"`; the entry
  keeps the mapped arrays. Small fields stay in memory.
- An inactive section that is unchanged since the project was opened can
  instead point at its arrays inside the project archive (read on switch).
- The cache folder is removed on close; a crash leaves it in the system
  temporary folder.

## Persistence (project schema 4)

- `section_images` ("embed" or "link", default "embed"; see Decisions).
- Top level stays as today and holds the **active** section, so the loader,
  recovery file and every existing field keep their meaning.
- New `sections`: a list of the **inactive** entries, each with the section
  fields above (same validation and defaults as the top-level ones), plus
  `active_section_id`, names and order.
- Arrays shared between entries are stored once (existing deduplication).
- Portable projects stream every section's original source as an attachment.
- Each section keeps its own histology provenance; relocation and checksum
  checks run per section on load, falling back to its embedded raster.
- Saving rewrites the archive (atomic, as now). Copying unchanged sections'
  members from the old archive without re-compressing is a later
  optimisation.
- Schema 1–3 projects open as a one-section book: the saved section becomes
  the only entry, keeping its `section_id`. Mapping records of other section
  ids (sections mapped before this feature) are listed as **earlier sections
  without a stored image**: their parts stay usable and can be deleted, but
  they cannot be opened.
- 2.3 and earlier refuse schema-4 files ("newer persistence schema"), as
  they do now; WhatsNew says so.

The unsaved-change digest must not rehash every inactive raster on each check:
inactive entries are immutable until switched to, so their digests are cached
per entry and recomputed only when an entry changes.

## Interface

V2 Project step, new **Sections** card:

- a list: name, plane and page, landmark pairs, review state, what was mapped
  ("Fiber 1, 2 cells"), marked *active*;
- **Add section…** (load an image as a new section), **Open** (switch; also
  double-click), **Rename…**, **Remove…**, **Move up/down** (order is for the
  user; AP order is suggested from the matched pages);
- the rail shows "Section 2 of 3: 1108-pfc-2".

Annotate and Results name the section of each mapping and part; a mapping of
another section offers **Open its section**. The Implants card shows "mapped
on 2 of 3 sections".

Classic interface: loading an image also adds a section; a **Sections…**
dialog (Image menu) lists, opens, renames and removes them.

## Phases

1. **Engine:** `sections.py`, `SECTION_FIELDS`, add-on-load,
   `switch_section`, remove, spill cache. Tests: switching keeps each
   section's raster, landmarks, page/tilt, marks and layers bit-for-bit;
   mapping again after switching back replaces that section's part; failure
   during a switch rolls back.
2. **Persistence:** schema 4, migration of 1–3, portable sources and
   provenance per section, digest caching. Tests: the persistence checklist
   in `AGENTS.md` for every section (round trip, legacy read, duplicate-array
   storage, streamed attachments, relocation, checksum mismatch, embedded
   fallback, portable restoration), plus a three-section implant built after
   reopening.
3. **Interface:** V2 Sections card, rail, section names in Annotate and
   Results; classic Sections dialog.
4. **Real-data check and docs:** the two 1108-pfc sections end to end (add,
   register both, map a fiber on each, switch back and edit one, build, save,
   reopen, build again, identical report); file size and switch time
   measured; MANUAL, WhatsNew, UpdateLog, agent guides; release 2.4.0.

## Decisions (2 November 2026)

1. **Images of inactive sections: chosen per project.** A project setting
   `section_images` is `"embed"` (default: every section's exact raster is in
   the archive, so the project alone restores everything) or `"link"` (only
   the active section's raster is embedded, as the persistence contract
   requires; inactive sections keep their small fields and a provenance link,
   and are read from their original files, verified by checksum, when
   opened). A linked section whose original is missing or changed cannot be
   opened and says why; its parts and mapping records stay usable. Changing
   the setting takes effect at the next save. Portable copies embed every
   section's source regardless. The Sections card shows the setting and the
   estimated project size.
2. **Add and remove only.** Loading an image adds a section; there is no
   Replace. Project > Replace section becomes **Add section…**.
3. **Undo is cleared on switching sections**, as on loading one today.
