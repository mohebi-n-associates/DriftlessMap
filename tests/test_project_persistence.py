import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from functools import wraps
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
from PyQt6.QtWidgets import QApplication, QFileDialog

from driftlessmap.app import DriftlessMap
from driftlessmap.persistence import load_driftlessmap_file


PROJECT_TEST_CHILD = os.environ.get("DRIFTLESSMAP_PROJECT_TEST_CHILD") == "1"


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


if __name__ == "__main__":
    unittest.main()
