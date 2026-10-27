# Phase 3 design: mapping records, staleness and undo

Status: implemented in 2.0.0a8–2.0.0a12 (approved 27 October 2026). It implements the
decisions taken on 27 October 2026 for the V2 redesign (Section 3 and
Section 12 of `version2_redesign.md`):

1. Mapping keeps the section's marks (option B). The mapped atlas copy is a
   derived result that can be updated.
2. Identity is per kind of mark, per section, per probe: re-mapping replaces
   that unit and never adds a duplicate.
3. Undo covers Map, Update mapping, Make parts and Build: up to 10 steps
   within a 500 MB budget, masks stored compressed, not saved with the
   project.

## 1. What changes for the user

| Action | Today | Phase 3 |
| --- | --- | --- |
| Map to atlas | Copies marks to the atlas and clears them from the section | Same atlas result; the section's marks are kept in a **mapping record** and stay visible on the section as a read-only "mapped" overlay |
| Edit a landmark or change plane, page or tilt after mapping | Atlas marks silently keep the old registration | The mapping and the parts made from it are labelled **out of date**; **Update mapping** re-maps the kept marks with the current registration |
| Map the same kind again (for example cells after more were clicked) | Overwrites the atlas copy | Replaces that unit's record and atlas copy; parts made from the old copy are labelled out of date until Make parts runs again, which replaces them |
| Edit mapped marks | Not possible; redraw | **Edit marks** returns the kept marks to the section as editable marks; mapping them again replaces the unit |
| Undo after Map, Update, Make parts or Build | Not available (Edit parts only reverses Build) | Undo restores the section marks, atlas copy, parts, records and review state together |

Nothing changes in the coordinates mapping produces: the same transfer code
runs on the same points with the same registration.

## 2. Why the kept marks live in the record

All probes on a section share one list of section marks (`img-probe`), and
cells, drawings and contours each have one list too. If mapping simply left
the marks in those lists, probe A's points would still be there while probe B
is marked, and Make parts' "not yet mapped" warning would fire for marks that
were mapped. So mapping still empties the live lists, exactly as today, and
moves a copy of the marks into the record. The live lists keep meaning "marks
not mapped yet"; records hold "marks that were mapped, and how".

## 3. Data model (GUI-free, `driftlessmap/mapping_records.py`)

**Section identity.** `section_id`: a random 32-hex identifier made when a
section is loaded (load, replace, choose another plane or pyramid level) and
saved with the project. Paths and file names are never identity.

**Unit key.** `(section_id, kind, probe)`, where `kind` is one of `cells`,
`probe`, `drawing`, `contour`, `expression`, and `probe` is the probe name for
probe marks (None otherwise; 1.x probe marks without a V2 probe name use
None).

**MappingRecord** (one per unit):

| Field | Meaning |
| --- | --- |
| `unit_id` | Random 32-hex identifier, kept when the unit is re-mapped |
| `revision` | 1 on the first mapping, increased by each re-map or update |
| `section_id`, `kind`, `probe` | The unit key |
| `source` | The kept section marks: point arrays (and cell size, symbol and channel lists) or the expression mask |
| `source_digest` | SHA-256 of `source`, to detect edited marks |
| `registration` | Registration fingerprint at mapping time (landmarks, frame points, plane, page, tilt, image size: the one the review uses) |
| `review` | "reviewed", "not reviewed" or "not recorded" at mapping time |
| `mapped_at` | UTC ISO time |

**Parts and objects.** A new list `obj_derivation`, parallel to the existing
object lists, gives each object the `(unit_id, revision)` pairs it was made
from: one for a part, all of its parts' pairs for a built object, empty for
imported or older objects ("origin not recorded").

## 4. Out-of-date rules

A record of the loaded section is **current** when the current registration
fingerprint equals `registration`. Otherwise:

- **registration changed** — landmarks, frame points, plane, page or tilt
  changed since mapping. Update mapping is offered.
- (not out of date) **another section** — its section is no longer the
  loaded one. That section's registration can no longer change, so the record
  and its parts stay valid; Update and Edit marks are not offered. Probes built
  from several sections rely on this.

A part or built object is out of date when any of its units is, or when a
unit was re-mapped after the part was made (the part's stored revision is
older than the record's). Objects with no recorded origin are never called current
or out of date; they say "origin not recorded".

Display-only changes (brightness, colours, visibility, theme) never make
anything out of date. Out-of-date results stay visible and exportable, with
the export noting that they are out of date.

## 5. Undo

`driftlessmap/transactions.py` holds a bounded history of **transactions**.
Each records, before the action runs, everything the action can change:

- the live section and atlas mark lists of the kinds involved,
- the records of the units involved,
- the object lists (names, types, data, display settings, derivation),
- the registration review and mapping review state.

Masks are stored compressed (zlib), so a mostly empty full-slide mask costs a
few megabytes. The history keeps the last 10 transactions within 500 MB,
dropping the oldest first; a single transaction larger than the budget is not
undoable, and the action says so before it runs. Undo restores a
transaction's snapshot and moves the current state to redo; a new action
clears redo. Opening a project or loading a section starts a fresh history.
The Edit menu names the action ("Undo Map cells"). The existing short
per-tool history for drawing and erasing stays as it is.

A failed action leaves the last committed state: the snapshot is taken first
and the action's own validate-then-commit order is kept (Build already works
this way).

## 6. Persistence

Payload schema stays 3: the new fields are optional and absent in files made
by the 2.0.0a1–2.0.0a7 preview builds, which were never released.

| Field | Default when absent |
| --- | --- |
| `section_id` | A new identifier; existing atlas marks and parts get "origin not recorded" |
| `mapping_records` (list of records; arrays stored as `.npy` entries) | No records |
| `object_data["obj_derivation"]` | Empty for every object |

Loading validates every field (identifiers are 32 hex characters, kinds are
known, arrays have the shape of their kind, digests match the stored source)
and drops an invalid record with a message rather than failing the project.
Undo history is never saved.

## 7. Tests (with the implementation)

- Records: replace-not-duplicate per unit; probe units per name; digests;
  round trip; invalid records rejected.
- Out of date: landmark, frame-point, plane, page and tilt changes; display
  changes do not count; section replacement; parts follow their units.
- Mapping (engine): same coordinates as 2.0.0a7 for every kind; kept marks;
  Edit marks; Update mapping equals a fresh map with the new registration.
- Undo/redo for Map, Update, Make parts and Build, including review state;
  budget eviction and the over-budget refusal; history reset on load.
- Projects: save and reopen with records, derivation and out-of-date state;
  2.0.0a7 projects open with "origin not recorded".
- V2: out-of-date labels, Update mapping, Edit marks and named Undo entries.

## 8. Points to confirm in review

1. Kept marks shown on the section as a read-only overlay (Section 1).
2. Out-of-date results remain exportable with a note, rather than blocked.
3. Re-making parts replaces the parts of the same unit; built objects made
   from replaced parts are labelled out of date, and rebuilding is explicit.
4. The 10-step / 500 MB limits.
