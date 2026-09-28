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
from driftlessmap.provenance import path_stat_signature

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
            window._loaded_histology_signature = path_stat_signature(source)
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
            self.assertEqual(payload["img_ctrl_data"]["image_scale"], 1.0)
            self.assertEqual(restored.image_view.current_scale, 1.0)
            # Older projects stored only the slider percentage.
            self.assertEqual(
                restored.image_view._restored_scale({"current_scale": 10}), 1.0
            )
            self.assertEqual(restored.site_face, 2)
            self.assertTrue(restored.tool_box.merge_sites)
            self.assertEqual(
                restored.image_view.channel_visible[:3], [True, False, True]
            )
            # The drawn channels, not only the model, must honour the choice.
            self.assertEqual(
                [item.isVisible() for item in restored.image_view.img_stacks.image_list[:3]],
                [True, False, True],
            )
            fresh_counts = [
                window.image_view.chn_widget_list[i].color_combo.count()
                for i in range(3)
            ]
            self.assertEqual(
                [
                    restored.image_view.chn_widget_list[i].color_combo.count()
                    for i in range(3)
                ],
                fresh_counts,
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
            window._loaded_histology_signature = path_stat_signature(source)
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

    @isolated_gui_test
    def test_switching_atlases_tracks_the_active_atlas_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            volume_path = window.volume_atlas_path
            slice_image = root / "slice.png"
            cv2.imwrite(str(slice_image), np.full((12, 16, 3), 70, dtype=np.uint8))
            self.assertTrue(window.load_slice_atlas(str(slice_image)))

            window.switch_atlas()
            self.assertEqual(window.current_atlas, "volume")
            self.assertEqual(window.current_atlas_path, volume_path)
            window.switch_atlas()
            self.assertEqual(window.current_atlas, "slice")
            self.assertEqual(window.current_atlas_path, str(slice_image))

    @isolated_gui_test
    def test_downloaded_atlas_is_registered_for_provenance(self):
        import driftlessmap.app as app_module
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            atlas_folder = make_processed_atlas(Path(folder) / "waxholm")

            class FinishedDownload:
                continue_process = True

                def __init__(self):
                    self.worker = type(
                        "Worker", (), {"saving_folder": str(atlas_folder),
                                       "deleteLater": lambda self: None}
                    )()

                def exec(self):
                    return 1

                def deleteLater(self):
                    pass

            window = self.create_window()
            with patch.object(app_module, "AtlasDownloader", FinishedDownload), patch.object(
                app_module, "save_last_atlas_path"
            ) as remember:
                window.download_waxholm_rat_atlas()
            self.assertEqual(window.volume_atlas_path, str(atlas_folder))
            self.assertEqual(window.current_atlas_path, str(atlas_folder))
            self.assertIn(
                os.path.abspath(str(atlas_folder)), window._loaded_atlas_signatures
            )
            remember.assert_called_once_with(str(atlas_folder))

    @isolated_gui_test
    def test_embedded_fallback_never_links_a_changed_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "histology.png"
            project = root / "study.dmap"
            resaved = root / "resaved.dmap"
            cv2.imwrite(str(source), np.full((8, 10, 3), 40, dtype=np.uint8))

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)
            with patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(project), "")
            ):
                self.assertTrue(window.save_project_called())
            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            original = payload["histology_provenance"]["reference"]

            # The source is replaced by different pixels at the same path.
            cv2.imwrite(str(source), np.full((8, 10, 3), 200, dtype=np.uint8))
            restored = self.create_window()
            with patch.object(restored, "_ask_for_verified_input", return_value=None):
                prepared = restored.prepare_project_sources(payload, str(project))
            self.assertEqual(prepared["_histology_load_mode"], "embedded")
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            self.assertIsNone(restored.current_img_path)

            with patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(resaved), "")
            ):
                self.assertTrue(restored.save_project_called())
            resaved_payload, error = load_driftlessmap_file(resaved, "project")
            self.assertIsNone(error)
            relinked = resaved_payload["histology_provenance"]["reference"]
            self.assertEqual(relinked["sha256"], original["sha256"])

    @isolated_gui_test
    def test_pieces_use_atlas_frame_points_in_x_y_order(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_volume_atlas(Path(folder))
            window.working_atlas_data["atlas-virus"] = [[5.5, 9.5], [6.5, 9.5]]
            window.working_atlas_data["atlas-contour"] = [[3.0, 4.0], [7.0, 4.0]]
            window.working_atlas_data["atlas-cells"] = [[2.0, 3.0], [8.0, 9.0]]
            window.working_atlas_data["cell_layer_index"] = [0, 1]
            window.working_atlas_data["cell_size"] = [5, 5]
            window.working_atlas_data["cell_symbol"] = ["o", "o"]
            window.working_atlas_data["cell_count"] = [1, 1, 0, 0, 0]
            window.make_object_pieces()

            pieces = dict(zip(window.object_ctrl.obj_name, window.object_ctrl.obj_data))
            expected_virus = window.atlas_view.get_3d_data_from_2d_view(
                np.array([[5.5, 9.5], [6.5, 9.5]]), window.atlas_display
            )
            np.testing.assert_allclose(pieces["virus - piece"], expected_virus)
            self.assertIn("contour - piece", pieces)
            self.assertEqual(len(pieces["cells - piece"]), 1)
            self.assertEqual(len(pieces["cells 1 - piece"]), 1)

    @isolated_gui_test
    def test_untransferred_histology_annotations_are_reported_not_misplaced(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_volume_atlas(Path(folder))
            window.a2h_transferred = True
            window.working_img_data["img-cells"] = [[20.0, 30.0]]
            window.working_img_data["img-contour"] = [[1.0, 2.0], [3.0, 4.0]]
            virus = np.zeros((10, 10), dtype=np.uint8)
            virus[2, 3] = 1
            window.working_img_data["img-virus"] = virus
            window.make_object_pieces()

            self.assertEqual(window.object_ctrl.obj_name, [])
            message = window.statusbar.currentMessage()
            for kind in ("cells", "contours", "virus pixels"):
                self.assertIn(kind, message)
            # Histology data is kept so it can still be transferred.
            self.assertEqual(window.working_img_data["img-cells"], [[20.0, 30.0]])

    @isolated_gui_test
    def test_slice_atlas_supports_virus_clearing_and_slice_edits(self):
        from pyqtgraph import ColorButton

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            slice_image = root / "slice.png"
            cv2.imwrite(str(slice_image), np.full((12, 16, 3), 70, dtype=np.uint8))
            window = self.create_window()
            self.assertTrue(window.load_slice_atlas(str(slice_image)))
            self.assertIn("atlas-virus", window.atlas_view.slice_stack.image_dict)
            window.atlas_view.clear_atlas_stacks()

            window.process_slice()
            erased = window._atlas_raster("atlas-slice").copy()
            erased[:4] = 0
            window._set_atlas_raster("atlas-slice", erased)
            np.testing.assert_array_equal(window.atlas_view.processing_slice, erased)

            window.working_atlas_data["atlas-drawing"] = [[1, 1], [5, 1], [5, 5]]
            window.tool_box.is_closed = True
            button = ColorButton(color=(10, 200, 30))
            window.change_pencil_color(button)
            window.tool_box.pencil_size_valt.setText("4")
            window.change_pencil_size()
            self.assertEqual(window.pencil_size, 4)

    @isolated_gui_test
    def test_objects_export_with_safe_names_and_reimport_inside_the_atlas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            export_dir = root / "objects"
            export_dir.mkdir()
            window = self._window_with_volume_atlas(root)
            inside = np.array([[0.0, 0.0, 0.0], [1.0, 2.0, -3.0]])
            for name in ("a/b - piece", "a:b - piece"):
                window.object_ctrl.add_object(name, "contour piece", inside, "opaque")
            window.merge_contour()
            self.assertEqual(sorted(window.object_ctrl.obj_name), ["a/b", "a:b"])

            with patch.object(
                QFileDialog, "getExistingDirectory", return_value=str(export_dir)
            ):
                window.save_merged_object("contour")
            exported = sorted(path.name for path in export_dir.iterdir())
            self.assertEqual(exported, ["a_b (2).dmapobj", "a_b.dmapobj"])

            outside = root / "outside.dmapobj"
            from driftlessmap.persistence import save_driftlessmap_file

            save_driftlessmap_file(
                outside,
                {"type": "contour piece", "data": np.array([[0.0, 0.0, 20.0]]),
                 "name": "outside"},
                "object",
            )
            paths = [str(export_dir / name) for name in exported] + [str(outside)]
            with patch.object(QFileDialog, "getOpenFileNames", return_value=(paths, "")):
                window.load_objects()
            self.assertEqual(len(window.object_ctrl.obj_name), 4)
            self.assertIn("outside.dmapobj", window.statusbar.currentMessage())

    @isolated_gui_test
    def test_undo_snapshots_are_independent_and_survive_layer_deletion(self):
        window = self.create_window()
        cells = [[1.0, 2.0]]
        sizes = [5]
        snapshot = {"data": cells, "size": sizes, "symbol": ["+"], "index": [0],
                    "count": [1, 0, 0, 0, 0]}
        window.save_current_action("loc_btn", "img-cells", snapshot, None)
        window.save_current_action("probe_btn", "img-probe", {"data": [[3.0, 4.0]]}, None)
        cells.append([9.0, 9.0])
        sizes.append(7)
        stored = window.action_list[0]["data"]
        self.assertEqual(stored["data"], [[1.0, 2.0]])
        self.assertEqual(stored["size"], [5])

        # Undo onto a layer that does not exist must not raise.
        window.undo_called()

        window.forget_layer_actions("img-cells")
        self.assertEqual(
            [action["link"] for action in window.action_list], ["img-probe"]
        )
        self.assertEqual(window.action_id, 0)

    @isolated_gui_test
    def test_invalid_probe_planning_is_rejected_before_it_changes_anything(self):
        window = self.create_window()
        planning = window.get_probe_planning_data()
        before = (window.probe_type, window.site_face)
        for bad in ({"probe_type": 99}, {"site_face": 7}, {"pre_site_face_index": 12}):
            with self.assertRaises(ValueError):
                window.set_probe_planning_data(dict(planning, **bad))
            self.assertEqual((window.probe_type, window.site_face), before)

        window.working_atlas_data["atlas-probe"] = [[3.0, 4.0], [5.0, 6.0]]
        window.set_probe_planning_data(dict(planning, site_face=2))
        self.assertEqual(window.site_face, 2)
        self.assertEqual(window.working_atlas_data["atlas-probe"], [[3.0, 4.0], [5.0, 6.0]])

    @isolated_gui_test
    def test_settings_dialogs_prefill_and_respect_cancel(self):
        from driftlessmap.wtiles import LayerSettingDialog, SliceSettingDialog

        dialog = SliceSettingDialog("Sagittal", 11.5, 8.0, -2.3)
        self.assertEqual(dialog.cut_combo.currentText(), "Sagittal")
        self.assertAlmostEqual(dialog.width_val.value(), 11.5)
        self.assertAlmostEqual(dialog.distance_val.value(), -2.3)

        layer = LayerSettingDialog("Shift", 0, 100, 250)
        self.assertEqual(layer.val_spinbox.value(), 100)
        layer = LayerSettingDialog("Shift", 0, 100, 150 // 2)
        self.assertEqual(layer.val_slider.value(), 75)

        window = self.create_window()
        window.layer_shift_val = 40
        with patch.object(LayerSettingDialog, "exec", return_value=0):
            window.shift_setting_changed()
        self.assertEqual(window.layer_shift_val, 40)

    @isolated_gui_test
    def test_clearing_atlas_layers_removes_every_adjacent_atlas_layer(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_volume_atlas(Path(folder))
            thumbnail = np.zeros((8, 8, 3), dtype=np.uint8)
            for link in ("atlas-probe", "atlas-cells", "atlas-drawing"):
                window.layer_ctrl.master_layers(thumbnail, layer_type=link, color=[0, 0, 0])
            window.working_atlas_data["cell_count"] = [2, 0, 0, 0, 0]
            window.delete_all_atlas_layer()
            self.assertEqual(
                [link for link in window.layer_ctrl.layer_link if "atlas" in link], []
            )
            self.assertEqual(window.working_atlas_data["cell_count"], [0] * 5)

    @isolated_gui_test
    def test_vertical_probe_is_drawn_at_its_ap_position_in_sagittal_view(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_volume_atlas(Path(folder))
            view = window.atlas_view
            origin = np.asarray(view.origin_3d, dtype=float)
            start = np.array([3.0, -6.0, -2.0])  # ML, AP, DV relative to Bregma
            end = np.array([3.0, -6.0, -9.0])
            display = {
                "insertion_vox": (start + origin).astype(int),
                "insertion_coords": start,
                "terminus_coords": end,
                "insertion_coords_3d": start,
                "terminus_coords_3d": end,
                "ap_angle": 0.0,
                "ml_angle": 0.0,
                "vis_color": (255, 0, 0, 255),
            }
            view.rotate_cs_plane_after_merging_probe(display)
            sagittal_x, _ = view.simg.display_objects[-1].getData()
            coronal_x, _ = view.cimg.display_objects[-1].getData()
            np.testing.assert_allclose(sagittal_x, [start[1] + origin[1]] * 2)
            np.testing.assert_allclose(coronal_x, [start[0] + origin[0]] * 2)

    @isolated_gui_test
    def test_atlas_layer_files_are_checked_against_the_current_slice(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_volume_atlas(Path(folder))
            height, width = (int(v) for v in window.atlas_view.slice_size)
            good_probe = {"layer_link": "atlas-probe", "data": [[1.0, 2.0]], "color": (1, 2, 3)}
            self.assertIsNone(window._atlas_layer_error(good_probe))
            cases = {
                "unknown": {"layer_link": "atlas-thing", "data": []},
                "missing": {"layer_link": "atlas-probe", "data": [[1.0, 2.0]]},
                "size": {"layer_link": "atlas-overlay",
                         "data": np.zeros((height + 3, width), dtype=np.uint8)},
                "outside": dict(good_probe, data=[[width + 5.0, 1.0]]),
                "cells": {"layer_link": "atlas-cells", "data": [[1.0, 1.0], [2.0, 2.0]],
                          "color": (1, 2, 3), "symbol": ["o"], "cell_count": [2, 0, 0, 0, 0],
                          "cell_size": [5], "cell_symbol": ["o", "o"],
                          "cell_layer_index": [0, 0]},
            }
            for name, layer in cases.items():
                with self.subTest(name):
                    self.assertIsNotNone(window._atlas_layer_error(layer))
                    self.assertFalse(window.set_atlas_layer_data(layer))

    def test_saved_working_data_is_merged_with_current_defaults(self):
        from driftlessmap.app import DriftlessMap

        defaults = DriftlessMap._default_working_atlas_data()
        merged = DriftlessMap._with_defaults(
            defaults, {"atlas-probe": [[1, 2]], "retired-key": 1, "cell_count": []}
        )
        self.assertEqual(merged["atlas-probe"], [[1, 2]])
        self.assertNotIn("retired-key", merged)
        self.assertEqual(merged["cell_count"], [0] * 5)
        self.assertEqual(merged["ruler_path"], [])

    @isolated_gui_test
    def test_registration_is_built_once_per_landmark_state(self):
        import driftlessmap.app as app_module

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "histology.png"
            cv2.imwrite(str(source), np.full((30, 40, 3), 80, dtype=np.uint8))
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.reset_corners_hist()
            window.reset_tri_points_atlas()
            with patch.object(
                app_module,
                "build_piecewise_affine_registration",
                wraps=app_module.build_piecewise_affine_registration,
            ) as build:
                first = window._build_triangulation_registration(strict=False, show_error=False)
                second = window._build_triangulation_registration(strict=False, show_error=False)
                self.assertIsNotNone(first)
                self.assertIs(first, second)
                self.assertEqual(build.call_count, 1)
                window.histo_tri_data[0] = [1.0, 1.0]
                window._build_triangulation_registration(strict=False, show_error=False)
                self.assertEqual(build.call_count, 2)

if __name__ == "__main__":
    unittest.main()
