# DriftlessMap 2.8.3 review

**Reviewed 4 November 2026.** Source commit `e7f85634e577247f5cbd7b696ddd7ee0e53d9948`. Comparison baseline: the [2.6.0 follow-up review](../2.6.0/REPORT.md), commit `ce419db8c73d7df518f254995106a21b5a76c895`. Scope includes the intervening fixes, 2.7.0 workflow changes, and all four 2.8 probe-planning phases, with particular attention to 2.8.3 proposals. The repository describes 2.8.3 as not yet published; this review assesses that source revision, not a downloaded installer.

**The previous seven findings are fixed in the scenarios rechecked. The new planning workflow is a useful advance, but it needs another correctness pass before release.** Eight new findings are documented below. Three are high priority: physical shanks can violate a proposal's constraints, pending edits can cross project boundaries, and failed-open recovery can change the animal-coordinate scale.

The implementation has several strengths: a GUI-free plan model, explicit coordinate conventions, reuse of existing reconstruction and persistence mechanisms, and synthetic geometry tests. The interface makes a pose editable without repeatedly creating parts and rebuilding them by hand. Entry/depth editing, the shank view, named craniotomies, and region-driven proposals form a coherent workflow. The weaker areas are the boundaries between presentation and document state, and the difference between a plausible search result and a fully checked plan.

## 1. Bugs that need attention and fixing

**P1:** fix before relying on the affected scientific workflow. **P2:** fix promptly; the scope is narrower or a workaround exists. Findings are reproduced with disposable synthetic fixtures; they are not claims of observed harm in real experiments.

| ID | Priority | Finding | Relevant addition |
| --- | --- | --- | --- |
| R1 | P1 | A four-shank proposal can cross an avoided region and miss its craniotomy | 2.8.3 proposals / 2.8.2 craniotomies |
| R2 | P1 | Pending pose edits are omitted from saves and can enter a new project | 2.8.0 delayed plan commit |
| R3 | P1 | Failed-open recovery loses atlas Lambda and changes coordinate scaling | 2.8.2 atlas-derived scaling |
| R4 | P2 | Conflicting Record/Keep out of choices silently discard the exclusion | 2.8.3 request validation |
| R5 | P2 | A proposal can end in a zero-label gap, without a warning in its results | 2.8.3 line scoring |
| R6 | P2 | Parent/child target coverage depends on list order | 2.8.3 hierarchy scoring |
| R7 | P2 | Changed search constraints leave old proposals selectable | 2.8.3 proposal dialog |
| R8 | P2 | Keyboard steering keeps modifying a hidden plan after leaving Annotate | 2.8.1 steering |

### R1. Check the physical shanks, or explicitly restrict the proposal feature

**Reproduction:** Use the supported Neuropixels 2.0 four-shank layout, a narrow target, a small craniotomy around the center line, and an avoided region along an outer shank. Search vertical proposals.

**Observed:** The search returns one proposal, reports the target reached with 200 µm coverage, and gives no failure reason. Sampling the four actual shank lines finds an outer shank crossing the avoided region. All four entry positions are outside the 100 µm-radius opening: their distances from its center are approximately 125, 168, 358, and 407 µm. Only one physical shank intersects the target in this fixture.

**Cause:** `_LineScorer.evaluate` evaluates one central line and one entry, without applying `shank_offsets_um` and roll to the constraints or coverage. The readout similarly describes the center line. The design explicitly acknowledges center-line searching as an implementation limitation, so this is not an undisclosed deviation from that design. The user-facing “Keep out of” and “Enter through the probe's craniotomy” controls, however, do not distinguish a center-line suggestion from a checked four-shank plan. [Scoring](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/probe_plans.py#L1095), [physical shank geometry](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/probe_plans.py#L670).

**Fix:** Validate every physical shank against exclusions, side/midline limits, its surface entry, and the opening, and score recording coverage by actual shank. Alternatively, restrict automatic proposals to single-shank plans until those checks exist, or make center-line-only proposals explicitly incomplete and prevent them from being presented as satisfying whole-probe constraints.

**Acceptance:** Test all shanks and multiple rolls, with an exclusion or opening boundary that only an outer shank violates. A proposal's stated target coverage must correspond to actual recording geometry.

### R2. Commit scientific state independently of the build debounce

**Reproduction:** Save a plan, nudge it with a steering action, then save or start a new project before the 500 ms commit timer expires. Also try Undo during that interval.

**Observed:** The displayed AP changes from 0 to +50 µm while `is_dirty()` remains false. Save writes AP 0; the display still shows +50 µm, and the window temporarily considers itself saved. Once the timer runs, AP +50 µm becomes stored and dirty. More seriously, executing the actual `project.new` command and choosing Keep the atlas leaves the old `Probe 1 plan` in the new document. Undo during the pending interval also permits the edited plan to reappear and clears redo.

**Cause:** `PlanEditor.preview` keeps scientific changes in `_pending` and `engine.plan_previews`, while canonical `probe_plans`, project collection, and dirty detection still describe the previous pose. The timer and editor state are not bound to a particular document or undo generation. Changing selection can call `commit()` after a new document has already been installed. [Pending state](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/v2/plan_editor.py#L508), [commit](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/v2/plan_editor.py#L722), [save and discard handling](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/v2/shell.py#L1066).

**Fix:** Store pose edits in the document immediately and debounce expensive reconstruction, or introduce an explicit pending-edit lifecycle that dirty detection, save/export, undo, close, and document replacement all honor. Cancel or invalidate callbacks belonging to a replaced document. Preserve sensible undo coalescing.

**Acceptance:** Within the debounce interval, save/reopen must reproduce the visible pose; a new project must remain empty; opening another project must not inject the previous plan; Undo must not be reversed by a late callback. Exercise real commands without manually invoking `editor.commit()` first.

### R3. Restore Lambda with the rest of the atlas metadata

**Reproduction:** Have an atlas with Lambda metadata and animal scaling that uses the atlas's Bregma–Lambda distance. Attempt to open a project with an invalid active raster so the existing document is restored.

**Observed:** Opening is correctly rejected, but the restored atlas's Lambda becomes `None`. In the synthetic fixture, the atlas distance goes from 500 µm to unavailable, and the scaling factor changes from 0.9 to 1.0. Consequently, subsequent animal-coordinate readouts/exports use a different scale even though the failed open is supposed to leave the document unchanged. The fixture supplies Lambda directly to the loaded view to isolate this metadata path; it is not a production rat-atlas test.

**Cause:** `ProjectSnapshot` reconstructs atlas metadata with only `vxsize` and `Bregma`. `AtlasView.set_data` now reads `Lambda`, but snapshot restoration does not supply it. The scaling fallback then returns 1.0. [Snapshot metadata](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/project_session.py#L40), [Lambda loading](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/atlas_view.py#L700).

**Fix:** Preserve all metadata required for atlas-derived calculations in runtime snapshots. Distinguish deliberately unscaled coordinates from a requested scale whose required reference is unavailable.

**Acceptance:** Failed-open rollback preserves atlas Lambda, the scale factor, and copied/exported animal coordinates exactly. Include both atlas-derived and explicitly entered reference distances.

### R4. Reject contradictory region constraints instead of deleting one

**Reproduction:** Add region A to both Record and Keep out of, then Find plans.

**Observed:** `ProposalRequest([A], avoid=[A])` silently changes the exclusion list to empty. The fixture then returns a proposal with no explanation, although the dialog still shows A in both lists.

**Cause:** Request construction filters out every avoided ID also listed as a target. This silently resolves a scientific constraint in favor of recording. Parent/descendant conflicts also need an explicit policy. [Request construction](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/probe_plans.py#L1038).

**Fix:** Reject the conflicting request with the region named, or ask the user to resolve it visibly. Validate hierarchical overlaps as well as exact duplicate IDs. Do not change constraints behind unchanged controls.

**Acceptance:** A contradictory request cannot produce an apparently unconstrained successful search. The displayed and effective constraints must agree.

### R5. Require an admissible tip and path before presenting a proposal

**Reproduction:** Put a zero-label gap immediately below a target, with labeled tissue farther down the same column. Search for that target with a vertical probe.

**Observed:** The best proposal reports 200 µm target coverage and no search reason, but `plan_readout` identifies its tip as outside the brain and warns accordingly. That warning is not included in the proposal table; it becomes apparent only through the plan readout.

**Cause:** The scorer bounds candidate depths by the **last** nonzero label within the shank length, then considers every earlier depth. It neither stops at the first tissue exit nor filters candidate tips to occupied tissue. Final proposals do not inherit the readout's warnings. [Depth limit and candidates](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/probe_plans.py#L1136).

**Fix:** Apply an explicit policy for unlabeled gaps and tissue exits, require a valid tip for accepted plans, and run final candidates through the same validity checks as the interactive readout. If traversing an unlabeled interval is permitted, disclose it rather than treating every interval as uninterrupted brain.

**Acceptance:** A layered phantom with a gap must not silently yield an outside-brain tip. The result list must show any permitted path warnings before Use this plan.

### R6. Make hierarchical target coverage independent of selection order

**Reproduction:** Score the same vertical line against a parent region and its child, first with `[parent, child]`, then `[child, parent]`.

**Observed:** The scorer reports one target reached in the first order and two in the second. With the parent first, the child is assigned zero coverage, despite the line crossing it. The live target readout repeats the order dependence. The diagnostic exercises the actual scorer and readout; it does not benchmark a full hierarchy search.

**Cause:** `_region_index` creates duplicate label IDs with different target owners, but `_owner` assigns each voxel to only the first matching owner. Target membership is not necessarily exclusive in an atlas hierarchy. [Membership index and lookup](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/probe_plans.py#L1050).

**Fix:** Either normalize redundant ancestor/descendant targets and explain that choice, or support membership in multiple requested regions. Avoid double-counting physical window length when ranking overlapping targets.

**Acceptance:** Reordering the same requested regions cannot change whether they are reached. Add parent/child, overlapping ancestor, duplicate, and disjoint-target cases to both scoring and readout tests.

### R7. Invalidate proposals when their inputs change

**Reproduction:** Search on the animal's right, select a result, change Side to the animal's left, and click Use this plan without searching again.

**Observed:** Use remains enabled and accepts the old right-side plan. In the fixture, the visible requested side is left while the chosen tip ML is +887.5 µm. Targets, exclusions, margins, tilts, and craniotomy selection likewise have no result-invalidation lifecycle.

**Cause:** `use()` accepts a stored proposal without comparing the current controls with the request that generated it. A request validation error also returns without explicitly clearing previous results. [Search and acceptance](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/v2/proposal_dialog.py#L191).

**Fix:** Bind results to an immutable request and probe/atlas identity. Clear or visibly mark them stale on relevant changes, disable Use until refreshed, and clear acceptance after invalid requests.

**Acceptance:** Changing any constraint requires a new search before acceptance, or clearly presents the previous request separately. Double-click acceptance must follow the same rule.

### R8. Stop steering when the planning context is no longer active

**Reproduction:** Enable Steer with keys, navigate to Project, then press W while focus is outside a text field.

**Observed:** The Plan editor is hidden, its steering toggle remains checked, and the stored tip moves +50 µm in AP. A Qt key event reproduces the mutation; this is not merely a direct call to the steering helper.

**Cause:** The application event filter checks modal windows, active window, and text input, but not whether the Plan editor is visible/active. Navigation does not remove the filter. This contradicts the design's “while the Plan card is active” scope. [Event filter](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/driftlessmap/v2/plan_editor.py#L141).

**Fix:** End steering when leaving the planning step, hiding its task column, changing the selected object, or replacing the document. If global steering is intentionally supported, it needs an unmistakable persistent indicator and an explicit scope.

**Acceptance:** Steering keys cannot silently edit a hidden plan in Project/Results or after a document change. Test actual key delivery and navigation, not only `steer_key()` calls.

## 2. UI and workflow improvements

### What is better

The Steps and Objects toggles make side-column control discoverable. Per-channel brightness beside the image reduces trips into the Section panel. New project in the same window is a useful addition, provided R2 is corrected. Planning by pose is much more direct than the old mark/add/build loop, and entry/depth editing fits the task well. The proposal dialog separates targets from exclusions clearly and gives explicit units and side conventions.

### Highest-value refinements

1. **Preview a proposal before committing it.** Selecting a row should show its track, actual shanks, opening, and target/exclusion intersections on the atlas, with a shank view available alongside it. At present, the modal results table supplies coordinates and coverage but no anatomical preview of the selected candidate. Use this plan should follow inspection, not be the first point at which the candidate can be seen anatomically.

2. **Give results an explicit validation summary.** Show targets reached/total, per-shank coverage, excluded-region intersections, entry/opening checks, and tip validity. Separate “candidate found” from “all requested checks passed.” Carry warnings into the table instead of waiting until after acceptance.

3. **Show which constraints remain active after manual adjustment.** Plans retain targets and exclusions, but the request's side, midline margin, and tilt limits are not retained as a complete request. After a nudge, users need to know whether the original proposal requirements still hold. Persist a request snapshot or clearly label proposal checks as applying only to the original candidate; re-evaluate exclusions for edited plans.

4. **Reduce the vertical cost of the Plan card.** At 1280 × 800, selecting a probe leaves its main action buttons and readout below the initial viewport. Scrolling to the readout hides the probe list and most surrounding context. Keep the selected probe identity, essential pose fields, and a compact status visible; move surgery setup and infrequent actions into disclosures. In this populated fixture, the task body's minimum width is 419 pixels against a 402-pixel viewport, so extend the compact-layout test to an active plan rather than only empty/basic steps.

5. **Clarify ranking and uncertainty.** The implementation penalizes tilt by 10 µm of coverage per degree and preserves tilt-band alternatives, while the manual's summary says coverage then shallowest tip. Explain why a shorter-coverage result may rank above another. Since the search samples lines and retains a limited set, use “No qualifying line found in this search” for heuristic failure; reserve absolute impossibility statements for a proved condition.

6. **Give the search progress and cancellation.** `propose_plans` has a progress callback, but the engine call does not connect it to a user-facing progress/cancel workflow. Include coarse search and refinement stages. Benchmark representative atlas/target combinations, particularly a failed multi-target search whose explanatory pass expands the angle search.

7. **Extend tests around realistic transitions and geometry.** The current tests establish useful nominal cases, but often explicitly commit before undo/save and call steering helpers directly. Add pending edit → save/new/open/undo, active steering → navigation, changed request → acceptance, parent/child targets, four-shank exclusions, tissue gaps, and failed-open scaling preservation.

Screenshots: [Plan at 1280 × 800](evidence/plan-1280.png), [Plan readout after scrolling](evidence/plan-readout-1280.png), [proposal dialog](evidence/proposal.png). These are synthetic offscreen fixtures; white rectangular tissue is intentional, not a finding about real-image rendering.

## Closure of the previous review

The seven previous probes were rerun against 2.8.3. The atlas probe was adapted only to record the now-expected export refusal rather than abort on it.

| Previous finding | Observed result in 2.8.3 |
| --- | --- |
| F1 — changed-in-place atlas | Reload rejected, 25 µm calibration retained, export rejects changed source files |
| F2 — unknown stored registration | Reports not verified before visiting the section; then registration changed when appropriate |
| F3 — checkerboard persistence | Saved raster has zero changed values; reopened overlay matches the canonical raster |
| F4 — repair selection | Merged cells remain selected; recovery stays visible; rebuild ends current |
| F5 — multi-section repair order | Next affected contribution advances to the second changed section |
| F6 — review command bypass | Command refuses unticked checklist and retains not reviewed |
| F7 — TIFF repeated reads | Four page-sections cause one full-series read, rather than four |

These are substantive fixes, not merely changed labels. The resolution work is a strong part of this release series. Broader original proposals such as crash recovery/autosave, linked review zoom, export preflight/manifests, and observed user validation remain separate from those bug closures.

## Validation and recommended next step

**Existing regression suite: 545 tests run, 543 passed, 2 skipped, in 278.418 seconds.** Both skips require external real section/atlas fixtures. Ruff, Python compilation, Qt UI compilation, and agent-guide equality passed. Local mypy remains inconclusive because 16 syntax errors in the installed PyQt6 stubs prevented further checking. The targeted probes reproduced the eight findings above independently of the passing regression suite.

The review used a clean isolated archive of the exact commit, preserving the working checkout. Diagnostics and screenshots use synthetic atlases and temporary settings on macOS arm64 with Qt offscreen rendering. No application code was modified. See [reproduction instructions and evidence](evidence/README.md).

I recommend fixing **R1–R3 before publishing the planning workflow**, then the remaining constraint/UI defects in the same stabilization effort. Follow with a representative real-atlas planning session that compares proposal coverage, physical contacts, built objects, and exported coordinates, plus native installer checks. The [release-validation record](https://github.com/mohebi-n-associates/DriftlessMap/blob/e7f85634e577247f5cbd7b696ddd7ee0e53d9948/release_validation.md) still records broader real-data, installer, and user-evaluation gates as pending. This review does not establish clinical/surgical accuracy, production-atlas performance, native 3D behavior, or real-user usability.
