## About atlas coordinates in DriftlessMap

> DriftlessMap 2.5 downloads the Waxholm v4.01 and SWC female rat atlases; see
> [Downloading the rat atlases](download_rat_atlases.md). Both use the Waxholm
> coordinates described below.

DriftlessMap downloads and processes the Waxholm Space rat atlas, the SWC
female rat atlas and the Allen mouse atlas (CCFv3), and processes your own
volume atlases with the Atlas Processor. Atlases are built on different
coordinate systems: their x, y and z axes point in different directions from
one atlas to the next. DriftlessMap converts each of them into one internal
coordinate system when the atlas is processed. This page describes the
coordinates of the common atlases, the internal one, and how Bregma is set.
The reference description is in the
[User Manual, Section 3](../../MANUAL.md#32-driftlessmap-internal-axes).

### Allen mouse atlas

Allen CCFv3 volumes store their voxels in the order (AP, DV, ML): the first
axis runs from anterior to posterior, the second from dorsal to ventral and
the third from left to right, as in this figure from the Allen community page
https://community.brain-map.org/t/how-to-switch-between-the-3-coordinate-systems-of-mouse-connectivity/952

<p align="center">
<img src="../../image/atlas_related/allen_atlas.jpg" width="80%">
</p>

### Waxholm rat atlas

The Waxholm Space files store x from left to right, y from posterior to
anterior and z from inferior to superior (RAS), as in this figure from the
NITRC page
https://www.nitrc.org/docman/view.php/1081/2094/Coordinate_system_orientation_v1-v1.01.pdf
(the NIfTI headers of the v4.01 annotation and the T2\* template both report
R, A, S). The SWC female rat atlas is delivered by BrainGlobe in another axis
order; DriftlessMap converts it to the Waxholm order when it is downloaded.

<p align="center">
<img src="../../image/atlas_related/waxholm_atlas.jpg" width="80%">
</p>

### DriftlessMap internal coordinates

DriftlessMap's internal 3D coordinates are those of the Waxholm atlas:

| Position | Axis | Positive direction |
| --- | --- | --- |
| 1 | ML | Right |
| 2 | AP | Anterior |
| 3 | DV | Dorsal (superior) |

The figure below is the legacy HERBS drawing of these axes; the axes are
unchanged in DriftlessMap.

<p align="center">
<img src="../../image/atlas_related/herbs_3d.jpg" width="80%">
</p>

Processing puts every atlas into this order:

- **Waxholm and SWC female rat atlases** are already in this order and are
  stored without changes.
- **Allen atlases** are flipped along AP and DV and then transposed, so the
  Allen (AP, DV, ML) voxel becomes the internal (ML, AP, DV) voxel.
- **Your own atlases** are flipped and transposed according to the axis
  directions you choose in the Atlas Processor (see
  [Upload and process user defined atlases](../upload_and_process_user_defined_atlases.md)).

The Allen downloader and the Atlas Processor save the conversion in
`atlas_axis_info.pkl` in the atlas folder. DriftlessMap uses that file to go
back to the atlas's own voxels: for external cell points, for the native
coordinates in a merged probe, and in drawing reports and CSV exports.
The Waxholm and SWC downloads write it too since DriftlessMap 2.5.1 (rat
folders processed earlier lack it); see
[Important to know before you upload external data](../External_Related/important_to_know_before_you_start.md).

For the 2D atlas views, the volume is rearranged so that coronal,
sagittal and horizontal pages are shown with dorsal at the top: the views
hold it as (DV from dorsal to ventral, ML, AP). Everything you click on a page
is converted back to the internal 3D coordinates automatically. Do not
reinterpret a view's on-screen (x, y) position as an atlas voxel yourself.

### About Bregma

DriftlessMap reports positions relative to the Bregma voxel stored when the
atlas was processed.

- **Waxholm and SWC female rat atlases:** Bregma is the Waxholm voxel
  (246, 653, 440) in (ML, AP, DV) order, the same point HERBS used. Coronal
  page 653 is therefore Bregma, and with 39.0625 µm voxels a page *n* lies
  (*n* − 653) × 39.0625 µm from Bregma (positive is anterior).
- **Allen mouse atlas:** the Allen atlas does not define Bregma. The download
  dialog fills in an estimated Bregma in Allen source voxels (AP, DV, ML),
  which you can change before processing: (540, 44, 570) at 10 µm,
  (216, 18, 228) at 25 µm and (108, 9, 114) at 50 µm. These come from a
  community-derived estimate of Bregma at Allen (AP, DV, ML) = (5400, 440,
  5700) µm. A zero in the AP or ML field is replaced by the middle of that
  axis.
- **Your own atlases:** you enter Bregma in the Atlas Processor as voxels of
  the source volume, before any flips. A zero in any field means "not given"
  and is replaced by the middle of that source axis.

For example, the 25 µm Allen volume has source shape (528, 320, 456) and
internal shape (456, 528, 320). The default Bregma (216, 18, 228) in Allen
(AP, DV, ML) voxels becomes the internal voxel (228, 311, 301): ML stays 228,
AP is flipped to 528 − 1 − 216 = 311 and DV is flipped to
320 − 1 − 18 = 301.
