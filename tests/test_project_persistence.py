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


    def _window_with_pieces(self, piece_type, names):
        window = self.create_window()
        for name in names:
            window.object_ctrl.add_object(
                name,
                piece_type,
                np.array([[10.0, 10.0, 10.0], [12.0, 12.0, 4.0]]),
                "opaque",
            )
        return window

    def _pretend_volume_atlas(self, window):
        window.current_atlas = "volume"
        window.atlas_view.atlas_label = np.ones((20, 20, 20), dtype=np.int32)
        window.atlas_view.origin_3d = np.array([10.0, 10.0, 10.0])
        window.atlas_view.label_info = {"index": [1], "label": ["root"]}

    @isolated_gui_test
    def test_probe_merge_without_volume_atlas_keeps_pieces(self):
        window = self._window_with_pieces(
            "probe piece", ["probe 0 - piece 0", "probe 1 - piece 0"]
        )
        window.merge_probes()
        self.assertEqual(window.object_ctrl.obj_type, ["probe piece"] * 2)

    @isolated_gui_test
    def test_failed_probe_reconstruction_keeps_every_piece(self):
        import driftlessmap.app as app_module

        window = self._window_with_pieces(
            "probe piece", ["probe 0 - piece 0", "probe 1 - piece 0"]
        )
        self._pretend_volume_atlas(window)
        outcomes = iter([({"probe": "first"}, 0), (None, 16)])
        with patch.object(
            window, "get_probe_atlas_metadata", return_value=({}, None)
        ), patch.object(
            app_module,
            "calculate_probe_info",
            side_effect=lambda *args: next(outcomes),
        ), patch.object(window.object_ctrl, "add_object") as add_object:
            window.merge_probes()
        add_object.assert_not_called()
        self.assertEqual(window.object_ctrl.obj_type, ["probe piece"] * 2)
        message = window.statusbar.currentMessage()
        self.assertIn("No pieces were removed", message)
        self.assertIn("leaves the atlas volume", message)

    @isolated_gui_test
    def test_point_merge_exception_keeps_every_piece(self):
        import driftlessmap.app as app_module

        window = self._window_with_pieces(
            "virus piece", ["virus 0 - piece 0", "virus 1 - piece 0"]
        )
        self._pretend_volume_atlas(window)
        calls = []

        def calculate(*args):
            calls.append(args)
            if len(calls) == 2:
                raise IndexError("label outside atlas")
            return {"virus": "first"}

        with patch.object(app_module, "calculate_virus_info", side_effect=calculate):
            window.merge_virus()
        self.assertEqual(len(calls), 2)
        self.assertEqual(window.object_ctrl.obj_type, ["virus piece"] * 2)

    @isolated_gui_test
    def test_successful_merge_replaces_pieces(self):
        window = self._window_with_pieces(
            "contour piece", ["contour 0 - piece 0", "contour 0 - piece 1"]
        )
        with patch.object(window.object_ctrl, "add_object") as add_object:
            window.merge_contour()
        self.assertEqual(window.object_ctrl.obj_type, [])
        add_object.assert_called_once()
        self.assertEqual(add_object.call_args[0][:2], ("contour 0", "merged contour"))
    @isolated_gui_test
    def test_failed_atlas_loads_leave_the_current_atlas_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            slice_image = root / "slice.png"
            cv2.imwrite(str(slice_image), np.full((12, 16, 3), 70, dtype=np.uint8))
            window = self.create_window()
            self.assertTrue(window.load_slice_atlas(str(slice_image)))
            signatures = dict(window._loaded_atlas_signatures)

            empty_atlas = root / "not-an-atlas"
            empty_atlas.mkdir()
            self.assertFalse(window.load_volume_atlas(str(empty_atlas)))

            broken_image = root / "broken.PNG"
            broken_image.write_bytes(b"not an image")
            self.assertFalse(window.load_slice_atlas(str(broken_image)))

            self.assertEqual(window.current_atlas, "slice")
            self.assertEqual(window.current_atlas_path, str(slice_image))
            self.assertEqual(window.slice_atlas_path, str(slice_image))
            self.assertIsNone(window.volume_atlas_path)
            self.assertEqual(window._loaded_atlas_signatures, signatures)
            self.assertEqual(window.atlas_view.slice_image_data.shape[:2], (12, 16))


    def _window_with_volume_atlas(self, root):
        from tests.atlas_fixture import make_processed_atlas

        window = self.create_window()
        atlas_folder = make_processed_atlas(root / "atlas")
        self.assertTrue(window.load_volume_atlas(str(atlas_folder)))
        return window

    @isolated_gui_test
    def test_loaded_landmarks_survive_the_view_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tri_path = root / "points.dmaptri"
            window = self._window_with_volume_atlas(root)
            self.assertEqual(window.atlas_display, "coronal")
            window.atlas_tri_inside_data.extend([[5.0, 6.0], [10.0, 12.0]])
            window.atlas_tri_data = (
                window.atlas_tri_onside_data + window.atlas_tri_inside_data
            )
            window.tri_simplices = None
            with patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(tri_path), "")
            ):
                window.save_triangulation_points()
            self.assertTrue(tri_path.is_file())

            window.atlas_view.section_rabnt2.setChecked(True)
            self.assertEqual(window.atlas_display, "sagittal")
            self.assertEqual(window.atlas_tri_inside_data, [])

            with patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(tri_path), "")
            ):
                window.load_triangulation_points()

            self.assertEqual(window.atlas_display, "coronal")
            self.assertEqual(window.atlas_tri_inside_data, [[5.0, 6.0], [10.0, 12.0]])
            self.assertEqual(
                [item.textItem.toPlainText() for item in window.working_atlas_text],
                ["1", "2"],
            )

    @isolated_gui_test
    def test_landmarks_for_a_different_slice_size_are_rejected(self):
        from driftlessmap.persistence import save_driftlessmap_file

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tri_path = root / "other.dmaptri"
            window = self._window_with_volume_atlas(root)
            corners = [[0, 0], [99, 0], [99, 79], [0, 79]]
            success, error = save_driftlessmap_file(
                tri_path,
                {
                    "atlas_corner_points": corners,
                    "atlas_side_lines": [],
                    "atlas_tri_data": corners + [[3, 3]],
                    "atlas_tri_inside_data": [[3, 3]],
                    "atlas_tri_onside_data": corners,
                    "atlas_display": "coronal",
                },
                "triangulation",
            )
            self.assertTrue(success, error)
            with patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(tri_path), "")
            ):
                window.load_triangulation_points()
            self.assertEqual(window.atlas_tri_inside_data, [])
            self.assertIn("different size", window.statusbar.currentMessage())

if __name__ == "__main__":
    unittest.main()
