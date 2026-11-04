# Resolution of the 2.8.3 review

All eight findings were reproduced on `main` (commit `e7f8563`) with the
review's own script (`evidence/probe_planning.py`) before any change, and all
eight are accepted. They are fixed together in **2.8.4**, which stays in the
2.8 series because it completes the same feature (probe planning). Every fix
has a test that fails on 2.8.3 and passes on 2.8.4; the tests use the review's
scenarios through the interface, without storing the edit by hand first.

| ID | Response | Fix in 2.8.4 |
| --- | --- | --- |
| R1 | Accepted. Centre-line search was a documented limitation, but the dialog's constraints read as whole-probe checks. Restricting proposals to one shank would have hidden the problem rather than solved it. | Every shank is sampled, at the plan's roll: each must enter through the craniotomy, keep out of avoided regions, stay on the side and outside the midline margin, and end in tissue; coverage is summed over the shanks' windows (and listed per shank). Final candidates go through `track_checks`, which walks each shank's path voxel by voxel (a grid traversal, not samples), so a corner graze that sampling misses is caught. The readout runs the same checks against the plan's own regions to keep out of. |
| R2 | Accepted. | The engine owns staged edits (`stage_probe_plan`): they count as unsaved work at once, and are stored and built (one undo step) when edits settle or before save, export, undo or redo, any other undoable action, and section switches (`flush_plan_edits`). Replacing the document (new project, opening, rollback) drops them (`discard_plan_edits`). The editor no longer keeps a copy or a timer of its own. |
| R3 | Accepted. | The rollback snapshot keeps the atlas's Lambda. A scale whose atlas reference is unknown is now *unavailable*: no animal coordinates, a readout warning, `unavailable` in the CSV and the copied line. Unscaled by choice (no animal distance) stays 1.0. |
| R4 | Accepted. Policy: a target equal to, or inside, a region to keep out of is a contradiction; keeping out of a *part* of a target (record HPF, keep out of DG) is allowed and its voxels are avoided. | `ProposalRequest` keeps both lists as given; `check(atlas)` refuses contradictions with the regions named, and the dialog shows the message with no results. |
| R5 | Accepted. Policy: a tip must be in labelled tissue on every shank; a track may cross an unlabelled gap above its tip, but the gap is disclosed. | Candidate tips are limited to tissue on every shank; final candidates carry the readout's notes into the results table ("passed, 1 note" with the text); the readout reports gaps for hand-made plans too. |
| R6 | Accepted. Membership is supported (not normalised away): a parent and its child are both measured. | Membership is per target (`_members`), so order no longer matters; ranking uses the window's length in *any* target (union), so overlapping targets are not counted twice. The readout's per-target lengths sample each shank's window independently. |
| R7 | Accepted. | Results are tied to the request that produced them (`describe()`): any change to a region, the side, the margin, a tilt limit or the craniotomy clears them and disables Use; Use (button or double click) refuses a request that no longer matches; an invalid request clears them. |
| R8 | Accepted. | Steering ends when the Plan section is hidden (another step, another probe, the task column hidden, another document), from its hide event and, as a safeguard, from the key filter itself, which then leaves the key alone. |

## UI and workflow suggestions

| # | Response |
| --- | --- |
| 1. Preview before committing | Done. Selecting a row draws the proposal on the atlas in white (pages move to its tip) and shows it in a shank view in the dialog, with its per-shank coverage and checks. Closing the dialog removes it. |
| 2. Validation summary | Done. A Checks column ("passed", or "passed, n notes" with the notes as a tooltip), reached/total for several targets, and per-shank coverage for the selected row. Candidates that fail a check are not listed; they are counted in the reasons when none is left. |
| 3. Constraints after manual adjustment | Partly. Targets and regions to keep out of stay with the plan, and the readout now re-checks them on every shank after any edit. Side, midline margin and tilt limits are search settings, not properties of a plan. Keeping them as requirements would turn a search filter into a standing constraint that the user did not set on the plan. The manual says so and asks for a new search to re-check them. |
| 4. Vertical cost of the Plan card | Done. The readout follows the fields; Angles, Craniotomy, Tip to surface, the Surgery menu, Region table… and Show in 3D fold under "Surgery and more". The fields no longer widen the column (318 px against 402 px at 1280 × 800); the column test now covers an active plan at the smallest window and at 1280 × 800. |
| 5. Ranking and uncertainty | Done. The manual describes the tilt penalty and the tilt bands. Failure messages now speak of what "this search found" ("No line through every target was found…"), not impossibility. |
| 6. Progress and cancellation | Done. A progress window with stages (searching the tilts, refining) and Stop; stopping keeps the best found so far and says so. On the Allen 10 µm atlas the four review-style searches took 1.6–5.4 s (single shank) and 4.1 s (four shanks, two targets, one region to keep out of). |
| 7. Realistic transitions | Done through R1-R8's tests: staged edit → save, undo, new project, open project; steering → navigation and real key delivery; changed constraints → acceptance; parent/child; four-shank exclusions and craniotomy at three rolls; tissue gaps; failed-open scaling. |

## Checks

- The review's script after the fixes: `conflict` refused with the region
  named; `gap` tip in tissue and the 0.30 mm gap disclosed; `hierarchy`
  identical in both orders (brain 2.80 mm, A 0.20 mm); `multi` no proposal (no
  four-shank position fits a 0.2 mm opening; the script's `props[0]` then
  raises, as there is nothing to index).
- Real Allen 10 µm atlas: single-shank proposals unchanged and all passing the
  shank checks; NP2 four shanks into PL and ILA while keeping out of ACA gives
  a single weak proposal, and the reasons say that 1,992 lines through both
  targets put some shank through ACA. A 0.75 mm-wide array beside the midline
  cannot reach mPFC without an outer shank crossing ACA, which 2.8.3's
  centre-line search did not report.
- What remains outside this resolution, as the review notes: a representative
  real planning session against built objects and exports, native installers,
  and observed users (`release_validation.md`). The shank's own width (about
  70 µm) is not modelled; constraints use each shank's centre line.
