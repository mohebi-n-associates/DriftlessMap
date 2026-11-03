# DriftlessMap 2.5.0 review

**Reviewed 3 November 2026.** Release commit `5305b1d78efcf1077dc2333e87d04aceabac3e18`.

DriftlessMap 2.5.0 has a useful foundation: a task-oriented interface, retained sections, explicit registration review, reproducible object exports, and substantial automated coverage. Its most urgent problems are **scientific state becoming associated with the wrong section or atlas**, and **out-of-date work appearing current**. These should be corrected before adding more automation or treating the new multi-section workflow as dependable for downstream analysis.

This review identifies **10 actionable defects**, followed by **12 UI and workflow improvements**. Six defects are high priority because they can misrepresent scientific results, place annotations on the wrong image, remove needed reconstruction parts, or block an advertised core workflow. The other four affect verification, portable saves, operation handling, and access to controls. No universal crash or unrecoverable loss of every project was established.

The review used an isolated archive of the release, preserving the working checkout's uncommitted tutorial, image, and atlas changes. During the review, the shared checkout advanced to 2.5.1 commit `e82afcd`, incorporating the rat-axis metadata fix described in B3. That fix is absent from the reviewed 2.5.0 release. Application code was not changed by this review.

**Validation:** 471 existing tests ran: **469 passed, 2 skipped**, in 201.4 seconds. The skipped tests need real section/atlas fixtures. Ruff, Python compilation, Qt UI parsing, and `AGENTS.md`/`CLAUDE.md` equality passed. Additional targeted probes reproduced the findings below. Type checking was inconclusive because the installed PyQt6 stubs contain syntax that stopped mypy before completion. See [validation and reproduction instructions](evidence/README.md), [observations](evidence/observations.txt), and [the suite log](evidence/unittest-output.txt).

Scope includes persistence and provenance, multi-section transitions, image/page identity, mapping and reconstruction, atlas processing, exports, and the V2 interface. Interface inspection used Qt offscreen rendering on macOS arm64, including both themes; the screenshots are synthetic-fixture layouts, not native-installer or real-data validation. Windows/macOS installer trials, real HERBS migration, real-data numerical agreement, and user studies remain pending in the release's [validation record](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/release_validation.md).

## 1. Bugs that need attention and fixing

**P1:** fix before relying on the affected scientific workflow. **P2:** fix promptly; the defect has a narrower impact or a practical workaround. These priorities are review judgments, not claims that every project is affected.

| ID | Priority | Defect | Evidence |
| --- | --- | --- | --- |
| B1 | P1 | Switching sections hides stale registrations in built results and exports | Engine integration probe |
| B2 | P1 | Loading another atlas leaves old results eligible for export with new atlas provenance | Engine integration probe |
| B3 | P1 | Fresh rat atlas processing omits metadata required to build probes | Processing-path probe and source trace; writer fixed in the newer 2.5.1 checkout |
| B4 | P1 | An unfinished implant outline can be committed to the wrong section | V2 interaction-path probe |
| B5 | P1 | Changing a TIFF page retains the previous page's registration review and mapping status | TIFF/engine integration probe |
| B6 | P1 | Removing a section with results discards other sections' parts inside a shared build | Multi-section integration probe |
| B7 | P2 | Rat download reuse trusts a manifest instead of checking the file's current bytes | Dialog verification probe |
| B8 | P2 | A portable save silently succeeds without a changed inactive section's original | Save/load probe |
| B9 | P2 | Escape bypasses the download dialog's active-operation close guard | Qt key-event probe with active-state simulation |
| B10 | P2 | Controls and labels are clipped at an accepted window size | Rendered 1280 × 800 layouts |

### B1. Switching sections makes stale results look current

**Reproduction:** Map two sections into a fiber and build it. Change the open section's atlas page without updating its mapping. Its status becomes `registration changed`. Open the other stored section and export all results.

**Observed:** The built fiber returns to `current`; export produces no stale-result note. The probe recorded `current → registration changed → current` solely because the active section changed. The changed section still exists in the project.

**Cause:** `MappingRecord.status` treats a different active section as `another section`, and `derivation_status` treats that as current. Its comment assumes a section that is no longer loaded cannot change—an assumption that no longer holds with retained editable sections. Both object status and export warnings use this logic. [Mapping status](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/mapping_records.py#L130), [derivation status](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/mapping_records.py#L298).

**Fix:** Resolve every mapped section against that section's current retained registration, including inactive sections. Represent unverifiable legacy sections separately. Use the same calculation for the object list, Results, build decisions, and all exports.

**Acceptance:** An object remains stale after switching away, saving/reopening with another section active, and exporting. Its explanation names the changed section. Updating the mapping and rebuilding restores current status.

### B2. Atlas replacement can mislabel existing scientific results

**Reproduction:** Build a two-section fiber using a 25 µm atlas. Load a different atlas of the same dimensions with 50 µm voxels, then reopen the first stored section.

**Observed:** The old merged fiber remains and is reported `current`. `get_object_export_provenance()` now returns the replacement atlas's checksum and 50 µm voxel size. Existing result coordinates were not recomputed for that atlas.

**Cause:** Atlas loading changes the document's active atlas without enforcing compatibility with retained section mappings and built objects. The registration fingerprint omits atlas content identity and voxel calibration; object export obtains provenance from the currently loaded atlas. Equal dimensions are therefore insufficient protection. [Atlas loading](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L7868), [registration fingerprint inputs](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L1911), [export provenance](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L8016).

**Fix:** Compare atlas content identity and coordinate-frame metadata before replacement. Allow relocation of identical content. For different content, require a deliberate new-document or remapping workflow; preserve each result's original atlas identity. Never restamp old results as belonging to a newly loaded atlas.

**Acceptance:** Test equal-shaped atlases with different labels, voxel sizes, and origins. Old results cannot be exported as current under the new atlas. A relocated identical atlas remains usable.

### B3. Freshly processed rat atlases cannot satisfy probe-building requirements

**Reproduction:** Download/process Waxholm or the SWC female rat atlas into a fresh folder, then attempt to build a probe.

**Observed evidence:** The release's rat processing path can finish successfully without creating `atlas_axis_info.pkl`. A processing-path probe, substituting tiny volumes for the expensive volume/mesh work, returned `processing_success: true` and `axis_metadata_written: false`. `get_probe_atlas_metadata()` explicitly refuses to proceed when that file is absent, telling the user to reprocess. Repeating the same release's rat processing does not add the missing writer. Full remote atlas downloads were not repeated for this review. [Rat processing](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/atlas_downloader.py#L109), [probe metadata requirement](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L7082).

**Fix:** Write and validate the WHS axis metadata before declaring processing complete. Provide a repair path for already processed 2.5.0 folders whose source identity and orientation can be verified.

**Existing work:** The newer 2.5.1 checkout (`e82afcd`) adds `waxholm_axis_info` and writes the file from the worker; this addresses the missing writer. Its native end-to-end behavior was outside this 2.5.0 review. Extend validation to a completed processed folder followed by probe building and native-coordinate export; testing the helper alone does not cover the full failure.

### B4. An unfinished outline can move to another section

**Reproduction:** In Annotate, select a fiber and start an outline on section B. Leave four vertices unclosed. Go to Project, open section A, return to Annotate, and finish the outline.

**Observed:** The editor stays in `draw` mode with B's vertices. Finishing writes those vertices into A's `implant_outlines`. The probe used `[[5,5], [15,5], [15,20], [5,20]]` and found exactly that outline on A.

**Cause:** The draft is held by the long-lived `OutlineEditor`; its saved interface state contains an implant ID and vertices but no section ID. Section switching replaces the engine's section while leaving that editor draft active. `_store` writes to whichever section is currently open. [Editor storage](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/outline_editor.py#L131), [draft state](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/implant_card.py#L404), [section switch](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/section_engine.py#L358).

**Fix:** Make draft outlines section-owned, validate that ownership when committing, and restore the relevant draft when switching sections. An explicit finish/discard choice is an acceptable interim solution.

**Acceptance:** Draw unfinished outlines on two sections, switch repeatedly, save/reopen, and finish each. No vertices cross section boundaries or disappear without an explicit choice.

### B5. A different TIFF page can still be marked reviewed

**Reproduction:** Open a two-page TIFF, place landmarks, map a fiber, and mark the current registration reviewed. Move the histology page slider to the other page.

**Observed:** The displayed raster changed from mean intensity 180 to 40 in the synthetic fixture, but section ID and registration fingerprint were identical. Review stayed `reviewed` and the mapping stayed `current`.

**Cause:** `image_page_changed` replaces the displayed image without a section/review transition. The registration fingerprint identifies image dimensions but not the histology page or source selection. This can reuse a review made against different anatomy. [Page change](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/image_view.py#L397), [fingerprint construction](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L1911).

**Fix:** Give page/scene selections an explicit scientific identity. Either open each as a retained section or deliberately invalidate affected registration, review, and mapping state when the raster changes. Include source selection and relevant raster transformations in review identity without treating brightness adjustments as anatomical edits.

**Acceptance:** Test Z/page, scene, and fixed-axis changes with identical image dimensions. A review cannot silently survive a change of anatomical image, and mapping a new page cannot overwrite the previous page's work unintentionally.

### B6. Removing one section destroys the other parts of a shared build

**Reproduction:** Map sections A and B into one fiber and build it. While B is open, remove A using **Remove with results**. Try to rebuild B's remaining contribution.

**Observed:** The merged fiber is deleted, the object list becomes empty, and B's mapping record remains. Building then fails with “Map Fiber 1 on at least one section first.” B's part was held inside the deleted build and was not restored. Its kept source marks remain available for recovery by remapping; this is not loss of all source data.

**Cause:** `remove_section(delete_results=True)` directly deletes any object whose derivation mentions A. It does not unpack unaffected parts first. The newer `_delete_results_of` path used by Remove mapping already handles that distinction. [Section removal](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/section_engine.py#L431), [mapping removal helper](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L4821).

**Fix:** Apply the same dependency-aware removal semantics to section deletion: unpack shared builds, delete only the removed section's contributions, and retain other parts. Make the operation undoable or explicitly establish a history boundary.

**Acceptance:** After removing A, B can be rebuilt without remapping. Cover fibers, prisms, probes, and merged annotation objects, including three-section builds and undo/redo behavior.

### B7. Cached rat downloads are not actually reverified

**Reproduction:** Keep a download manifest containing the expected SHA-256, but replace its corresponding archive with different nonempty bytes. Choose that folder again.

**Observed:** `_verified()` returns `True`. The test file contained `wrong nonempty bytes`; the manifest contained the expected archive checksum. No hash of the current file was calculated.

**Cause:** Verification checks that the file exists and that the manifest's remembered checksum equals the expected checksum. The manifest describes a previous download, not necessarily today's file. Processing and download reuse rely on this result. The classic processing entry point only checks for missing/empty files. [Reuse verification](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/rat_download_dialog.py#L143), [processing gate](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/atlas_downloader.py#L290).

**Fix:** Stream-hash existing files against pinned checksums before reuse/processing, off the GUI thread. Offer a specific repair/redownload action when they fail. Apply equivalent integrity requirements to both interfaces.

**Acceptance:** Modified, truncated, and replaced archives are rejected despite an unchanged manifest; unchanged files pass. Include a valid archive with altered content so success does not depend on the archive parser detecting corruption.

### B8. Portable saving treats inactive changed sources differently

**Reproduction:** Load two sections, leave A inactive, modify A's original image on disk, and save a portable project while B is active.

**Observed:** Saving succeeds. The archive contains B's original but no packed original for A; A's provenance records `source_changed_since_load: true`. The final status is “Project saved successfully.” A's lossless working raster is preserved. A warning is emitted during the save but is replaced by the success message.

**Cause:** The active-source portable path refuses a changed source. `sections_for_save` instead emits a note and omits the inactive source, without the same refusal or persistent disclosure. This violates the documented reload requirement for changed portable sources and makes completeness depend on the active section. [Stored-section packaging](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/section_engine.py#L289), [active-source policy](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L9011).

**Fix:** Apply one policy across all sections. Refuse changed-source portable packaging with a section-specific explanation, or explicitly offer a raster-only copy and retain an omissions summary. Never package changed bytes as the original.

**Acceptance:** Identical source changes produce identical decisions whether the section is active or inactive. The final result clearly identifies every omitted original.

### B9. Escape closes a dialog that refuses the Close button

**Reproduction:** In the rat atlas dialog, press Escape while an operation is active.

**Observed evidence:** A Qt key-event probe with `has_active_downloads()` reporting true hid the dialog and returned Rejected. The active-operation protection is implemented only in `closeEvent`, which Escape's rejection path bypasses. This test establishes the dismissal bug; it does not establish an actual download-thread crash. [Close guard](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/atlas_downloader.py#L333).

**Impact:** The user can lose the visible operation/progress workflow without a deliberate cancellation or background-operation handoff. The caller has already left the modal workflow, so the usual process-and-open sequence cannot be assumed to complete normally.

**Fix:** Centralize Close, Escape, rejection, and application shutdown around one operation lifecycle. Either safely cancel and wait for workers, or keep the dialog open with an explanation. Audit the Allen dialog's analogous guard too.

**Acceptance:** Exercise real short-lived workers with Close, Escape, and application exit during download and processing. No hidden orphan operation, destroyed running thread, or ambiguous completion.

### B10. The accepted compact layout hides controls

**Reproduction:** Run the V2 window at 1280 × 800 with an atlas and section loaded. Visit Section and Annotate.

**Observed:** Offscreen renders clip the right side of task cards, including channel fields and the implant action row. Compare/Section/Multi-plane labels are heavily elided, and atlas context is cut off. The view area measured 496 pixels wide for both images combined, before internal controls. The shell accepts windows down to 1100 × 700.

**Cause:** Fixed/minimum column widths and non-wrapping button rows exceed available space; the task scroll area disables horizontal scrolling. These constraints do not produce a consistently usable compact layout. [Shell sizing](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/shell.py#L85), [task scroll area](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/widgets.py#L192).

**Fix:** Reflow action rows, collapse the navigation rail or inspector at smaller widths, and ensure task content respects its viewport. Preserve a readable minimum image area. Keep the existing Focus mode as a user option, but essential controls must remain reachable outside it.

**Acceptance:** Inspect every step at 1100 × 700, 1280 × 800, and 1480 × 920 in both themes, then verify native Windows/macOS display scaling and keyboard access. No control may be clipped without an accessible route to it.

Evidence: [Section layout](evidence/section-1280.png) and [Annotate layout](evidence/annotate-1280.png). Small uniform images are intentional synthetic fixtures; their appearance is not a rendering-quality finding.

## 2. UI and workflow improvements for a more user-friendly application

The six-step structure, command search, explanation of disabled actions, explicit review status, named implants, retained sections, and Focus mode are worth keeping. The main opportunity is to reduce navigation and interpretation work around them. These proposals are design recommendations grounded in the current implementation; they have not been validated through a user study.

### U1. Make section identity and switching available beside the images

**Priority: high.** Currently, normal section switching lives in Project > Sections; Annotate explicitly sends users back there to edit other mappings. Add a persistent section selector with thumbnail, name, position, and previous/next shortcuts beside the canvas. Keep the current Match/Register/Annotate step when switching.

Show the active section name directly over its image, including TIFF page/scene identity. Tie drafts to that identity as in B4/B5. This reduces both repeated navigation and wrong-section edits. **Success measure:** a user can inspect and correct three sections without returning to Project or losing their working context. [Current section controls](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/project_panel.py).

### U2. Present one clear annotation pipeline across object types

**Priority: high.** Fiber/prism controls already present Draw → Map this section → Build. Other annotations require a warp preview, mapping, making parts, and building through separate cards; some operations require selecting objects in the right-hand list.

Use the same visible progression for each annotation kind: **Mark → Check registration → Map section → Build result → Inspect/export**. Offer the next valid action in place and explain its effect. Extend the existing probe behavior that prepares a needed preview, while keeping advanced manual controls available. Keep “map” and “build” distinct because they perform different scientific operations. **Success measure:** a new user can produce a cell result without being verbally guided through preview and part creation. [Current annotation flow](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/annotate_panel.py), [probe flow](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/probes.py).

### U3. Turn stale-result explanations into direct recovery actions

**Priority: high, after B1/B2.** Results already names why an object is out of date. Add buttons alongside the explanation: **Open affected section**, **Review registration**, **Update mapping**, and **Rebuild result**. Show which sections contribute to a result and which need attention.

Use per-object and per-section review history. The current Results panel's “Last mapping” sentence reads session-level state, which is less useful when inspecting an object built from several sections. **Success measure:** a user can repair a stale result entirely by following its status card, with no search through menus. [Results panel](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/results_panel.py).

### U4. Make the layout adapt before relying on Focus mode

**Priority: high.** Address B10 with a compact navigation rail, a collapsible inspector, wrapping actions, and shorter persistent hints. Put longer explanations in expandable Help sections. Automatically collapse empty inspector content on narrow windows, with a clear way to reopen it.

Keep the anatomical plane, section identity, active tool, and primary next action visible. Focus should be useful for inspection; it should not be required just to fit the application. **Success measure:** ordinary registration remains usable on a laptop display without repeated panel dragging.

### U5. Make saving follow familiar document conventions

**Priority: high.** Save currently opens a file dialog on every invocation; successful saves set `current_project_path` but the save dialog starts from `save_path`. Add ordinary **Save** to the current project, explicit **Save As**, and **Save portable copy** that leaves the original document active. The current portable UI label says “copy,” while its save path updates the active project.

Add a bounded recovery autosave separate from the user's canonical project, with a visible recovery timestamp and a clear restore choice after interruption. Preserve atomic saves and streaming attachments. **Success measure:** repeated Ctrl/Cmd+S needs no location decision, and users can explain which file they are editing after exporting a portable copy. [Save implementation](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L9056), [V2 save wrapper](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/shell.py#L850).

### U6. Keep warnings and export outcomes available after success

**Priority: high.** Introduce a session activity panel with copyable details and a persistent issue count. A later success message must not erase warnings about omitted originals, skipped sections, or incomplete exports. Export all already collects notes; build on that by writing a manifest/summary beside the exported files and offering **Open folder**.

Show an export preflight listing current, stale, unreviewed, and unbuilt items. Allow deliberate export of stale work with explicit status metadata rather than obscuring its state. **Success measure:** someone receiving the export can identify omissions and result status without access to the originating session. [Message handling](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/shell.py#L386), [export implementation](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L8111).

### U7. Make long operations understandable and recoverable

**Priority: medium.** Show named stages—download, verify, convert, build meshes, save—and useful byte or region counts. Provide safe cancellation where the implementation supports it, retry for a failed file, and an explicit resume/restart decision for interrupted processing. Consider opening 2D atlas views before optional mesh generation completes, if cache integrity can be preserved.

Background execution already keeps several operations responsive; the remaining need is control and recovery. Avoid presenting an unqualified percentage when the total work is unknown. **Success measure:** a failed atlas download can be repaired without redoing verified files, and users know whether an operation is running, cancelling, or finished. [Rat dialog](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/rat_download_dialog.py), [background runner](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/background.py).

### U8. Support adding a collection of sections in one operation

**Priority: medium.** Add multi-file selection, an import queue, natural filename ordering, and a preview of names/page/scene selections. Let users explicitly add selected TIFF pages as separate retained sections. Offer opt-in reuse of display settings and registration-channel choices; do not silently copy landmarks or anatomical placement.

The current Add section path uses a single-file chooser despite creating an unused `ExistingFiles` dialog. **Success measure:** importing ten sections takes one selection step and preserves each section's source identity. [Image loading](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/app.py#L7460).

### U9. Make registration review a visual task

**Priority: medium.** Add blink/checkerboard comparison, linked zoom/pan, and a short review checklist covering hemisphere, internal anatomy, boundaries, and cropped tissue. Provide a direct route from a landmark row to both image locations, building on the existing Centre on pair control.

Explain why a suggestion is uncertain and expose the relevant evidence rather than emphasizing a numerical score alone. Confidence is a heuristic, not a calibrated probability of anatomical correctness; the existing guide says its thresholds come from atlas-cut sections. **Success measure:** users detect a deliberate mirror error and a wrong-depth match before marking review complete. [Registration panel](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/register_panel.py), [matching implementation](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/atlas_matching.py).

### U10. Make channel controls easier to interpret without removing their distinctions

**Priority: medium.** Keep Show, Adjust, and Register separate—they serve different purposes—but make the active adjustment targets unmistakable. Add channel-selection presets, a compact all/none control, visible color names, and an in-place registration-input preview. Preserve user intent when the Adjust selection stops following Show.

Retain the explicit pixel-size source and make uncertainty visible during matching. Do not couple analysis channels to display brightness. **Success measure:** users can hide a channel while still using it for registration and can predict which channels a brightness change will affect. [Section panel](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/section_panel.py).

### U11. Make undo predictable across marks, mappings, and builds

**Priority: medium.** The application exposes ordinary Undo and a separate Undo mapping step shortcut. Make the scope visible at the point of action and provide an activity/history view showing what will be undone. Display when a section switch or an oversized operation clears history. Consider a unified command history later, after coverage across all mutation types is established.

Deletion dialogs should name affected sections, objects, and retained contributions rather than only object counts. **Success measure:** users can undo a misplaced point, a mapping, and a build correctly on the first attempt, and understand when an action is outside available history. [Undo help](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/widgets.py#L269), [transaction history](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/transactions.py).

### U12. Improve first-run guidance and verify accessibility with users

**Priority: medium.** Extend the existing empty-state actions into three clear starting paths: **Map histology**, **Plan a probe**, and **Open a project**. Offer a small bundled example that reaches a reviewed, exported result. Distinguish loading a processed atlas folder from downloading or processing one, and make both rat choices discoverable from the start.

Test keyboard-only completion, visible focus, meaningful accessible control names, text scaling, and long names in both themes. Keep a task-based V2 guide prominent; the manual currently introduces the classic interface before its V2 subsection. **Success measure:** new users finish the example without assistance, and experienced users can complete the same sequence with the keyboard. Record observed task times and errors instead of assuming the redesign improved usability. [Empty-state UI](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/driftlessmap/v2/shell.py#L325), [manual](https://github.com/mohebi-n-associates/DriftlessMap/blob/5305b1d78efcf1077dc2333e87d04aceabac3e18/MANUAL.md).

### Recommended delivery order

1. **Correct scientific identity and ownership:** B1, B2, B4, B5. Add regression cases that cross section/page/atlas transitions and inspect exported status.
2. **Restore complete core workflows:** B3 and B6; verify fresh rat atlas → probe build → coordinate export, and shared-build section removal.
3. **Make failures and incompleteness visible:** B7–B10, then U5/U6. Retain the rat-atlas fix now present in the 2.5.1 checkout.
4. **Reduce everyday effort:** U1–U4, then U7–U12, validating each change with representative users and real data.

Before closing the review, exercise clean native Windows and macOS installations end to end, copied real legacy projects, and representative brightfield/fluorescence/CZI/OME-TIFF data. Compare coordinates, labels, contacts, and exports against independently checked expectations with declared tolerances. The small digest benchmark measured about **23 ms for 6 MiB** and **102 ms for 192 MiB**, but excludes GUI latency, full project memory, warping, and save/reopen time; it does not close the outstanding performance gate.
