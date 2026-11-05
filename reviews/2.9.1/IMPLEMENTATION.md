# 2.9.1 implementation — unpublished

Owner instruction: improve as much of the remaining refactoring as practical,
commit/push/merge into main, and **do not publish**. No tag, release, PyPI
publication or desktop build dispatch is part of this change.

## Implemented

- DocumentState owns a GUI-free ObjectState. Object columns, creation/deletion,
  identity allocation, selection and serialization now have a model owner.
  ObjectControl exposes compatibility properties instead of a second data store.
  A control can bind an existing model; saved colours survive reconstruction.
- Project collection, transaction snapshots and export collection read the
  document's object model. Widgets remain responsible for rendering and signals.
- Optional obj_id and obj_count payload fields preserve object identities and
  allocation gaps through save/reopen and undo. Old payloads and invalid identity
  metadata retain generated identities. The archive/schema versions are unchanged.
  These are document-scoped object identities, not a completed migration of named
  probe ownership to UUIDs.
- Export-all orchestration is extracted from app.py into export_workflow.py and
  exercised through a widget-free fake application interface. Its existing
  project-copy, section, object, probe and layer behavior is preserved.
- Undo packing compresses/copies each repeated array identity once per snapshot.
  Restores preserve aliases within one state and remain independent across calls.
  Equal but distinct input arrays remain distinct. History budgets count retained
  arrays once; no cache survives between mutable snapshots.
- Source version is 2.9.1; README/download links still point to the actual 2.9.0
  published release. CITATION no longer assigns a release date to unpublished code.

## Measurement

macOS arm64, Python 3.14.10, NumPy 2.5.4. Synthetic observations, not real-data
performance gates. Raw outputs are in evidence/.

`tests/benchmark_history.py --baseline /tmp/old_transactions.py` compares the
2.9.0 packer with this change using one random 8 MiB array referenced three times:

| Metric | 2.9.0 | 2.9.1 |
| --- | ---: | ---: |
| Retained packed bytes | 25,173,507 | 8,391,169 |
| Packing time, one run | 0.332 s | 0.113 s |
| Traced allocation peak | 47,554,717 bytes | 30,772,193 bytes |

The baseline file was exported with `git show 0180aba:driftlessmap/transactions.py`.
The benchmark loads an explicitly supplied trusted Python module for comparison.

Existing benchmarks: exact dirty-state digests remain about 23 ms for a 6 MiB
raster and 98 ms for a 192 MiB raster. Adding 40 TIFF sections from an 80 MiB
stack took 1.64 s with one full-stack decode, a 225.3 MiB traced allocation peak
and 922.5 MiB process resident peak. No before/after speedup is claimed for these
unchanged paths. Measurements ran alongside validation and are not percentiles.

## Remaining work

Full document ownership for image/atlas/layer/tool state, stable probe-owner IDs
with legacy name migration, and command-specific history snapshots remain future
work. This change establishes the object-state boundary and fixes repeated array
retention; it does not claim those larger migrations complete. Real-data numerical
comparisons and clean-machine installer trials still require configured datasets
and native test environments. The existing release-validation waivers remain.
