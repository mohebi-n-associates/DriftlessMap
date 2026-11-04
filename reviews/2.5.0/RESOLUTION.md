# Resolution of the 2.5.0 review

How each finding in [REPORT.md](REPORT.md) was handled. Each release has a
regression test; details are in [UpdateLog.md](../../UpdateLog.md).

| ID | Resolution | Release |
| --- | --- | --- |
| B1 | Each section's registration fingerprint is kept when it is put away; results from a changed stored section stay out of date, also after save and reopen. Sections stored before 2.5.3 now show "not verified" (2.6.0 review F2). | 2.5.3, 2.6.1 |
| B2 | A different atlas cannot replace the one a project's results were made with (an identical copy can); File > New window starts another project. Files changed in the loaded folder are refused too (2.6.0 review F1). | 2.5.5, 2.6.1 |
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
| U1 | Section bar above the images: name, position, page; switches in place. | 2.6.0 |
| U2 | Annotate shows the pipeline and offers its next step as one button. | 2.6.0 |
| U3 | Results lists an object's sections and repairs it (open, review, update, build again). | 2.6.0 |
| U4 | Compact step rail below 1200 px (with the inspector folding of 2.5.8). | 2.6.0 |
| U7 | Named processing stages, retry of failed downloads, interrupted processing recognised; no cancellation. | 2.6.0 |
| U8 | Several files at once in natural order; TIFF pages as sections. | 2.6.0 |
| U9 | Review checklist; Blink and Checkerboard; no linked zoom. | 2.6.0 |
| U10 | All / None per channel column; colour names. | 2.6.0 |
| U11 | Mapping history view; cleared-history notes; delete dialogs name sections. | 2.6.0 |
| U12 | Three ways to start; every atlas download visible; quick start in the manual. No bundled example or user study. | 2.6.0 |

Also fixed while working through the review: landmark suggestion now repeats
exactly (2.5.6), and six probe-planning bugs found while redoing the tutorials
(2.5.7). Mapping a new page of a TIFF still replaces that section's earlier
mapping; opening pages as separate sections belongs with U8.
