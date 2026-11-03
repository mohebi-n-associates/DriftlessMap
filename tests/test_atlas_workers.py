import tests.settings_isolation  # noqa: F401  (before the app reads settings)
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

from driftlessmap.atlas_downloader import WorkerProcessData
from driftlessmap.atlas_processor import CustomerAtlasWorker
from driftlessmap.download_utils import thread_is_running


class WorkerFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_waxholm_worker_reports_failures_and_always_finishes(self):
        worker = WorkerProcessData()
        finished = []
        worker.finished.connect(lambda: finished.append(True))
        with tempfile.TemporaryDirectory() as folder:
            worker.set_data(
                os.path.join(folder, "missing", "folder"),
                "data.nii.gz", "labels.nii.gz", "mask.nii.gz",
                (1, 1, 1), (1, 1, 1), 39,
            )
            worker.run()
        self.assertEqual(finished, [True])
        self.assertFalse(worker.success)
        self.assertIn("Atlas processing failed", worker.message)

    def test_custom_atlas_worker_turns_exceptions_into_error_signals(self):
        worker = CustomerAtlasWorker()
        errors = []
        worker.error_occur.connect(errors.append)
        worker.vox_size = None  # comparing None raises inside the worker
        worker.run()
        self.assertEqual(len(errors), 1)
        self.assertIn("Atlas processing failed", errors[0])

    def test_custom_atlas_worker_accepts_a_mask_with_one_fourth_frame(self):
        # The Waxholm brain mask is stored as X x Y x Z x 1.
        import nibabel as nib
        import numpy as np

        worker = CustomerAtlasWorker()
        errors = []
        worker.error_occur.connect(errors.append)
        with tempfile.TemporaryDirectory() as folder:
            volume = np.zeros((12, 12, 12), dtype=np.float32)
            volume[3:9, 3:9, 3:9] = 1
            labels = (volume * 5).astype(np.uint16)
            for name, data in (("t.nii.gz", volume), ("a.nii.gz", labels),
                               ("m.nii.gz", (volume > 0).astype(np.uint8)[..., None])):
                nib.save(nib.Nifti1Image(data, np.eye(4)), os.path.join(folder, name))
            with open(os.path.join(folder, "labels.csv"), "w", encoding="utf-8") as stream:
                stream.write("id,name,acronym,parent_id,structure_id_path\n"
                             "99,Brain,Brain,-1,/99/\n5,Box,B,99,/99/5/\n")
            worker.set_data(folder, "t.nii.gz", "a.nii.gz", "labels.csv",
                            {"to_HERBS": (0, 1, 2), "from_HERBS": (0, 1, 2),
                             "direction_change": (False, False, False)},
                            (6, 6, 6), 25.0, mask_local="m.nii.gz", factor=2)
            worker.run()
            self.assertFalse(any("mask" in message for message in errors), errors)
            self.assertTrue(os.path.exists(os.path.join(folder, "atlas_axis_info.pkl")), errors)

    def test_deleted_or_missing_threads_count_as_stopped(self):
        self.assertFalse(thread_is_running(None))
        thread = QThread()
        self.assertFalse(thread_is_running(thread))

        class DeletedThread:
            def isRunning(self):
                raise RuntimeError("wrapped C/C++ object has been deleted")

        self.assertFalse(thread_is_running(DeletedThread()))



class AtlasProcessorFileChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_files_from_different_folders_keep_their_full_paths(self):
        from unittest.mock import patch

        from PyQt6.QtWidgets import QFileDialog

        from driftlessmap.atlas_processor import AtlasProcessor

        dialog = AtlasProcessor()
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            volume = os.path.join(first, "volume.nii.gz")
            labels = os.path.join(second, "labels.nii.gz")
            with patch.object(QFileDialog, "getOpenFileName", return_value=(volume, "")):
                dialog.get_data_file()
            with patch.object(QFileDialog, "getOpenFileName", return_value=(labels, "")):
                dialog.get_seg_file()
            with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
                dialog.get_seg_file()  # cancelled: keeps the previous choice
                dialog.get_info_file()
            self.assertEqual(dialog.data_local, os.path.abspath(volume))
            self.assertEqual(dialog.segmentation_local, os.path.abspath(labels))
            self.assertEqual(dialog.folder_path, os.path.abspath(first))
            self.assertIsNone(dialog.label_local)
            self.assertEqual(dialog.check_empty_file(), "Please select label information file.")
            self.assertEqual(
                os.path.join(dialog.folder_path, dialog.segmentation_local),
                os.path.abspath(labels),
            )

    def test_every_atlas_dialog_opens(self):
        from driftlessmap.allen_downloader import AllenDownloader
        from driftlessmap.atlas_downloader import AtlasDownloader
        from driftlessmap.atlas_processor import AtlasProcessor

        for dialog_class in (AtlasProcessor, AllenDownloader, AtlasDownloader):
            with self.subTest(dialog_class.__name__):
                dialog = dialog_class()
                dialog.deleteLater()

if __name__ == "__main__":
    unittest.main()
