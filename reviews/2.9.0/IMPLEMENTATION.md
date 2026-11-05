# 2.9.0 implementation and validation

5 November 2026. Implements the first cross-application refactoring release
from the 2.8.8 assessment, preserving scientific algorithms and file schemas.

## Delivered

- Solid convex prism clearance detects containment, segment/face crossing and
  separation using actual rendered dimensions; includes a bounded geometry cache.
- Fixed-tip overlap and fixed/fixed conflicts remain in spacing results.
- A GUI-free PlanService shares copied scientific readouts and pair clearances.
  Keys include every serialized plan field and installed immutable atlas identity;
  caches are bounded. Presentation/surgery annotations are applied outside them.
- Spacing uses only entry/geometry during trials; a cancellable worker computes
  candidate poses and the GUI rejects results if document, atlas or plans changed.
- Object export captures widget state then delegates archive writes to a pure
  service on a worker. Region surface generation also runs off the GUI thread,
  with reentrant refresh and atlas replacement guards.
- TIFFReader chooses a requested single-plane pyramid level before pixel decoding.
  Existing page-stack sharing, physical calibration and default-resolution
  behavior remain intact.
- Regression coverage includes solid containment, crossing/separation, cache
  copy isolation/invalidation, cancellation, fixed conflicts and initial TIFF levels.
- PyQt6 6.12.0 is excluded because its malformed stubs prevent type checking;
  validation and desktop bundles use PyQt6/Qt6 6.11.0. New pure services are
  included in the mypy target list.

## Local diagnostic comparison

Same synthetic fixtures as the 2.8.8 review, macOS arm64. Small sample sizes,
profile overhead and concurrent suite activity limit interpretation.

| Operation | 2.8.8 | 2.9.0 working implementation |
| --- | ---: | ---: |
| Unchanged prism shell refresh (profiled) | 40–42 ms | 2.3–2.7 ms |
| Unchanged prism overlay refresh | 6.1–6.5 ms | 0.10–0.18 ms |
| Two-fiber spacing search (profiled) | 1.58 s | 0.125 s |

Raw profiles are in `evidence/`. These are targeted improvements, not an
application-wide speedup claim. Native installation, real-data numerical and
human usability gates remain subject to the previously recorded waiver.

## Architectural scope

The release establishes service boundaries in planning and object export and
improves imaging/rendering execution paths. It does not rewrite every subsystem
or remove the classic engine. The longer-term document-model migration, stable
object identity migration, command-specific undo and representative real-data
performance program remain future architecture work from REFACTORING.md.
These are explicitly not claimed complete by this release.
