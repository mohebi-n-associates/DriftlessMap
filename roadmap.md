# DriftlessMap Roadmap

Review baseline: `main` at `06f2abc` (release 1.4.0), reviewed 2026-09-27.
All 126 tests pass on Python 3.14 in the HERBS environment, but they miss
most of the problems listed below.

This document ranks the changes needed, starting with the ones that need
immediate attention. Each item gives the location, what goes wrong, and a
suggested fix. Line numbers refer to the reviewed commit.

Priority levels:

- **P0: Immediate.** Security holes, silent loss of user work, and silent
  scientific errors (wrong numbers with no warning).
- **P1: Crashes and broken workflows.** Errors the user sees, which block a
  feature but do not corrupt data.
- **P2: Warnings.** Robustness, provenance gaps, performance, and edge cases.
- **P3: Maintenance.** Code health, CI, packaging, and repository hygiene.

Every fix should come with a regression test (CLAUDE.md rule 2). Items marked
✔ were reproduced or checked directly against the code during review.

## Status (updated for 1.4.52)

Each item was fixed in its own release, 1.4.1 to 1.4.51, with regression
tests. The suite grew from 126 to 233 tests. The detailed item list below is
kept as the original review record; line numbers refer to 1.4.0.

| Items | Release |
| --- | --- |
| 0.1 mesh pickles; 0.2 allocation bomb | 1.4.1; 1.4.2 |
| 0.3 load clears objects; 0.4 merge deletes pieces | 1.4.3; 1.4.4 |
| 0.5 atlas load commits early (plus the broken slice-image load) | 1.4.5 |
| 0.6 landmark load wipes points | 1.4.6 |
| 0.7 dialog Cancel; 0.12 dialog rows; validity flags; faces shown | 1.4.7 |
| 0.8 site faces 1/3 | 1.4.8 |
| 0.9 ruler scale; 0.10 CZI scale; 1.12 scene switch | 1.4.9 |
| 0.11 Allen DV voxel; 1.16 integer point files | 1.4.10 |
| 0.13 switch paths; 0.14 Waxholm path | 1.4.11 |
| 0.15 unverified re-link | 1.4.12 |
| 0.16 virus axes; 0.17 a2h cells; 1.8 contour crash | 1.4.13 |
| 1.1 label colour | 1.4.14 |
| 1.2 pencil key; 1.3 slice `atlas-virus`; 1.4 `atlas-slice` | 1.4.15 |
| 1.5 rotate; 1.6 shift | 1.4.16 |
| 1.7 eraser; 1.14 size fields; magic wand band | 1.4.17 |
| 1.9 short tracks; 1.10 unknown labels; NaN angles | 1.4.18 |
| 1.11 object import bounds; export names | 1.4.19 |
| 1.13 dark images; hidden channels; histogram state; swatches | 1.4.20 |
| 1.15 undo | 1.4.21 |
| 1.18 worker exceptions and deleted threads | 1.4.22 |
| Settings dialogs; probe-planning validation | 1.4.23 |
| Layer deletion loop; stale links; cell counts; label numbering | 1.4.24 |
| Stack-wide flips and rotations without blur | 1.4.25 |
| Warp half-pixel offset; last row and column | 1.4.26 |
| Sagittal overlay axis | 1.4.27 |
| Floor instead of truncate; surface depth; region volume speed | 1.4.28 |
| Surface entry; region path length | 1.4.29 |
| ROI metric by name; natural shank order | 1.4.30 |
| File mode, fsync, cleanup; `np.core` | 1.4.31 |
| Portable re-hash; atlas identity files; extraction path | 1.4.32 |
| Merged-probe atlas SHA-256 | 1.4.33 |
| Atlas layer validation; older-project defaults; failed-load report | 1.4.34 |
| Atomic atlas caches and unfinished-run marker | 1.4.35 |
| gzip length; HTTPS hops; checksum manifest | 1.4.36 |
| Atlas Processor paths, cancelled picks, CSV column (plus a crash on open) | 1.4.37 |
| Non-ASCII paths; TIFF folders; CZI metadata | 1.4.38 |
| Registration rebuilt twice | 1.4.39 |
| Background hashing, saving, verification and warps; cell detection | 1.4.40, 1.4.41 |
| 3.2 dead, vendored and debug code; `utils.py` rename | 1.4.42–1.4.44 |
| 3.3 star imports, unused code, wider lint; mypy | 1.4.43, 1.4.46 |
| 3.5 CI consolidation, SHA pins, Dependabot, gated releases, constraints, script exit codes, arm64 naming, optional signing | 1.4.45 |
| 3.6 contributor guide, `.DS_Store`, `MANIFEST.in` | 1.4.47 |
| 3.4 test backfill | throughout, plus 1.4.48 |
| 3.1 atlas session, view registry, `project_io`, per-tool handlers, `LandmarkModel` | 1.4.49–1.4.51 |

### Still open

These items need a maintainer decision or resources that are not in the
repository.

- **Large binaries** (`CookBook.pdf`, tutorial video, demo images). Moving
  them to Git LFS or release assets rewrites history and needs a force-push.
  `CONTRIBUTING.md` now asks contributors not to add more.
- **Code signing and notarization.** The workflow steps are in place and run
  once `WINDOWS_CERTIFICATE_*`, `MACOS_CERTIFICATE_*`,
  `MACOS_SIGNING_IDENTITY` and `APPLE_*` secrets are added.
- **Intel macOS builds.** They need an Intel (`macos-13`) or universal build
  job; the DMG is currently labelled arm64.
- **Fully transactional project loading.** Loads are now validated up front,
  default missing fields and report partial failures, but a failure halfway
  through still leaves a partly restored session instead of rolling back.
- **Further `app.py` decomposition.** Project save and load assembly still
  live in `app.py`. `LandmarkModel` owns the landmark state but does not yet
  emit change signals, so views are still refreshed by explicit calls.
- **CI on GitHub.** The consolidated workflows could only be checked locally.
  Their first run happens on the next push.

---

## P0: Immediate

### Security

**0.1 ✔ Atlas mesh caches are loaded with unrestricted `pickle.load`.**
- *Where:* `app.py:6821` and `app.py:6836` load `atlas_meshdata.pkl` and
  `atlas_small_meshdata.pkl`. Other `pickle.load` sites:
  `atlas_downloader.py:85` and `:123`, `allen_downloader.py:208` and `:352`,
  `atlas_processor.py:290`.
- *Why it matters:* the atlas folder is chosen by the user, or resolved from
  a `.dmap` file's reference. The last-used atlas also auto-loads at startup.
  A shared "project + atlas folder" zip containing a crafted mesh pickle
  therefore runs arbitrary code when opened. This bypasses the whole safe-file
  design.
- *Fix:*
  - Store meshes as `.npz` files (vertices and faces), rebuild `gl.MeshData`
    on load, and write the new format when an atlas is processed.
  - Until then, route these reads through the restricted unpickler, with an
    allow-list for the MeshData reconstruction. Treat `meshes/*.pkl` the
    same way.
  - Add a test that shows a malicious mesh pickle is rejected.

**0.2 A tiny archive can force a huge memory allocation.**
- *Where:* `persistence.py:329` (`read_array`).
- *Why it matters:* a 627-byte `.dmaplayer` whose `.npy` header declares
  shape `(2**34,)` makes the reader try to allocate about 137 GB before any
  data is read. `MAX_ARCHIVE_BYTES` (64 GiB) still allows deflate bombs.
- *Fix:* parse the header with `numpy.lib.format.read_magic` and
  `_read_array_header`. Before allocating, require
  `prod(shape) * itemsize <= member.file_size - header_len`.

### Silent loss of user work

**0.3 ✔ Load Project deletes all objects before a project is chosen.**
- *Where:* `app.py:8422`.
- *Why it matters:* `object_ctrl.clear_all()` runs right after the "Save
  current project?" prompt. It runs whether the user answers No, the save
  fails, or the file picker is cancelled. It also leaves `object_3d_list`
  untouched, so GL items and the object list go out of sync (colour,
  visibility, and delete then act on the wrong object).
- *Fix:*
  - Clear objects and 3D items together, and only after a file has been
    chosen and `prepare_project_sources` succeeds.
  - Add a Cancel button to the prompt, and abort if the save failed.

**0.4 ✔ Merging deletes pieces before checking that the merge can succeed.**
- *Where:* `object_control.py:1673` (`merge_pieces` calls `delete_objects`),
  used by `merge_probes` (`app.py:6139-6231`) and by `merge_virus`,
  `merge_cells`, `merge_drawings` and `merge_contour`.
- *Why it matters:* several failures happen after the pieces are already
  deleted, and every piece is lost when they do:
  - a slice atlas is active, so `np.transpose(None)` raises `TypeError`;
  - a probe has only one point;
  - the pre-plan multi-piece check fails;
  - any `error_index != 0`;
  - short tracks raise `IndexError` (item 1.9).

  If several probes are merged, those after a failing one are also lost.
- *Fix:*
  - Check the inputs and compute every merged object first. Delete the pieces
    only after all of them succeed.
  - Replace "Error index: N, contact maintainers" with a readable reason.

**0.5 Loading a volume atlas changes state before it has succeeded.**
- *Where:* `app.py:6773-6801`.
- *Why it matters:* the paths, signatures, `current_atlas` and axis info are
  set, and `delete_all_atlas_layer()` runs, before `AtlasLoader.success` is
  checked. After a failed load, the next save records the wrong atlas as the
  provenance of the current work, and atlas layers are lost. A missing mesh
  is reported, but loading continues. `load_project` (`app.py:8118`) ignores
  the failure.
- *Fix:* load into local variables, commit state only on success, and return
  a bool that `load_project` checks. `load_slice_atlas`
  (`app.py:6643-6657`) needs the same fix.

**0.6 ✔ Loading registration landmarks can wipe the landmarks just loaded.**
- *Where:* `app.py:1953-1988`.
- *Why it matters:* the loaded point lists are assigned first. Then
  `section_rabntN.setChecked(True)` fires `display_changed` →
  `reset_tri_points_atlas`, which clears `atlas_tri_inside_data` and
  `tri_simplices` whenever the file's view differs from the current one. The
  old text items are also never removed from the scene, and a missing key
  raises an uncaught `KeyError`.
- *Fix:*
  - Switch the view (with signals blocked) before assigning the data.
  - Refresh the labels through `_refresh_triangulation_text`.
  - Check the keys and the `slice_size`.

**0.7 Cancelling the probe settings dialogs does not undo the edits.**
- *Where:* `probe_utiles.py:1349` (`get_settings` returns live lists), and
  `wtiles.py:313`, `433-457`, `521-555` and `588`, which change them in
  place.
- *Why it matters:* pressing Cancel still changes the probe geometry.
- *Fix:* have each dialog work on a `copy.deepcopy` of the settings.

### Silent scientific errors

**0.8 ✔ Contact positions are wrong for site faces 1 and 3 on tilted probes.**
- *Where:* `probe_utiles.py:1183` and `:1191`.
- *Why it matters:* `t_hat = [r1, r0, 0]` is not perpendicular to `r_hat`.
  Face 0 correctly uses `[-r1, r0, 0]`. For r = (0.5, 0.5, −0.71), u·r =
  0.707, so lateral offsets leak into the axial direction. Contact
  coordinates and their region labels shift. Current tests only cover
  face 0.
- *Fix:* face 1 = −(face 0 u, n), and face 3 mirrors face 2. Add tests that
  check the vectors are orthonormal for every face and for combined ML+AP
  tilts.

**0.9 ✔ Ruler lengths are wrong after a project is reopened.**
- *Where:* `image_view.py:471` saves `scale_slider.value()` (a percentage)
  as `current_scale`. Line 488 loads it back into `current_scale`, which
  everywhere else is a fraction.
- *Why it matters:* `app.py:2487` divides by it, so µm readings are off by a
  factor of 10 to 100 after any project reload.
- *Fix:*
  - Save the real scale under its own key, and keep the slider value for the
    UI only.
  - For old files, derive the scale from `image_file.scale`.
  - Add a round-trip test.

**0.10 Non-mosaic CZI files record the wrong scale.**
- *Where:* `czi_reader.py:188-202` and `:228-232`.
- *Why it matters:* the pixels are read at full resolution, but the slider
  value is stored as the scale. At 10%, ruler lengths are 10× too long.
- *Fix:* record 1.0 for non-mosaic reads, or actually resample the image.

**0.11 Exported Allen DV coordinates are one voxel off.**
- *Where:* `probe_reconstruction.py:104` together with `atlas_view.py:1199`.
- *Why it matters:* the view uses the pixel-edge convention (`k = D − y`),
  but `herbs_vox_to_source_vox` flips with `size − 1 − k`, which is the
  voxel-index convention. The exported `allen_DV_vox` is dorsal by one voxel
  (25 µm at 25 µm resolution). The exported voxel can carry a different
  structure than the reported label. This affects probe CSVs and ROI CSVs
  (`roi_analysis.py:268`). AP has a half-voxel ambiguity.
- *Fix:* use one convention everywhere (for edge coordinates the flip is
  `size − p`). Add a round-trip test from view pixel to HERBS voxel to
  source voxel to label.

**0.12 ✔ The Linear Silicon dialog puts new columns' fields in the wrong rows.**
- *Where:* `wtiles.py:449-450` (compare the constructor at `:388-389`).
- *Why it matters:* in columns added with the spinbox, site spacing and
  sites-per-column swap rows. Users enter a site count into the spacing field
  and corrupt the probe geometry.
- *Fix:* swap the two `addWidget` rows.

**0.13 ✔ Switching atlases records the wrong atlas path.**
- *Where:* `app.py:1866-1879`.
- *Why it matters:* switching from volume to slice sets `current_atlas_path`
  to the *volume* path, and switching back sets the *slice* path. Saves then
  fail with a false "atlas changed" error, or record a slice file as the
  volume atlas. That project then fails to reload.
- *Fix:* swap the two assignments. Better, set the atlas path in one
  "atlas session" routine (see 3.1).

**0.14 Downloading the Waxholm atlas never records its path.**
- *Where:* `app.py:1648-1690`.
- *Why it matters:* after an Allen atlas has been loaded, a Waxholm download
  leaves the Allen path and signatures in place. The next save attaches
  Waxholm-space work to Allen provenance.
- *Fix:* set the paths and signature from `wax.worker.saving_folder`, or
  route the download through `load_volume_atlas`.

**0.15 Embedded-raster fallback re-links a mismatched histology file.**
- *Where:* `app.py:8154-8156`, `7712-7730` and `8078`.
- *Why it matters:* suppose the saved histology file no longer matches its
  checksum and the user cancels "Locate". `current_img_path` is kept while
  the signature is `None`, so the next save hashes the changed file and
  records it as the source of the embedded raster. The persistence contract
  forbids this. Slice atlases never record a signature, so they have the same
  problem at `app.py:8131` and `:7701`.
- *Fix:* mark the session as unlinked, and on save reuse the stored
  reference (or `None`). Never re-describe an unverified file.

**0.16 Virus pieces from histology use the wrong axis order.**
- *Where:* `app.py:5964-5965`.
- *Why it matters:* the code builds `[rows, cols]`, where every other path
  uses `[x, y]`. The frame check is also inconsistent: virus and contour use
  `h2a_transferred`, while probe, cell and drawing use `a2h_transferred`.
  With no transfer at all, raw histology pixels can become atlas objects.
- *Fix:*
  - Use `[cols, rows]`.
  - Add one `active_frame()` helper that returns the matching data
    dictionary, and use it for every piece type.

**0.17 Histology cells are dropped in a2h mode.**
- *Where:* `app.py:6051-6055`.
- *Why it matters:* the cell positions come from `working_img_data`, but the
  counts come from `working_atlas_data`. No pieces are created and no message
  is shown. The atlas lists are cleared instead of the image lists.
- *Fix:* pick one source dictionary and use it throughout.

---

## P1: Crashes and broken workflows

Each of these raises an exception inside a Qt slot. Under PyQt6 that can
abort the whole process, which loses unsaved work.

**1.1 ✔ Changing a label colour crashes on sparse-ID atlases** such as Allen.
`label_tree.py:221` indexes `current_lut[label_id]` where it should index
`current_lut[display_index_by_id[label_id]]`.

**1.2 ✔ Changing the pencil colour raises `KeyError`.** `app.py:2793` uses
`"img-drawing"` on atlas stacks, which only have `"atlas-drawing"`.

**1.3 ✔ The slice atlas has no `"atlas-virus"` entry.** The `SliceStack` in
`image_stacks.py:123-136` lacks it, so Virus Register, Accept Transform and
Edit → Clear crash in slice mode. The calls are at `app.py:3070`, `:3073`,
`:4010` and `:1251`.

**1.4 `working_atlas_data["atlas-slice"]` does not exist.** The eraser
(`app.py:5236`), lasso (`:5450`) and mask delete (`:5479`) raise `KeyError`.
Use `atlas_view.processing_slice`, which is what saves read.

**1.5 ✔ Rotating vector layers crashes.** `app.py:1365` and `:1392` call
`np.dot(rot_mat, temp)` on an (N, 2) array; use `temp @ rot_mat.T`.
- Line 1379 centres atlas layers on `histo_tri_onside_data`.
- The vector rotation turns the opposite way to the raster rotation.

**1.6 Shifting layers transposes the output.** `app.py:1318` and `:1335`
pass `shape[:2]` to `cv2.warpAffine`, which expects `(width, height)`. The
result is misaligned on non-square slices.

**1.7 The image eraser crashes on raster or atlas layers.** At `app.py:4200`,
the truth value of an ndarray is ambiguous, and atlas links raise
`KeyError`.

**1.8 `make_contour_piece` crashes.** At `app.py:5987`, `list != 0` gives a
scalar, so `inds[1]` raises `IndexError`.

**1.9 Short probe tracks crash instead of reporting an error.** When the
length minus the tip is shorter than `y_bias`, the site arrays are empty.
`get_column_loc` (`probe_utiles.py:669-685`, `766`) then raises. Combined
with 0.4, the pieces are also lost.

**1.10 A label missing from `label_info` crashes the merge.**
`probe_utiles.py:646` uses `np.where(...)[0][0]`. Fall back to
"Unknown [id]".

**1.11 Loading objects with only a slice atlas raises `TypeError`.** At
`app.py:7135`, `atlas_size` is `None`. The bound check also uses `>` where
it should use `>=`, and it has no check for negative coordinates.

**1.12 Switching CZI scenes raises `TypeError`.** `image_view.py:362` passes
a float to `setValue`.

**1.13 Nearly black images fail to load.** In `uuuuuu.py:378-394`, bins are
set to `np.max(channel)`, and cubic `interp1d` needs at least 4 points. A
binary mask or an image with maximum 1 or 2 fails to load.

**1.14 Clearing a size field throws on every edit.** `int('')` raises in
`toolbox.py:524`, `app.py:2390` and `app.py:2828`.

**1.15 The undo stack can crash or restore the wrong state.** `app.py:1547`
raises `IndexError` after a layer has been deleted. Snapshots store live
references (`app.py:4303-4306` and `:4408`). Deep-copy the snapshots, and
prune the stack when a layer is deleted.

**1.16 Integer point files are rejected.** At `app.py:8529-8532`, the check
`isinstance(np.int64, int)` is `False`. Use `np.issubdtype`.

**1.17 `load_slice_atlas` does not check `cv2.imread`'s result.** The call
returns `None` on failure, which then crashes `cvtColor`. The extension check
is also case-sensitive (`.PNG`).

**1.18 Atlas worker threads have no exception handling.** In
`atlas_downloader.py:77` and `atlas_processor.py:71`, an error is never
reported and the dialog cannot close. `allen_downloader.py:893` checks a
thread that has already been deleted (`deleteLater`).

**1.19 Clearing Site Height hides OK/Cancel for good.** `wtiles.py:506` calls
`setVisible(False)` where `setEnabled(False)` was meant.

---

## P2: Warnings

### Probe and settings state

- **Probe validity flags can stick.**
  - `set_linear_silicon` (`app.py:2654-2696`) never sets
    `valid_probe_settings=True` again after an invalid entry.
  - The tip-length warning returns early and skips the other checks.
  - `multi_probe_setting_called` (`app.py:1023-1028`) leaves the old
    validity flag in place on error.
- **Loaded probe planning is not validated.** `set_probe_planning_data`
  (`app.py:1089-1125`) has no range checks on `probe_type`, `site_face` or
  the combo indices. A load that changes the probe type also clears
  unaccepted probe points.
- **Settings dialogs ignore Cancel and forget current values.**
  - `SliceSettingDialog` and `LayerSettingDialog` override `accept()` as
    `close()`, and their callers ignore `exec()`.
  - Reopening Slice Settings resets them to 0 / Coronal and wipes the
    calibration (`wtiles.py:72`, `app.py:1770`).
  - The layer setting value is set before its range, so values above 99 are
    clamped.
- **Saved faces always show as "Out".** In `MultiProbePlanningDialog`,
  `setCurrentText(str(face_index))` (`wtiles.py:610`) matches no item.
- **Magic wand band is one-sided.** At `app.py:4341-4346`, `THRESH_BINARY`
  has no upper bound, and `astype(uint8)` wraps on 16-bit data. Use
  `cv2.inRange`.

### Layers, objects and display

- **`delete_all_atlas_layer` skips layers.** At `app.py:5695-5700` it deletes
  while iterating, and it runs `layers_exist_changed` twice. Iterate over a
  reversed copy.
- **`linked_indexes` goes stale after delete or merge.**
  `object_control.py:1515-1541` stores list indexes. Use object IDs instead.
- **Deleting the atlas-cells layer sets `cell_count = []`.** At `app.py:5794`
  it should be `[0]*5`.
- **Landmark labels are numbered from 0 after a load.** After a project load
  or triangulation load, labels start at 0 (`app.py:1984`, `8376`, `8389`).
  Interactive labels start at 1. Stale text items also build up, so a move
  targets the wrong label.
- **Hidden channels reappear.** `ImageStacks.set_data` makes every channel
  visible (`image_stacks.py:303-305`) after load, flip, rotate or page
  change. The test checks only the model list, not `isVisible()`.
- **Histogram state leaks between images.** In `image_curves.py:120-123`,
  pen and brush lists grow, and `enable_channel` keeps stale entries.
- **Colour combo entries pile up.** Swatches accumulate on every project load
  (`image_view.py:543`).
- **Each rotation step degrades the embedded raster.** `image_1_rotate`
  (`image_view.py:663-678`) crops and blurs on every 1° step. Flips and
  rotations touch only the current page of multi-page volumes. Some paths
  don't emit `sig_image_changed`.

### Measurement edge cases

- **Warped images are offset from transferred points by up to half an atlas
  pixel.** `triangulation.py:404-421` evaluates the pixel index where
  `cv2.remap` expects the pixel centre. Add +0.5 / −0.5, plus a scale-only
  regression test.
- **The sagittal probe overlay uses ML where it should use AP.** In the
  untilted branch at `atlas_view.py:1144-1145`, use index 1.
- **Region path lengths are misreported.** The length is divided by all
  columns and excludes the tip (`probe_utiles.py:557-600`), so
  `_regions.csv` under-reports border regions. Its values do not match
  `_track.csv`.
- **Surface entry can be taken from the wrong tissue.** The scan uses the
  first labelled voxel from the atlas box along the extended line
  (`probe_utiles.py:237-255`), which is wrong under concave surfaces.
- **Surface depth is off by up to one voxel.** In `roi_analysis.py:108-116`,
  the dorsal-most voxel gets NaN.
- **Negative coordinates can pass the bounds checks.** `astype(int)`
  truncates towards zero where it should floor (`probe_utiles.py:722`,
  `897`, `1070`; `roi_analysis.py:242`; `uuuuuu.py:120-136`). Floor
  everywhere, then check bounds.
- **Last-row and last-column points are rejected as outside the mesh.**
  `triangulation.py:48-60` and `486-491` use `<= width-1` where they should
  use `< width`.
- **The ROI metric is chosen from the piece name.** `roi_analysis.py:292`
  looks for "area" in the name. Persist the drawing mode instead.
- **Horizontal directions give NaN angles.** `get_angles`
  (`probe_utiles.py:263-267`) produces NaN for purely horizontal ML or AP
  directions.
- **Faces pair with the wrong shanks when there are more than 10 probes.**
  `np.unique` sorts "probe 10" before "probe 2" (`app.py:6152`). Use a
  natural sort.

### Provenance and persistence

- **Merged-probe metadata identifies the atlas by name and path only.** At
  `app.py:6118-6122`, add the SHA-256 reference.
- **`load_project` is not transactional.** At `app.py:8077-8170`, an early
  return leaves a half-loaded session. There are no defaults for keys missing
  from older files.
- **`set_atlas_layer_data` has no validation.** At `app.py:7496`, unknown
  links become phantom layers (`app.py:7637`).
- **Saved files get mode 0600 and no `fsync`.** At `persistence.py:378-398`,
  keep the destination's mode, `fsync` the file and the directory, and clean
  up on `BaseException`.
- **Atlas caches are written non-atomically and in separate steps.** A
  crashed run can pair a new `segment_pre_made.pkl` with a stale
  `atlas_pre_made.pkl`. Write via temp file plus `os.replace`, and add a
  completion marker.
- **Portable packing does not re-hash the bytes it streams.** Hash while
  copying (`provenance.py:264-287`).
- **Directory verification ignores identity files added later.** It also
  never recomputes the aggregate hash (`provenance.py:226-243`).
- **Extraction can return a path that doesn't exist.** When `name` and
  `path` differ in the payload (`provenance.py:297-317`).
- **Decoding breaks shared arrays.** Shared arrays are decoded into separate
  copies, and each lookup scans `namelist()` (O(n)) (`persistence.py:324`).
- **`np.core.multiarray` is deprecated.** `persistence.py:102-105` will
  break when NumPy removes it. Resolve through `numpy._core` first.

### Downloads and input

- **Download length check is confused by gzip.** `iter_content` decompresses
  gzip, so the byte count is compared against a compressed Content-Length.
  Send `Accept-Encoding: identity`.
- **Downloads are never checksummed.** No caller passes `expected_sha256`.
  Pin hashes for the NITRC and Allen downloads.
- **HTTPS is checked on the final URL only.** Also check `response.history`.
- **The Atlas Processor keeps only file basenames.** Files picked from
  different folders resolve wrongly, and a cancelled pick (`""`) passes the
  "is None" checks (`atlas_processor.py:595-660`).
- **The atlas CSV error names the wrong column.** It asks for `parent_id` but
  the message says `parent_structure_id` (`atlas_processor.py:132`).
- **`cv2.imread` fails on non-ASCII paths on Windows.** Use
  `cv2.imdecode(np.fromfile(...))`.
- **Folder TIFFs are reduced to 8-bit RGB.** Folder reads of `.tif` use
  `IMREAD_COLOR` (`image_reader.py:57`, `225`). Route them through tifffile.
- **CZI metadata edge cases.** `czi_reader.py` raises a bare `IndexError`
  when `DisplaySetting` or `Scaling` is missing, and `czi_path[:-4]` fails
  for `Path` input.
- **Object export uses unsanitised names as filenames.** Names containing
  `/`, and duplicate names, break or overwrite files (`app.py:7003`).

### Responsiveness

- **Long operations freeze the UI.** SHA-256 hashing, portable packing,
  object verification, `warp_image_piecewise`, `transform_accept` and cell
  detection all run on the GUI thread. Multi-GB CZI files freeze the UI.
  Move this work to `QThread` workers with progress and cancel.
- **Registration is rebuilt twice per edit.** `update_atlas_tri_lines` and
  `update_histo_tri_lines` both rebuild it (`app.py:3495`, `3529`).
- **Region volume costs O(R·V).** It runs a full-atlas `np.where` per region
  (`uuuuuu.py`). Use `np.bincount`.

---

## P3: Maintenance

### 3.1 Architecture

`app.py` holds one class with 234 methods. Its `__init__` is 567 lines and
`img_stacks_clicked` is 487 lines. Most P0 and P1 bugs come from this
structure: ad-hoc state spread across attributes, magic-string dictionary
keys, and signal side effects. Planned steps, in order:

1. **`AtlasSession` / `LoadedInput` records.** Each holds the path, kind,
   reference, signature, axis info and verified/embedded status, and is
   replaced atomically only when a load succeeds. This fixes 0.5, 0.13, 0.14
   and 0.15 by construction.
2. **`LandmarkModel`.** Owns the atlas and histology landmarks, the topology
   and the text items, and emits a single change signal.
3. **A view registry.** Applies pen and brush changes to every stack and
   checks each key exists. This fixes the 1.2 and 1.3 class of bugs.
4. **Validate, then commit, then delete.** Merge, load project and atlas
   switch should follow this order, with tests that inject a failure midway.
5. **Split the tool handlers into per-tool classes.** Move project I/O out
   of `app.py` into a `project_io.py` module.

### 3.2 Dead, vendored and debug code

- **Rename `uuuuuu.py` to `utils.py`.** It is imported by 14 modules. Remove
  its 21 unused functions; several are broken (`read_label`,
  `interpolate_contour_points`, `order_contour_pnt`, `hex2rgb`).
- **Delete unused modules:**
  - `popup_message.py`, which prints `'222'`;
  - `triangulation_points.py`, a LearnOpenCV sample with hard-coded
    `/Users/jingyig/...` paths and `cv2.imshow`;
  - `images_reader.py`, an empty stub;
  - `movable_points.TriangulationPointsTest`;
  - `CurvesPlot.set_plot`.
- **Remove dead actions and methods:** `actionExport_Atlas_Overlay`,
  `actionMerge_Slices` (in the menu but a no-op), `load_images`,
  `rotation_btn_clicked`, `reset_atlas_slice`, `check_n_trajectory`, and the
  orphaned layer add/delete buttons.
- **Remove write-only state:** `layer_action_after_matching` (grows without
  limit), `undo_count`, `redo_count`, `probe_lines_2d_list`.
- **Remove debug `print` calls:** `"Killing"`, `'gjgjhgjhg'`, `"rgb"`,
  `print(axis_info)`, `'image_view', size`.
- **Remove dead dependencies.** `numba` is only imported, never used
  (`app.py:23`). Drop it to speed up the move to new Python versions and
  shrink the bundles. `natsort` is unused (or use it for the face sort in
  P2). `pandas`, `csv` and `copy` are unused in `app.py`.
- **Unused package data:** three `data/*.pkl` files and `herbs.png` (1 MB)
  ship in the wheel but are never read.
- **Attribute vendored code.** `MovablePoints` is adapted from a pyqtgraph
  example and needs attribution.

### 3.3 Lint and typing

- **Widen the ruff rule set.** It currently selects only `E9`, `F63`, `F7`
  and `F82`. With `F` and `B` enabled there are about 1,380 findings:
  - 1,186 from `import *` (F405) and 56 star imports themselves (F403);
  - 108 unused imports (F401);
  - 23 unused variables (F841).
- *Plan:* enable F401 and F841 now, replace star imports module by module,
  then enable `B`.
- **Add a type checker.** Start with mypy or pyright on the non-GUI core:
  `persistence`, `provenance`, `triangulation`, `probe_*` and
  `roi_analysis`.

### 3.4 Tests

These areas have no tests, or only thin ones:

- **Modules:**
  - no tests: `czi_reader`, `image_curves`, `toolbox`, `wtiles`,
    `atlas_processor`, `atlas_downloader`;
  - only 2 integration tests: `app.py` and `image_view`.
- **Probe geometry:** site faces 1–3 with tilt, short or zero-length probes,
  unknown labels, and a round trip from pixel to voxel to label.
- **Merge failures:** a failed merge must keep its pieces.
- **Project load:** cancelling Load Project must keep the objects.
- **Persistence limits:** oversized `.npy` headers, malformed archives,
  duplicate archive entries, and the file mode and cleanup after a failed
  save.
- **Security:** a malicious mesh pickle must be rejected.
- **Downloads:** checksum mismatch, gzip `Content-Encoding`, and insecure
  redirects.
- **Round trips:** ruler scale and channel visibility after reload.

Also set `testpaths` for pytest.

### 3.5 CI and release

- **Merge the duplicate workflows.** `ci.yml` and `tests.yml` run the same
  3.10–3.14 matrix, which doubles CI time. `tests.yml` has no
  `permissions:` block and does not pin ruff. Keep one workflow, and add
  `concurrency:` and path filters.
- **Pin actions to SHAs.** `pypi-publish@release/v1` is a branch reference.
  Add Dependabot for actions and pip.
- **Limit write permissions.** `desktop-builds.yml` grants `contents: write`
  to the whole job while it installs unpinned dependencies. Give write
  access only to the upload step.
- **Test before releasing.** Make the release and desktop builds depend on
  the tests passing (`needs: tests`).
- **Reproducible builds.** Add a constraints or lock file for the bundles,
  so the "built reproducibly" claim in WhatsNew is true.
- **Windows build script.** `build_windows.ps1` must check
  `$LASTEXITCODE` after each step.
- **macOS builds.** The DMG is arm64-only (`macos-14`). Either label it
  "Apple Silicon" or add an Intel/universal build.
- **Code signing.** Plan Apple notarization and Windows Authenticode signing.
- **Citation metadata.** Add `date-released` to `CITATION.cff`.

### 3.6 Repository hygiene

- **Move large binaries out of git.** `CookBook.pdf` (45 MB),
  `Tutorial/Videos/pre_np1.mov` (14.5 MB), the demo PNGs (9.5 MB) and
  `image/` (14 MB) should move to Git LFS or release assets. The pack is
  78 MB.
- **Stop tracking `.DS_Store`.** Untrack `/.DS_Store` and
  `Extra_Data/.DS_Store`, and add the pattern to `.gitignore`.
- **Clean up `MANIFEST.in`.** Remove its stale numpy-distutils header, and
  include `MANUAL.md`, `UpdateLog.md` and `tests/` in the sdist.
- **Contributor files.** Add a `CONTRIBUTING.md`, and restore `CODEOWNERS`
  at `.github/CODEOWNERS` (it was deleted from `workflows/`).

---

## Suggested order of work

1. **1.4.1 security and data-loss patch:**
   - 0.1 and 0.2 (security);
   - 0.3, 0.4 and 0.6 (loss of work);
   - 0.13 and 0.14 (atlas provenance);
   - 0.12 (dialog rows).
2. **1.4.2 measurement-correctness release:**
   - 0.8 to 0.11 (contact faces, ruler and CZI scale, Allen DV offset);
   - 0.15 to 0.17 (raster re-link, virus axes, dropped cells);
   - the P2 measurement edge cases.

   Document every changed output in `WhatsNew.md` and `UpdateLog.md`, because
   users may need to re-export CSVs. Mesh storage moves to `.npz`; atlases
   already processed must still load.
3. **1.5.0:**
   - all P1 crash fixes;
   - the P2 state and dialog fixes;
   - background workers for hashing, packing and warping;
   - CI consolidation.
4. **Ongoing:** the P3 refactor steps (3.1, points 1 to 5), the lint
   ratchet, and the test backfill.
