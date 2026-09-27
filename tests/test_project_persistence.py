import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from functools import wraps
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT_TEST_CHILD = os.environ.get("DRIFTLESSMAP_PROJECT_TEST_CHILD") == "1"

import cv2
import numpy as np

from driftlessmap.persistence import load_driftlessmap_file

if PROJECT_TEST_CHILD:
    from PyQt6.QtWidgets import QApplication, QFileDialog

    from driftlessmap.app import DriftlessMap


def isolated_gui_test(test):
    """Run each OpenGL integration case in its own Qt process."""

    @wraps(test)
    def wrapper(self):
        if PROJECT_TEST_CHILD:
            return test(self)
        environment = os.environ.copy()
        environment["DRIFTLESSMAP_PROJECT_TEST_CHILD"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_project_persistence.{}".format(test.__qualname__),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        self.assertEqual(
            result.returncode,
            0,
            "{}\n{}".format(result.stdout, result.stderr),
        )

    return wrapper


class ProjectPersistenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = (
            QApplication.instance() or QApplication([])
            if PROJECT_TEST_CHILD
            else None
        )

    def setUp(self):
        self.windows = []

    def tearDown(self):
        for window in reversed(self.windows):
            window.close()
            window.deleteLater()
        if self.application is not None:
            self.application.processEvents()

    def create_window(self):
        window = DriftlessMap()
        self.windows.append(window)
        return window

    @isolated_gui_test
    def test_image_project_restores_embedded_raster_when_source_moves(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "histology.png"
            project = root / "study.dmap"
            pixels_bgr = np.zeros((8, 10, 3), dtype=np.uint8)
            pixels_bgr[..., 0] = 20
            pixels_bgr[..., 1] = 80
            pixels_bgr[..., 2] = 140
            cv2.imwrite(str(source), pixels_bgr)

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            expected = window.image_view.current_img.copy()
            window.image_view.channel_visible[1] = False
            window.image_view.img_stacks.image_list[1].setVisible(False)
            window.site_face = 2
            window.tool_box.merge_sites = True

            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            self.assertEqual(payload["project_schema_version"], 2)
            self.assertEqual(payload["probe_planning"]["site_face"], 2)
            self.assertTrue(payload["probe_planning"]["merge_sites"])
            reference = payload["histology_provenance"]["reference"]
            self.assertEqual(reference["relative_path"], "histology.png")
            self.assertEqual(len(reference["sha256"]), 64)

            source.rename(root / "moved.png")
            restored = self.create_window()
            with patch.object(restored, "_ask_for_verified_input", return_value=None):
                prepared = restored.prepare_project_sources(payload, str(project))
            self.assertEqual(prepared["_histology_load_mode"], "embedded")
            restored.current_project_path = str(project)
            restored.load_project(prepared)

            np.testing.assert_array_equal(restored.image_view.current_img, expected)
            self.assertEqual(restored.site_face, 2)
            self.assertTrue(restored.tool_box.merge_sites)
            self.assertEqual(
                restored.image_view.channel_visible[:3], [True, False, True]
            )

    @isolated_gui_test
    def test_portable_project_streams_and_reopens_original_histology(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.png"
            project = root / "portable.dmap"
            cv2.imwrite(str(source), np.full((6, 7, 3), 91, dtype=np.uint8))

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=True)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            self.assertTrue(payload["portable"])
            source.unlink()

            restored = self.create_window()
            prepared = restored.prepare_project_sources(payload, str(project))
            self.assertEqual(prepared["_histology_load_mode"], "source")
            self.assertTrue(Path(prepared["img_path"]).is_file())
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            self.assertEqual(restored.image_view.current_img.shape, (6, 7, 3))

    def _window_with_one_object(self, root):
        source = root / "histology.png"
        cv2.imwrite(str(source), np.full((6, 7, 3), 50, dtype=np.uint8))
        window = self.create_window()
        self.assertTrue(window.load_single_image_file(str(source), ".png"))
        window.object_ctrl.add_object(
            "line drawing - piece",
            "drawing piece",
            np.array([[0.0, 0.0, 2.0], [0.0, 0.0, 5.0]]),
            "opaque",
        )
        self.assertEqual(len(window.object_ctrl.obj_list), 1)
        return window

    @isolated_gui_test
    def test_cancelled_project_load_keeps_current_objects(self):
        from PyQt6.QtWidgets import QMessageBox

        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_one_object(Path(folder))
            buttons = QMessageBox.StandardButton
            for reply in (buttons.No, buttons.Cancel):
                with patch.object(
                    QMessageBox, "question", return_value=reply
                ), patch.object(
                    QFileDialog, "getOpenFileName", return_value=("", "")
                ):
                    window.load_project_called()
                self.assertEqual(len(window.object_ctrl.obj_list), 1)

            # Choosing to save first but cancelling the save must not load.
            with patch.object(
                QMessageBox, "question", return_value=buttons.Yes
            ), patch.object(
                QFileDialog, "getSaveFileName", return_value=("", "")
            ), patch.object(
                QFileDialog, "getOpenFileName"
            ) as open_dialog:
                window.load_project_called()
            open_dialog.assert_not_called()
            self.assertEqual(len(window.object_ctrl.obj_list), 1)

    @isolated_gui_test
    def test_unreadable_project_file_keeps_current_objects(self):
        from PyQt6.QtWidgets import QMessageBox

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_one_object(root)
            broken = root / "broken.dmap"
            broken.write_bytes(b"not a project")
            with patch.object(
                QMessageBox, "question", return_value=QMessageBox.StandardButton.No
            ), patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(broken), "")
            ):
                window.load_project_called()
            self.assertEqual(len(window.object_ctrl.obj_list), 1)


if __name__ == "__main__":
    unittest.main()
