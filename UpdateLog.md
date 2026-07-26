# Update Log

### 25th July 2026
##### HERBS 1.0.4

Improves manual atlas registration with one reproducible triangulation mesh,
live quality feedback, safer landmark editing, and smoother seam-free warping.
See the cumulative [What’s New in HERBS](WhatsNew.md) history for details.

### 25th July 2026
##### HERBS 1.0.3

Adds estimated Allen CCFv3 stereotaxic coordinate reporting and fixes atlas
hover handling at image boundaries. See the cumulative
[What’s New in HERBS](WhatsNew.md) history for details.

### 18th July 2026
##### HERBS 0.2.8.1

Reliability, security, packaging, and maintainability release. See the
cumulative [What’s New in HERBS](WhatsNew.md) history for the complete change
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


