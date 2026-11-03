# Update Log

### 3rd November 2026
##### 2.6.0: usability, U2 (one annotation pipeline)

Review U2. `v2.state.annotation_pipeline(engine)` reports, for cells, expression, contours and drawings, which kinds are marked on the section, mapped (atlas marks not made into parts), in parts and built, the review state and the next step (mark, map, parts, build, inspect). The Annotate card "Map annotations to atlas" lists the stages (✓ done, → next) and one primary button does the next step for every kind waiting at it: map (switching on the section → atlas warp preview first, as probes do), make parts, build, or open Results. Review registration opens the Register step; the separate Map to atlas / Mark reviewed buttons are replaced, and the individual Make parts / Build / Edit parts buttons stay. Test: cells and a contour go from section marks to two built objects with the one button, starting without a warp preview.

### 3rd November 2026
##### 2.6.0: usability, U3 (repair out-of-date results)

Review U3. Results' Selected object card lists the object's contributions (`DriftlessMap.object_contributions`: record and status per unit, in section order) with each section's status and review, replacing the session-level "Last mapping…" sentence. For an out-of-date object (`stale_contribution`: the first stale unit) it shows Open <section> (section bar), Review registration (opens the section, then Register), Update mapping (`ProbeBook.update_section`, then `make_pieces_of` for cells, drawings, contours and expression) and Build again (implant `build_implant`, probe `ProbeBook.build`, other built kinds: unmerge, then merge, which leaves superseded parts out). Tests: a two-section fiber repaired from the Results card (open, update to revision 2, build, current); built cells repaired on the open section.

### 3rd November 2026
##### 2.6.0: usability, U1 (section bar)

From `reviews/2.5.0/REPORT.md` U1. `v2/section_bar.SectionBar` under the canvas header: "n/N · name" list of the book's sections, ◀ ▶ and commands `section.previous` / `section.next` (Ctrl+PgUp / Ctrl+PgDown), and the shown part of a multi-part file (`selection_text` of `ImageView.source_selection`). Switching calls `engine.switch_section` and keeps the current step (previously only Project > Sections switched). Hidden until a section is loaded. Annotate's note and stored-section out-of-date reasons now point to the bar. The canvas plane label takes the free header space. Test: two sections, the bar lists both, previous/next and choosing switch while the Register step stays open.

### 3rd November 2026
##### DriftlessMap 2.5.8

Review B10, U5 and U6. B10: measured each step panel's content minimum against its column: at 1280 × 800 and 1100 × 700 only Annotate overflowed (content 498 px in a 400 px viewport, horizontal scrolling off): the Implants card's state label did not wrap (444 px), its four action buttons (366 px) and the Mapped marks buttons (380 px, the third added in 2.4.4) were single rows. The label wraps and both rows are 2 × 2 grids (content 289 px). At 1100 px the rail, 410 px panel, views and 280 px inspector exceeded the window, so the views overlapped the panel and the view buttons were cut to "Co…re"; below `COMPACT_WIDTH` (1360) the inspector folds away with a message and returns when widened, unless shown or hidden by hand; the view-context label yields its width first. With a four-channel image the Section step needs 379 of 400 px. Test: at the minimum window every step's content fits its column and every view button its label (fails without the change: 498 > 400; Compare 53 < 94 px); folding and unfolding the inspector. U5: `project.save` writes to `current_project_path` without a dialog (asks only for a new project), new `project.save_as` (Ctrl+Shift+S) asks and starts in the open project's folder, and the portable copy is written `as_copy` (it used to become the open project; its shortcut moved to Save as). U6: every shell message is kept (`activity`, last 500); warnings and errors since last viewed are counted on a status-bar button that opens a copyable list (`session.messages`); the save no longer replaces the engine's message (with its notes) by "Project saved.". Test: new project asks once, then Save does not; Save as changes the file; the portable copy leaves it; a warning stays listed after a later message. Version 2.5.8.

### 3rd November 2026
##### DriftlessMap 2.5.7

Probe-planning bugs found while redoing the probe tutorials. (1) Four shanks, Left/Right face: `multi_shanks_btn_clicked` moved the shank offsets from probe-frame x to y for faces 2/3, and `get_center_lines` rotates the probe frame by the face again, so the two swaps cancelled and the parts were made in the view plane (measured on Allen 10 µm page 579: Left face, four parts at ML 92.5-167.5 voxels, same AP) while the preview (y offsets) showed one line. The offsets now stay in x; the parts lie 250 µm apart along AP (same ML 130, AP −162.5 to −237.5 voxels). `get_pre_multi_shank_vis_base` now takes the face and uses `shank_plane_offsets`, the same mapping as `get_center_lines` (it ignored the face, mirroring custom layouts for In). Test: for all four faces the preview's in-plane offsets equal the parts' offsets along the view, and out-of-plane shanks are not drawn. (2) Re-planning: `ProbeBook._add_section` in planning mode now deletes the probe's earlier part and build after the new part is made (it gave two parts; build failed with "a pre-surgery plan can be merged from only one piece"). (3) `load_image` showed the after-surgery face box without setting `site_face` from it (a planning Left stayed index 2 under "Up"). (4) `site_face_changed` cleared the drawing but not the planned points; in planning mode it now clears both, after surgery it redraws. (5) Selecting Linear-silicon copied the previous type's geometry and kept it valid; it is now invalid until the designer is accepted. (6) A probe type's built-in shank layout (`multi_layout_from_type`) is no longer kept for a type without one. Real checks with the probe-tutorial repro scripts on Allen 10 µm: re-planning replaces and builds; the face box and `site_face` agree after loading 1108-pfc-1. Tests: preview/parts agreement, re-planning (probe book), and an engine test for face clearing, Linear-silicon, layout carry-over and face after loading (fails without the change). Version 2.5.7.

### 3rd November 2026
##### DriftlessMap 2.5.6

Review B8 and landmark determinism. B8: `sections_for_save` noted a changed stored-section source and, for a portable copy, packed nothing for it, while the open section's changed source refused the portable save; the note was then replaced by "Project saved successfully" (review probe). A changed stored source now raises for a portable save ("the original image of <name> changed after it was loaded, so it cannot be packed as its original…"), and the final save message keeps every note (reminder colour). Test: a stored section's file changed → portable refused naming it, no file written; normal save names the note; original deleted → portable saved with the omission named (fails without the change: the portable save succeeded). Determinism (found while redoing the registration tutorial): `propose_landmarks` on 1108-pfc-1 gave 3 different results in 3 runs (overlap 0.9617-0.9626, different landmarks). SimpleITK multithreading: a fixed 4 or 8 threads, per-method `SetNumberOfThreads(1)` or one thread around the affine stage still varied; one global ITK thread around the B-spline fits gave identical results (10 of 10 runs in three processes, overlap 0.961621), 10.2 s instead of 4.4 s; running the three single-threaded fits in parallel Python threads was 4.4 s but varied in 2 of 6 runs, so they run in turn (`_single_itk_thread` restores the setting). Test: two proposals on the same synthetic section are identical and the global thread count is restored. Version 2.5.6.

### 3rd November 2026
##### DriftlessMap 2.5.5

Review B2. `load_volume_atlas` replaced the document's atlas without regard to existing results, and export provenance came from the atlas now loaded (review probe: a two-section fiber built on a 25 µm atlas reported current, with the replacement atlas's checksum and 50 µm voxels). New `has_atlas_results` (mapping records, objects, or landmarks on any section, stored ones by their summary) and `atlas_replacement_problem`: with results, a different folder is accepted only if its identity files have the same sizes and `references_match(describe_atlas_path(...))` (relocated copy); the same folder with an unchanged stat signature is accepted at once. Otherwise the load is refused before anything is read, with the reason and the way to start a new project. Project loading passes `replacing_document=True`. V2: File > New window (Ctrl+N, `project.new_window`) starts a fresh process. Measured: hashing both atlases when sizes match takes up to 7.3 s (Allen 10 µm, 13.3 GB of identity files) + 3.0 s (SWC, 5.5 GB); different sizes are refused without hashing. Real check: the saved 1108-pfc project (Allen 10 µm) refused the SWC rat atlas at once and kept its atlas. Test: a different 50 µm atlas is refused and the export provenance keeps 25 µm; the same atlas and an identical copy load; a project still opens over a document with results. Version 2.5.5.

### 3rd November 2026
##### DriftlessMap 2.5.4

Review B4 and B5. B4: the long-lived `OutlineEditor` kept a draft (mode and vertices) across a section switch and `_store` wrote it to whichever section was open (review probe: B's four vertices became A's outline). The editor now records the section its draft belongs to; `follow_section()` (called on refresh, click, finish and mode changes) parks an unfinished outline in `drafts[section]` and stops editing when the open section changed, and `ImplantCard.refresh` resumes the open section's parked draft. `leave_state` saves the draft with its `section_id` and the parked drafts; `resume` restores each only to its section (older states without a section are the open section's). Test (V2 shell): a draft on section two is not finished or clicked onto section one, is listed under section two, resumes and closes on section two only. B5: `image_page_changed` swapped the raster without changing the fingerprint, which held the image shape but not the page (review probe: page mean 180 → 40, same fingerprint, still reviewed). `image_reader.source_selection(n_pages, page, n_scenes, scene, planes)` gives the shown page, scene and fixed planes, or None for a single image; `registration_fingerprint(source=)` includes it only when set, so single-image fingerprints are unchanged (test). The selection is saved in `source_metadata`; `EmbeddedImageReader` carries it, and projects before 2.5.4 derive it from the saved page, scene and planes, so opening from the embedded raster keeps the review. Mapping a new page still replaces the section's earlier mapping of that kind (adding pages as separate sections is planned with U8). Test: on a two-page TIFF the review and mapping go out of date on page change, current again on return, and stay current when reopened with the TIFF deleted (fails without the change). Version 2.5.4.

### 3rd November 2026
##### DriftlessMap 2.5.3

Review B1. `MappingRecord.status` returned OTHER_SECTION (counted current) for every record of a section that is not open, on the assumption that a section no longer loaded cannot change; with retained, editable sections that hid stale results (review probe: current → registration changed → current on switching; no export note). `section_summary` now stores the open section's `current_registration_fingerprint()` in the summary kept with it when it is put away (saved with the stored section; validated on load as 64 hex digits, else unknown), and `status` / `derivation_status` take `stored` (section → fingerprint, `stored_registrations`): a record whose section's stored fingerprint differs from the record's is REGISTRATION_CHANGED. Unknown (sections saved before 2.5.3, removed sections kept as results) remains OTHER_SECTION. `out_of_date_reason` adds "open <section> (Project > Sections)" for a stored section. No schema change (the summary is free-form and optional). Tests: a fiber over two sections with pfc-2's page changed stays out of date after switching to pfc-1, in Export all results, and after saving and opening with pfc-1 open; updating pfc-2's mapping and building again makes it current in both sections (the test fails without the change: "current" instead of "registration changed"); record and derivation status with stored fingerprints; summary validation. Version 2.5.3.

### 3rd November 2026
##### DriftlessMap 2.5.2

First fixes from `reviews/2.5.0/REPORT.md` (B6, B7, B9). B6: `remove_section(delete_results=True)` deleted every object whose derivation named the section, including built objects holding other sections' parts (review probe: a two-section fiber left no parts, and building failed with "Map Fiber 1 on at least one section first"); it now calls `_delete_results_of` per unit (take the build apart, delete only that unit's parts), forgets the records, and clears the mapping undo history (its steps can refer to the removed section). Test: a three-section fiber, removing one leaves two parts and builds from two sections. B7: the V2 rat dialog's `_verified` compared the manifest's remembered checksum, not the file (review probe: replaced bytes passed); `AtlasDownloader.matching_files` now hashes each file (`download_utils.file_sha256`, off the GUI thread, cached by size and mtime) for reuse and before processing in both interfaces. Real Waxholm folder (952 MB): 0.6 s, then cached. Tests: wrong bytes under a correct manifest are rejected, a file changed after checking is hashed again, the classic dialog refuses to process an altered archive. B9: Escape calls `reject()`, which skipped the `closeEvent` guard; `reject()` now refuses while `busy()` (rat dialogs and Allen), and processing failures still close because they clear `continue_process` first. Test: Escape on each dialog while busy keeps it open; when idle it closes. Version 2.5.2.

### 3rd November 2026
##### DriftlessMap 2.5.1

Found while redoing the tutorials with real runs in the 2.0 interface. (1) Rat atlases: `WorkerProcessData` (Waxholm, and in 2.5.0 SWC) never wrote `atlas_axis_info.pkl`, so `get_probe_atlas_metadata` refused probe builds ("The atlas has no axis metadata") and external cell points refused to load; HERBS shipped the file separately (`Extra_Data`). The worker now writes `rat_atlases.waxholm_axis_info` (identity transpose, no flips, size), which is what the Atlas Processor derives for RAS axes (test). Verified by reprocessing the SWC download (21.5 min): the file is written and a Neuropixels 1.0 plan builds (it stopped before). The file is part of the atlas identity, so folders processed before must be processed again (documented). (2) Slice atlas: `crop_slice` / `process_slice` added the `atlas-slice` layer with the default Overlay composition, which is black on the black base; it now gets Plus like `img-process` (`CHANNEL_LAYERS`). (3) Atlas Processor: masks went through a plain shape comparison, so the 4-D single-frame Waxholm mask was refused; it now uses `prepare_atlas_mask` (test with a 12³ volume and a 12³×1 mask through the worker). Tutorials: all rewritten for 2.0 with screenshots from real runs of 2.5.0 (registration on 1108-pfc-1 with Allen 10 µm; probes on Allen 10 µm; slice atlas with a plate rendered from Waxholm v4.01 page 589; Atlas Processor run on the WHS v4.01 files, 35 min, output identical to the built-in download; 125 synthetic cell points in WHS space); install guides rewritten around current commands and their HERBS-era Anaconda/PyCharm screenshots removed; the index lists every tutorial. Bugs seen during the runs and not fixed here: Suggest landmarks varies between runs (SimpleITK multithreading in the B-spline stage; identical with one thread); "Not sure" plane detection can choose a plane whose upright score is below the runner-up; Annotate Lasso/Measure need a volume atlas or section, so a plate alone cannot be cropped; `.xlsx` label tables need openpyxl, which is not a dependency; replanning a planned probe adds a second part and Rebuild fails (the tutorial gives the workaround); a planning site face is kept internally but not shown after a section is loaded; the four-shank preview draws one line for Left/Right faces; changing the site face hides but keeps placed points; Linear-silicon inherits the previous type's geometry until the designer is opened; the shank layout carries over between probes. Version 2.5.1.

### 3rd November 2026
##### DriftlessMap 2.5.0

Rat atlases (`rat_atlases.py`). Waxholm: the download used the v4 annotation (2021) with a label file packaged since HERBS; NITRC's newest is v4.01 (2023-04-20: regions 504-506 added, 76 removed, 407 renamed, 6 parents changed), served only after its agreement page (CC BY 4.0, cite; the dialog shows it and requires "I agree", then requests `?i_agree=1&download_now=1`). The download is now the v4.01 MBAT zip (annotation and `.ilf` hierarchy) plus T2* and brain mask v1.01; `label_info_from_ilf` builds `atlas_labels.pkl` from the hierarchy. Compared with the packaged file it gives exactly the v4.01 changes, plus corrected `level_indicator` values (108 regions in the old file were one level deeper than their own parent chain). SWC female rat: BrainGlobe `whs_sd_swc_female_rat_39um` v1.0 (asr, 1024 × 512 × 512), converted to WHS RAS order by `brainglobe_to_whs`; the axis mapping was found by searching all 48 axis orders and flips against the WHS v4.01 annotation, and with it the SWC annotation equals WHS v4.01 at 100% of voxels where both are labelled (36.3 of 41.2 million WHS voxels are labelled in SWC; 9 regions, e.g. spinal cord, are absent); `label_info_from_brainglobe` gives the same hierarchy as the `.ilf` for its 304 regions. Both share WHS Bregma (246, 653, 440), Lambda and 39.0625 µm voxels. All files pinned by SHA-256. `AtlasDownloader(atlas=)` serves both (classic: new Atlas > Download SWC Female Rat Atlas); `WorkerProcessData.set_data(prepare=)` runs the preparation before the shared processing; V2 `RatAtlasDownloadDialog` (Terms, Folder with checksum-verified reuse, Download, Process and open). `download_utils` serialises manifest writes: parallel downloads could each overwrite the others' entries. Found while taking the screenshots: the V2 download dialogs (also the existing Allen one) opened shorter than their content, because word-wrapped hints made the layout minimum too small, so the download rows were squeezed to 2-12 px and overlapped; both now start at their full height (test checks every row gets its height). End to end on macOS through the V2 dialog: SWC downloaded in 9 s and processed in 25 min; Waxholm downloaded (950 MB) in 66 s and processed in 26 min; both load (512 × 1024 × 512; 304 and 314 regions; 216 and 223 labels present), and the same coronal page shows the same anatomy and region outlines on both templates. Tutorial *Downloading the rat atlases* with screenshots of this run; the HERBS Waxholm tutorial points to it. Tests: hierarchy reading (order, parents, levels, colours, repeats), BrainGlobe structures, axis conversion, archive unpacking and refusal, SWC conversion to NIfTI and labels, parallel manifest writes, terms gating in both dialogs, reuse of verified files, failing preparation. Version 2.5.0.

### 3rd November 2026
##### DriftlessMap 2.4.4

Removing a mapping. Found by experiment on the test atlas: Edit marks, delete every mark, map again did nothing for cells and named probes (`_transform_accept` and `ProbeBook.add_section` saw no marks) and was refused for implants ("Draw the outline… first"); the record, its part and objects built from it stayed current, and no action removed a single mapping. New `DriftlessMap.remove_mapping(unit_id)` (undoable): forgets the record, deletes its parts and its atlas marks not yet made into parts, and first takes apart (unmerges) each built object whose derivation or per-part derivation contains it (`_delete_results_of`); building again would otherwise unmerge and re-merge the removed part. `cleared_edit(kind, probe)` finds a record being edited whose marks are all deleted (an all-zero expression mask counts as empty); `_transform_accept`, `map_implant` and `ProbeBook.add_section` then remove it instead of refusing or doing nothing. V2: Remove mapping button and command; the probe and implant Map this section buttons read "Remove this section's mapping" in that state; a probe left without parts stays listed. Tests: cells built and a contour mapped, cells edited, deleted and mapped (record, part and build gone, contour untouched, undo restores), Remove mapping clears unmade atlas marks; a fiber built from two sections loses one section's outline (build taken apart, the other part current, rebuilt from one section, undo restores the two-section build, removal refused from another section); probe book removal keeps the probe. Version 2.4.4.

### 2nd November 2026
##### DriftlessMap 2.4.3

Frame fitted to the landmarks (`landmarks.fit_frame`, `DriftlessMap.fit_frame_to_landmarks`). Found on 1108-pfc-2: the frame pinned the section's corners to the atlas image corners, 217-263 px (2.2-2.6 mm) from where an affine fit of its 8 landmarks (residuals 4-14 px) puts them. Proposals carried the atlas frame into the section and clamped it to the section image, which restores the same contradiction whenever the section covers part of the slice. Each axis is now fitted by least squares (atlas = scale × section + offset; at least 3 pairs, spread ≥ 5% of the image side, positive scale); the section frame is the part of the section image inside the atlas image under the fit, and the atlas frame is its image under the fit. Applied after proposals, added, moved and deleted pairs and by Match Boundaries (bounding-rectangle matching remains for fewer pairs); never on load. Measured with the warped tissue mask (`tissue_mask`) against the atlas brain (labels ≠ 0) on the Allen 10 µm atlas: the saved pfc-2 landmarks, Dice 0.758 → 0.951, tissue outside the brain 37.6% → 2.5%, brain covered 96.5% → 92.8%; fresh proposals, pfc-1 Dice 0.700 → 0.941 (outside 45.8% → 3.9%), pfc-2 0.784 → 0.967 (34.7% → 3.5%); mesh status unchanged (review). Tests: fitting, a section larger than the atlas, too few / bunched / mirrored pairs, the frame moving on the third placed pair. Version 2.4.3.

### 2nd November 2026
##### DriftlessMap 2.4.2

Landmark dots: the toolbox colour button defaulted to pyqtgraph's gray (128, 128, 128) and the dots only took a colour when it changed; the default is now red (`toolbox.LANDMARK_COLOR`), applied to the section and atlas dots at start, and saved `triangulation_color` equal to the old gray default opens red. Region colours: new `region_colors.distinct_region_colors`, applied in `AtlasView.set_data`. On the Allen 10 µm atlas (sampled every 4 voxels, 0.9 s), 1273 touching label pairs in different areas had a CIE76 difference below 20 before (e.g. PL 47,168,80 and ILA 89,179,99); with the threshold of 30, 75 areas change and no touching pair found at that sampling is below 30; sampling every 2 voxels (6.3 s, not used) finds one more contact below it, the interpeduncular nucleus (IP) against voxels labelled only Brain (13.9); PL becomes 0,229,169 and ILA 0,158,41. Areas are a label and its same-coloured descendants, so layers keep one colour; larger areas keep theirs first. Tests: colour conversion round trip, areas, touching pairs, recolouring of a touching pair with layers, untouched regions unchanged, landmark default and old-default migration. Version 2.4.2.

### 2nd November 2026
##### DriftlessMap 2.4.1

Out-of-date objects name their reason. Found on a real export (1108-pfc-1/2, Fiber 1): the message said only "out-of-date objects: Fiber 1"; the project copy showed the 1108-pfc-2 record's registration fingerprint differed from the current one with page 972, tilt 0 and the image unchanged (no single deleted pair or frame change reproduced it), i.e. its landmarks were edited after mapping. `DriftlessMap.out_of_date_reason(index)` gives the cause per object (implant settings changed; `<section>` mapped again since; landmarks, page or tilt of `<section>` changed since mapping) with the fix; `out_of_date_lines` feeds Export all results, the single-object export message and the V2 Results status. Test: two sections mapped and built, a moved landmark names pfc-2.png in the reason and the export note, remapping pfc-1 names it, changed specs name the settings. Version 2.4.1.

### 2nd November 2026
##### DriftlessMap 2.4.0

Release of multi-section projects (phases 1-3 below) with 2.0.1-2.3.0, none of which was published on its own. Phase 4 fix: an added section started with the previous section's atlas landmarks (3 atlas points against 0 section points in the check), its atlas marks and layers and the warp preview, because loading clears only the section side (as Replace section always did); `finish_new_section` now resets the atlas landmarks, atlas layers and transforms, `working_atlas_data` and `atlas_mark_origin` for the new section (the previous section keeps them in its stored fields). End-to-end check through the V2 interface on the Allen 10 µm atlas with 1108-pfc-1 and 1108-pfc-2 (1600 × 1200 RGB brightfield, 4.4 µm): matched coronal pages 990 and 977 (3° tilt), 10 suggested pairs each, reviewed, one fiber mapped on each; reopening section 1 from the Sections card took 0.4 s with its page, pairs, review and mapping current; editing and mapping again gave revision 2 with still 2 parts; build: tip in infralimbic layer 5, ML +0.55, AP +2.17, DV 2.93 mm from atlas Bregma (the earlier one-section build of pfc-1 gave infralimbic layer 5, ML +0.41, AP +2.11); save 8.9 s, 24.3 MB; export wrote both section TIFFs, landmark CSVs and `sections.json`; reopening (17.4 s) found both originals by checksum with pages, pairs and review intact, and building again gave an identical tip. Version 2.4.0 (version.py, CITATION.cff, tests, README, MANUAL, agent guides, release_validation).

### 2nd November 2026
##### 2.4.0: multi-section projects, phase 3 (interface)

V2 Project step: the Current section card became **Sections** (list with plane and page, landmark pairs, review and mapped implants/probes/kinds; the open one bold and marked; Add section…, Open (double-click), Rename…, Move up/down, Remove… with keep/remove results; a note for mapped sections without a stored section). `section.load` is "Add section…". The Project rail status reads "section N of M: name"; Annotate's mapped list names other sections with mappings; implant rows say "built from N sections"; object tooltips name the sections their parts came from (`object_section_names`). Classic: File > Sections… (`sections_dialog.SectionsDialog`). Export all results adds `sections/`: each section's working raster as a zlib TIFF (CYX ImageJ hyperstack for uint8/uint16/float32, channel labels and pixel size from `section_pixel_size_um`), `<name>_landmarks.csv` (pair, atlas x/y, section x/y; names without the image extension) and `sections.json` (name, id, open, pixel size, channels, atlas plane/page/tilt, source path and SHA-256). Tests: Sections card (add, open, rename, order, remove keeping results, rail, Annotate note, tooltips), classic dialog, export read back bit-for-bit. Rendered offscreen with the 1108-pfc sections on the Allen 10 µm atlas.

### 2nd November 2026
##### 2.4.0: multi-section projects, phase 2 (persistence)

Project schema 4 (`PROJECT_SCHEMA_VERSION`). The open section stays at the top level; `sections` holds `schema_version` 1, `active_section_id`, `order`, `names` and `stored` (each stored section's `section_id`, name, summary and `SECTION_FIELDS` state with its embedded working raster and its own histology provenance). `sections_for_save` (in the background) fingerprints each stored section's source when it is unchanged since loading (stat signature), keeps the earlier reference otherwise, notes changed sources, and for portable copies packs each source (`portable_sources.sections`) or passes on a source packed in the opened project. `restore_sections` rebuilds the book after `load_project`, spills stored arrays, and leaves out invalid stored sections with a message (identity, fields of another section, missing raster or registration). Opening a stored section finds its source with `resolve_reference` (checksum; relocation next to the project) or extracts and verifies its packed source, else opens the saved raster. `SectionEntry.digest` caches each stored section's digest for change detection; `sections_index` is the payload's `sections`. Schemas 1-3 open as one section; `sections_without_image` lists mapped sections without a stored section. Every section's raster is embedded; linking originals instead was dropped (owner's decision), because the saved raster is the working raster after rotations, flips and crops, which a linked file cannot reproduce. Real data (Allen 10 µm atlas, IM-1076_left_All_insertion 11520 × 5990 × 4 and 1108-pfc-1): save 26 s, 162 MB; reopen 14.6 s; opening the large stored section afterwards 2.9 s. Tests: round trip of two sections through two saves, moved / changed / missing sources, portable projects with the originals deleted, schema 3 and a damaged stored section, cached digests.

### 2nd November 2026
##### 2.4.0: multi-section projects, phase 1 (engine)

Phase 1 of `multi_section_design.md`; not usable from the interface yet (phase 3) and saves keep only the open section (phase 2), so it is not released on its own. `sections.py`: `SECTION_FIELDS`, `section_fields`, `section_state`, `SectionEntry`, `SectionBook` (order, unique names, put away / add / activate / opened / remove / move, `follow_active` when the open section is read again), `SpillCache` (arrays ≥ 1 MB saved once per content, SHA-256 of dtype, shape and bytes, reopened `mmap_mode="c"`; folder removed on close, collection or exit). `section_engine.SectionsMixin`: `load_image` adds a section; `switch_section` reuses `ProjectSnapshot.restore` with the target's fields, restores its `section_id` (mapping current again; mapping again replaces its part), clears undo, and opens the embedded raster when the source is missing or its stat signature changed; `remove_section(delete_results=)`. `_restore_project_payload` takes `runtime["keep_atlas"]` to leave the volume in the views. Saving with several sections warns that only the open one is saved. Measured on the Allen 10 µm atlas with 1108-pfc-1 (1600 × 1200 RGB) and IM-1076_left_All_insertion (11520 × 5990 × 4, 276 MB): a switch takes 0.3 s to the small section and 2.5 s to the large one (reading its TIFF; first put-away of the large one adds about 1 s for the cache file, 282 MB); memory stays flat over eight switches. Found on the way and not fixed here: `set_volume_atlas_to_view` keeps about 400 MB per call (seen through `ProjectSnapshot.restore`, used when opening a project fails and is rolled back); switching no longer calls it. Tests: `tests/test_sections.py` (book, cache, two sections switched bit-for-bit with page, landmarks and mapping; remap replaces the section's part; a failed switch restores the open section; changed source opens the saved raster; removing with results).

### 2nd November 2026
##### DriftlessMap 2.3.0

`implants.model_section(model, origin, axis_x, axis_y, shape)` returns the slice pixels inside a fitted cylinder (flat ends, radius) or block, or None when the slice misses it (plane distance test, then only the model's bounding box in slice pixels is evaluated). `implant_overlay.ImplantOverlay` (created with `AtlasView`, both interfaces) maps each atlas view's slice with `get_coronal_3d` / `get_sagittal_3d` / `get_horizontal_3d` (so tilts match the mapped outlines) and draws `cv2.findContours` outlines as `QGraphicsPolygonItem`s (implant colour, 70/255 fill, z 50) for visible built implants; it redraws on page and tilt signals and checks every 400 ms for builds, deletions, undo and visibility. `ImplantEngineMixin.show_implant_on_atlas` sets the three pages through the model's bottom point; V2 implant card **Show on atlas**. Before, built implants were drawn in 3D only. Version 2.3.0 (feature).

### 2nd November 2026
##### DriftlessMap 2.2.0

`V2Window.toggle_focus` / `is_focused` / `_sync_focus`; command `view.focus` ("Focus on images (hide side panels)", Ctrl+Shift+F, palette synonyms full screen, hide panels, maximise); header `focus_button` and checkable View menu `focus_item`. Focus sets the existing View items `toggle_task_item` and `toggle_inspector_item`, so hiding both by hand also counts as focus; the view splitter is re-balanced after the layout pass. Not saved with the project. Version 2.2.0 (feature).

### 2nd November 2026
##### DriftlessMap 2.1.2

`PhysicalSection.measure` multiplies the template-edge and label-edge agreements by the coverage (section tissue inside the slice's brain ÷ section tissue). Cause: the combined score adds z-scores of outline, template-edge and label-edge agreement; a sagittal slice near the lateral edge (page 1086, 2,102 brain voxels against ~700,000) had outline 0.00 but template agreement 0.43-0.55 over its few overlapping pixels, and won. Reported case (IM-1076_left_All_insertion.tif, channel 1, 1.633 µm, Allen 10 µm, midline 570): before, 1086 (5.16 mm), 589, 595, 580; after, 605, 587, 594, 625 (0.17-0.55 mm). Atlas-cut sections (DAPI-like stain, 1.5 × 1.275 resampling, 0 or 35 % ventral removed), error before → after: sagittal 620: 4660 → 190 and 4650 → 330 µm; 750: 310 → 310 and 260 → 260; 900: 1860 → 170 and 1860 → 1210; 1030: 30 → 30 and 0 → 0; coronal 500/800/1100: unchanged (0-60 µm). Sagittal errors remain larger than coronal and are rated low. `confidence_points` (0-100: `_points` maps each criterion so its fair threshold is 50 and confident 80; weakest wins; unknown size 79) and `_criteria`, shared with `confidence`, whose levels are unchanged. The dialog shows "confidence: level (N/100)" on its own line and explains the scale in the tooltip. Version 2.1.2.

### 2nd November 2026
##### DriftlessMap 2.1.1

`v2/widgets.keys(sequence)` (native shortcut text) and `undo_help()` (point, step and edit-marks sentences). `ProbeControls`: tooltips on Mark track, the point count, Map this section and Build, plus `undo_note` under the buttons. `ImplantCard`: Delete…, Map this section (also when `refresh` sets the tooltip) and Build. Test: three probe clicks, Undo twice leaves the first point, Redo restores the second. Version 2.1.1.

### 2nd November 2026
##### DriftlessMap 2.1.0

`v2/state.sagittal_hemisphere(engine)` returns (`sagittal_side`, mm from `origin_3d[0]` × `vox_size_um`) for the sagittal page shown, or None; `plane_summary` adds "right/left hemisphere N mm" or "midline". `MatchPanel` gets a hemisphere status row (visible only for sagittal) and **Other hemisphere** (`mirrored_index`, clamped to the slider range). `atlas_matching.hemisphere_from_name` reads a single whole word "left" or "right" from the file name; when it disagrees with the page shown the row warns. Reported case: IM-1076_left_All_insertion.tif applied at sagittal page 581, which the readout names as the right hemisphere when the midline page is below 581 (about 570 in a 1140-page atlas; not checked against the user's atlas). Version 2.1.0 (a feature, per the 2.N.0 rule).

### 2nd November 2026
##### DriftlessMap 2.0.2

`v2/shell.V2Window`: `_visible_views()` (visible frames of `engine.splitter_3`), `_balance_views()` records `_balanced_views`, and `refresh()` calls `_balance_if_views_changed()`, which balances one event-loop pass later (`QTimer.singleShot(0)`) when the visible set changed; `set_view` also balances again after layout. Cause: the engine switches to atlas + section by itself on loading (`show_2_windows`), and the splitter kept the histology frame at the width it had while hidden (50 px in the report, 0 px with fresh settings); sizes set in the same pass as a frame is shown are ignored. Widths the user drags are kept until the visible set changes. `image_reader.color_name`, `channel_names_from_colors`: TIFF channels without names but with stored colours (ImageJ `LUTs`, OME `Color`) are named after the colour's hue (repeated colours numbered, "Green 2"); `_ome_channels` returns no names when no channel has a `Name`. The reported file (ImageJ 1.54p composite, LUT ends (0,107,255), (25,255,0), (255,157,0), (234,0,0), no `Labels`) was named Gray, Red, Green, Blue; now Blue, Green, Orange, Red. Files with neither names nor colours keep `CHANNEL_NAMES`. Version 2.0.2.

### 2nd November 2026
##### DriftlessMap 2.0.1

`v2/section_panel.SectionPanel`: the per-row radio button (`select_group`, one `_selected` channel, default 0) is replaced by an **Adjust** checkbox per row (`_adjusted` list). `_adjusted` follows `channel_visible` while `_adjust_follows_show` (reset when `id(image_file)` changes, not on rename); ticking or `_select(i)` makes it the user's choice; the last ticked row cannot be unticked. `_bc_changed(kind)` moves brightness or contrast per channel, keeping that channel's other value; `_range_changed(kind)` sets only the edited Min, Max or Gamma on each; Auto and Reset use each channel's own range (`_apply_each`). The title names the adjusted channels, marks hidden ones, and says whose values are shown when they differ. The reported case: an RGB PNG with only Green shown adjusted Red. `shell.WINDOW_LABEL` is "DriftlessMap <version>" and the rail shows the version (was "2.0 preview (development build of …)"); the application display name is "DriftlessMap" (the application name, which keys V2 preferences, is unchanged); `python -m driftlessmap.v2 --version` prints "<version> (2.0 interface)". The manual says "2.0 interface" instead of "2.0 preview". Version 2.0.1 in `version.py`, `CITATION.cff` (2026-11-02), tests, README, MANUAL and the agent guides.

### 29th October 2026
##### DriftlessMap 2.0.0

Stable release of 2.0.0rc16 with no code changes: version 2.0.0 in `version.py`, `CITATION.cff` (dated 2026-10-29) and tests; README, MANUAL, guides and `release_validation.md` describe 2.0.0 as current and install without `--pre`. The automatic-matching tutorial describes the 2.0 steps (section plane, registration channels, pixel size, real-size placement, confidence, side choice); its screenshots are still from 1.6. The manual's step table and suggestion-dialog description mention pixel size and tissue size. Released at the owner's request with all `release_validation.md` gates pending; the waiver is recorded there. `CookBook.pdf` (HERBS) deleted (still in Git history) and dropped from README, MANUAL and the CI path filters. Credits: package metadata, `CITATION.cff`, `AUTHOR.txt`, `CONTRIBUTORS.md` and the About dialog list the DriftlessMap team as authors; the HERBS developers are acknowledged. `ORIGINS.md` is now the HERBS legacy note (connection, publication, licensing, compatibility names, legacy material); README and MANUAL point to it instead of repeating it. The README no longer asks for the HERBS paper to be cited; `CITATION.cff` still lists it under references.

### 29th October 2026
##### DriftlessMap 2.0.0rc16

`atlas_matching.PhysicalSection` (section resampled to the search voxel size, or sized to each slice's width without a pixel size) and `place`: coarse grid of `FIT_SCALES` × `FIT_STRETCHES` at half resolution (outline distance capped at `COARSE_REACH_UM` 450 µm), then coordinate refinement within `FIT_LIMITS` (scale 0.9–1.5, stretch 0.8–1.3, ±10°); translation by `cv2.matchTemplate` of the capped distance to the atlas outline (`OUTLINE_REACH_UM` 180 µm) per outline pixel plus `OUTSIDE_WEIGHT` 3 × tissue share outside the brain. Outline agreement = 1 − cost. `NormalisedSection` wraps the old comparison; `rank_depths`/`refine_tilt`/`_refine_page` take `section=` (pass 2 and page refinement refined; tilts keep the depth's fit and re-place only). `suggest_sections(voxel_um=, pixel_um=)`; `Suggestion.fit_scale`, `SuggestionReport.size_known` (False caps confidence at medium). App asks for a missing pixel size (`ImageView.pixel_size_declined`). Whole pipeline on Allen 10 µm coronal pages 500/800/1100 cut from the atlas, DAPI-like random-region stain, tissue at 100 % and 80 %, 0 or 35 % ventral removed: known size ≤ 110 µm, unknown size ≤ 40 µm, old ≤ 5240 µm (35 % cut: 140–5240). Time 14–27 s (old 5–7 s). Confidence was mostly low/medium on these re-stained sections because template agreement is low by construction. User's IM-1109 sections need ~1.3× enlargement (about 24 % shrinkage) to fit; 01 fits no page closely (outline cost ≈ 0.73).

### 29th October 2026
##### DriftlessMap 2.0.0rc15

`image_reader.tiff_pixel_size_um` reads OME `PhysicalSizeX` (+unit), ImageJ resolution with its `unit`, centimetre resolution, and inch resolution only below 20 µm (`PIXEL_SIZE_RANGE_UM` 0.01–1000 via `valid_pixel_size`); `TIFFReader` and TIFF folders set `scaling_val`. `ImageView.pixel_size_override` (optional `img_ctrl_data['pixel_size_um']`, None in older files), `full_resolution_pixel_size()`, `pixel_size_um()` (÷ read scale), `set_pixel_size`. `scale_bar.ScaleBar` (pyqtgraph ScaleBar picking 1/2/5×10ⁿ µm ≈ 1/5 of the view width) on `ImageStacks`, `SliceStacks` and `SliceStack`. New `actionPixel_Size`, `DriftlessMap.ask_pixel_size`, `pixel_size_dialog.PixelSizeDialog`, `user_settings.load/save_last_pixel_size`; V2 Section step pixel-size row. The user's IM-1109/IM_1112 TIFFs read 1.634 µm. Ruler uses `pixel_size_um()`.

### 28th October 2026
##### DriftlessMap 2.0.0rc14

`atlas_matching.confidence(suggestion, report, voxel_um)` returns (level, reasons): the minimum of template-edge agreement (`CONFIDENT_ANATOMY` 0.5, `FAIR_ANATOMY` 0.3), the span of depths within `DEPTH_TIE` (1.0 z) of the best in the every-few-pages pass (`SuggestionReport.depth_span`, ≤ 500 µm high, ≤ 1000 µm medium) and the plane margin when the plane was detected. `Suggestion.template_edges` and `SuggestionReport.depth_span` are new (defaulted). Thresholds measured on Allen 10 µm coronal pages 450–1100 cut from the atlas (flattened 15 %, noise): agreement 0.60–0.95, span ≤ 360 µm, depth error ≤ 60 µm; the user's two fluorescence sections: 0.09–0.19, rated low. The dialog no longer calls a plane the user chose "clear".

### 28th October 2026
##### DriftlessMap 2.0.0rc13

`auto_registration._bspline_on_intensities` fits the B-spline once per `BSPLINE_SAMPLINGS` (1.0, 0.9, 1.12: the moving image linearly resampled, `_resampled`) and combines the fits per control point: mean displacement × clip(1 − spread / (`BSPLINE_AGREEMENT` 0.05 × control spacing)), spread = largest distance of a fit from the mean. The keep test (MI improved, Dice drop ≤ 0.03) applies to the combined transform. A single fit's optimum moved with the analysis size: over `ANALYSIS_MAX_SIDE` 1700–2500 (10 sizes) a grid of atlas points on the user's sagittal section spread by up to 982 section pixels (median 339); now 7 (median 5). Coronal IM-1109 04: 4 → 4; 01: 5 → 56 at one size (2300), ≤ 18 elsewhere, as the keep decision now has little effect. Synthetic warp, 8 seeds: median error 2.42 px mean, 2.91 worst (was 2.74 / 2.82). Two fits left one coronal section unstable (up to 691 px); a 7 % tolerance gave up to 198 px. B-spline time roughly triples (sagittal action 3 s → 7.5 s).

### 28th October 2026
##### DriftlessMap 2.0.0rc12

`LayersControl.add_layer` gave every new layer `DEFAULT_BLEND_MODE` (Overlay) and emitted it; for `img-process` `layers_blend_mode_changed` applies the mode to the histology channel items, and Overlay over the black base layer renders black (inherited from HERBS). `CHANNEL_LAYERS` now starts `img-process` in Plus. Blend modes are not saved in projects, so no migration. Reproduced and verified on the user's 3-channel IM-1109 TIFF (view grab black before, section visible after) for crop and Process Image.

### 28th October 2026
##### DriftlessMap 2.0.0rc11

Channel `ImageItem`s in `image_stacks.ImageStacks` use `setAutoDownsample(True)`: `makeARGB` LUT application on the full 24.8 Mpx raster dominated each display change (0.57 s → 0.055 s per brightness step, measured through `SectionPanel.brightness` on the user's IM-1109 TIFF). Channels 5–16 now also use `CompositionMode_Plus` (only 1–4 did).

### 28th October 2026
##### DriftlessMap 2.0.0rc10

New `file_dialogs` module wraps `QFileDialog.getOpenFileName(s)`, `getSaveFileName` and `getExistingDirectory` for all 32 call sites: a start directory that is empty, the home folder or missing is replaced by the last chosen folder (a suggested file name is kept), and every choice is remembered. `user_settings.update_settings` merges keys (`save_last_atlas_path` used to overwrite the file), with `load_last_folder`/`save_last_folder`; settings schema stays 1. Tests use `tests/settings_isolation.py` (temporary `DRIFTLESSMAP_CONFIG_DIR`).

### 28th October 2026
##### DriftlessMap 2.0.0rc9

`sig_label_changed`'s mesh logic is replaced by `sync_region_meshes`: mesh keys are strings and the tree's checked ids ints, so the second pass never matched; regions checked before enabling were not shown and disabling hid nothing. `show_small_area_in_3d(visible)` takes the button state and syncs. V2 had no control for `show_child_mesh` (default False), so checked regions never appeared in 3D; the Regions tab has a "Show checked regions in 3D" check box, on by default.

### 28th October 2026
##### DriftlessMap 2.0.0rc8

`persistence._fsync_file` opened the temporary archive read-only before `os.fsync`; Windows' `_commit` rejects read-only handles with EBADF, so every `save_driftlessmap_file` (projects, layers, objects, Export all results) failed on Windows since atomic saves gained the flush. It now opens the file `r+b` and treats a failing flush as best effort (some network/removable drives cannot flush; `os.replace` stays atomic). `switch_3d_display_mode` referred to `actionMode_Dark` instead of `action3D_Mode_Dark` (AttributeError on every 3D mode switch).

### 28th October 2026
##### DriftlessMap 2.0.0rc7

Mark displays now follow their data: `_transform_accept` redraws each mapped kind with `_show_section_marks` (the 1.x transfer cleared `working_img_data` but left the plot items and layer thumbnails), `_make_pieces_of` calls `_show_atlas_marks` after the maker cleared the atlas marks, and `_show_section_marks` clears the item/layer (`_clear_section_item`) and the probe trajectory when a kind is empty. New `clear_live_marks(kind)`; `ProbeControls.delete_probe` uses it for the selected probe's unmapped marks.

### 28th October 2026
##### DriftlessMap 2.0.0rc6

`auto_registration.propose_landmarks` analyses sections larger than `ANALYSIS_MAX_SIDE` (2048) on an INTER_AREA copy (`_analysis_copy`); the moving images keep physical space in section pixels (spacing × factor), outline contours and mask lookups are scaled, and `_section_in_atlas` takes the factor. Affine results agree with full-resolution analysis within 8.5 section pixels on the user's sagittal section; small sections are unchanged. `registration_input.prepare` takes percentiles from an evenly spaced grid of about `PERCENTILE_SAMPLE` (4 M) pixels and averages channels in place. Whole action on an 11520×5990×3 section: 5.8 s → 2.2 s (macOS), peak memory several GB lower. Known: the B-spline stage on real sections is sensitive to small input changes (its keep/reject decision flips); not changed here.

### 28th October 2026
##### DriftlessMap 2.0.0rc5

`registration_section` runs `registration_input.prepare` (per-channel percentiles of the full raster, several seconds on an 11520×5990×3 section) through `run_in_background` instead of on the GUI thread before the progress dialog. `run_in_background` shows its dialog after 150 ms (was 400). V2 `widgets.button` handlers go through `widgets.respond`: wait cursor and repaint before the handler, re-entrant clicks ignored until a modal window opens (`window_shown`, called from the shell's Show hook); when a handler held the window > 0.2 s without a modal window, press/release/key events stamped within it are dropped by the shell event filter (`respond.seen`, `PRESS_EVENTS`).

### 28th October 2026
##### DriftlessMap 2.0.0rc4

`atlas_matching.suggest_sections(..., planes=)` restricts `search_planes`; `PLANE_CHOICES`, `planes_for(choice)` and `plane_from_name(path)` (one unambiguous plane word in the file name). `DriftlessMap.suggest_atlas_section(plane=None)` asks with `ask_section_plane` (QInputDialog, preselected from `section_plane` or the file name) when no plane is given and remembers `section_plane` for the session. V2 Match step: Section plane combo (`MatchPanel.chosen_plane`), and `match.find` passes it. On the user's IM-1109 coronal DAPI/DiI/DiO section the unconstrained search preferred a lateral sagittal page (outline 0.763 vs 0.769, scale-free); constrained to coronal it returns frontal coronal pages.

### 28th October 2026
##### DriftlessMap 2.0.0rc3

Lasso closing: the image lasso compared a squared distance with 5 % of the image size (a few image pixels on large images) and the slice lasso used a squared distance < 5; both now close within `LASSO_CLOSE_PIXELS` (12) screen pixels via `layer_geometry.lasso_tolerance(view_box)`/`lasso_closes`. `lasso_points_clicked` read the slot arguments as (points, ev) and tested only `ev[0]`; pyqtgraph lists points last first, so clicking the first point of a closed or overlapping lasso hit the duplicate last point and called `inactive_lasso`. It now closes only when any clicked point has index 0 (`lasso_point_closes`) and otherwise does nothing. `cut_image`/`crop_slice` close an open lasso of ≥3 points (`close_image_lasso`/`close_slice_window_lasso`) and report when there is none.

### 28th October 2026
##### DriftlessMap 2.0.0rc2

V2 theme stylesheet is set on `V2Window` instead of `QApplication` (an application stylesheet repolished all ~2,000 widgets, including ~940 hidden menu, colour-dialog and view-menu widgets); top-level windows outside the V2 window get it on `Show` via `_theme_window` (marked `v2_theme`) and follow `apply_theme`. The application event filter compares against a precomputed `EDIT_EVENTS` set and no longer calls the base filter. Toggle time 0.50 s → 0.10 s offscreen on macOS.

### 28th October 2026
##### DriftlessMap 2.0.0rc1

Release candidate of 2.0 (previews 2.0.0a1–a27). Auto-registration's B-spline now evaluates Mattes MI on every masked pixel instead of a seeded 30 % random sample and smooths every level (`BSPLINE_SMOOTHING` = 6, 3, 1.5 px): its accuracy had depended on the sample by up to 2 section pixels, which failed Linux CI from 2.0.0a17 on (median error 4.17 vs 3.41 px on macOS). Over eight noise realisations of the synthetic warp the median error is now 2.71 px mean, 2.79 px worst (was 3.56 / 4.55). Version, citation, PyPI classifier (4 - Beta), README, manual installation (`pip install --pre`, release-candidate downloads) and release-validation status updated; no other code changes since 2.0.0a27.

### 28th October 2026
##### DriftlessMap 2.0.0a27

`interfaces.requested_interface` defaults to the 2.0 interface; `--classic` and `DRIFTLESSMAP_INTERFACE=classic` select the classic one, flags before the environment. `interface_command("classic")` passes `--classic` (bundle and `-m driftlessmap`), and `run` strips interface flags before Qt sees them.

### 28th October 2026
##### DriftlessMap 2.0.0a26

Shared project collection and transactional replacement in `project_session.py`;
recovery borrows the previous atlas/raster arrays and restores mutable metadata,
original image reader and history. `state_digest.py` hashes complete saved values
with chunked array reads; V2 schedules status checks after input/commands, with
unconditional checks before closing/replacing work and conservative error handling.
Registration fingerprints version their content and include canonical triangle
connectivity; on load, `_migrate_mapping_fingerprints` restamps the loaded
section's records whose stored fingerprint equals the pre-a26 one
(`registration_fingerprint(..., simplices=legacy)`, `MappingLedger.restamp`), so
unchanged mappings stay current while reviews still lapse. Unusable probe planning
again only warns on load instead of rolling the open back. Probe rename updates stored part names and ledger owners without
changing unit IDs or revisions. Implant build status compares stored report specs
with current specs and propagates to the UI, object files and implant CSV. Undo/redo
share a bounded budget and unrecordable edits clear history. Content signatures
record same-name rebuilds; exceptions roll back retained transactions. A failed
widget recovery preserves a recovery archive and blocks partial-session saves.
Regression coverage
and a reproducible digest benchmark were added; see `release_validation.md` for
remaining native-installation, user-evaluation and performance gates.

### 28th October 2026
##### DriftlessMap 2.0.0a25

Projects store `interface_state` (optional, plain JSON via `clean_interface_state`, no schema bump) from `interface_state_provider`; `on_project_loaded` hands it to V2 `resume` (step, view, implant selection, `ProbeBook.state`, Mark track, outline draft). Unmapped probes count in the unsaved-change digest. Point layers use `layer_points` / `plot_points`: empty layers saved as `[None, None]` made `load_project` fail part-way; they now load, and empty layers save as [].

### 28th October 2026
##### DriftlessMap 2.0.0a24

Region boundaries drawn as an RGBA overlay in `BOUNDARY_COLOUR` (`slice_stacks.boundary_rgba`) instead of an additive white image, which vanished over brightfield overlays; V2 View > Show region boundaries (`view.boundaries`, B) drives `show_boundary_btn`.

### 27th October 2026
##### DriftlessMap 2.0.0a23

V2: probes merged into the Implants card (`ProbeControls`); probe summary rows in the implant table (`probe_csv_row`); `export_all_results` with Results > Export all results (project copy via `save_project_called(path=, as_copy=True)`, objects, probe CSVs, implant table, layers); Add implant dialog widths.

### 27th October 2026
##### DriftlessMap 2.0.0a22

pyqtgraph `useNumba` is set only when numba is importable, removing a UserWarning on every image drawn without numba (e.g. Python 3.14).

### 27th October 2026
##### DriftlessMap 2.0.0a21

Atlas page slider: throttled drag updates (40 ms) instead of a debounce that withheld every page during a continuous drag; coronal pages are copied contiguously before display (10 µm: preview 108 → 4 ms, full page 260 → 25 ms).

### 27th October 2026
##### DriftlessMap 2.0.0a20

Suggest Atlas Section keeps sections upright and unflipped unless clearly better otherwise, and shows the orientation it applies.

### 27th October 2026
##### DriftlessMap 2.0.0a19

Find atlas section ranks depth in two passes and compares close orientations on sampled pages; checked on the Allen 25 µm atlas.

### 27th October 2026
##### DriftlessMap 2.0.0a18

Find atlas section prefers upright orientations and compares close ones by anatomy; the coronal atlas slider previews pages while dragging.

### 27th October 2026
##### DriftlessMap 2.0.0a17

Find atlas section and Suggest landmarks handle brightfield sections (inverted, illumination flattened, black background); hole filling fixed for tissue touching two edges.

### 27th October 2026
##### DriftlessMap 2.0.0a16

Find atlas section searches fine atlases on a sampled copy and refines the pages at full resolution (about 8x faster at 10 µm).

### 27th October 2026
##### DriftlessMap 2.0.0a15

Implants card in the 2.0 preview: outline (draw or propose), mark the tip or bottom, map, build and report fibers and microprisms.

### 27th October 2026
##### DriftlessMap 2.0.0a14

Implants in the engine: map outlines, build, undo, save in projects, 3D display, object import/export and the implant CSV.

### 27th October 2026
##### DriftlessMap 2.0.0a13

Implant model: fibers and microprisms are fitted to mapped section outlines (fiber tip; prism bottom DV and ML edges), with warnings.

### 27th October 2026
##### DriftlessMap 2.0.0a12

Map, Update mapping, Make parts and Build can be undone and redone as whole steps (Ctrl+Alt+Z / Ctrl+Alt+Shift+Z).

### 27th October 2026
##### DriftlessMap 2.0.0a11

Update mapping and Edit marks for kept marks; rebuilding leaves out replaced parts; Edit parts works for built contours.

### 27th October 2026
##### DriftlessMap 2.0.0a10

Mappings, parts and built objects are labelled out of date when the registration changes or the marks are mapped again; object exports record the status.

### 27th October 2026
##### DriftlessMap 2.0.0a9

Mapping keeps the section's marks in mapping records; mapping or making parts again replaces earlier results instead of duplicating them.

### 27th October 2026
##### DriftlessMap 2.0.0a8

Projects save mapping records and each object's mapping origin (groundwork for keeping section marks after mapping).

### 27th October 2026
##### DriftlessMap 2.0.0a7

Pyramidal TIFFs can be read at a stored lower resolution with the Scale slider; the level is saved and restored with the project.

### 27th October 2026
##### DriftlessMap 2.0.0a6

The desktop application can open the 2.0 preview (Help > Open the 2.0 Preview, or `--v2`), and the preview can open the classic interface.

### 27th October 2026
##### DriftlessMap 2.0.0a5

The 2.0 preview's light and dark themes now restyle the 1.x tool options, atlas controller and region tree.

### 27th October 2026
##### DriftlessMap 2.0.0a4

Choose which time point (or other further axis plane) of a TIFF to read; the choice is saved in the project.

### 27th October 2026
##### DriftlessMap 2.0.0a3

Channels named in a file without stored colours get conventional colours (DAPI blue, GFP green, tdTomato red, Cy5 magenta).

### 27th October 2026
##### DriftlessMap 2.0.0a2

**Suggest Atlas Section** names the anatomical side: where the animal's right is in the section, or the Right or Left hemisphere for sagittal sections.

### 27th October 2026
##### DriftlessMap 2.0.0a1

In the 2.0 preview, actions that cannot run yet are greyed out with the reason in their tooltip, Match and Register show what to load first, and empty views and side panels are replaced by short guidance.

### 28th September 2026
##### DriftlessMap 1.6.1

Fixes **Show Boundary**, which drew atlas region boundaries almost black and therefore invisibly. **Propose Landmarks** now suggests up to 10 landmarks on features both images show (outline tips and notches, shared internal edges) instead of about 36. Adds a tutorial for the automatic section and landmark suggestions.

### 27th September 2026
##### DriftlessMap 1.6.0

Adds **Atlas > Suggest Atlas Section...**, which suggests the atlas plane, section, tilt and histology orientation for a loaded section. Also adds **Atlas > Propose Landmarks**, which fits the shown atlas slice to the histology and fills in registration landmarks for review. SimpleITK is now a required dependency.

### 27th September 2026
##### DriftlessMap 1.5.0

Review release: corrects probe site faces, source-voxel mirroring, brain-entry detection, region path lengths, image scale, pixel-centre warps, voxel flooring and surface depth; closes a mesh-cache code-execution hole and an allocation bomb; stops several ways of losing work; fixes many crashes; and runs long operations in the background. See the "re-export if…" list in [What’s New](WhatsNew.md) before reusing results from earlier versions.

### 27th August 2026
##### DriftlessMap 1.4.0

Adds native Windows and macOS desktop release builds, a new application icon,
visible GUI version information, and separate end-user and developer
installation instructions.

### 27th August 2026
##### DriftlessMap 1.3.0

Adds reproducible project archives with checksummed, relocatable atlas and
histology references; lossless embedded working histology; optional portable
histology sources; complete probe-planning persistence; and atlas-bound object
provenance. Standalone probe-setting save/load is now implemented.

### 27th July 2026
##### DriftlessMap 1.2.0

Adds a versioned four-file probe-localization export with a labeled centerline
track suitable for assigning continuous unit depths to Allen CCF coordinates
and brain structures. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 27th July 2026
##### DriftlessMap 1.1.0

Establishes DriftlessMap as an independently maintained continuation of HERBS,
with complete upstream attribution, a distinct package and application identity,
new DriftlessMap archive extensions, and compatibility for existing HERBS data
and scripts. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 25th July 2026
##### HERBS 1.0.4

Improves manual atlas registration with one reproducible triangulation mesh,
live quality feedback, safer landmark editing, and smoother seam-free warping.
See the cumulative [What’s New in DriftlessMap](WhatsNew.md) history for details.

### 25th July 2026
##### HERBS 1.0.3

Adds estimated Allen CCFv3 stereotaxic coordinate reporting and fixes atlas
hover handling at image boundaries. See the cumulative
[What’s New in DriftlessMap](WhatsNew.md) history for details.

### 18th July 2026
##### HERBS 0.2.8.1

Reliability, security, packaging, and maintainability release. See the
cumulative [What’s New in DriftlessMap](WhatsNew.md) history for the complete change
details, reasons, compatibility notes, and upgrade instructions.

### 1st May 2023
##### Bug fix!
Fix the bugs that reported in the issue page. 
1. Bug when changing color or size of the uploaded probe obj.
2. Bug when saving projects that contain virus layers/obj.




### 23rd Dec. 2022
##### Minor update!
Feature: Keep slice angles when page number changed for volume atlas.

### 20th Dec. 2022
##### Major update!
1. Re-design probe sites visualisation.
2. Add linear silicon probe design.
3. Add multi-shanks probe design.
4. Support uploading external cell points.
5. Support un-merging merged object.

### 04th Nov. 2022
##### Minor debug.
Fix the valid values for the text input of on side points.

### 29th Oct. 2022
##### Minor update!
Fix the atlas rotation slider value changed issue.

### 28th Oct. 2022
##### Major update! 
support for displaying merged object in 2D atlas view. Only merged probe is finished implementation at the moment. 

<p align="center">
<img src="image/update_log_281022.png" width="50%">
</p>


- By clicking **2D button**, the current activated merged objects will be displayed in the 2D atlas view. 
For probe objects, all three planes will be translated to the corresponding according to the insertion voxels,
and Coronal and Sagittal plane will be rotated according to the AP and ML angle respectively. 
The probe will be shown in both Coronal and Sagittal 2D atlas view.


- By clicking **info button**, the information window of the current activated object will pop up. 
The previous way to read the information by double clicking the object is no longer supported. 
