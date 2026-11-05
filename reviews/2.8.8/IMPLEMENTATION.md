# 2.9.0 implementation progress

Branch: `codex/2.9.0-refactoring`. Release, merge, push, PyPI publication and native desktop builds are authorized by the owner. Do not publish the partial implementation as the finished refactoring release.

## Completed first checkpoint

- Spacing never relaxes its required surface gap below zero, so overlapping fixed tips remain a reported conflict (R2).
- Fixed/fixed conflicts are included in the final report without adding them to the optimization objective (R3).
- Spacing trials calculate surface entry only instead of a full anatomical readout. Build/display retain their full diagnostics.
- Added regressions for both conflicts and a test that prohibits anatomical readout calls during spacing while checking final ferrule clearance.
- Updated the manual, unreleased notes, and both identical agent guides.
- Validation: 37 planning/spacing tests passed; Ruff and whitespace checks passed. Full application suite must run after subsequent changes.

## Remaining work before release

1. Correct solid-device containment/distance geometry (R1) with independent regression fixtures.
2. Shared derived-data cache and precise invalidation for plan editor/overlay; profile unchanged refreshes.
3. Responsive/cancellable spacing jobs and result lifecycle checks (R4).
4. Incremental document/application service extraction and measured imaging/rendering improvements from REFACTORING.md; retain archive and numerical contracts.
5. Full tests, type checking with usable dependency stubs, performance comparison, and recorded limitations for native/real-data gates.
6. Synchronize 2.9.0 version metadata/docs, commit final changes, push and merge validated work, publish the GitHub release, verify PyPI and Windows/macOS build workflows and uploaded artifacts.

Version is deliberately still 2.8.8 until release preparation. No release has been published by this checkpoint.
