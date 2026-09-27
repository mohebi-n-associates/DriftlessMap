# Update Log

### 27th September 2026
##### DriftlessMap 1.4.7

Probe geometry dialogs: Cancel now discards edits, added linear-silicon columns put site count and spacing in the right rows, OK reflects every field, saved multi-probe faces display correctly, and geometry validity is re-evaluated on every accept.

### 27th September 2026
##### DriftlessMap 1.4.6

Loading triangulation points no longer wipes the loaded landmarks when the file was saved in a different atlas view; files are validated against the current atlas, and landmark labels are numbered consistently.

### 27th September 2026
##### DriftlessMap 1.4.5

Volume and slice atlas loads now validate everything before changing the session, so a failed load no longer corrupts atlas provenance or deletes atlas layers; slice atlases can be loaded from images again.

### 27th September 2026
##### DriftlessMap 1.4.4

Merging probe, virus, cell, drawing and contour pieces no longer deletes the pieces when the merge fails; all merged objects are computed first and pieces are removed only when every one succeeds.

### 27th September 2026
##### DriftlessMap 1.4.3

Load Project no longer deletes the current objects before a replacement project has been chosen and verified, and its save prompt now offers Cancel.

### 27th September 2026
##### DriftlessMap 1.4.2

Security fix: array sizes declared inside project, layer and object archives are checked against the stored data before memory is allocated, so a small crafted file can no longer exhaust memory.

### 27th September 2026
##### DriftlessMap 1.4.1

Security fix: processed-atlas mesh caches are now read with a restricted, non-executable reader, closing a code-execution path through shared atlas folders.

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
