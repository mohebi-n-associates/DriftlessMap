import os
import subprocess
import sys
import tempfile
import unittest
from functools import wraps
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
V2_TEST_CHILD = os.environ.get("DRIFTLESSMAP_V2_TEST_CHILD") == "1"

import numpy as np

from driftlessmap.v2 import channel_display

if V2_TEST_CHILD:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QAbstractButton, QApplication, QPushButton

    from driftlessmap.v2.shell import V2Window


def isolated_gui_test(test):
    """Run each shell case in its own Qt process (OpenGL teardown is fragile)."""

    @wraps(test)
    def wrapper(self):
        if V2_TEST_CHILD:
            return test(self)
        environment = os.environ.copy()
        environment["DRIFTLESSMAP_V2_TEST_CHILD"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "tests.test_v2_shell.{}".format(test.__qualname__)],
            check=False, capture_output=True, text=True, env=environment,
        )
        self.assertEqual(result.returncode, 0, "{}\n{}".format(result.stdout, result.stderr))

    return wrapper


class BrightnessContrastTests(unittest.TestCase):
    def test_window_round_trip(self):
        for black, white in ((0, 65535), (1000, 5000), (30000, 30100), (0, 255)):
            limit = 65535 if white > 255 else 255
            b, c = channel_display.brightness_contrast(black, white, limit)
            low, high = channel_display.window_from_brightness_contrast(b, c, limit)
            self.assertAlmostEqual(low, black, delta=limit * 1e-6 + 1e-6)
            self.assertAlmostEqual(high, white, delta=limit * 1e-6 + 1e-6)

    def test_full_range_is_neutral(self):
        self.assertEqual(channel_display.brightness_contrast(0, 255, 255), (50.0, 50.0))


class NativeDialogTests(unittest.TestCase):
    def test_file_dialogs_use_the_operating_system_dialog(self):
        package = Path(__file__).resolve().parent.parent / "driftlessmap"
        offenders = [str(path.relative_to(package)) for path in package.rglob("*.py")
                     if "DontUseNativeDialog" in path.read_text(encoding="utf-8")]
        self.assertEqual(offenders, [])


class V2ShellTests(unittest.TestCase):
    @isolated_gui_test
    def test_loaded_document_navigation_does_not_mark_work_dirty(self):
        import cv2
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            root = Path(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            source = root / "section.png"
            cv2.imwrite(str(source), np.zeros((32, 24, 3), dtype=np.uint8))
            self.assertTrue(engine.load_single_image_file(str(source), ".png"))
            window.mark_saved()
            for step in ("project", "section", "match", "register", "annotate", "results"):
                window.go_to(step)
                self.assertFalse(window.is_dirty(), step)
            for view in ("compare", "atlas", "section", "3d", "multi", "compare"):
                window.set_view(view)
                self.assertFalse(window.is_dirty(), view)

    @isolated_gui_test
    def test_saved_work_edits_are_dirty_and_idle_refresh_does_not_rescan(self):
        import cv2
        from unittest.mock import patch
        from PyQt6.QtWidgets import QMessageBox

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            engine = window.engine
            source = str(Path(folder) / "section.png")
            cv2.imwrite(source, np.zeros((32, 24, 3), dtype=np.uint8))
            self.assertTrue(engine.load_single_image_file(source, ".png"))
            window.mark_saved()
            fiber = engine.add_implant("fiber")
            self.assertTrue(window.is_dirty())
            window.mark_saved()
            engine.set_implant_outline(fiber.implant_id, [[1, 1], [5, 1], [5, 5]])
            self.assertTrue(window.is_dirty())
            window.mark_saved()
            engine.set_implant_specs(fiber.implant_id, {"diameter_um": 400})
            self.assertTrue(window.is_dirty())
            engine.working_img_data["img-cells"] = [[float(i), float(i)] for i in range(100)]
            window.mark_saved()
            engine.working_img_data["img-cells"][-1] = [5., 6.]
            self.assertTrue(window.is_dirty())
            engine.image_view.current_img[0, 0, 0] = 100
            window.mark_saved()
            engine.image_view.current_img[0, 0, 0] = 0
            engine.image_view.current_img[0, 1, 0] = 100
            self.assertTrue(window.is_dirty())
            window.mark_saved()
            engine.site_face = (engine.site_face + 1) % 4
            self.assertTrue(window.is_dirty())
            window.mark_saved()
            with patch.object(window, "_digest", side_effect=ValueError("bad state")):
                self.assertTrue(window.is_dirty())
                with patch("driftlessmap.v2.shell.QMessageBox.question",
                           return_value=QMessageBox.StandardButton.Cancel) as question:
                    self.assertFalse(window.confirm_discard("close"))
                    question.assert_called_once()
            window.mark_saved()
            with patch.object(window, "_digest", wraps=window._digest) as digest:
                window.refresh()
                window.refresh()
                digest.assert_not_called()

    @classmethod
    def setUpClass(cls):
        cls.application = (QApplication.instance() or QApplication([])) if V2_TEST_CHILD else None

    def make_window(self, folder):
        settings = QSettings(str(Path(folder) / "v2.ini"), QSettings.Format.IniFormat)
        window = V2Window(settings)
        self.addCleanup(self._close, window)
        return window

    def _close(self, window):
        window.mark_saved()
        window.close()
        window.deleteLater()
        self.application.processEvents()

    @isolated_gui_test
    def test_every_1x_menu_command_is_reachable(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            names = {c.name for c in window.registry.all()}
            engine_actions = [a for a in window.engine.findChildren(QAction)
                              if a.text().replace("&", "").strip() and not a.isSeparator()
                              and a.menu() is None and not a.property("classic_only")]
            reachable = {c.handler for c in window.registry.all()}
            for action in engine_actions:
                with self.subTest(action.text()):
                    self.assertIn(action.trigger, reachable)
            self.assertIn("Suggest landmarks", names)
            # The preview offers the classic interface, not another preview.
            self.assertIn("Open the classic interface", names)
            self.assertNotIn("Open the 2.0 Preview", names)
            self.assertIn(window.engine.actionOpen_Preview, window.engine.menuHelp.actions())
            merge = [c.name for c in window.registry.search("merge")]
            self.assertIn("Build 3D probe", merge)
            self.assertIn("Suggest landmarks",
                          [c.name for c in window.registry.search("triangulation")])
            # Unavailable commands explain why instead of running.
            self.assertIn("volume atlas", window.registry.run("match.find"))

    @isolated_gui_test
    def test_navigation_is_not_a_change_but_recipes_are(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            self.assertFalse(window.is_dirty())
            for step in ("project", "section", "match", "register", "annotate", "results"):
                window.go_to(step)
            for view in ("compare", "atlas", "section", "3d", "multi"):
                window.set_view(view)
            window.toggle_theme()
            self.assertFalse(window.is_dirty())
            from driftlessmap.registration_input import RegistrationInput
            window.engine.registration_input = RegistrationInput.legacy()
            self.assertTrue(window.is_dirty())

    @isolated_gui_test
    def test_channel_rows_drive_display_and_registration_only(self):
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "six.ome.tif"
            rng = np.random.default_rng(2)
            data = rng.integers(100, 50000, (6, 30, 40), dtype=np.uint16)
            names = ["DAPI", "GFP", "Tracer", "NeuN", "Iba1", "Olig2"]
            tifffile.imwrite(path, data, ome=True,
                             metadata={"axes": "CYX", "Channel": {"Name": names}})
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            window.go_to("section")
            panel = window.panels["section"]
            panel.refresh()
            self.assertEqual(len(panel._rows), 6)
            self.assertEqual([row["name"].text() for row in panel._rows], names)
            raw = engine.image_view.current_img.copy()

            # Registration channels: DAPI and NeuN, independent of visibility.
            panel._rows[0]["register"].setChecked(True)
            panel._rows[3]["register"].setChecked(True)
            self.assertEqual(engine.registration_input.channels, (0, 3))
            self.assertEqual(engine.registration_input.channel_names, ("DAPI", "NeuN"))
            panel._rows[3]["show"].setChecked(False)
            self.assertFalse(engine.image_view.channel_visible[3])
            self.assertEqual(engine.registration_input.channels, (0, 3))

            # Display range and gamma change the lookup table, never the pixels.
            panel._select(2)
            panel._auto()
            black, white, gamma = channel_display.channel_levels(engine.image_view, 2)
            self.assertGreater(black, float(data[2].min()) - 1)
            self.assertLess(white, float(data[2].max()) + 1)
            channel_display.set_channel_levels(engine.image_view, 2, 2000, 9000, 1.5)
            self.assertEqual(channel_display.channel_levels(engine.image_view, 2),
                             (2000.0, 9000.0, 1.5))
            table = engine.image_view.curve_widget.table_output[2]
            self.assertEqual(int(table[2000]), 0)
            self.assertEqual(int(table[9000]), 65535)
            np.testing.assert_array_equal(engine.image_view.current_img, raw)

            # Legacy mode ignores the ticks; ticking again returns to channels.
            panel.reg_mode.setCurrentIndex(1)
            self.assertEqual(engine.registration_input.mode, "legacy")
            panel.reg_mode.setCurrentIndex(0)
            self.assertEqual(engine.registration_input.channels, (0, 3))

            # Renaming changes the display name, not the channel index.
            panel._rows[0]["name"].setText("Hoechst")
            panel._rename(0, "Hoechst")
            self.assertEqual(engine.image_view.image_file.channel_name[0], "Hoechst")
            self.assertEqual(engine.registration_input.channel_names, ("Hoechst", "NeuN"))


    @isolated_gui_test
    def test_actions_that_need_data_are_disabled_with_a_reason(self):
        import tifffile
        from PyQt6.QtWidgets import QPushButton

        def find(panel, text):
            return next(b for b in panel.findChildren(QPushButton) if b.text() == text)

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            engine = window.engine
            window.go_to("register")
            register = window.panels["register"]
            card, _reason = register._requirement
            self.assertTrue(card.isVisibleTo(register))
            suggest = find(register, "Suggest landmarks")
            self.assertFalse(suggest.isEnabled())
            self.assertIn("Load", suggest.toolTip())
            self.assertFalse(find(register, "Mark review complete").isEnabled())
            # Nothing loaded: a starting card replaces the empty 1.x views.
            self.assertTrue(window.empty_canvas.isVisibleTo(window))
            self.assertFalse(window.views.isVisibleTo(window))
            self.assertTrue(window.objects_empty.isVisibleTo(window.inspector_tabs.widget(0)))
            self.assertFalse(engine.object_ctrl.outer_frame.isVisibleTo(window))

            path = Path(folder) / "two.ome.tif"
            data = np.random.default_rng(3).integers(0, 4000, (2, 30, 40), dtype=np.uint16)
            tifffile.imwrite(path, data, ome=True, metadata={"axes": "CYX"})
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            window.refresh()
            self.assertFalse(window.empty_canvas.isVisibleTo(window))
            self.assertTrue(window.views.isVisibleTo(window))
            # A section alone enables the Section step but not atlas matching.
            window.go_to("section")
            self.assertTrue(find(window.panels["section"], "Auto").isEnabled())
            window.go_to("match")
            self.assertFalse(find(window.panels["match"], "Find atlas section").isEnabled())
            window.go_to("register")
            self.assertTrue(card.isVisibleTo(register))
            self.assertIn("atlas", register._requirement_text.text())
            window.go_to("annotate")
            self.assertTrue(find(window.panels["annotate"], "Cells").isEnabled())
            self.assertFalse(find(window.panels["annotate"], "Map to atlas").isEnabled())

    @isolated_gui_test
    def test_section_step_reads_another_time_plane(self):
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tzcyx.tif"
            data = np.zeros((3, 2, 2, 10, 12), dtype=np.uint16)
            for t in range(3):
                data[t] = 10 * (t + 1)
            tifffile.imwrite(path, data, imagej=True, metadata={"axes": "TZCYX"})
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            engine.current_img_path = str(path)
            window.go_to("section")
            panel = window.panels["section"]
            panel.refresh()
            self.assertTrue(panel.planes_host.isVisibleTo(panel))
            box = panel._plane_boxes["T"]
            self.assertEqual((box.minimum(), box.maximum(), box.value()), (1, 3, 1))
            box.setValue(3)
            panel._read_planes()
            self.assertEqual(engine.image_view.image_file.fixed_axes, {"T": 2})
            self.assertTrue(np.all(engine.image_view.current_img == 30))
            panel.refresh()
            self.assertEqual(panel._plane_boxes["T"].value(), 3)

    @isolated_gui_test
    def test_adopted_1x_controls_follow_the_light_theme(self):
        from PyQt6.QtGui import QColor, QImage, QPixmap

        from driftlessmap.v2 import adopted

        image = QImage(3, 1, QImage.Format.Format_ARGB32)
        image.setPixelColor(0, 0, QColor(255, 255, 255, 255))
        image.setPixelColor(1, 0, QColor(105, 159, 76, 255))
        image.setPixelColor(2, 0, QColor(0, 0, 0, 0))
        result = adopted.recolour_white(QPixmap.fromImage(image), "#1a1e23").toImage()
        self.assertEqual(result.pixelColor(0, 0).name(), "#1a1e23")
        self.assertEqual(result.pixelColor(1, 0).name(), "#699f4c")
        self.assertEqual(result.pixelColor(2, 0).alpha(), 0)

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            window.apply_theme("light")
            engine = window.engine
            self.assertNotIn("rgb(50, 50, 50)", engine.toolbar.styleSheet())
            self.assertNotIn("color: white", engine.atlas_view.label_tree.styleSheet())
            self.assertEqual(engine.atlas_view.show_boundary_btn.styleSheet(), "")
            # Region boundaries need an atlas; the View menu tick stays truthful.
            window.boundaries_item.trigger()
            self.assertFalse(engine.atlas_view.show_boundary_btn.isChecked())
            self.assertFalse(window.boundaries_item.isChecked())
            # Switching back and forth recolours from the original icons.
            window.apply_theme("dark")
            window.apply_theme("light")
            icons = [b for b in engine.toolbar.findChildren(QAbstractButton)
                     if getattr(b, "_v2_original_icon", None) is not None]
            self.assertTrue(icons)

    @isolated_gui_test
    def test_buttons_respond_at_once_and_drop_clicks_queued_while_busy(self):
        import time

        from types import SimpleNamespace

        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
        from driftlessmap.v2.widgets import button, respond

        def press(stamp):
            # Only the window-system timestamp of the input matters.
            return SimpleNamespace(timestamp=lambda: stamp)

        cursors, runs = [], []

        def slow():
            cursors.append(QApplication.overrideCursor().shape())
            runs.append(1)
            time.sleep(0.3)

        widget = button("Slow", slow)
        self.assertFalse(respond.seen(press(10_000)))  # the click that starts it
        widget.click()
        self.assertEqual(cursors, [Qt.CursorShape.WaitCursor])
        self.assertIsNone(QApplication.overrideCursor())
        # Presses made while it held the window are dropped; later ones are not.
        self.assertTrue(respond.seen(press(10_200)))
        self.assertFalse(respond.seen(press(11_000)))

        # An action that waits in a dialog blocks nothing, and the dialog's own
        # buttons still work.
        inner = button("Inner", lambda: runs.append("inner"))

        def asks():
            respond.window_shown()  # what the shell does when a modal opens
            inner.click()
            time.sleep(0.3)

        self.assertFalse(respond.seen(press(20_000)))
        button("Asks", asks).click()
        self.assertIn("inner", runs)
        self.assertFalse(respond.seen(press(20_200)))

    @isolated_gui_test
    def test_theme_is_set_on_the_window_and_follows_separate_windows(self):
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from driftlessmap.v2.theme import stylesheet

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            window.apply_theme("dark")
            # An application stylesheet restyles every widget of the program,
            # hidden ones included, which made switching slow.
            self.assertEqual(QApplication.instance().styleSheet(), "")
            self.assertEqual(window.styleSheet(), stylesheet("dark"))
            box = QMessageBox(QMessageBox.Icon.Information, "Title", "Text")
            box.show()
            QApplication.processEvents()
            self.assertEqual(box.styleSheet(), stylesheet("dark"))
            window.apply_theme("light")
            self.assertEqual(box.styleSheet(), stylesheet("light"))
            box.close()
            box.deleteLater()

    @isolated_gui_test
    def test_annotate_lists_mapped_marks_and_flags_out_of_date_ones(self):
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                Path(folder) / "atlas"))))
            image = np.zeros((32, 24, 3), dtype=np.uint8)
            image[4:28, 4:20] = 200
            cv2.imwrite(str(Path(folder) / "s.png"), image)
            self.assertTrue(engine.load_single_image_file(str(Path(folder) / "s.png"), ".png"))
            engine.working_img_data["img-drawing"] = [[6.0, 6.0], [18.0, 20.0]]
            engine.transfer_to_atlas_clicked()
            engine.transform_accept()
            window.go_to("annotate")
            panel = window.panels["annotate"]
            panel.refresh()
            self.assertEqual(panel.mapped_list.count(), 1)
            self.assertEqual(panel.mapped_list.item(0).text(), "Drawing · 2 marks · current")
            engine.atlas_view.current_coronal_index += 1
            panel.refresh()
            self.assertTrue(panel.mapped_list.item(0).text().startswith("⚠ Drawing"))
            from driftlessmap.v2 import state
            self.assertIn("1 mapping out of date", state.step_status(engine)["annotate"])

            update = next(b for b in panel.findChildren(QPushButton)
                          if b.text() == "Update mapping")
            panel.mapped_list.setCurrentRow(-1)
            panel.apply_gates()
            self.assertFalse(update.isEnabled())
            panel.mapped_list.setCurrentRow(0)
            panel.apply_gates()
            self.assertTrue(update.isEnabled())
            panel.update_selected()
            panel.refresh()
            self.assertEqual(panel.mapped_list.item(0).text(), "Drawing · 2 marks · current")
            self.assertEqual(panel.selected_unit(), panel.mapped_list.item(0).data(
                Qt.ItemDataRole.UserRole))
            record = engine.mapping_ledger.records()[0]
            self.assertEqual(record.revision, 2)
            window._name_undo_steps()
            self.assertEqual(window.undo_step_item.text(), "Undo Update mapping")
            self.assertIsNone(window.registry.run("edit.undo_step"))
            self.assertEqual(engine.mapping_ledger.records()[0].revision, 1)
            window._name_undo_steps()
            self.assertEqual(window.redo_step_item.text(), "Redo Update mapping")
            window.run("edit.redo_step")
            self.assertEqual(engine.mapping_ledger.records()[0].revision, 2)
            panel.refresh()
            panel.mapped_list.setCurrentRow(0)
            panel.edit_selected()
            self.assertEqual(engine.working_img_data["img-drawing"], [[6.0, 6.0], [18.0, 20.0]])
            self.assertIn("Edit mapped marks", [c.name for c in window.registry.all()])

    @isolated_gui_test
    def test_implants_card_outlines_maps_and_builds_a_fiber(self):
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                Path(folder) / "atlas"))))
            image = np.full((32, 24, 3), 120, dtype=np.uint8)
            image[4:20, 10:14] = 240           # a bright track
            cv2.imwrite(str(Path(folder) / "s.png"), image)
            self.assertTrue(engine.load_single_image_file(str(Path(folder) / "s.png"), ".png"))
            window.go_to("annotate")
            panel = window.panels["annotate"]
            card = panel.implants
            from unittest.mock import patch

            from PyQt6.QtWidgets import QInputDialog, QLabel

            from driftlessmap.v2.widgets import Card
            self.assertIn("Nothing yet", card.active.text())
            self.assertIn("Add implant (fiber, microprism, probe)…",
                          [c.name for c in window.registry.search("optical fiber")])

            fiber = engine.add_implant("fiber", specs={"diameter_um": 100})
            engine.add_implant("prism")
            card.probe_card.new_probe()
            card.refresh(select=fiber.implant_id)
            self.assertEqual(card.list.count(), 3)
            self.assertIn("probe · no sections yet", card.list.item(2).text())
            self.assertEqual(card.implant(), fiber)
            self.assertFalse(card.map_button.isEnabled())

            # Draw by clicking; clicking the first vertex again closes it.
            card.draw.setChecked(True)
            card._mode("draw")
            editor = card.editor
            for x, y in ([10.0, 4.0], [14.0, 4.0], [14.0, 20.0], [10.0, 20.0], [10.0, 4.0]):
                editor._clicked((x, y))
            self.assertIsNone(editor.mode)
            np.testing.assert_allclose(engine.implant_outline(fiber.implant_id)["points"],
                                       [[10, 4], [14, 4], [14, 20], [10, 20]])
            self.assertIsNotNone(editor._roi)
            card.point.setChecked(True)
            card._mode("point")
            editor._clicked((12.0, 19.5))
            self.assertEqual(engine.implant_outline(fiber.implant_id)["point"], [12.0, 19.5])
            card.refresh()
            self.assertTrue(card.map_button.isEnabled())
            self.assertIn("tip marked", card.outline_state.text())

            # Propose outlines the bright track from one click.
            card.propose.setChecked(True)
            card._mode("propose")
            editor._clicked((12.0, 10.0))
            proposed = np.asarray(engine.implant_outline(fiber.implant_id)["points"])
            self.assertTrue(np.all((proposed[:, 0] >= 9) & (proposed[:, 0] <= 15)))
            self.assertTrue(np.all((proposed[:, 1] >= 3) & (proposed[:, 1] <= 21)))

            card.map_section()
            self.assertEqual(engine.object_ctrl.obj_type, ["fiber piece"])
            self.assertIsNone(editor._roi)
            panel.refresh()
            self.assertEqual(panel.mapped_list.item(0).text(), "Fiber 1 · outline · current")
            card.build()
            self.assertEqual(engine.object_ctrl.obj_type, ["merged fiber"])
            card.refresh()
            self.assertTrue(card.report.text().startswith("Tip (marked tip)"))
            self.assertIn("built", card.list.item(0).text())

            self.assertTrue(card.probe_card.isHidden())

            # Selecting the probe row shows the probe controls in the same card.
            card.list.setCurrentRow(2)
            self.assertTrue(card.map_button.isHidden())
            self.assertFalse(card.probe_card.isHidden())
            self.assertEqual(card.probe_card.current(), "Probe 1")
            self.assertEqual(card.active.text(), "Probe 1 · Probe")
            self.assertIs(panel.probes, card.probe_card)

            # Rename and delete act on the selected probe; no separate Probes card.
            with patch.object(QInputDialog, "getText", return_value=("Probe L", True)):
                card.rename()
            self.assertEqual(card.current(), "probe:Probe L")
            self.assertEqual(card.probe_card.current(), "Probe L")
            card.delete()
            self.assertEqual(card.list.count(), 2)
            self.assertIsNone(card.probe_card.current())
            self.assertTrue(card.probe_card.isHidden())
            self.assertFalse(any(isinstance(w, Card) and w.findChild(QLabel, "CardTitle")
                                 and w.findChild(QLabel, "CardTitle").text() == "Probes"
                                 for w in panel.findChildren(Card)))

            # Mark track with a fiber selected starts a new probe and shows it.
            card.list.setCurrentRow(0)
            window.run("probe.mark")
            self.assertEqual(card.probe_card.current(), "Probe 1")
            self.assertEqual(card.current(), "probe:Probe 1")
            self.assertTrue(card.probe_card.mark.isChecked())
            window.clear_tools()

            # Export all results writes one new folder with everything available.
            from PyQt6.QtWidgets import QFileDialog
            results = window.panels["results"]
            with patch.object(QFileDialog, "getExistingDirectory", return_value=folder):
                results.export_all()
            exported = [p for p in Path(folder).iterdir() if " results " in p.name]
            self.assertEqual(len(exported), 1)
            self.assertTrue((exported[0] / "DriftlessMap.dmap").exists() or
                            (exported[0] / "project.dmap").exists())
            self.assertTrue((exported[0] / "objects" / "Fiber 1.dmapobj").exists())
            self.assertTrue((exported[0] / "implants.csv").exists())
            self.assertIn("Exported", results.export_status.text())

    @isolated_gui_test
    def test_3d_display_mode_switches_both_ways(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = self.make_window(folder).engine
            engine.action3D_Mode_Dark.trigger()
            self.assertEqual(engine.display_mode_3d, "light")
            self.assertEqual(engine.action3D_Mode_Dark.text(), "3D Mode: Light")
            engine.action3D_Mode_Dark.trigger()
            self.assertEqual(engine.display_mode_3d, "dark")
            self.assertEqual(engine.action3D_Mode_Dark.text(), "3D Mode: Dark")

    @isolated_gui_test
    def test_a_deleted_probe_leaves_no_marks_on_screen(self):
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((40, 30, 3), 120, dtype=np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            window.go_to("annotate")
            probes = window.panels["annotate"].implants.probe_card
            section_item = engine.image_view.img_stacks.image_dict["img-probe"]
            atlas_item = engine.atlas_view.working_atlas.image_dict["atlas-probe"]

            def drawn(item):
                return 0 if item.data is None else len(item.data)

            probes.new_probe("NP A")
            probes.toggle_marking()
            for point in ((13.0, 5.0), (14.0, 25.0)):
                engine.img_stacks_clicked(point)
            self.assertEqual(drawn(section_item), 2)
            probes.add_section()
            # Mapped marks are shown by the kept-marks overlay only.
            self.assertEqual(drawn(section_item), 0)
            self.assertEqual(drawn(atlas_item), 0)
            self.assertEqual(len(engine._kept_marks_item.data), 2)
            for point in ((12.0, 6.0), (13.0, 20.0)):
                engine.img_stacks_clicked(point)
            self.assertEqual(drawn(section_item), 2)

            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.Yes):
                probes.delete_probe()
            self.assertEqual(engine.working_img_data["img-probe"], [])
            self.assertEqual(drawn(section_item), 0)
            self.assertEqual(drawn(atlas_item), 0)
            self.assertEqual(len(engine._kept_marks_item.data), 0)
            self.assertEqual(engine.object_ctrl.obj_name, [])

    @isolated_gui_test
    def test_a_saved_project_reopens_where_the_user_left_off(self):
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QFileDialog

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            image = np.full((40, 30, 3), 120, dtype=np.uint8)
            cv2.imwrite(str(root / "s.png"), image)
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            window.go_to("annotate")
            card = window.panels["annotate"].implants
            probes = card.probe_card

            # Probe A: one section mapped, then half of the next track marked.
            probes.new_probe("Probe A")
            probes.toggle_marking()
            for point in ((13.0, 5.0), (14.0, 25.0)):
                engine.img_stacks_clicked(point)
            probes.add_section()
            for point in ((13.0, 6.0), (13.5, 15.0)):
                engine.img_stacks_clicked(point)
            # Probe B added but nothing marked yet: unsaved work too.
            window.mark_saved()
            probes.new_probe("Probe B")
            self.assertTrue(window.is_dirty())
            # A fiber outline still being drawn.
            fiber = engine.add_implant("fiber")
            card.refresh(select=fiber.implant_id)
            card.draw.setChecked(True)
            card._mode("draw")
            for point in ((12.0, 4.0), (16.0, 4.0)):
                card.editor._clicked(point)
            window.set_view("section")

            path = root / "half.dmap"
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                window.run("project.save")
            self.assertFalse(window.is_dirty())

            reopened = self.make_window(folder)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
                reopened.run("project.open")
            engine = reopened.engine
            card = reopened.panels["annotate"].implants
            self.assertIs(reopened.stack.currentWidget(), reopened.panels["annotate"])
            self.assertTrue(reopened.view_buttons["section"].isChecked())
            self.assertEqual(engine.working_img_data["img-probe"], [[13.0, 6.0], [13.5, 15.0]])
            self.assertEqual(card.probe_card.book.names(), ["Probe A", "Probe B"])
            self.assertEqual(card.probe_card.book.summary("Probe A"), "1 section · not built")
            self.assertEqual(card.current(), fiber.implant_id)
            self.assertEqual(card.editor.mode, "draw")
            self.assertEqual(card.editor.vertices, [[12.0, 4.0], [16.0, 4.0]])
            self.assertFalse(reopened.is_dirty())
            for point in ((16.0, 28.0), (12.0, 28.0), (12.0, 4.0)):
                card.editor._clicked(point)
            self.assertEqual(len(engine.implant_outline(fiber.implant_id)["points"]), 4)

            # Probe A selected with Mark track on comes back the same way.
            card.refresh(select="probe:Probe A")
            card.probe_card.toggle_marking()
            with patch.object(QFileDialog, "getSaveFileName", return_value=(str(path), "")):
                reopened.run("project.save")
            again = self.make_window(folder)
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
                again.run("project.open")
            again_card = again.panels["annotate"].implants
            self.assertEqual(again_card.current(), "probe:Probe A")
            self.assertTrue(again.engine.tool_box.checkable_btn_dict["probe_btn"].isChecked())
            self.assertTrue(again_card.probe_card.mark.isChecked())

    @isolated_gui_test
    def test_allen_download_dialog_reuses_verified_files(self):
        import json
        from unittest.mock import patch

        from driftlessmap.v2.allen_download_dialog import AllenDownloadDialog

        with tempfile.TemporaryDirectory() as folder:
            dialog = AllenDownloadDialog()
            self.addCleanup(dialog.deleteLater)
            dialog.vs_rabnt3.setChecked(True)
            dialog.vs_rabnt2.setChecked(True)
            radios = (dialog.vs_rabnt1, dialog.vs_rabnt2, dialog.vs_rabnt3)
            self.assertEqual([r.isChecked() for r in radios], [False, True, False])
            self.assertEqual(dialog.voxel_size, 25)
            # Only files recorded in the manifest for the same URL count as done.
            for local in (dialog.data_local, dialog.segmentation_local):
                Path(folder, local).write_bytes(b"x")
            Path(folder, "download_manifest.json").write_text(json.dumps(
                {dialog.data_local: {"url": dialog.data_url},
                 dialog.segmentation_local: {"url": "https://example.org/other"}}))
            dialog.saving_folder = folder
            dialog._scan_folder()
            self.assertEqual(dialog.finish[:2], [True, False])
            started = []
            with patch.object(dialog, "start_thread",
                              side_effect=lambda url, local, setter: started.append(local)), \
                    patch.object(dialog, "download_mesh_start") as meshes:
                dialog.download_everything()
                self.assertEqual(started, [dialog.segmentation_local])
                dialog.set_segmentation_bar_value(100)
                dialog._refresh()
                meshes.assert_called_once()
            dialog.process_finished = True
            dialog.close()


if __name__ == "__main__":
    unittest.main()
