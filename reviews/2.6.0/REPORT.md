# DriftlessMap 2.6.0 — follow-up review

**Reviewed 3 November 2026.** Commit `ce419db8c73d7df518f254995106a21b5a76c895`, compared with the [original 2.5.0 review](../2.5.0/REPORT.md). The reviewed code was extracted into an isolated directory. This review changes documentation and adds diagnostic evidence only.

The execution is substantial and mostly well directed. The changes address the original failure scenarios, make section navigation easier, improve small-window layouts, and give users clearer ways to save, review, and recover work. The implementation generally reuses the existing engine, rather than creating another copy of scientific state in the interface. Focused commits, regression tests, manual updates, and the resolution table make the work unusually easy to trace.

**I would prioritize a stabilization patch next.** Seven actionable findings remain: two affect the trustworthiness of atlas identity or result status; the others affect saved previews, completing repairs, review consistency, and batch-import cost. Several arise when individually tested features interact. Having a new button and a passing test for it does not yet establish that a user can complete the whole workflow.

## Execution assessment

### What was done well

- **Correct priorities.** The sequence tackles result integrity, section ownership, source verification, and save behavior before expanding the interface. The separate fixes for probe planning and deterministic registration also address scientific behavior rather than just appearance.
- **Shared mechanisms.** Section switching uses the section engine; Results repairs use mapping/build operations; download dialogs retain shared processing logic. The interface remains comparatively thin.
- **Specific regression coverage.** The suite now exercises stale stored sections, shared builds after section deletion, changed portable sources, outline ownership, multipart-image review identity, download rejection, compact layouts, and the new UI features.
- **Useful everyday improvements.** Save versus Save as versus portable copy is clearer. The section bar removes a recurring navigation detour. Persistent warnings are better than transient status messages. Natural file order and channel-column selection reduce repetitive work.
- **Better compact layouts.** At 1280 × 800, the same style of synthetic comparison fixture provides 706 pixels for the view area, versus 496 in the original review. The inspector folds away, and the inspected task controls fit. The 1100-pixel light-theme view also exposes the channel controls without the original horizontal clipping. These are offscreen observations, not display-scaling certification.

### Where execution needs refinement

The main weakness is **testing each feature more thoroughly than testing the transitions between features**. Saving while a comparison mode is active, reloading a changed atlas in the same folder, reopening old sections without the new summary field, and repairing more than one contribution reveal gaps. In particular, the Results tests manually reset `current_obj_index` after updating a mapping; that bypasses a real UI problem instead of detecting it.

The [resolution record](../2.5.0/RESOLUTION.md) is useful but should distinguish implemented portions from full acceptance. It already discloses missing cancellation, linked zoom, examples, and user studies. It should also explicitly retain the original recovery/autosave and export-manifest/preflight proposals as deferred, and reopen B1/B2 for the cases below.

## 1. Bugs that need attention and fixing

**P1:** fix before trusting the affected scientific workflow. **P2:** fix promptly; impact is narrower or a workaround exists. All seven findings have targeted executable observations in [evidence/observations.txt](evidence/observations.txt); the scripts use disposable synthetic data.

| ID | Priority | Finding | Relationship to prior review |
| --- | --- | --- | --- |
| F1 | P1 | Reloading an atlas changed in place bypasses the replacement guard | B2 remains incomplete |
| F2 | P1 | Older stored sections with unknown registration identity can appear current | B1 migration gap |
| F3 | P2 | Checkerboard display pixels enter saved project/layer data | New U9 integration defect |
| F4 | P2 | Updating a result selects a part and hides the remaining repair controls | New U3 workflow defect |
| F5 | P2 | Repair targeting repeatedly chooses a remapped contribution before another changed section | New U3 multi-section defect |
| F6 | P2 | The command palette bypasses the review checklist | New U9 consistency defect |
| F7 | P2 | Importing TIFF pages rereads the entire stack for every section | New U8 scaling defect |

### F1. Compare replacement atlases against the loaded identity

**Reproduction:** Load a 25 µm atlas, map two sections, and build a fiber. Replace the processed files in that same atlas folder with the fixture's 50 µm version. Reload the folder.

**Observed:** Loading succeeds; voxel size changes from 25 to 50 µm; the existing `Fiber 1` remains; its export provenance reports 50 µm. The ordinary different-folder test passes, but this same-folder case defeats the guard.

**Cause:** After the loaded stat signature no longer matches, `atlas_replacement_problem` hashes the current folder and the candidate folder. When both paths are the same, it compares the changed files with themselves. A copy of that changed directory has the same conceptual problem. [Replacement comparison](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/app.py#L7951).

**Fix:** Compare the candidate against immutable content identity captured for the loaded atlas. If that identity is unavailable and the source changed, refuse replacement while dependent work exists. Preserve the valid identical-relocation case.

**Acceptance:** Test changed files at the same path, a copy of the changed files, an unchanged relocation, and a missing original. The first two must leave the old calibration, objects, and export identity intact when rejected.

### F2. Unknown identity must not become “current”

**Reproduction:** Build from two sections, change one section's atlas page, and switch away. Use a stored-section summary without `registration`, matching the older optional-field format, then save and reopen.

**Observed:** With the fingerprint present, the build reports `registration changed`. Without it, the build reports `current`, including after reopening. Visiting the changed section reveals `registration changed` again. The diagnostic deliberately removes the new summary field; it is a migration-shape fixture, not a historical real-user archive.

**Cause:** `MappingRecord.status` returns `OTHER_SECTION` when no stored fingerprint is available. `derivation_status` accepts that as current, and Results renders it as current. Older projects are therefore loadable but not conservatively classified. [Status fallback](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/mapping_records.py#L130), [built-result status](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/mapping_records.py#L305).

**Fix:** Derive a trustworthy fingerprint from the stored section when migration can do so. Otherwise expose “not verified — open this section to check,” and propagate that state to Results and exports. Preserve the work; do not silently certify it or unnecessarily discard it.

**Acceptance:** Older summaries with unchanged and changed registrations, missing stored images, and malformed fingerprints must remain distinguishable from verified-current work before the user opens every section.

### F3. Keep comparison rendering out of persisted raster data

**Reproduction:** Preview the section on the atlas, enable Checkerboard, save, and reopen.

**Observed:** The project layer raster equals the checkerboard image rather than the complete warped section. In the small fixture, 1,440 array values differ from the original. Reopening retains the altered overlay. This establishes a saved-preview defect; it does not establish changed landmark coordinates or reconstructed implant geometry.

**Cause:** `_toggle_checker` replaces the actual overlay `ImageItem.image`. `project_payload` collects layer pixels through `get_atlas_single_layer_vis_data`, which reads that displayed image. Standalone layer export uses the same collector. [Comparison rendering](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/v2/register_panel.py#L187), [layer collection](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/app.py#L8680).

**Fix:** Render comparison through a separate presentation item/mask, or make every persistence/export/snapshot path read the canonical overlay. Give comparison modes an explicit lifecycle when the document, section, or preview changes.

**Acceptance:** Save, export a layer, switch away/back, undo, and reopen with Checkerboard or Blink active. Canonical raster pixels must remain identical. Comparison controls must accurately reflect the image they display.

### F4. Keep the built result selected throughout repair

**Reproduction:** Build cells, change registration, select the stale build in Results, and click Update mapping.

**Observed:** Selection changes from `merged cells` to `cells piece`. The recovery card disappears although the original merged object still reports `mapped again since`. Calling the rebuild handler with that selection leaves the stale build unchanged. The user must rediscover and reselect the original object.

**Cause:** Updating/making a replacement part changes the engine selection, and the panel refreshes against that new selection. Both existing Results repair tests manually restore the built-object index before rebuilding. [Update handler](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/v2/results_panel.py#L159), [test's manual reselection](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/tests/test_v2_shell.py#L857).

**Fix:** Retain the repair target across changes to object rows, preferably by stable identity. Reselect it and present the next required action after a successful mapping update.

**Acceptance:** An actual click sequence completes repair without assigning `current_obj_index` in the test or requiring a manual reselection. Cover cells, probes, and implants, including a section switch during repair.

### F5. Advance repair to the next section that needs mapping

**Reproduction:** Build a fiber from two sections, change both registrations, and update the first section's mapping. Inspect the next affected contribution.

**Observed:** The first contribution now says `mapped again since`; the second still says `registration changed`. `stale_contribution` nevertheless keeps returning the first section. Repeated Update actions target work already remapped instead of advancing to the second section. Rebuilding in between is a possible workaround, but does not provide the intended guided repair.

**Cause:** The selector takes the first out-of-date contribution in section order, without distinguishing “needs remapping” from “already remapped; needs rebuilding.” [Contribution selection](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/app.py#L4987).

**Fix:** Represent repair stages explicitly. Prioritize changed registrations, advance through them, then offer one rebuild from the updated parts. Show which section is being repaired and how many remain. Explain or gate rebuilding while contributions still need remapping.

**Acceptance:** A build with two or more changed sections progresses through each exactly once and ends current. Include mixed remapped/registration-changed/missing contributions.

### F6. Put review gating on the shared command

**Reproduction:** With three landmark pairs and all four checklist boxes unticked, run `register.review` through the command registry used by the palette.

**Observed:** The command is available and changes the registration from `not reviewed` to `reviewed`. The main Register button is disabled in the same state.

**Cause:** Checklist availability is attached to the panel button; the registry command calls `engine.mark_registration_reviewed` without that gate. [Command registration](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/v2/shell.py#L738).

**Fix:** Apply the V2 review requirement to the shared command so all routes agree. If expert override is intentional, make it explicit and document its meaning. Keep human review distinct from geometric mesh validity.

**Acceptance:** Button, palette, menu, and any shortcut use the same availability decision. A fresh registration cannot be marked reviewed through a less restrictive UI route.

### F7. Read a TIFF stack once when splitting its pages

**Reproduction:** Import a four-page `ZYX` TIFF using pages-as-sections, counting `TiffPageSeries.asarray` calls.

**Observed:** Four sections cause four reads of the complete `[4, 32, 24]` series. `add_sections` calls `add_section_from_file` for every page, constructing a fresh `TIFFReader` each time. For N equal-sized pages, this produces N full-stack decodes, or quadratic pixel-read work in page count. The probe measures reads, not a real-data wall-clock slowdown or an out-of-memory failure. [Page loop](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/app.py#L7592), [full-series read](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/driftlessmap/image_reader.py#L477).

**Fix:** Reuse a validated reader/decoded stack or read individual pages lazily while creating independent section state. Retain spill-cache behavior and source-selection provenance. Add batch-level progress and a safe way to stop between sections.

**Acceptance:** Count decode calls on a many-page fixture, verify exact raster/page identity after save/reopen, and benchmark a representative large stack with elapsed time and peak memory.

## 2. UI and workflow improvements

### Status of the original suggestions

| ID | Assessment of execution | Remaining work |
| --- | --- | --- |
| U1 — persistent section navigation | Delivered well: section name, position, page, and in-place switching | Add concise per-section mapping/review status where useful; test long names and keyboard navigation |
| U2 — clearer annotation pipeline | Useful next-step button for other annotations; implants retain their tailored controls | Keep the primary next action visible and report operation success from actual outcomes |
| U3 — actionable stale results | Good contribution list and repair entry points | Complete the repair sequence; F4/F5 currently interrupt it |
| U4 — compact layout | Clear improvement; original clipping addressed in inspected views | Native scaling/accessibility checks and more canvas space at the minimum width |
| U5 — predictable save behavior | Save, Save as, and portable-copy behavior delivered | Recovery/autosave proposal still deferred; avoid implying session saving is crash recovery |
| U6 — durable warnings | Session activity list and warning count delivered | Export manifest/preflight and durable sharing context remain useful follow-ups |
| U7 — understandable long operations | Named stages and download retry delivered | Safe cancellation remains deferred; add progress to batch imports too |
| U8 — batch sections | Natural ordering and TIFF-page creation delivered | Address full-stack rereads; expose partial completion clearly |
| U9 — registration review | Checklist and comparison tools are useful additions | F3/F6; linked zoom remains deferred; validate against actual anatomy |
| U10 — channel controls | Per-column selection and color names reduce repetitive work | Label bulk actions explicitly and verify distinguishability beyond color alone |
| U11 — undo discoverability | History display and cleared-history explanations delivered | Check discoverability and expectations with users, especially across section changes |
| U12 — first use | Three entry routes and quick-start documentation delivered | Bundled example project and observed novice sessions remain deferred |

### Additional recommendations after inspecting the implementation

1. **Keep the next action visible.** At 1280 × 800, Annotate's implants and other-annotation cards push the new mapping workflow below the initial viewport. A compact sticky next-action area, or collapsing irrelevant cards after choosing a task, would make the new guidance easier to discover. Keep detailed controls available without making every user scroll past every workflow.

2. **Make repair a short guided sequence.** Show “Update section 1 of 2,” then “Build again,” while keeping the same result selected. Preserve a visible success state once complete. Users should not need to understand object-row selection changes to recover a result.

3. **Use honest status language consistently.** Distinguish registration not reviewed, registration changed, mapping updated but build old, and identity unknown. Show the specific next action. A green “current” label should have a clear evidentiary meaning, including for migrated projects and exported results.

4. **Spend compact-window space on images.** The reflow is effective, but the 1100-pixel layout still gives a large share of width to controls, with additional image width taken by the atlas histogram/controller. Consider collapsing advanced display controls and making the task-column width easier to adjust. Measure usable image area as well as whether buttons fit.

5. **Give batches a visible outcome.** Show files/pages queued, added, failed, and remaining; offer a safe stop between sections. Preserve the successfully added sections and provide a clear retry route. The same summary should be available after the transient operation UI closes.

6. **Test workflows through the UI contract.** Replace hidden selection repairs in tests with button/command sequences and assertions about the next visible action. Add transition coverage for compare → save/reopen, repair → switch section → update → rebuild, old project → export, and batch import → save → reopen. Keep direct engine tests for scientific behavior, but do not let them substitute for UI completion tests.

Screenshots: [Annotate at 1280 × 800](evidence/annotate-1280.png), [Section at 1100 × 800, light theme](evidence/section-light-1100.png). Uniform images are intentional fixtures; their appearance is not a finding about anatomical rendering quality.

## Original bug closure and recommended order

| Original finding | Follow-up assessment |
| --- | --- |
| B1 — stale stored sections | Original current-version path addressed; migration remains incomplete (F2) |
| B2 — atlas replacement | Different-folder scenario addressed; changed-in-place reload remains unsafe (F1) |
| B3 — rat axes | Axis-file write and regression coverage present; this review did not repeat the production rat download/build |
| B4 — outline ownership | Section-owned drafts and regression coverage present |
| B5 — multipart image identity | Source page/scene/plane included in review identity, with regression coverage |
| B6 — deletion of shared builds | Shared builds are dismantled and unaffected parts preserved, with regression coverage |
| B7 — cached download verification | File-content verification added, with regression coverage |
| B8 — portable inactive source | Changed inactive originals now refuse portable packaging; messages retained |
| B9 — Escape during downloads | Rejection guard added and tested in download dialogs |
| B10 — clipped controls | Reflow and responsive inspector address inspected layouts; native scaling remains unverified |

Recommended order: **F1/F2 first**, then **F3–F6 together with transition tests**, then **F7 and a large-stack benchmark**. After those, spend effort on a representative real-data workflow, clean native installations, and short observed user sessions before expanding the feature set again. The existing [release-validation record](https://github.com/mohebi-n-associates/DriftlessMap/blob/ce419db8c73d7df518f254995106a21b5a76c895/release_validation.md) correctly records those broader gates as waived/pending; this source review does not close them.

## Validation and limits

**Existing regression suite: 504 tests run, 502 passed, 2 skipped, in 397.064 seconds.** Both skips require external real section/atlas fixtures. Ruff, Python compilation, Qt UI XML parsing, and `AGENTS.md`/`CLAUDE.md` equality passed. Local mypy was inconclusive: 16 syntax errors in installed PyQt6 stubs prevented further checking. The seven targeted defect scenarios and compact-layout probes completed independently; a green existing suite does not cover or disprove these additional observations.

The review covers the changes since 2.5.0, with emphasis on provenance, persistence, sections, mapping/build repair, registration review, imports, and UI transitions. It is not proof that every function is defect-free. Diagnostics use tiny synthetic atlases/images and Qt offscreen rendering on macOS. No native Windows/macOS installer certification, real HERBS migration, fresh production-atlas download, representative large-file benchmark, real-anatomy accuracy study, or user study was performed. See [evidence/README.md](evidence/README.md) for reproduction and environment details.
