## Important to know before you upload external data

External data, such as cell coordinates found by other software, must be
given in **atlas space**: as voxel coordinates of the atlas's own volume
file, in that file's axis order. DriftlessMap stores every atlas in its own
internal axis order (see
[About atlas coordinates](../Atlas_Related/about_atlas_through_herbs.md)),
so it needs to know how the atlas file's axes were turned into the internal
ones. That information is the file `atlas_axis_info.pkl` in the processed
atlas folder.

Every atlas folder processed by DriftlessMap 2.5.1 or later has it: the Allen
mouse atlas and the Waxholm and SWC female rat atlases downloaded with
DriftlessMap, and your own atlas processed with the Atlas Processor
([tutorial](../upload_and_process_user_defined_atlases.md)).

**Rat atlas folders processed earlier do not.** Waxholm or SWC folders
processed by DriftlessMap 2.5.0 or earlier (and Waxholm folders from HERBS)
lack the file. Without it, **Cell points…** stops with the message *No atlas
rotation information saved. Please contact maintainers.* and loads nothing,
and building a probe stops with *The atlas has no axis metadata*. Open the
same download again (Project > Atlas tools), choose the folder, and click
**Process and open atlas**: the downloaded files are reused and processing
writes the file.

HERBS asked users to copy this file from its GitHub `Extra_Data` folder. That
is no longer needed. Both rat atlases are stored in the Waxholm file order
unchanged, on a 512 × 1024 × 512 grid, so their file holds no flips and no
reordering; it is the same information the Atlas Processor writes for Waxholm
files:

```python
{"to_HERBS": (0, 1, 2), "from_HERBS": (0, 1, 2),
 "direction_change": (False, False, False), "size": (512, 1024, 512)}
```

DriftlessMap identifies an atlas by the content of its processed files, this
file included. Projects saved with a folder that lacked it therefore ask for
that atlas again after you process it; keep a copy of the old folder if you
need to reopen such projects unchanged.
