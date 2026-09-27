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

    def test_deleted_or_missing_threads_count_as_stopped(self):
        self.assertFalse(thread_is_running(None))
        thread = QThread()
        self.assertFalse(thread_is_running(thread))

        class DeletedThread:
            def isRunning(self):
                raise RuntimeError("wrapped C/C++ object has been deleted")

        self.assertFalse(thread_is_running(DeletedThread()))


if __name__ == "__main__":
    unittest.main()
