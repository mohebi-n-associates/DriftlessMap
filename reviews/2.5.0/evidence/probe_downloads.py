"""Diagnostic evidence for the 2.5.0 review, not an application change.
Run in a dedicated environment with DRIFTLESSMAP_REVIEW_SOURCE pointing at
an extracted copy of commit 5305b1d78efcf1077dc2333e87d04aceabac3e18.
Generated projects and source images use temporary folders. GUI checks run
offscreen, and settings are isolated. Observations are printed as JSON.
"""
import os,sys,tempfile,json
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0, os.environ['DRIFTLESSMAP_REVIEW_SOURCE'])
import tests.settings_isolation
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from unittest.mock import patch
from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog
from driftlessmap.rat_atlases import SWC_FEMALE_RAT
app=QApplication([])
d=RatAtlasDownloadDialog(SWC_FEMALE_RAT)
root=Path(tempfile.mkdtemp(prefix='dmap-review-dialog-'))
item=SWC_FEMALE_RAT.files[0]
(root/item.local).write_bytes(b'wrong nonempty bytes')
(root/'download_manifest.json').write_text(json.dumps({item.local:{'sha256':item.sha256,'size_bytes':item.size}}))
d.saving_folder=str(root)
print('REVIEW_RESULT',json.dumps({'corrupt_file_verified':d._verified(item)}),flush=True)
d.show(); app.processEvents()
with patch.object(d,'has_active_downloads',return_value=True):
    QTest.keyClick(d,Qt.Key.Key_Escape); app.processEvents()
    print('REVIEW_RESULT',json.dumps({'escape_hides_active_dialog':not d.isVisible(),'result':d.result()}),flush=True)
from driftlessmap.atlas_downloader import WorkerProcessData
import numpy as np
worker=WorkerProcessData()
worker.set_data(str(root),'t.nii.gz','a.nii.gz',None,(1,1,1),(1,1,1),39.0625)
result=(np.ones((8,8,8)),[],np.zeros((8,8,8)),np.array([0]),{},'Atlas loaded successfully.')
with patch('driftlessmap.atlas_downloader.process_atlas_raw_data',return_value=result), patch('driftlessmap.atlas_downloader.render_volume',return_value=None):
    worker.run()
print('REVIEW_RESULT',json.dumps({'processing_success':worker.success,'axis_metadata_written':(root/'atlas_axis_info.pkl').exists(),'message':worker.message}),flush=True)
sys.stdout.flush();os._exit(0)
