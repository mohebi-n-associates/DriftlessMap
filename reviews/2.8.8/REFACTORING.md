# Whole-codebase refactoring assessment

Reviewed 5 November 2026 against DriftlessMap 2.8.8, commit `e2956d748798d8b82d236c0df7b8f6930d99be52`.

## Recommendation

**Yes: DriftlessMap warrants an incremental refactoring program across the whole application.** The strongest immediate performance opportunity is to stop recalculating unchanged derived data and to keep long computations out of GUI callbacks. The larger architectural opportunity is to separate scientific document state, application operations, and presentation. Moving functions between files alone will not make DFM faster.

Keep the working application and extract one workflow at a time. A wholesale rewrite, a new GUI framework, or a language migration is not justified by the evidence collected here. The existing pure scientific modules, safe archive format, provenance checks, section storage, and regression suite provide a useful foundation.

This assessment covers architecture across GUI orchestration, scientific computations, imaging, rendering, persistence, history, and validation. Runtime measurements cover selected synthetic workflows, not every operation or real-world dataset. It does not establish a whole-application speedup percentage or certify every source file.

## Evidence and its limits

An AST inventory found **100 Python files and 47,674 physical lines** under `driftlessmap`, including blank lines and comments. `app.py` accounts for 10,408 lines; its main class has 344 directly declared methods. Other substantial modules include `probe_plans.py` (2,145), `object_control.py` (1,951), `probe_utiles.py` (1,613), `v2/shell.py` (1,523), `atlas_view.py` (1,494), `atlas_matching.py` (1,252), and `v2/plan_editor.py` (1,172). Size indicates concentrated responsibilities; it is not a performance measurement.

Local measurements on macOS 26.1 arm64, Python 3.14.10, NumPy 2.5.4, with offscreen Qt:

| Operation | Observation | What it supports |
| --- | --- | --- |
| Three unchanged shell refreshes with one prism | About 40–42 ms each under cProfile; 12 calls to `plan_readout` across three refreshes | The same scientific result is computed four times per refresh; eliminate duplicate work before micro-optimizing arithmetic |
| Unchanged plan-overlay refresh with one prism | About 6.1–6.5 ms each, unprofiled | The overlay computes tracks before checking whether its render key changed |
| Space out two fibers in a small synthetic atlas | 1.58 s under cProfile; 295 full readouts; 1.42 s cumulative in `track_checks` | Search candidates repeatedly calculate diagnostics that the spacing objective does not consume |
| Exact dirty-state digest, 6 MiB raster | Median 22 ms | Small-state hashing is already modest |
| Exact dirty-state digest, 192 MiB raster | Median 100 ms | Large mutable-state scans can be noticeable; retain correctness while reducing when they are needed |

These are small local diagnostic samples, some taken while the test suite ran. cProfile adds overhead; cumulative times overlap and must not be added. The timings are not latency percentiles, interactive frame rates, release budgets, or predictions for large atlases. The call counts and dependency paths are the strongest evidence. Raw profiles and inputs are in [evidence](evidence/README.md).

## Assessment by subsystem

| Area | Current assessment | Recommended change | Expected benefit and priority |
| --- | --- | --- | --- |
| Application orchestration | V2 hosts a hidden classic `DriftlessMap` window and adopts its widgets. `app.py` still combines project installation, dialogs, mapping, export, rendering, and scientific operations. Extracted mixins still depend on many shared attributes. | Introduce explicit application services around existing operations, with narrow inputs and outputs. Keep both interfaces calling the same operations. Migrate one complete workflow before expanding. | High maintainability and regression-control value; indirect speed benefit. **High** |
| Document and section state | `project_payload()` collects state from image, atlas, layer, object, and tool widgets. Save, recovery, history, and dirty checks depend on this structure. | Establish a document-owned model with explicit document, section, scientific, and presentation fields. Let widgets observe and edit it through commands. Start with plans or objects, preserving archive adapters. | Enables safe caching, reliable worker jobs, and less UI coupling. **High**, staged |
| Derived data and UI refresh | The shell polls every 600 ms and plan overlays every 400 ms. Plan editor fill/readout and clearance paths repeat work. The overlay's key check occurs after scientific computation. | Share derived results keyed by atlas identity/generation and immutable plan inputs. Separate entry/geometry, anatomical diagnostics, collision checks, and display products. Invalidate only affected results; refresh visible panels on relevant changes. | Directly evidenced responsiveness and idle-CPU opportunity. **First performance priority** |
| Collision and spacing | Clearance uses segmented geometry with correctness gaps; spacing is synchronous and recomputes full readouts for candidate poses. | Fix the review findings first. Define one physical geometry model shared by drawing, clearance, and spacing. Cache geometry per candidate; use conservative bounds to reject distant pairs, then reliable solid intersection/distance checks for near pairs. | Correctness plus reduced repeated work. **First correctness priority** |
| Background computation | `run_in_background` is a useful shared worker helper but waits in a local modal event loop. Spacing bypasses it; cancellation/progress support varies by operation. | Add a common job lifecycle: immutable input snapshot, progress, cancellation, document/input generation, GUI-thread result commit, and visible errors. Preserve single-threaded deterministic ITK computation. | Keeps windows responsive; does not itself reduce computation time. **High** |
| Image loading and memory | TIFF pages now share one decode; inactive sections use content-addressed memory maps. However, `TIFFReader.__init__` decodes the first full series before lower pyramid levels can be selected. | Separate metadata discovery from pixel decoding. Introduce a reader interface for scene/page/plane/level selection and bounded caches. Measure supported encodings before selecting lazy, mapped, or eager paths. | Potentially large load-time and memory benefit for large files; workload evidence still required. **Medium–high** |
| Persistence, provenance, and recovery | Safe ZIP/NumPy serialization, atomic replacement, streamed attachments, array deduplication, and rollback snapshots are valuable existing work. | Keep these primitives. Move widget-dependent collection into explicit snapshot adapters as state ownership improves. Benchmark collection, fingerprinting, compression, disk I/O, and installation separately. | Safer evolution; speed opportunity depends on measured phase. **Medium** |
| Undo and dirty detection | History is bounded and compresses large arrays. Exact digests deduplicate arrays within a call; the shell already avoids idle full-state scans. History packing still traverses and copies/compresses the mutation state. | Measure history preparation separately from actual operations. Consider immutable array handles and smaller command-specific snapshots only after mutations are centralized. Keep exact checks at destructive transitions until revision tracking is proven complete. | Potential reduction in latency and peak memory without losing edits. **Medium** |
| Atlas and scene rendering | Slice previews and image downsampling already address display scale. Region surfaces are built synchronously on first use; scene refreshes can reconstruct more than changed data. | Separate CPU geometry generation from Qt/OpenGL installation; cache by atlas/region/geometry identity with bounded memory. Update changed scene items in place where practical. Profile actual paint and upload costs on native displays. | Potential smoother navigation and region selection. **Medium**, profile first |
| Registration, mapping, reconstruction | Many algorithms are already GUI-free. Deterministic triangulation, exact coordinate conventions, review fingerprints, and single-threaded ITK are deliberate contracts. | Preserve algorithms initially. Split orchestration from calculation, make units/frames explicit at boundaries, and profile representative images before vectorizing or changing sampling. | Maintainability first; numerical optimization only where justified. **Medium** |
| Objects, layers, and identity | `object_control.py` mixes storage, presentation, and dialogs. Probe ownership also depends on names and prefixes. | Extract typed object/layer records and accessors; move ownership toward stable IDs through compatibility adapters. Keep readable names and support legacy projects throughout migration. | Reduces rename/delete/rebuild coupling and makes invalidation more reliable. **Medium**, after state boundaries |
| Tests, typing, and release validation | Broad automated coverage exists, but synthetic tests miss solid containment and contradictory spacing summaries. New planning modules are outside the explicit mypy target list. Real-data/native gates remain pending. | Add behavioral fixtures at scientific and persistence boundaries, broaden typed pure-core coverage gradually, and record native/real-data performance and numerical baselines. | Makes refactoring reviewable and limits silent scientific changes. **High**, continuous |

Concrete source anchors: [project collection](../../driftlessmap/project_session.py), [UI refresh](../../driftlessmap/v2/shell.py), [plan editor](../../driftlessmap/v2/plan_editor.py), [overlay](../../driftlessmap/plan_overlay.py), [readouts and spacing](../../driftlessmap/probe_plans.py), [worker helper](../../driftlessmap/background.py), [TIFF reader](../../driftlessmap/image_reader.py), [section storage](../../driftlessmap/sections.py), [history](../../driftlessmap/transactions.py), [digest](../../driftlessmap/state_digest.py), [region surfaces](../../driftlessmap/region_meshes.py).

## Suggested sequence

### 1. Protect behavior and establish a baseline

Fix the reproduced clearance/reporting defects in [the release review](REPORT.md), with regression fixtures. Record timing and peak resident memory for startup, atlas loading, TIFF/CZI opening, section switching, slice dragging, landmark edits, registration, mapping/building, plan editing/spacing, undo, save/reopen, and export. Include one small, one typical, and one large project, plus several plan counts. Record cold and warm runs and a GUI event-loop heartbeat during long work.

Use existing project formats, coordinate results, registrations, contacts, region assignments, and exports as behavior contracts. Add representative real data to the validation process without storing private datasets unnecessarily. Existing release waivers remain waivers; synthetic profiles do not close them.

### 2. Deliver a focused performance improvement

Start with plan readouts and refreshes, where redundant computation is demonstrated. Calculate once per relevant input version, reuse across the editor and overlay, and separate collision-search inputs from expensive explanatory readouts. Validate the resulting candidate fully before presenting or committing it. Move spacing to a cancellable job using an input snapshot.

Acceptance: unchanged refreshes invoke no full scientific readout; a changed pose invalidates the affected plan and relevant pair checks; atlas, bank, roll, specs, targets, avoidance, surgery settings, previews, undo, and document replacement cannot leave stale results. Record before/after timing with identical fixtures. Cancellation must leave the document unchanged.

### 3. Extract state and application operations workflow by workflow

Start with planning or object build/update because their boundaries and regression cases are already visible. Introduce typed records and a service API; keep existing engine methods as adapters. Route classic and V2 actions through the same service. Move save/history collection for that workflow to the model, then remove redundant widget reads. Repeat for sections, registration/mapping, and export.

Acceptance: each migrated operation can be tested without constructing the main window; GUI tests still verify the real action, undo/redo, dirty state, save/reopen, and failed-load recovery. No second scientific state store appears in V2. A file becoming smaller is a by-product, not the completion criterion.

### 4. Optimize I/O, memory, and rendering from the baseline

Address first-full-series TIFF decoding if it dominates actual opening workflows. Tune history snapshots if packing dominates edits. Move region geometry generation off the GUI thread if it causes measured stalls. Preserve streaming, immutable sharing, exact raster recovery, and coordinate frames in each change.

Acceptance: peak memory and operation latency improve on the targeted datasets, with no extra full decodes, stale caches, missing undo state, or changed scientific outputs. Set actual performance budgets after baseline collection, then enforce a small stable benchmark set rather than noisy timing assertions throughout unit tests.

## Boundaries to preserve

- Backward loading of supported DriftlessMap/HERBS files and the restricted legacy reader.
- Atomic saves, ZIP64/streamed portable attachments, exact embedded working rasters, and atlas provenance identity.
- Registration fingerprints, stale-result detection, multi-section ownership, pending-edit flushing, and rollback independence from missing source files.
- Anatomical signs/units, prism tip migration, multi-shank roll and offsets, and deterministic registration behavior.
- One shared scientific implementation for both interfaces.

Do not start by changing frameworks, rewriting numerical algorithms, globally caching mutable arrays, disabling exact dirty checks, parallelizing ITK fits, or merely splitting `app.py` into more mixins. The proposed program should earn its scope through measured performance gains and simpler, testable ownership boundaries.
