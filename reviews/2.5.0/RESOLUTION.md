# Resolution of the 2.5.0 review

How each finding in [REPORT.md](REPORT.md) was handled. Each release has a
regression test; details are in [UpdateLog.md](../../UpdateLog.md).

| ID | Resolution | Release |
| --- | --- | --- |
| B1 | Each section's registration fingerprint is kept when it is put away; results from a changed stored section stay out of date, also after save and reopen. | 2.5.3 |
| B2 | A different atlas cannot replace the one a project's results were made with (an identical copy can); File > New window starts another project. | 2.5.5 |
| B3 | Rat atlas processing writes `atlas_axis_info.pkl`; checked by reprocessing the SWC download and building a probe. | 2.5.1 |
| B4 | Unfinished outlines belong to their section; switching parks them, and they resume only on their section. | 2.5.4 |
| B5 | The page, scene and planes of a multi-part image file are part of the registration fingerprint (single images unchanged). | 2.5.4 |
| B6 | Removing a section with its results takes shared builds apart and keeps the other sections' parts. | 2.5.2 |
| B7 | Rat atlas files are hashed against the published checksums before reuse or processing, in both interfaces. | 2.5.2 |
| B8 | A portable save is refused for any section whose original changed; save notes stay in the final message. | 2.5.6 |
| B9 | Escape cannot close a busy download dialog (rat and Allen). | 2.5.2 |
| B10 | Every step fits its column at the minimum window; the objects column folds away below 1360 px. | 2.5.8 |
| U5 | Save writes to the open file; Save as is new; the portable copy no longer becomes the open project. | 2.5.8 |
| U6 | Warnings and errors are counted and listed for the session (copyable). | 2.5.8 |
| U1-U4, U7-U12 | Open. | — |

Also fixed while working through the review: landmark suggestion now repeats
exactly (2.5.6), and six probe-planning bugs found while redoing the tutorials
(2.5.7). Mapping a new page of a TIFF still replaces that section's earlier
mapping; opening pages as separate sections belongs with U8.
