import tests.settings_isolation  # noqa: F401  (before the app reads settings)
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
from driftlessmap.project_io import CELL_COUNT_SLOTS

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
    @isolated_gui_test
    def test_failed_recovery_preserves_an_archive_and_blocks_partial_saves(self):
        from driftlessmap.project_session import snapshot_metadata

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_one_object(root)
            pixels = window.image_view.current_img.copy()
            incoming = snapshot_metadata(window.project_payload())
            recovery = root / "recovery"
            recovery.mkdir()
            with patch.object(window, "_restore_project_payload", side_effect=ValueError("widget failure")), \
                    patch("driftlessmap.project_session.tempfile.mkdtemp", return_value=str(recovery)):
                self.assertFalse(window.load_project(incoming))
            path = window._project_recovery_path
            payload, error = load_driftlessmap_file(path, "project")
            self.assertIsNone(error)
            np.testing.assert_array_equal(payload["img_ctrl_data"]["current_img"], pixels)
            self.assertEqual(payload["object_data"]["obj_name"], ["line drawing - piece"])
            forbidden = root / "partial.dmap"
            self.assertFalse(window.save_project_called(path=str(forbidden)))
            self.assertFalse(forbidden.exists())
            payload["_histology_load_mode"] = "embedded"
            self.assertTrue(window.load_project(payload, project_path=path))
            self.assertFalse(hasattr(window, "_project_recovery"))
            self.assertTrue(window.save_project_called(path=str(root / "recovered.dmap")))

    @isolated_gui_test
    def test_failed_project_restore_rolls_back_unsaved_work_without_sources(self):
        import copy
        from tests.atlas_fixture import make_processed_atlas
        from driftlessmap.v2.state import scientific_digest

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_one_object(root)
            self.assertTrue(window.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            window.current_project_path = str(root / "original.dmap")
            implant = window.add_implant("fiber")
            window.set_implant_outline(implant.implant_id, [[1, 1], [4, 1], [4, 4]])
            window.undo_history.commit(window.undo_history.prepare("previous edit", {"a": 1}))
            before = scientific_digest(window)
            pixels = window.image_view.current_img.copy()
            reader = window.image_view.image_file
            (root / "histology.png").unlink()
            for failure in ("settings", "objects", "image"):
                incoming = copy.deepcopy(window.project_payload())
                incoming["_histology_load_mode"] = "embedded"
                incoming["img_ctrl_data"]["current_img"] = np.zeros_like(pixels)
                if failure == "settings":
                    del incoming["setting_data"]["atlas_rect"]
                elif failure == "objects":
                    incoming["object_data"]["obj_data"] = []
                else:
                    incoming["img_ctrl_data"]["current_img"] = np.zeros((0, 0))
                with self.subTest(failure), patch.object(
                        window, "load_volume_atlas", wraps=window.load_volume_atlas) as loader:
                    self.assertFalse(window.load_project(incoming, project_path=str(root / "bad.dmap")))
                    self.assertEqual(loader.call_count, 0 if failure == "image" else 1)
                    self.assertFalse(hasattr(window, "_project_recovery"), window.statusbar.currentMessage())
                    self.assertEqual(window.current_project_path, str(root / "original.dmap"))
                    self.assertEqual(window.undo_history.undo_label(), "previous edit")
                    self.assertIs(window.image_view.image_file, reader)
                    np.testing.assert_array_equal(window.image_view.current_img, pixels)
                    self.assertEqual(scientific_digest(window), before)

    @isolated_gui_test
    def test_unusable_probe_settings_do_not_stop_a_project_opening(self):
        import copy
        with tempfile.TemporaryDirectory() as folder:
            donor = self._window_with_one_object(Path(folder))
            payload = copy.deepcopy(donor.project_payload())
            payload["_histology_load_mode"] = "embedded"
            for planning in ({"probe_settings": {}},
                             {"probe_settings": {"probe_type": "nonsense"}}):
                with self.subTest(planning):
                    payload["probe_planning"] = planning
                    window = self.create_window()
                    with patch.object(window, "print_message") as message:
                        self.assertTrue(window.load_project(payload))
                    self.assertEqual(window.object_ctrl.obj_name, ["line drawing - piece"])
                    self.assertTrue(any("probe settings were not restored" in str(call)
                                        for call in message.call_args_list))

    @isolated_gui_test
    def test_marks_mapped_before_a26_stay_current_when_nothing_changed(self):
        import copy
        from driftlessmap.mapping_records import CURRENT, REGISTRATION_CHANGED
        with tempfile.TemporaryDirectory() as folder:
            window = self._window_with_one_object(Path(folder))
            window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            window.histo_tri_inside_data[:] = [[1.0, 1.0], [6.0, 1.0], [3.0, 5.0]]
            old = window.current_registration_fingerprint(legacy=True)
            track = {"points": [[1.0, 2.0], [3.0, 4.0]]}
            window.mapping_ledger.record(window.section_id, "probe", track, old,
                                         "not reviewed", "t", probe="A")
            payload = copy.deepcopy(window.project_payload())
            payload["_histology_load_mode"] = "embedded"
            restored = self.create_window()
            self.assertTrue(restored.load_project(payload))
            fingerprint = restored.current_registration_fingerprint()
            record, = restored.mapping_ledger.records()
            self.assertEqual(record.status(restored.section_id, fingerprint), CURRENT)
            # A changed registration is still out of date after the migration.
            payload["mapping_records"][0]["registration"] = "d" * 64
            restored = self.create_window()
            self.assertTrue(restored.load_project(payload))
            record, = restored.mapping_ledger.records()
            self.assertEqual(record.status(restored.section_id,
                                           restored.current_registration_fingerprint()),
                             REGISTRATION_CHANGED)

    @isolated_gui_test
    def test_failed_load_into_an_empty_session_stays_empty(self):
        import copy
        with tempfile.TemporaryDirectory() as folder:
            donor = self._window_with_one_object(Path(folder))
            payload = copy.deepcopy(donor.project_payload())
            payload["_histology_load_mode"] = "embedded"
            del payload["setting_data"]["atlas_rect"]
            window = self.create_window()
            self.assertFalse(window.load_project(payload, project_path=str(Path(folder) / "bad.dmap")))
            self.assertIsNone(window.image_view.image_file)
            self.assertIsNone(window.image_view.current_img)
            self.assertEqual(window.object_ctrl.obj_name, [])
            self.assertIsNone(window.current_project_path)
            self.assertFalse(hasattr(window, "_project_recovery"), window.statusbar.currentMessage())

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
            from driftlessmap.registration_input import RegistrationInput
            window.registration_input = RegistrationInput.from_channels((2,), ["Blue"])

            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            self.assertEqual(payload["project_schema_version"], 3)
            self.assertEqual(payload["registration_input"]["mode"], "channels")
            self.assertEqual(payload["registration_input"]["channels"], [2])
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

            self.assertEqual(restored.registration_input.channels, (2,))
            self.assertEqual(restored.registration_input.channel_names, ("Blue",))
            # A schema-2 project was registered with Legacy input.
            old_payload = dict(payload, project_schema_version=2)
            old_payload.pop("registration_input")
            self.assertEqual(restored._saved_registration_input(old_payload).mode, "legacy")
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
    def test_six_channel_uint16_section_displays_saves_and_reopens(self):
        import tifffile

        from driftlessmap.registration_input import RegistrationInput

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "six.tif"
            project = root / "six.dmap"
            rng = np.random.default_rng(5)
            data = rng.integers(0, 60000, (6, 24, 30), dtype=np.uint16)
            tifffile.imwrite(source, data, imagej=True, metadata={"axes": "CYX"})

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".tif"))
            view = window.image_view
            self.assertEqual(view.current_img.shape, (24, 30, 6))
            self.assertEqual(view.current_img.dtype, np.uint16)
            self.assertEqual(sum(w.isVisibleTo(view.chn_widget_wrap)
                                 for w in view.chn_widget_list), 6)
            view.set_channel_visible(False, 5)
            self.assertFalse(view.img_stacks.image_list[5].isVisible())
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)
            window.registration_input = RegistrationInput.from_channels((4,), ["Channel 5"])
            window.atlas_tri_inside_data = [[1.0, 2.0], [3.0, 4.0], [5.0, 1.0]]
            window.histo_tri_inside_data = [[2.0, 3.0], [6.0, 8.0], [10.0, 2.0]]
            self.assertEqual(window.registration_review_state(), "not reviewed")
            self.assertTrue(window.mark_registration_reviewed())
            self.assertEqual(window.registration_review_state(), "reviewed")
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            source.unlink()  # reopen from the embedded raster
            restored = self.create_window()
            with patch.object(restored, "_ask_for_verified_input", return_value=None):
                prepared = restored.prepare_project_sources(payload, str(project))
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            np.testing.assert_array_equal(
                restored.image_view.current_img, np.moveaxis(data, 0, -1))
            self.assertEqual(restored.image_view.channel_visible[:6],
                             [True] * 5 + [False])
            self.assertEqual(restored.registration_input.channels, (4,))
            self.assertEqual(restored.atlas_tri_inside_data, window.atlas_tri_inside_data)
            self.assertEqual(restored.registration_review_state(), "reviewed")
            restored.histo_tri_inside_data[0] = [2.5, 3.0]
            self.assertEqual(restored.registration_review_state(), "not reviewed")
            old_payload = dict(payload, project_schema_version=2)
            self.assertEqual(
                restored._saved_registration_review(old_payload).state("x" * 64),
                "not recorded")

    @isolated_gui_test
    def test_chosen_time_plane_is_saved_and_reread_from_the_source(self):
        import tifffile

        from driftlessmap.registration_input import RegistrationInput

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "tzcyx.tif"
            project = root / "planes.dmap"
            data = np.zeros((3, 4, 2, 12, 14), dtype=np.uint16)
            for t in range(3):
                data[t] = 100 * (t + 1)
            data[2, 1] += 7  # Z plane 2 of time point 3
            tifffile.imwrite(source, data, imagej=True, metadata={"axes": "TZCYX"})

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".tif"))
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)
            window.registration_input = RegistrationInput.from_channels((1,), ["Channel 2"])
            self.assertTrue(window.select_image_planes({"T": 2}))
            self.assertEqual(window.image_view.image_file.fixed_axes, {"T": 2})
            self.assertEqual(window.registration_input.channels, (1,))
            window.image_view.page_ctrl.page_slider.setValue(1)
            self.assertTrue(np.all(window.image_view.current_img == 307))
            self.assertFalse(window.select_image_planes({"T": 3}))
            self.assertEqual(window.image_view.image_file.fixed_axes, {"T": 2})
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            self.assertEqual(payload["img_ctrl_data"]["plane_selection"], {"T": 2})
            restored = self.create_window()
            prepared = restored.prepare_project_sources(payload, str(project))
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            self.assertEqual(restored.image_view.image_file.fixed_axes, {"T": 2})
            self.assertTrue(np.all(restored.image_view.current_img == 307))
            restored.image_view.page_ctrl.page_slider.setValue(0)
            self.assertTrue(np.all(restored.image_view.current_img == 300))

    @isolated_gui_test
    def test_pyramid_level_is_read_saved_and_reread(self):
        import tifffile

        from driftlessmap.app import _valid_read_scale

        self.assertIsNone(_valid_read_scale("x"))
        self.assertIsNone(_valid_read_scale(1.0))
        self.assertIsNone(_valid_read_scale(float("nan")))
        self.assertEqual(_valid_read_scale(0.25), 0.25)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "pyramid.ome.tif"
            project = root / "pyramid.dmap"
            data = np.random.default_rng(6).integers(0, 60000, (2, 64, 80), dtype=np.uint16)
            with tifffile.TiffWriter(source) as tiff:
                tiff.write(data, subifds=2, metadata={"axes": "CYX"}, tile=(16, 16))
                tiff.write(data[:, ::2, ::2], subfiletype=1, tile=(16, 16))
                tiff.write(data[:, ::4, ::4], subfiletype=1, tile=(16, 16))

            window = self.create_window()
            self.assertTrue(window.load_single_image_file(str(source), ".tif"))
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)
            view = window.image_view
            self.assertFalse(view.scale_wrap.isHidden())
            view.scale_slider.setValue(30)
            view.scale_slider_released()
            self.assertEqual(view.current_scale, 0.5)
            self.assertEqual(view.scale_slider.value(), 50)
            self.assertEqual(view.current_img.shape, (32, 40, 2))
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            restored = self.create_window()
            prepared = restored.prepare_project_sources(payload, str(project))
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            self.assertEqual(restored.image_view.image_file.scale["scene 0"], 0.5)
            self.assertEqual(restored.image_view.current_scale, 0.5)
            np.testing.assert_array_equal(restored.image_view.current_img,
                                          np.moveaxis(data[:, ::2, ::2], 0, -1))

    @isolated_gui_test
    def test_mapping_records_and_object_origin_are_saved(self):
        from driftlessmap.mapping_records import MappingLedger, derivation, is_identifier

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "section.png"
            project = root / "records.dmap"
            cv2.imwrite(str(source), np.full((20, 24, 3), 80, dtype=np.uint8))
            window = self.create_window()
            first_section = window.section_id
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            self.assertNotEqual(window.section_id, first_section)
            self.assertTrue(is_identifier(window.section_id))
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)
            fingerprint = window.current_registration_fingerprint()
            record = window.mapping_ledger.record(
                window.section_id, "probe", {"points": [[1.0, 2.0], [5.0, 9.0]]},
                fingerprint, "not reviewed", "2026-10-27T00:00:00Z", probe="A")
            o = window.object_ctrl
            # A built drawing with two parts of known origin: Edit parts
            # restores each part's own origin.
            other = window.mapping_ledger.record(
                window.section_id, "drawing", {"points": [[0, 0], [3, 3]]},
                fingerprint, "not reviewed", "t")
            o.add_object("A", "merged drawing",
                         {"object_type": "drawing", "data": [np.zeros((2, 3)), np.ones((2, 3))],
                          "pieces_names": ["A - piece", "A - piece"]},
                         window.obj_display_mode,
                         derivation=derivation([record]) + derivation([other]),
                         piece_derivation=[derivation([record]), derivation([other])])
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)

            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            restored = self.create_window()
            prepared = restored.prepare_project_sources(payload, str(project))
            restored.current_project_path = str(project)
            restored.load_project(prepared)
            self.assertEqual(restored.section_id, window.section_id)
            self.assertEqual({r.unit_id for r in restored.mapping_ledger.records()},
                             {record.unit_id, other.unit_id})
            ro = restored.object_ctrl
            self.assertEqual(ro.obj_derivation, [derivation([record]) + derivation([other])])
            ro.current_obj_index = 0
            ro.unmerge_objects()
            self.assertEqual(ro.obj_type, ["drawing piece", "drawing piece"])
            self.assertEqual(ro.obj_derivation, [derivation([record]), derivation([other])])

            # Projects from before mapping records: a new section, no records,
            # objects without origin.
            older, _ = load_driftlessmap_file(project, "project")
            for key in ("section_id", "mapping_records"):
                older.pop(key)
            older["object_data"].pop("obj_derivation")
            older["object_data"].pop("obj_piece_derivation")
            old_window = self.create_window()
            prepared = old_window.prepare_project_sources(older, str(project))
            old_window.load_project(prepared)
            self.assertTrue(is_identifier(old_window.section_id))
            self.assertEqual(len(old_window.mapping_ledger), 0)
            self.assertEqual(old_window.object_ctrl.obj_derivation, [[]])
            self.assertIsInstance(old_window.mapping_ledger, MappingLedger)

    @isolated_gui_test
    def test_mapping_keeps_marks_and_parts_record_their_origin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "section.png"
            project = root / "kept.dmap"
            image = np.zeros((32, 24, 3), dtype=np.uint8)
            image[4:28, 4:20] = 200
            cv2.imwrite(str(source), image)
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            window._loaded_histology_signature = path_stat_signature(source)

            def click_cells(points):
                window.working_img_data["img-cells"] = [list(p) for p in points]
                window.working_img_data["cell_size"] = [5] * len(points)
                window.working_img_data["cell_symbol"] = ["o"] * len(points)
                window.working_img_data["cell_layer_index"] = [0] * len(points)
                window.working_img_data["cell_count"][0] = len(points)

            click_cells([[8.0, 8.0], [12.0, 20.0]])
            window.transfer_to_atlas_clicked()
            self.assertTrue(window.h2a_transferred)
            window.transform_accept()
            mapped = [list(p) for p in window.working_atlas_data["atlas-cells"]]
            self.assertEqual(len(mapped), 2)
            # The live list is emptied as before; the marks are kept.
            self.assertEqual(window.working_img_data["img-cells"], [])
            record = window.mapping_ledger.get(window.section_id, "cells")
            self.assertEqual(record.revision, 1)
            np.testing.assert_array_equal(record.source["points"], [[8, 8], [12, 20]])
            xs, ys = window._kept_marks_item.getData()
            self.assertEqual(sorted(zip(xs.tolist(), ys.tolist())), [(8.0, 8.0), (12.0, 20.0)])
            self.assertIs(window.atlas_marks_origin("cells"), record)

            # Saved before making parts, the atlas marks keep their origin.
            with patch.object(
                QFileDialog,
                "getSaveFileName",
                return_value=(str(project), "DriftlessMap Project (*.dmap)"),
            ):
                window.save_project_called(portable=False)
            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            restored = self.create_window()
            self.assertTrue(restored.load_volume_atlas(window.volume_atlas_path))
            prepared = restored.prepare_project_sources(payload, str(project))
            restored.load_project(prepared)
            self.assertEqual(restored.atlas_marks_origin("cells").unit_id, record.unit_id)
            self.assertEqual(len(restored._kept_marks_item.getData()[0]), 2)

            parts = window.make_pieces_of("cells")
            self.assertEqual(len(parts), 1)
            o = window.object_ctrl
            self.assertEqual(o.obj_derivation[parts[0]], [[record.unit_id, 1]])

            # Mapping more cells replaces the unit; making parts again
            # replaces the earlier part instead of adding a second.
            click_cells([[8.0, 8.0], [12.0, 20.0], [16.0, 10.0]])
            window.transform_accept()
            again = window.mapping_ledger.get(window.section_id, "cells")
            self.assertEqual((again.unit_id, again.revision), (record.unit_id, 2))
            self.assertEqual(len(window.mapping_ledger), 1)
            parts = window.make_pieces_of("cells")
            self.assertEqual(o.obj_type, ["cells piece"])
            self.assertEqual(o.obj_derivation[parts[0]], [[record.unit_id, 2]])
            self.assertEqual(len(o.obj_data[0]), 3)

            # Atlas marks edited after mapping lose their origin.
            window.working_img_data["img-probe"] = [[6.0, 6.0], [10.0, 26.0]]
            window.transform_accept(probe="A")
            window.working_atlas_data["atlas-probe"].append([1.0, 1.0])
            self.assertIsNone(window.atlas_marks_origin("probe"))
            window.working_img_data["img-probe"] = [[7.0, 6.0], [11.0, 26.0]]
            window.transform_accept(probe="B")
            self.assertIsNotNone(window.mapping_ledger.get(window.section_id, "probe", "A"))
            self.assertIsNotNone(window.mapping_ledger.get(window.section_id, "probe", "B"))
            self.assertEqual(len(window.mapping_ledger), 3)

    @isolated_gui_test
    def test_mappings_and_parts_go_out_of_date_with_the_registration(self):
        from driftlessmap.mapping_records import CURRENT, REGISTRATION_CHANGED

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "section.png"
            image = np.zeros((32, 24, 3), dtype=np.uint8)
            image[4:28, 4:20] = 200
            cv2.imwrite(str(source), image)
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            window.working_img_data["img-contour"] = [[6.0, 6.0], [18.0, 6.0], [18.0, 26.0]]
            window.transfer_to_atlas_clicked()
            window.transform_accept()
            part = window.make_pieces_of("contour")[0]
            record = window.mapping_ledger.get(window.section_id, "contour")
            self.assertEqual(window.mapping_status(record), CURRENT)
            self.assertEqual(window.object_mapping_status(part), CURRENT)

            # Changing the atlas page changes the registration.
            view = window.atlas_view
            page = view.current_coronal_index
            view.current_coronal_index = page + 1
            self.assertEqual(window.mapping_status(record), REGISTRATION_CHANGED)
            self.assertEqual(window.out_of_date_objects(), [part])
            # Display changes do not count.
            window.image_view.set_channel_visible(False, 1)
            view.current_coronal_index = page
            self.assertEqual(window.out_of_date_objects(), [])

            view.current_coronal_index = page + 1
            exported = root / "contour.dmapobj"
            window.object_ctrl.current_obj_index = part
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(exported), "")), \
                    patch.object(window, "get_object_export_provenance", return_value={}):
                window.save_current_object()
            data, error = load_driftlessmap_file(exported, "object")
            self.assertIsNone(error)
            self.assertEqual(data["mapping_status"], REGISTRATION_CHANGED)

            # Loading another section leaves parts of the earlier one current.
            other = root / "other.png"
            cv2.imwrite(str(other), image)
            self.assertTrue(window.load_single_image_file(str(other), ".png"))
            self.assertEqual(window.object_mapping_status(part), CURRENT)
            self.assertEqual(window.kept_marks(), [])

    @isolated_gui_test
    def test_update_mapping_and_edit_marks(self):
        from driftlessmap.mapping_records import CURRENT, REMAPPED

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "section.png"
            image = np.zeros((32, 24, 3), dtype=np.uint8)
            image[4:28, 4:20] = 200
            cv2.imwrite(str(source), image)
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.current_img_path = str(source)
            drawing = [[6.0, 6.0], [18.0, 20.0], [10.0, 26.0]]
            window.working_img_data["img-drawing"] = [list(p) for p in drawing]
            window.transfer_to_atlas_clicked()
            window.transform_accept()
            first_atlas = [list(p) for p in window.working_atlas_data["atlas-drawing"]]
            part = window.make_pieces_of("drawing")[0]
            record = window.mapping_ledger.get(window.section_id, "drawing")
            view = window.atlas_view
            view.current_coronal_index += 1
            self.assertEqual(window.out_of_date_objects(), [part])

            # Unmapped cells on the section are not touched by the update.
            window.working_img_data["img-cells"] = [[9.0, 9.0]]
            window.working_img_data["cell_size"] = [5]
            window.working_img_data["cell_symbol"] = ["o"]
            window.working_img_data["cell_layer_index"] = [0]
            updated = window.update_mapping(record.unit_id)
            self.assertEqual((updated.unit_id, updated.revision), (record.unit_id, 2))
            self.assertEqual(window.mapping_status(updated), CURRENT)
            self.assertEqual(window.working_img_data["img-cells"], [[9.0, 9.0]])
            self.assertEqual(window.working_img_data["img-drawing"], [])
            self.assertEqual(window.working_atlas_data["atlas-cells"], [])
            np.testing.assert_allclose(window.working_atlas_data["atlas-drawing"], first_atlas)
            self.assertEqual(window.object_mapping_status(part), REMAPPED)
            parts = window.make_pieces_of("drawing")
            self.assertEqual(window.object_ctrl.obj_type.count("drawing piece"), 1)
            self.assertEqual(window.object_mapping_status(parts[0]), CURRENT)

            # Edit parts on a build made before the update restores the old
            # part; building again leaves it out instead of using both.
            window.working_img_data["img-contour"] = [[6.0, 6.0], [18.0, 6.0], [18.0, 26.0]]
            for key in ("img-cells", "cell_size", "cell_symbol", "cell_layer_index"):
                window.working_img_data[key] = []
            window.transform_accept()
            window.make_pieces_of("contour")
            window.merge_contour()
            contour = window.mapping_ledger.get(window.section_id, "contour")
            window.update_mapping(contour.unit_id)
            window.make_pieces_of("contour")
            o = window.object_ctrl
            o.current_obj_index = o.obj_type.index("merged contour")
            o.unmerge_objects()
            self.assertEqual(o.obj_type.count("contour piece"), 2)
            window.merge_contour()
            self.assertEqual(o.obj_type.count("contour piece"), 0)
            built = o.obj_type.index("merged contour")
            self.assertEqual(o.obj_derivation[built], [[contour.unit_id, 2]])
            self.assertEqual(window.object_mapping_status(built), CURRENT)
            # Contours built by earlier versions kept no part names.
            o.add_object("old", "merged contour",
                         {"object_type": "contour", "data": [np.zeros((3, 3))]},
                         window.obj_display_mode)
            o.current_obj_index = len(o.obj_name) - 1
            o.unmerge_objects()
            self.assertEqual(o.obj_name[-1], "old - piece")
            o.delete_objects([len(o.obj_name) - 1])

            # Edit marks: refused while unmapped marks of that kind exist.
            window.working_img_data["img-drawing"] = [[1.0, 1.0]]
            self.assertFalse(window.edit_mapped_marks(record.unit_id))
            window.working_img_data["img-drawing"] = []
            self.assertTrue(window.edit_mapped_marks(record.unit_id))
            self.assertEqual(window.working_img_data["img-drawing"], drawing)

            def overlay_count():
                return len(window._kept_marks_item.getData()[0])

            def kept(kinds):
                return sum(len(r.source["points"]) for r in window.kept_marks()
                           if r.kind in kinds)

            # The drawing being edited is no longer shown as kept.
            self.assertEqual(overlay_count(), kept({"contour"}))
            window.working_img_data["img-drawing"][0] = [7.0, 7.0]
            window.transform_accept()
            again = window.mapping_ledger.get(window.section_id, "drawing")
            self.assertEqual((again.unit_id, again.revision), (record.unit_id, 3))
            self.assertEqual(again.source["points"][0].tolist(), [7.0, 7.0])
            self.assertEqual(overlay_count(), kept({"contour", "drawing"}))

            # Records of a section that is no longer loaded cannot be changed.
            other = root / "other.png"
            cv2.imwrite(str(other), image)
            self.assertTrue(window.load_single_image_file(str(other), ".png"))
            self.assertIsNone(window.update_mapping(record.unit_id))
            self.assertFalse(window.edit_mapped_marks(record.unit_id))

    @isolated_gui_test
    def test_map_parts_and_build_undo_and_redo_together(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "section.png"
            image = np.zeros((32, 24, 3), dtype=np.uint8)
            image[4:28, 4:20] = 200
            cv2.imwrite(str(source), image)
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            history = window.undo_history
            self.assertIsNone(history.undo_label())
            contour = [[6.0, 6.0], [18.0, 6.0], [18.0, 26.0]]
            window.working_img_data["img-contour"] = [list(p) for p in contour]
            window.transfer_to_atlas_clicked()
            window.transform_accept()
            self.assertEqual(history.undo_label(), "Map contour")
            window.sync_mapping_undo_actions()
            self.assertEqual(window.actionUndo_Mapping.text(), "Undo Map contour")
            mapped = [list(p) for p in window.working_atlas_data["atlas-contour"]]
            window.make_object_pieces()
            self.assertEqual(history.undo_label(), "Make parts")
            window.merge_contour()
            self.assertEqual(history.undo_label(), "Build contours")
            o = window.object_ctrl
            self.assertEqual(o.obj_type, ["merged contour"])

            # Undo Build restores the part and its origin.
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, ["contour piece"])
            record = window.mapping_ledger.get(window.section_id, "contour")
            self.assertEqual(o.obj_derivation, [[[record.unit_id, 1]]])
            # Undo Make parts restores the atlas marks.
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, [])
            np.testing.assert_allclose(window.working_atlas_data["atlas-contour"], mapped)
            self.assertIsNotNone(window.atlas_marks_origin("contour"))
            # Undo Map restores the section's marks and removes the record.
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(window.working_img_data["img-contour"], contour)
            self.assertEqual(window.working_atlas_data["atlas-contour"], [])
            self.assertEqual(len(window.mapping_ledger), 0)
            self.assertEqual(len(window._kept_marks_item.getData()[0]), 0)
            self.assertFalse(window.undo_mapping_step())

            # Redo replays all three, in order.
            for label in ("Map contour", "Make parts", "Build contours"):
                self.assertEqual(history.redo_label(), label)
                self.assertTrue(window.redo_mapping_step())
            self.assertEqual(o.obj_type, ["merged contour"])
            self.assertEqual(len(window.mapping_ledger), 1)

            # A new action clears redo; an action that changes nothing is not
            # recorded; loading a section starts a fresh history.
            window.undo_mapping_step()
            window.merge_contour()
            self.assertIsNone(history.redo_label())
            window.make_object_pieces()
            self.assertEqual(history.undo_label(), "Build contours")
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            self.assertIsNone(history.undo_label())

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
    def test_a_pencil_click_without_a_stroke_saves_and_reopens(self):
        from driftlessmap.persistence import save_driftlessmap_file

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "histology.png"
            cv2.imwrite(str(source), np.full((30, 40, 3), 80, dtype=np.uint8))
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.tool_box.checkable_btn_dict["pencil_btn"].setChecked(True)
            window.img_stacks_clicked((5.0, 6.0))
            self.assertIn("img-drawing", window.layer_ctrl.layer_link)
            # The layer exists but its line holds no points yet.
            window.image_view.img_stacks.image_dict["img-drawing"].clear()
            project = root / "pencil.dmap"
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(project), "")):
                self.assertTrue(window.save_project_called())
            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            index = payload["layer_data"]["layer_link"].index("img-drawing")
            self.assertEqual(list(payload["layer_data"]["2d_data"][index]), [])

            # Projects saved before the fix stored [None, None]; they open too.
            payload["layer_data"]["2d_data"][index] = [None, None]
            old = root / "old.dmap"
            save_driftlessmap_file(old, payload, "project")
            restored = self.create_window()
            prepared = restored.prepare_project_sources(
                load_driftlessmap_file(old, "project")[0], str(old))
            restored.current_project_path = str(old)
            restored.load_project(prepared)
            self.assertIn("img-drawing", restored.layer_ctrl.layer_link)
            self.assertEqual(restored.interface_state, {})

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
            self.assertEqual(window.working_atlas_data["cell_count"], [0] * CELL_COUNT_SLOTS)

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
        from driftlessmap.project_io import CELL_COUNT_SLOTS

        self.assertEqual(merged["cell_count"], [0] * CELL_COUNT_SLOTS)
        self.assertEqual(merged["ruler_path"], [])
        # Five-entry counts from 1.x projects are kept and padded.
        old_counts = DriftlessMap._with_defaults(defaults, {"cell_count": [1, 2, 3, 4, 5]})
        self.assertEqual(old_counts["cell_count"][:5], [1, 2, 3, 4, 5])
        self.assertEqual(len(old_counts["cell_count"]), CELL_COUNT_SLOTS)

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

    @isolated_gui_test
    def test_lasso_closes_near_its_first_point_and_crops(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "histology.png"
            cv2.imwrite(str(source), np.full((300, 400, 3), 80, dtype=np.uint8))
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            # Fit the image in the view, as the shown window does.
            window.image_view.img_stacks.vb.setRange(xRange=(0, 400), yRange=(0, 300), padding=0)
            window.tool_box.checkable_btn_dict["lasso_btn"].setChecked(True)
            for point in ((100.0, 50.0), (300.0, 60.0), (280.0, 200.0)):
                window.img_stacks_clicked(point)
            # Clicking a drawn point other than the first keeps the lasso.
            window.lasso_points_clicked(None, [SimpleNamespace(index=lambda: 2)])
            self.assertEqual(len(window.working_img_data["lasso_path"]), 3)
            self.assertFalse(window.img_lasso_is_closure)
            # The first point closes it even when the overlapping last one is
            # listed first, as pyqtgraph does.
            window.lasso_points_clicked(
                None, [SimpleNamespace(index=lambda: 3), SimpleNamespace(index=lambda: 0)])
            self.assertTrue(window.img_lasso_is_closure)
            self.assertEqual(window.working_img_data["lasso_path"][-1], [100.0, 50.0])

            # A click a few image pixels from the first point closes a lasso.
            window.inactive_lasso()
            for point in ((100.0, 50.0), (300.0, 60.0), (280.0, 200.0), (104.0, 53.0)):
                window.img_stacks_clicked(point)
            self.assertTrue(window.img_lasso_is_closure)
            self.assertEqual(len(window.working_img_data["lasso_path"]), 4)

            # Crop closes an open lasso itself and crops to its bounds.
            window.inactive_lasso()
            for point in ((100.0, 50.0), (300.0, 60.0), (280.0, 200.0)):
                window.img_stacks_clicked(point)
            window.cut_image()
            self.assertEqual(window.image_view.processing_img.shape[:2], (151, 201))
            self.assertEqual(window.working_img_data["lasso_path"], [])

            # The cropped section is still drawn: its channels add up on the
            # black background instead of switching to Overlay (black).
            from PyQt6.QtGui import QPainter
            for channel in window.image_view.img_stacks.image_list[
                    :window.image_view.image_file.n_channels]:
                self.assertEqual(channel.paintMode,
                                 QPainter.CompositionMode.CompositionMode_Plus)

            # Without a lasso, crop explains what to do and changes nothing.
            with patch.object(window, "print_message") as message:
                window.cut_image()
            self.assertIn("Draw a lasso", message.call_args[0][0])

    @isolated_gui_test
    def test_click_dispatch_reaches_each_tool(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            source = root / "histology.png"
            cv2.imwrite(str(source), np.full((30, 40, 3), 80, dtype=np.uint8))
            self.assertTrue(window.load_single_image_file(str(source), ".png"))
            window.reset_corners_hist()
            buttons = window.tool_box.checkable_btn_dict

            buttons["ruler_btn"].setChecked(True)
            window.img_stacks_clicked((5.0, 6.0))
            window.img_stacks_clicked((15.0, 16.0))
            self.assertEqual(len(window.working_img_data["ruler_path"]), 2)
            buttons["ruler_btn"].setChecked(False)

            buttons["triang_btn"].setChecked(True)
            before = len(window.atlas_tri_inside_data)
            window.atlas_stacks_clicked((10.0, 12.0))
            self.assertEqual(len(window.atlas_tri_inside_data), before + 1)
            buttons["triang_btn"].setChecked(False)

            buttons["probe_btn"].setChecked(True)
            window.atlas_stacks_clicked((8.0, 9.0))
            self.assertEqual(len(window.working_atlas_data["atlas-probe"]), 1)

    @isolated_gui_test
    def test_suggested_section_is_applied_to_the_views(self):
        from driftlessmap.atlas_matching import atlas_slice
        from driftlessmap.section_suggestion_dialog import SectionSuggestionDialog

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            view = window.atlas_view
            target = int(view.origin_3d[0]) + 5
            slice_ = atlas_slice(view.atlas_data, "sagittal", target).astype(np.float32)
            section = cv2.resize(slice_, None, fx=6, fy=6)
            section = np.rot90(section)  # the histology arrives rotated
            path = root / "section.png"
            cv2.imwrite(str(path), np.dstack([section] * 3).astype(np.uint8))
            self.assertTrue(window.load_single_image_file(str(path), ".png"))
            before = window.image_view.current_img.shape

            chosen = []
            original_choice = SectionSuggestionDialog.choice

            def record(dialog):
                chosen.append(original_choice(dialog))
                return chosen[-1]

            # Without a plane, the user is asked; cancelling runs nothing.
            from PyQt6.QtWidgets import QInputDialog
            with patch.object(QInputDialog, "getItem", return_value=("", False)) as ask, \
                    patch("driftlessmap.app.run_in_background") as search:
                window.suggest_atlas_section()
            ask.assert_called_once()
            search.assert_not_called()

            with patch.object(SectionSuggestionDialog, "exec", return_value=1), patch.object(
                SectionSuggestionDialog, "choice", record
            ):
                window.suggest_atlas_section(plane="sagittal")
            self.assertEqual(window.section_plane, "sagittal")

            plane, index, _orientation, tilt, _rotate = chosen[0]
            self.assertEqual(plane, "sagittal")
            self.assertTrue(view.section_rabnt2.isChecked())
            self.assertEqual(window.atlas_display, "sagittal")
            # The fixture brain is uniform in ML, so depth itself is arbitrary;
            # what matters is that the chosen suggestion is applied exactly.
            self.assertEqual(view.current_sagital_index, index)
            self.assertAlmostEqual(view.srotation_ctrl.h_spinbox.value(), tilt[0])
            self.assertAlmostEqual(view.srotation_ctrl.v_spinbox.value(), tilt[1])
            # the histology was turned back to the atlas orientation
            self.assertEqual(window.image_view.current_img.shape[:2], before[:2][::-1])

    @isolated_gui_test
    def test_proposed_landmarks_fill_the_triangulation_tool(self):
        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap.atlas_matching import atlas_slice

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self._window_with_volume_atlas(root)
            view = window.atlas_view
            view.section_rabnt2.setChecked(True)
            index = int(view.origin_3d[0])
            view.spage_ctrl.set_val(index)
            slice_ = atlas_slice(view.atlas_data, "sagittal", index).astype(np.float32)
            section = cv2.resize(slice_, None, fx=6, fy=6, interpolation=cv2.INTER_LINEAR)
            path = root / "section.png"
            cv2.imwrite(str(path), np.dstack([section] * 3).astype(np.uint8))
            self.assertTrue(window.load_single_image_file(str(path), ".png"))
            window.reset_corners_hist()
            window.reset_tri_points_atlas()

            window.propose_registration_landmarks()
            atlas = np.asarray(window.atlas_tri_inside_data)
            histology = np.asarray(window.histo_tri_inside_data)
            self.assertGreaterEqual(len(atlas), 3)
            self.assertEqual(len(atlas), len(histology))
            errors = np.linalg.norm(histology - atlas * 6, axis=1)
            self.assertLess(np.median(errors), 6.0)  # within one atlas pixel
            self.assertTrue(window.tool_box.checkable_btn_dict["triang_btn"].isChecked())
            self.assertEqual(len(window.working_atlas_text), len(atlas))
            self.assertIsNotNone(window.triangulation_registration)

            # Existing landmarks are only replaced after confirmation.
            before = list(window.atlas_tri_inside_data)
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                window.propose_registration_landmarks()
            self.assertEqual(window.atlas_tri_inside_data, before)

if __name__ == "__main__":
    unittest.main()
