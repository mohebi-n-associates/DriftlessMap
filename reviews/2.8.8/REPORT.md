# DriftlessMap 2.8.8 review

Reviewed 5 November 2026 at commit `e2956d748798d8b82d236c0df7b8f6930d99be52`, including changes since the 2.8.3 review. The accompanying [whole-codebase refactoring assessment](REFACTORING.md) addresses the subsequent question about performance and architecture across all of DFM.

## Assessment of execution

The implementation has made meaningful progress. The 2.8.4 response introduced engine-owned staged edits and explicit flush/discard boundaries, restored atlas Lambda in snapshots, checked proposals across shanks, and added cancellation and hidden-editor steering protections. Those changes address ownership and lifecycle problems rather than only adjusting messages. The current suite includes regressions for these paths and passes locally.

Fibers, prisms, hardware, and spacing build on shared planning interfaces, and the prism-tip migration preserves the interpretation of older poses. These are useful extensions. However, drawing, clearance checking, and spacing now represent device geometry differently. Three reproduced cases show that a successful-looking spacing/clearance result can conceal physical overlap or unresolved fixed-device conflicts. Address these before treating Space out as a dependable whole-device clearance check.

The next engineering investment should combine correctness fixes with incremental refactoring. A broader restructuring is justified, but there is no evidence supporting a full rewrite or a claimed percentage speedup for the entire application.

## 1. Bugs needing attention

| ID | Priority | Finding | Origin |
| --- | --- | --- | --- |
| R1 | P1 | A fiber inside a prism body can report positive clearance | Implant clearance representation introduced before 2.8.8; inherited by Space out |
| R2 | P1 | Space out accepts overlapping fixed tips without reporting a clash | 2.8.8 spacing relaxation |
| R3 | P2 | Conflicts between two fixed plans disappear from the spacing report | 2.8.8 pair filtering/reporting |
| R4 | P2 | Space out performs repeated expensive scientific work synchronously on the GUI thread | 2.8.8 search; compounded by broader refresh duplication |

### R1. Clearance must detect solid containment

**Reproduction:** In the existing 50 µm synthetic atlas, create a vertical prism with corner tip `(500, -500, -1400)` µm, roll 90°, width/depth 1000 µm, length 3000 µm, and a flat 90° bevel. Place a vertical, 100 µm-diameter fiber at `(0, 0, -500)` µm with bare length 10000 µm. The fiber passes through the prism's interior.

**Observed:** `clearances` returns approximately **477 µm**, exceeding the default 300 µm gap. In the prism model, the fiber tip is 500 µm behind the face, centered across its width, and 900 µm above its bottom: inside the solid.

**Cause:** `plan_segments` represents a prism using `device_lines(..., outline=True)`: parallel boundary lines with zero radius. `_pair_gap` measures distance to those lines. A device contained inside the prism can be far from every boundary line, and containment is never checked. Prism segment lengths also follow the generic above-entry extent rather than the actual model's length.

**Fix:** Use a common solid geometry representation for the actual prism body, fiber, and hardware. Include intersection/containment tests before reporting separation, with a reliable distance computation for disjoint solids. A sampled boundary should not establish whole-body clearance.

**Acceptance:** Include fiber-inside-prism, prism-inside-prism, edge/face crossings, disjoint devices, nonzero roll/tilt, bevels, and different lengths. Intersecting solids must not report a positive gap. Rendering and clearance must describe the same dimensions and frame.

Sources: [plan segments and pair distances](../../driftlessmap/probe_plans.py), functions `plan_segments` (line 1119), `_pair_gap` (1172), `device_lines` (1479), and `planned_model` (1529); [solid prism membership](../../driftlessmap/implants.py), `model_section` prism branch around line 866. Reproduction: `audit.py containment`.

### R2. Impossible tip overlap must remain an unresolved conflict

**Reproduction:** Use the spacing-test fiber dimensions: 200 µm bare diameter, 1500 µm bare length, and 1250 µm × 6400 µm ferrule. Put both tips at `(0, 0, -1200)` µm and allow both plans to move with default settings.

**Observed:** Both plans tilt, `ap_used` becomes true, and `report['clashes']` is empty. The ordinary clearance result still reports **0 µm** separation. Two finite-diameter fibers cannot become nonintersecting while their tips occupy the same point.

**Cause:** For two segments reaching their tips, `space_plans.gap` reduces the required gap to `distance_between_tips - radii - 1 µm`. This can be negative. The relaxation intentionally accommodates nearby fixed tips, but it also treats physical overlap as satisfying the spacing objective. The final report filters by that relaxed objective.

**Fix:** Distinguish a requested gap that is unattainable at fixed tips from actual overlap. Retain an explicit unresolved-overlap result and explain that the user must move tips or change device dimensions. Smaller nonnegative tip clearance can be a documented exception, but it should be reported rather than implied to meet the requested gap.

**Acceptance:** Test coincident tips, partially overlapping tip cross-sections, exactly touching surfaces, and close but disjoint tips. A successful ferrule adjustment must not hide a remaining body overlap.

Source: [spacing](../../driftlessmap/probe_plans.py), nested `gap` around lines 1227–1247 and final clash filtering around 1338. Reproduction: `audit.py overlap`.

### R3. Report unresolved fixed-device conflicts

**Reproduction:** Place fixed fibers at `(-800, 0, -1200)` and `(-600, 0, -1200)` µm, and a third fiber at `(900, 900, -1200)` µm. Select only the third fiber as movable and set both tilt limits to zero.

**Observed:** The two fixed ferrules overlap; ordinary clearance returns 0 µm. Spacing reports `moved=[]` and `clashes=[]`. The dialog translates that into **“Nothing needed to move.”**

**Cause:** Search pairs are limited to those containing a movable plan, which is sensible for optimization, but the final report uses the same limited set. The dialog promises that every plan keeps the gap, yet silently omits conflicts that the selected degrees of freedom cannot resolve.

**Fix:** Keep optimization limited to movable plans, but independently assess and report all remaining conflicts. Label fixed/fixed pairs as requiring a selection or geometry change. Distinguish “selected plans already satisfy the objective” from “all plans clear.”

**Acceptance:** Test fixed/fixed, fixed/movable, and movable/movable conflicts together. The list, result summary, and ordinary clearance readout must agree on which conflicts remain.

Sources: [pair filtering](../../driftlessmap/probe_plans.py), lines 1219–1220 and final report; [summary](../../driftlessmap/v2/spacing_dialog.py), `spacing_summary`. Reproduction: `audit.py fixed`.

### R4. Keep the spacing search off the GUI thread and avoid full readouts for every trial

**Observed:** A profiled two-fiber search on the small test atlas took about 1.58 seconds and called `plan_readout` 295 times. Cumulative `track_checks` time was about 1.42 seconds. `SpacingDialog.run` changes the cursor and directly calls the synchronous engine operation; it provides neither progress nor cancellation while the search runs.

**Cause:** Every trial and accepted candidate computes a full anatomical readout, although spacing consumes entry/geometry information. Segment geometry is also regenerated during pair evaluations. The underlying search can do substantially more work as device count and geometry grow, but larger-workload timings were not collected here.

**Fix:** Split the spacing inputs from explanatory anatomical diagnostics, reuse immutable per-pose geometry, and run the search on a worker with progress/cancellation. Validate the final candidate fully, then commit all accepted poses as one undoable operation on the GUI thread. Reject a result belonging to an old document/input generation.

**Acceptance:** A GUI heartbeat continues during the search; cancel leaves state unchanged; changes to input state invalidate stale results. Benchmark identical plan sets before and after. Preserve the final scientific checks rather than dropping them to achieve speed.

Sources: [dialog callback](../../driftlessmap/v2/spacing_dialog.py), `run`; [engine operation](../../driftlessmap/probe_plan_engine.py), line 469; [trial evaluation](../../driftlessmap/probe_plans.py), nested `apply` at 1264. Evidence: `audit.py pure_perf`.

## 2. UI and workflow improvements

1. **Preview a batch spacing result before applying it.** Show before/after ML and AP angles, entry displacement, minimum physical gap, target/avoid-region changes, and craniotomy warnings. Offer Apply and Cancel; keep Apply as one undo step. The current instruction to recheck regions is helpful, but users should see the consequences together.
2. **Make the outcome explicit.** Distinguish “all requested gaps met,” “close tips limit the achievable gap,” “overlap remains,” “fixed plans conflict,” and “geometry could not be checked.” List the affected device pair and the corrective action. Update the initial “too close” list after a run and when the requested gap changes.
3. **Make long operations visibly active and cancellable.** Space out should report progress and support cancellation. Extend a consistent job presentation to matching, registration, geometry generation, and large I/O where practical. Cancellation semantics must match the operation's actual safe stopping points.
4. **Refresh the affected UI, not all scientific calculations.** An unchanged prism panel currently requests four full readouts per shell refresh. Shared readout data and targeted updates should reduce idle CPU use and make edits feel more immediate, especially with multiple devices.
5. **Show which constraints spacing preserves.** Fixed tips and tilt limits are enforced; craniotomy and tissue/target suitability need re-evaluation after a tilt. State this near the action and expose changed checks in the result. Do not imply a globally minimal solution: the implementation is a greedy, one-degree local search.
6. **Use consistent device terminology and units.** The shared planning engine is useful, but generic result/error text should say device/plan when fibers and prisms are included. Preserve precise anatomical axis names and display actual achievable clearance alongside the requested millimeter gap.

These are workflow recommendations based on code paths and synthetic execution, not findings from a new human usability study or a native OpenGL visual assessment.

## Validation and limitations

- Tested an isolated archive of the reviewed commit, avoiding changes to application source and user settings.
- Full suite: **584 tests run, 582 passed, 2 skipped**, in 313.215 seconds. The skips require external real-data fixtures.
- Ruff passed on the reviewed snapshot. Python compilation, Qt `.ui` parsing, and `AGENTS.md`/`CLAUDE.md` equality passed.
- **Mypy did not complete:** the installed PyQt6 `QtGui.pyi` has 16 parameter-order syntax errors. This is a local dependency-stub blocker, not a passing type-check or evidence of 16 application defects.
- Three independent geometry/report reproductions and focused CPU profiles are retained in [evidence](evidence/README.md).
- Existing tests passing does not negate the new reproduced cases. No production fixes were made as part of this review.
- No clean-machine Windows/macOS installer trial, native rendering certification, CZI runtime trial, or representative real-data performance/numerical validation was completed. The relevant gates in `release_validation.md` remain pending.
