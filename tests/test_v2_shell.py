import tests.settings_isolation  # noqa: F401  (before the app reads settings)
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

from driftlessmap.v2 import channel_display, state

if V2_TEST_CHILD:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtGui import QAction, QKeySequence
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



def card_names(window):
    """Names listed in the Annotate step's Implants card."""
    card = window.panels["annotate"].implants
    return [i.name for i in window.engine.implants.implants()] + card.probe_card.book.names()

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
    def test_loading_a_section_shows_atlas_and_section_at_equal_widths(self):
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            window.resize(1480, 950)
            window.show()
            engine = window.engine
            splitter = engine.splitter_3

            def shown_widths():
                self.application.processEvents()
                return [size for size, shown in zip(splitter.sizes(), window._visible_views())
                        if shown]

            # Atlas first: it takes the whole canvas. Loading the section
            # switches the engine to atlas + section by itself.
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            window.refresh()
            self.assertEqual(len(shown_widths()), 1)
            source = root / "section.png"
            cv2.imwrite(str(source), np.full((60, 120, 3), 80, dtype=np.uint8))
            self.assertTrue(engine.load_single_image_file(str(source), ".png"))
            window.refresh()
            atlas_width, section_width = shown_widths()
            self.assertGreater(section_width, 200)
            self.assertLessEqual(abs(atlas_width - section_width), 0.05 * atlas_width)

            # Widths the user drags are kept until the visible views change.
            total = atlas_width + section_width
            shares = iter((total * 2 // 3, total // 3))
            splitter.setSizes([next(shares) if shown else 0
                               for shown in window._visible_views()])
            dragged = shown_widths()
            window.refresh()
            self.assertEqual(shown_widths(), dragged)
            window.set_view("section")
            window.refresh()
            window.set_view("compare")
            atlas_width, section_width = shown_widths()
            self.assertLessEqual(abs(atlas_width - section_width), 0.05 * atlas_width)

    @isolated_gui_test
    def test_match_step_names_the_sagittal_hemisphere_and_mirrors_the_page(self):
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            view = engine.atlas_view
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            window.go_to("match")
            panel = window.panels["match"]
            panel.refresh()
            self.assertFalse(panel.hemisphere_row.isVisibleTo(panel))   # coronal

            view.section_rabnt2.setChecked(True)
            midline = int(view.origin_3d[0])
            view.spage_ctrl.set_val(midline + 3)
            panel.refresh()
            self.assertTrue(panel.hemisphere_row.isVisibleTo(panel))
            self.assertTrue(panel.hemisphere.text().startswith("Right hemisphere"))
            self.assertIn("right hemisphere", state.plane_summary(engine))
            # A file named for the other side is pointed out.
            engine.current_img_path = str(root / "IM-1076_left_All_insertion.tif")
            panel.refresh()
            self.assertIn("The file name says left", panel.hemisphere.text())

            panel.show_other_hemisphere()
            self.assertEqual(int(view.current_sagital_index), midline - 3)
            panel.refresh()
            self.assertTrue(panel.hemisphere.text().startswith("Left hemisphere, 0.07"))
            self.assertNotIn("file name", panel.hemisphere.text())
            view.spage_ctrl.set_val(midline)
            panel.refresh()
            self.assertEqual(panel.hemisphere.text(), "At the midline.")

    @isolated_gui_test
    def test_focus_hides_and_restores_the_side_panels(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            window.resize(1400, 900)
            window.show()
            self.application.processEvents()
            self.assertEqual(window.registry.get("view.focus").shortcut, "Ctrl+Shift+F")

            def shown():
                return (window.task_column.isVisibleTo(window),
                        window.inspector_column.isVisibleTo(window))

            self.assertEqual(shown(), (True, True))
            window.run("view.focus")
            self.assertEqual(shown(), (False, False))
            self.assertTrue(window.focus_button.isChecked())
            self.assertTrue(window.focus_item.isChecked())
            self.assertIn("Side panels hidden", window.message_label.text())
            window.focus_button.click()
            self.assertEqual(shown(), (True, True))
            self.assertFalse(window.focus_button.isChecked())
            # Hiding both columns from the View menu counts as focus too, and
            # Focus then brings both back.
            window.toggle_task_item.setChecked(False)
            self.assertFalse(window.focus_button.isChecked())
            window.toggle_inspector_item.setChecked(False)
            self.assertTrue(window.focus_button.isChecked())
            window.run("view.focus")
            self.assertEqual(shown(), (True, True))

    def push(self, root, text):
        """Click the visible push button labelled ``text`` inside ``root``."""
        found = [b for b in root.findChildren(QPushButton) if b.text() == text]
        self.assertEqual(len(found), 1, text)
        self.assertTrue(found[0].isEnabled(), found[0].toolTip())
        found[0].click()
        self.application.processEvents()

    @staticmethod
    def document_fields(engine):
        """A digest of each saved field, the section identity left out (each
        document gets a new one)."""
        from driftlessmap.state_digest import state_digest

        payload = engine.project_payload()
        for key in ("created_at", "saved_at", "software", "num_windows", "section_id",
                    "sections", "interface_state", "atlas_provenance"):
            payload.pop(key, None)
        return {key: state_digest(value) for key, value in payload.items()}

    def answer_new_project(self, window, text):
        """Click ``text`` in the New project question once it is open."""
        from PyQt6.QtCore import QTimer

        def answer():
            box = getattr(window, "new_project_box", None)
            if box is None or not box.isVisible():
                QTimer.singleShot(20, answer)   # not open yet
                return
            [choice] = [b for b in box.buttons() if b.text().replace("&", "") == text]
            choice.click()

        QTimer.singleShot(0, answer)

    @isolated_gui_test
    def test_new_project_from_the_project_step_keeps_or_closes_the_atlas(self):
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atlas = str(make_processed_atlas(root / "atlas"))
            # Ground truth: a fresh window with only this atlas loaded.
            fresh = self.make_window(folder)
            self.assertTrue(fresh.engine.load_volume_atlas(atlas))
            fresh_fields = self.document_fields(fresh.engine)

            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(atlas))
            volume = engine.atlas_view.atlas_data
            fiber = engine.add_implant("fiber", specs={"diameter_um": 100})
            for name, value in (("pfc-1.png", 200), ("pfc-2.png", 120)):
                cv2.imwrite(str(root / name), np.full((32, 24, 3), value, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(root / name), "")):
                    engine.load_image()
                engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                engine.set_implant_outline(fiber.implant_id, [[10.0, 4.0], [14.0, 4.0],
                                                              [14.0, 20.0], [10.0, 20.0]])
                self.assertTrue(engine.map_implant(fiber.implant_id)[0])
            self.assertTrue(engine.build_implant(fiber.implant_id)[0])
            saved = str(root / "work.dmap")
            self.assertTrue(engine.save_project_called(path=saved))
            window.mark_saved()
            old_section = engine.section_id
            provenance = engine.atlas_provenance
            self.assertIsNotNone(provenance)
            window.go_to("annotate")
            window.refresh()
            self.assertTrue(window.is_dirty() is False)
            engine.working_img_data["img-cells"] = [[3.0, 3.0]]   # unsaved work
            window._dirty_check_pending = True
            window.refresh()

            panel = window.panels["project"]
            window.go_to("project")
            # Cancel at the unsaved-work question: nothing changes.
            with patch("driftlessmap.v2.shell.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Cancel):
                self.push(panel, "New project")
            self.assertEqual(len(engine.sections), 2)
            # Discard, then Cancel the atlas question: nothing changes either.
            self.answer_new_project(window, "Cancel")
            with patch("driftlessmap.v2.shell.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Discard):
                self.push(panel, "New project")
            self.assertEqual(len(engine.sections), 2)
            self.assertEqual(engine.current_project_path, saved)

            self.answer_new_project(window, "Keep the atlas")
            with patch("driftlessmap.v2.shell.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Discard):
                self.push(panel, "New project")
            window.refresh()
            # The same volume in memory (not read again), nothing else kept.
            self.assertIs(engine.atlas_view.atlas_data, volume)
            self.assertIsNone(engine.image_view.current_img)
            self.assertEqual(len(engine.sections), 1)
            self.assertNotEqual(engine.section_id, old_section)
            self.assertEqual(engine.mapping_ledger.records(), [])
            self.assertEqual(engine.implants.implants(), [])
            self.assertEqual(engine.object_ctrl.obj_name, [])
            self.assertEqual(engine.undo_history.labels(), ([], []))
            self.assertIsNone(engine.current_project_path)
            self.assertFalse(window.is_dirty())
            self.assertTrue(window.windowTitle().startswith("Untitled"))
            self.assertIs(window.stack.currentWidget(), panel)
            fields = self.document_fields(engine)
            self.assertEqual([key for key in fresh_fields if fields.get(key) != fresh_fields[key]],
                             [])
            self.assertEqual(set(fields), set(fresh_fields))
            # The atlas's verified identity is kept with it.
            self.assertEqual(engine.atlas_provenance, provenance)
            # Save asks where; the saved file still holds the earlier work.
            with patch.object(engine, "save_project_called", return_value=False) as ask:
                window.run("project.save")
                ask.assert_called_once_with()
            # Work continues normally: a section can be added and saved.
            with patch.object(file_dialogs, "get_open_file_name",
                              return_value=(str(root / "pfc-1.png"), "")):
                engine.load_image()
            self.assertEqual(len(engine.sections), 1)
            self.assertTrue(engine.save_project_called(path=str(root / "new.dmap")))

            # Close the atlas too: the start screen returns.
            window.mark_saved()
            self.answer_new_project(window, "Close the atlas too")
            self.push(panel, "New project")
            window.refresh()
            self.assertIsNone(engine.atlas_view.atlas_data)
            self.assertIsNone(engine.image_view.current_img)
            self.assertTrue(window.empty_canvas.isVisibleTo(window))
            self.assertIn("already", (lambda: (window.run("project.new"),
                                               window.message_label.text())[1])())
            self.assertEqual(window.registry.get("project.new").shortcut, "Ctrl+N")

            # The earlier project still opens with its work.
            with patch.object(file_dialogs, "get_open_file_name", return_value=(saved, "")):
                window.run("project.open")
            self.assertEqual(len(engine.sections), 2)
            self.assertEqual(len(engine.implants.implants()), 1)

    @isolated_gui_test
    def test_side_columns_show_and_hide_from_beside_the_images(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            window.resize(1500, 900)
            window.show()
            self.application.processEvents()

            def shown():
                return (window.task_column.isVisibleTo(window),
                        window.inspector_column.isVisibleTo(window))

            window.task_toggle.click()
            self.assertEqual(shown(), (False, True))
            self.assertFalse(window.task_toggle.isChecked())
            self.assertFalse(window.toggle_task_item.isChecked())
            self.assertFalse(window.focus_button.isChecked())
            window.inspector_toggle.click()
            self.assertEqual(shown(), (False, False))
            self.assertTrue(window.focus_button.isChecked())
            window.task_toggle.click()
            self.assertEqual(shown(), (True, False))
            self.assertTrue(window.task_toggle.isChecked())
            # The View menu and the buttons agree, both ways.
            window.toggle_inspector_item.setChecked(True)
            self.assertTrue(window.inspector_toggle.isChecked())
            self.assertEqual(shown(), (True, True))
            window.run("view.focus")
            self.assertFalse(window.task_toggle.isChecked())
            self.assertFalse(window.inspector_toggle.isChecked())
            window.run("view.task_column")
            self.assertEqual(shown(), (True, False))
            window.run("view.inspector")
            self.assertEqual(shown(), (True, True))

    @isolated_gui_test
    def test_brightness_per_channel_above_the_section_image(self):
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from driftlessmap.v2 import channel_display as display
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            image = np.zeros((40, 30, 3), np.uint8)
            image[..., 0] = np.arange(30, dtype=np.uint8)[None, :] * 8
            image[..., 1] = 100
            image[..., 2] = 200
            cv2.imwrite(str(root / "section.png"), image)
            with patch.object(file_dialogs, "get_open_file_name",
                              return_value=(str(root / "section.png"), "")):
                engine.load_image()
            window.go_to("section")
            window.refresh()
            view = engine.image_view
            strip = window.channel_strip
            self.assertTrue(strip.isVisibleTo(window))
            self.assertEqual(len(strip.rows), 3)
            # The strip sits above the image in the histology view.
            grid = engine.image_view_layout
            self.assertEqual(grid.getItemPosition(grid.indexOf(strip))[0], 0)
            self.assertEqual(grid.getItemPosition(grid.indexOf(view.img_stacks))[0], 1)
            pixels = view.current_img.copy()
            before = [display.channel_levels(view, i) for i in range(3)]
            self.assertTrue(window.is_dirty() is not None)
            window.mark_saved()

            # Dragging one channel's slider right brightens only that channel.
            slider = strip.rows[1]["slider"]
            slider.setValue(slider.value() + 200)
            after = [display.channel_levels(view, i) for i in range(3)]
            self.assertLess(after[1][1], before[1][1])       # white point lower
            self.assertLess(after[1][0], before[1][0])
            self.assertAlmostEqual(after[1][1] - after[1][0], before[1][1] - before[1][0],
                                   delta=2)                    # contrast kept
            self.assertEqual(after[0], before[0])
            self.assertEqual(after[2], before[2])
            np.testing.assert_array_equal(view.current_img, pixels)
            self.assertTrue(window.is_dirty())
            # The Section step shows the new range of that channel.
            section = window.panels["section"]
            self.assertEqual(section._rows[1]["span"].text().split()[0],
                             "{:.0f}".format(after[1][0]))

            # The Section step's Brightness slider brightens to the right too.
            section._select(2)
            low, high, _gamma = display.channel_levels(view, 2)
            section.brightness.setValue(section.brightness.value() + 100)
            window.refresh()
            new_low, new_high, _gamma = display.channel_levels(view, 2)
            self.assertLess(new_high, high)
            self.assertEqual(strip.rows[2]["slider"].value(), section.brightness.value())

            # Auto and Reset act on every channel.
            strip.auto_button.click()
            for index in range(3):
                self.assertEqual(display.channel_levels(view, index)[:2],
                                 display.auto_levels(view, index))
            strip.reset_button.click()
            for index in range(3):
                self.assertEqual(display.channel_levels(view, index),
                                 display.reset_levels(view, index))
            np.testing.assert_array_equal(view.current_img, pixels)

            # Saved and reopened with the project.
            slider.setValue(slider.value() + 150)
            levels = display.channel_levels(view, 1)
            path = str(root / "bright.dmap")
            self.assertTrue(engine.save_project_called(path=path))
            window.mark_saved()
            from PyQt6.QtWidgets import QMessageBox

            with patch.object(file_dialogs, "get_open_file_name", return_value=(path, "")), \
                    patch("driftlessmap.app.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.No):
                window.run("project.open")
            window.refresh()
            self.assertEqual(display.channel_levels(engine.image_view, 1), levels)
            self.assertEqual(strip.rows[1]["slider"].value(), slider.value())

    @isolated_gui_test
    def test_plan_a_probe_is_offered_once_an_atlas_is_loaded(self):
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            panel = window.panels["project"]
            window.go_to("project")
            window.refresh()
            self.assertFalse(panel.plan_probe.isEnabled())
            # Without an atlas, planning asks for one first; cancelled, nothing opens.
            from unittest.mock import patch

            from driftlessmap import file_dialogs

            with patch.object(file_dialogs, "get_existing_directory", return_value=""):
                window.run("probe.plan")
            self.assertIn("needs a volume atlas", window.message_label.text())
            self.assertEqual(card_names(window), [])
            self.assertTrue(engine.load_volume_atlas(
                str(make_processed_atlas(root / "atlas", axis_info=True))))
            window.refresh()
            # The start screen is gone; the Project step offers planning instead.
            self.assertFalse(window.empty_canvas.isVisibleTo(window))
            self.assertTrue(panel.plan_probe.isEnabled())
            self.assertEqual([a.text() for a in panel.plan_probe.menu().actions()],
                             ["A probe…", "An optical fiber…", "A microprism…"])
            panel.plan_probe.menu().actions()[0].trigger()
            self.application.processEvents()
            self.assertIs(window.stack.currentWidget(), window.panels["annotate"])
            card = window.panels["annotate"].implants
            self.assertEqual(card.probe_card.book.names(), ["Probe 1"])
            self.assertEqual(card.probe_card.probe, "Probe 1")
            # The probe starts with a plan (since 2.8.0), built at once.
            self.assertIsNotNone(engine.probe_plan("Probe 1"))
            self.assertTrue(engine.plan_objects("Probe 1"))
            self.assertIn("Probe 1 planned", window.message_label.text())
            # Again: Probe 1 is planned, so a second probe is opened.
            window.go_to("project")
            panel.plan_probe.menu().actions()[0].trigger()
            self.assertEqual(card.probe_card.book.names(), ["Probe 1", "Probe 2"])
            self.assertIn("Plan a probe on the atlas",
                          [c.name for c in window.registry.search("probe")])

    @isolated_gui_test
    def test_a_probe_plan_is_a_pose_with_a_live_readout(self):
        import csv
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap import file_dialogs
        from driftlessmap.mapping_records import CURRENT
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            # Large enough for a Neuropixels tip and its first sites (1.4 mm deep).
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                root / "atlas", shape=(80, 64, 64), axis_info=True))))
            window.run("probe.plan")
            window.refresh()
            card = window.panels["annotate"].implants.probe_card
            editor = card.plan_editor
            book = card.book
            self.assertTrue(editor.isVisibleTo(window))
            # Without a section the track steps are hidden: the plan is the probe.
            self.assertFalse(card.mark.isVisibleTo(window))
            plan = engine.probe_plan("Probe 1")
            readout = engine.probe_plan_readout("Probe 1")
            self.assertIsNotNone(readout["entry_um"])
            self.assertEqual(readout["warnings"], [])
            self.assertIn("Entry", editor.readout.text())
            self.assertIn("Depth", editor.readout.text())
            # The planned object belongs to Probe 1; it is not a probe of its own.
            self.assertEqual(book.names(), ["Probe 1"])
            self.assertEqual(book.summary("Probe 1"), "planned")
            [built] = engine.plan_objects("Probe 1")
            self.assertEqual(engine.object_ctrl.obj_name[built], "Probe 1 plan")
            self.assertEqual(engine.object_mapping_status(built), CURRENT)
            info = engine.object_ctrl.obj_data[built]
            np.testing.assert_allclose(info["terminus_coords"], plan.tip_um, atol=1e-6)

            # Snap the tip to the centre of the brain ("CH" holds every labelled
            # voxel) on the tip's side, the animal's right.
            editor.snap_to_region(10)
            atlas = engine.plan_atlas()
            brain = np.argwhere(atlas.labels != 0) + 0.5
            centre = brain[brain[:, 0] >= atlas.bregma[0]].mean(axis=0)
            np.testing.assert_allclose(atlas.to_vox(engine.probe_plan("Probe 1").tip_um),
                                       centre, atol=1.0)
            plan = engine.probe_plan("Probe 1")
            self.assertEqual(engine.object_ctrl.obj_data[engine.plan_objects("Probe 1")[0]]
                             ["plan"], plan.to_dict())
            # Editing a field shows the readout at once and builds when it settles.
            editor.ap_tilt.setValue(10.0)
            self.assertIn("10.0° anterior", editor.readout.text())
            self.assertEqual(engine.probe_plan("Probe 1").ap_tilt_deg, 0.0)
            editor.commit()
            tilted = engine.probe_plan("Probe 1")
            self.assertEqual(tilted.ap_tilt_deg, 10.0)
            [built] = engine.plan_objects("Probe 1")
            self.assertAlmostEqual(engine.object_ctrl.obj_data[built]["ap_angle"], 10.0)
            # Depth slides the tip along the probe from the same entry.
            entry = engine.probe_plan_readout("Probe 1")["entry_um"]
            editor.depth.setValue(0.2)
            editor.commit()
            moved = engine.probe_plan_readout("Probe 1")
            np.testing.assert_allclose(moved["entry_um"], entry, atol=1e-6)
            self.assertAlmostEqual(moved["depth_um"], 200.0, delta=1e-6)
            # Each settled edit is one undo step.
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.probe_plan("Probe 1"), tilted)
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.probe_plan("Probe 1"), plan)
            self.assertTrue(engine.redo_mapping_step())
            self.assertEqual(engine.probe_plan("Probe 1"), tilted)

            # Two clicks on the coronal view (entry, then tip) set the plan.
            view = engine.atlas_view
            engine.atlas_display = "coronal"
            editor.click_button.click()
            self.assertTrue(editor.clicking)
            atlas = engine.plan_atlas()
            mid = view.current_coronal_index
            points2 = np.array([[atlas.bregma[0] + 1.0, view.atlas_size[0] - 30.0],
                                [atlas.bregma[0] + 2.0, view.atlas_size[0] - 10.0]])
            engine.working_atlas_data["atlas-probe"] = points2.tolist()
            expected = np.asarray(view.get_3d_data_from_2d_view(points2, "coronal")) \
                * view.vox_size_um
            window.refresh()
            self.assertFalse(editor.clicking)
            self.assertEqual(engine.working_atlas_data["atlas-probe"], [])
            clicked = engine.probe_plan("Probe 1")
            np.testing.assert_allclose(clicked.tip_um, expected[np.argmin(expected[:, 2])],
                                       atol=1e-6)
            self.assertEqual(view.current_coronal_index, mid)

            # Drawn on the atlas through the tip.
            self.assertTrue(engine.show_plan_on_atlas("Probe 1"))
            engine.plan_overlay.refresh()
            self.assertEqual(engine.plan_overlay.drawn("coronal"), 1)
            self.assertEqual(engine.plan_overlay.drawn("horizontal"), 1)
            # The track crosses the shown slices, so each view has its solid
            # part; its path must build (pyqtgraph hides errors while painting).
            import pyqtgraph as pg
            for plane in ("coronal", "sagittal", "horizontal"):
                lines = [item for _stack, item in engine.plan_overlay._items[plane]
                         if isinstance(item, pg.PlotDataItem)]
                self.assertEqual(len(lines), 2, plane)
                for item in lines:
                    self.assertFalse(item.curve.getPath().isEmpty(), plane)

            # Copy coordinates puts one self-describing line on the clipboard.
            editor.copy_coordinates()
            line = QApplication.clipboard().text()
            self.assertTrue(line.startswith("Probe 1:"))
            self.assertIn("from Bregma", line)

            # Renaming the probe renames its plan and its planned object.
            book.rename("Probe 1", "Left PFC")
            self.assertIsNone(engine.probe_plan("Probe 1"))
            self.assertEqual(engine.probe_plan("Left PFC").probe, "Left PFC")
            [built] = engine.plan_objects("Left PFC")
            self.assertEqual(engine.object_ctrl.obj_name[built], "Left PFC plan")
            self.assertEqual(book.names(), ["Left PFC"])

            # Export all results writes the plan table.
            out = root / "results"
            out.mkdir()
            paths, _notes = engine.export_all_results(str(out))
            self.assertIn(str(out / "probe_plans.csv"), paths)
            with (out / "probe_plans.csv").open() as stream:
                [row] = list(csv.DictReader(stream))
            self.assertEqual(row["probe"], "Left PFC")
            self.assertAlmostEqual(float(row["tip_dv_mm"]),
                                   engine.probe_plan("Left PFC").tip_um[2] / 1000.0, places=3)

            # Saved and reopened with the project.
            saved = engine.probe_plan("Left PFC")
            path = str(root / "plan.dmap")
            self.assertTrue(engine.save_project_called(path=path))
            window.mark_saved()
            with patch.object(file_dialogs, "get_open_file_name", return_value=(path, "")), \
                    patch("driftlessmap.app.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.No):
                window.run("project.open")
            window.refresh()
            self.assertEqual(engine.probe_plan("Left PFC"), saved)
            [built] = engine.plan_objects("Left PFC")
            self.assertEqual(engine.object_mapping_status(built), CURRENT)

            # Deleting the probe deletes its plan.
            book.delete("Left PFC")
            self.assertIsNone(engine.probe_plan("Left PFC"))
            self.assertEqual(engine.plan_objects(), [])

    @isolated_gui_test
    def test_a_plan_is_steered_by_entry_depth_keys_and_shown_along_its_shank(self):
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                root / "atlas", shape=(80, 64, 64), axis_info=True))))
            window.run("probe.plan")
            window.refresh()
            editor = window.panels["annotate"].implants.probe_card.plan_editor
            editor.snap_to_region(10)

            # Edit by entry and depth: the entry is on the surface at AP/ML.
            editor.mode_box.setCurrentIndex(1)
            self.assertEqual(editor.ap_label.text(), "Entry AP")
            self.assertFalse(editor.dv.isEnabled())
            editor.ap.setValue(0.5)
            editor.ml.setValue(0.3)
            editor.depth.setValue(0.6)
            editor.commit()
            readout = engine.probe_plan_readout("Probe 1")
            np.testing.assert_allclose(readout["entry_um"][:2], [300.0, 500.0], atol=1e-6)
            self.assertAlmostEqual(readout["depth_um"], 600.0, places=6)
            surface = readout["entry_um"][2]
            self.assertAlmostEqual(editor.dv.value(), round(surface / 1000.0, 3), places=3)
            # The tilts now turn about the entry, which stays put.
            editor.ap_tilt.setValue(12.0)
            editor.commit()
            tilted = engine.probe_plan_readout("Probe 1")
            np.testing.assert_allclose(tilted["entry_um"], readout["entry_um"], atol=1e-6)
            self.assertAlmostEqual(tilted["depth_um"], 600.0, places=6)
            self.assertEqual(engine.probe_plan("Probe 1").ap_tilt_deg, 12.0)

            # The recording window: NP1 has three banks; Every site records all 960.
            self.assertEqual(editor.bank_box.count(), 4)
            self.assertEqual(tilted["window_sites"], 384)
            editor.bank_box.setCurrentIndex(3)
            self.assertIsNone(engine.probe_plan("Probe 1").bank)
            self.assertEqual(engine.probe_plan_readout("Probe 1")["window_sites"], 960)
            self.assertIn("Recording", editor.readout.text())
            editor.bank_box.setCurrentIndex(0)
            self.assertEqual(engine.probe_plan("Probe 1").bank, 0)
            editor.copy_coordinates()
            self.assertIn("recording bank 0", QApplication.clipboard().text())

            # Keyboard steering: W moves the tip anterior by the step, + makes
            # the step larger, Shift takes the largest, I tilts, Esc stops.
            editor.mode_box.setCurrentIndex(0)
            before = engine.probe_plan("Probe 1")
            editor.steer_button.click()
            self.assertTrue(editor.legend.isVisibleTo(window))
            self.assertTrue(editor.steer_key(Qt.Key.Key_W))
            self.assertTrue(editor.steer_key(Qt.Key.Key_Plus))
            self.assertTrue(editor.steer_key(Qt.Key.Key_D))
            self.assertTrue(editor.steer_key(Qt.Key.Key_A, Qt.KeyboardModifier.ShiftModifier))
            self.assertTrue(editor.steer_key(Qt.Key.Key_I))
            self.assertFalse(editor.steer_key(Qt.Key.Key_F))
            self.assertTrue(editor.steer_key(Qt.Key.Key_Escape))
            self.assertFalse(editor.steer_button.isChecked())
            steered = engine.probe_plan("Probe 1")
            np.testing.assert_allclose(
                np.subtract(steered.tip_um, before.tip_um), [100 - 500, 50, 0], atol=1e-9)
            self.assertEqual(steered.ap_tilt_deg, before.ap_tilt_deg + 5)
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.probe_plan("Probe 1"), before)
            self.assertTrue(engine.redo_mapping_step())

            # Tip to the surface along the probe: the tip goes to the entry and
            # the plan is not built until it has a depth; undo brings it back.
            entry = engine.probe_plan_readout("Probe 1")["entry_um"]
            editor.tip_to_surface(True)
            np.testing.assert_allclose(engine.probe_plan("Probe 1").tip_um, entry, atol=1e-6)
            self.assertEqual(engine.plan_objects("Probe 1"), [])
            self.assertTrue(any("surface" in w for w in
                                engine.probe_plan_readout("Probe 1")["warnings"]))
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.probe_plan("Probe 1"), steered)
            self.assertTrue(engine.plan_objects("Probe 1"))
            straight = editor.tip_to_surface(False)
            self.assertIsNone(straight)
            tip = engine.probe_plan("Probe 1").tip_um
            self.assertAlmostEqual(tip[2], surface, places=6)

            # The shank view draws the plan and names what lies under the mouse.
            editor.depth.setValue(0.8)
            editor.commit()
            view = editor.shank_view
            view.resize(400, 320)
            self.assertIsNotNone(view.readout)
            _plane, strip = view._areas()
            text = view.describe(strip.center().x(), strip.center().y())
            self.assertIn("mm deep", text)
            first = view.readout["regions"][0]
            self.assertTrue(text.startswith(first["name"]) or any(
                text.startswith(r["name"]) for r in view.readout["regions"]))
            self.assertFalse(view.grab().isNull())
            self.assertIsNone(view.describe(-5, -5))

    @isolated_gui_test
    def test_plans_for_surgery_craniotomy_clearance_arm_angles_and_scaling(self):
        import csv
        from unittest.mock import patch

        from driftlessmap.probe_plans import ProbePlan, arm_from_tilts, clearances
        from driftlessmap.v2 import plan_editor
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                root / "atlas", shape=(80, 64, 64), axis_info=True))))
            window.run("probe.plan")
            window.refresh()
            card = window.panels["annotate"].implants.probe_card
            editor = card.plan_editor
            editor.snap_to_region(10)

            # A craniotomy centred on the entry; the probe goes through it.
            hole = editor.new_craniotomy(diameter_um=800.0)
            plan = engine.probe_plan("Probe 1")
            self.assertEqual(plan.craniotomy, hole.craniotomy_id)
            entry = engine.probe_plan_readout("Probe 1")["entry_um"]
            np.testing.assert_allclose(hole.centre_um, entry[:2], atol=1e-6)
            self.assertEqual(editor.hole_box.currentText(), hole.name)
            self.assertIn("Craniotomy", editor.readout.text())
            # Moving the entry 0.5 mm away puts it outside the 0.8 mm opening.
            editor.mode_box.setCurrentIndex(1)
            editor.ap.setValue(round((entry[1] + 500.0) / 1000.0, 3))
            editor.commit()
            readout = engine.probe_plan_readout("Probe 1")
            self.assertTrue(any("outside its 0.80 mm opening" in w
                                for w in readout["warnings"]))
            # Fit the craniotomy to its probe: the entry is inside again.
            editor.fit_craniotomy()
            hole = engine.craniotomies.get(hole.craniotomy_id)
            readout = engine.probe_plan_readout("Probe 1")
            self.assertFalse(any("opening" in w for w in readout["warnings"]))
            np.testing.assert_allclose(hole.centre_um, readout["entry_um"][:2], atol=1e-6)
            self.assertAlmostEqual(hole.diameter_um, 500.0)   # the minimum
            engine.show_plan_on_atlas("Probe 1")
            engine.plan_overlay.refresh()
            self.assertEqual(engine.plan_overlay.holes_drawn(), 1)

            # A second probe 0.2 mm away is reported for both.
            second = card.new_probe()
            first = engine.probe_plan("Probe 1")
            engine.set_probe_plan(ProbePlan(second, [first.tip_um[0] - 200.0] + first.tip_um[1:],
                                            probe_settings=first.probe_settings))
            # Their 6.2 mm NP1.0 bases collide above the brain (2.8.6) ...
            for probe in ("Probe 1", second):
                warnings = engine.probe_plan_readout(probe)["warnings"]
                self.assertTrue(any("touches" in w and "above the brain" in w
                                    for w in warnings), probe)
            # ... and the shanks themselves are 0.2 mm apart.
            bare = [engine.probe_plan(p).copy(probe_settings=None) for p in ("Probe 1", second)]
            pairs = clearances([(p, engine.probe_plan_readout(p, others=False)) for p in bare])
            self.assertAlmostEqual(pairs[0]["distance_um"], 200.0, places=3)
            window.panels["annotate"].implants._select_probe("Probe 1")

            # Arm angles: entered as azimuth and elevation, stored as tilts.
            editor.mode_box.setCurrentIndex(0)
            editor.angle_box.setCurrentIndex(1)
            self.assertEqual(editor.first_angle_label.text(), "Azimuth")
            self.assertEqual(window.settings.value("plan/angles"), "Arm angles")
            editor.ap_tilt.setValue(90.0)
            editor.ml_tilt.setValue(10.0)
            editor.commit()
            plan = engine.probe_plan("Probe 1")
            self.assertAlmostEqual(plan.ap_tilt_deg, 0.0, places=6)
            self.assertAlmostEqual(plan.ml_tilt_deg, 10.0, places=6)
            azimuth, elevation = arm_from_tilts(plan.ap_tilt_deg, plan.ml_tilt_deg)
            self.assertAlmostEqual(azimuth, 90.0, places=6)
            self.assertIn("Arm", editor.readout.text())
            editor.angle_box.setCurrentIndex(0)
            self.assertAlmostEqual(editor.ml_tilt.value(), 10.0, places=1)

            # Bregma-Lambda: this atlas records no Lambda, so both are entered.
            self.assertIsNone(engine.atlas_bregma_lambda_um())
            with patch.object(plan_editor, "bregma_lambda_dialog",
                              return_value={"bregma_lambda_um": 3990.0,
                                            "atlas_bregma_lambda_um": 4200.0}):
                editor.edit_bregma_lambda()
            self.assertAlmostEqual(engine.surgery_scale(), 0.95)
            self.assertIn("For this animal", editor.readout.text())
            editor.copy_coordinates()
            line = QApplication.clipboard().text()
            self.assertIn("Bregma-Lambda scale x0.950", line)
            self.assertIn("through " + hole.name, line)
            self.assertIn("arm azimuth 90.0°", line)
            out = root / "plans.csv"
            engine.export_probe_plans(str(out))
            with out.open() as stream:
                rows = {row["probe"]: row for row in csv.DictReader(stream)}
            readout = engine.probe_plan_readout("Probe 1")
            self.assertAlmostEqual(float(rows["Probe 1"]["animal_depth_mm"]),
                                   readout["depth_um"] * 0.95 / 1000.0, places=3)
            self.assertEqual(rows["Probe 1"]["craniotomy"], hole.name)
            self.assertEqual(rows["Probe 1"]["closest_probe"], second)
            self.assertAlmostEqual(float(rows["Probe 1"]["arm_azimuth_deg"]), 90.0)

            # Saved and reopened; undo takes back the scaling and the craniotomy.
            path = str(root / "surgery.dmap")
            self.assertTrue(engine.save_project_called(path=path))
            from driftlessmap.persistence import load_driftlessmap_file

            payload, error = load_driftlessmap_file(path, expected_kind="project")
            self.assertIsNone(error)
            self.assertEqual(payload["craniotomies"], engine.craniotomies.to_list())
            self.assertEqual(payload["surgery_settings"]["bregma_lambda_um"], 3990.0)
            self.assertTrue(engine.undo_mapping_step())     # the scaling
            self.assertEqual(engine.surgery_scale(), 1.0)
            editor.remove_craniotomy()
            self.assertIsNone(engine.probe_plan("Probe 1").craniotomy)
            self.assertEqual(len(engine.craniotomies), 0)
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(len(engine.craniotomies), 1)
            self.assertEqual(engine.probe_plan("Probe 1").craniotomy, hole.craniotomy_id)

    @isolated_gui_test
    def test_a_plan_is_proposed_from_the_regions_to_record(self):
        from unittest.mock import patch

        from PyQt6.QtWidgets import QDialog

        from driftlessmap.probe_plans import REACHED_UM
        from driftlessmap.v2 import proposal_dialog
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
                root / "atlas", shape=(80, 64, 64), axis_info=True))))
            window.go_to("annotate")
            card = window.panels["annotate"].implants.probe_card
            card.new_probe()
            window.refresh()
            editor = card.plan_editor
            # A probe without a plan offers a proposal straight away.
            self.assertTrue(editor.start_propose.isVisibleTo(window))
            # The Regions tree's checked regions become targets ("GC", label 20).
            tree = engine.atlas_view.label_tree
            tree.checked = {20}
            seen = {}

            def run(dialog):
                dialog.add_checked(dialog.targets)
                self.assertEqual(dialog.regions(dialog.targets), [20])
                dialog.side.setCurrentIndex(0)
                dialog.midline.setValue(0.0)
                dialog.find()
                seen["rows"] = dialog.table.rowCount()
                seen["reasons"] = dialog.reasons.text()
                self.assertTrue(dialog.use_button.isEnabled())
                dialog.use()
                return QDialog.DialogCode.Accepted

            with patch.object(proposal_dialog.ProposalDialog, "exec", run):
                editor.propose()
            self.assertGreater(seen["rows"], 0)
            self.assertEqual(seen["reasons"], "")
            plan = engine.probe_plan("Probe 1")
            self.assertEqual(plan.targets, [20])
            self.assertTrue(engine.plan_objects("Probe 1"))
            readout = engine.probe_plan_readout("Probe 1")
            [(name, length)] = readout["targets"]
            self.assertEqual(name, "GC")
            self.assertGreaterEqual(length, REACHED_UM)
            self.assertIn("Targets in the window", editor.readout.text())
            # Undo takes the proposal back (the probe had no plan before).
            self.assertTrue(engine.undo_mapping_step())
            self.assertIsNone(engine.probe_plan("Probe 1"))

            # A target the atlas does not have: the dialog says so, nothing is used.
            def missing(dialog):
                dialog._add(dialog.targets, 999)
                dialog.find()
                seen["missing"] = dialog.reasons.text()
                self.assertFalse(dialog.use_button.isEnabled())
                return QDialog.DialogCode.Rejected

            with patch.object(proposal_dialog.ProposalDialog, "exec", missing):
                editor.propose()
            self.assertIn("None of the target regions", seen["missing"])
            self.assertIsNone(engine.probe_plan("Probe 1"))

    # ------------------------------------------------- review of 2.8.3
    def planned_window(self, folder):
        from tests.atlas_fixture import make_processed_atlas

        window = self.make_window(folder)
        engine = window.engine
        self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(
            Path(folder) / "atlas", shape=(80, 64, 64), axis_info=True))))
        window.run("probe.plan")
        window.refresh()
        return window, engine, window.panels["annotate"].implants.probe_card.plan_editor

    @isolated_gui_test
    def test_plan_a_prism_and_a_fiber_from_the_start_screen(self):
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap import file_dialogs
        from driftlessmap.mapping_records import CURRENT
        from driftlessmap.persistence import load_driftlessmap_file
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atlas = make_processed_atlas(root / "atlas", shape=(80, 64, 64), axis_info=True)
            window = self.make_window(folder)
            engine = window.engine
            window.refresh()
            self.assertTrue(window.empty_canvas.isVisibleTo(window))
            # The start screen asks for the atlas, then opens the plan (2.8.5:
            # before, it only said to load an atlas, and the screen then went).
            with patch.object(file_dialogs, "get_existing_directory", return_value=str(atlas)):
                self.push(window.empty_canvas, "Plan a prism…")
            window.refresh()
            self.assertIsNotNone(engine.atlas_view.atlas_data)
            self.assertFalse(window.empty_canvas.isVisibleTo(window))
            self.assertIs(window.stack.currentWidget(), window.panels["annotate"])
            [prism] = engine.implants.implants()
            self.assertEqual((prism.kind, prism.specs["width_um"], prism.specs["depth_um"],
                              prism.specs["length_um"], prism.specs["bevel_deg"]),
                             ("prism", 1500.0, 1500.0, 3000.0, 45.0))
            plan = engine.implant_plan(prism.implant_id)
            self.assertEqual(plan.roll_deg, 90.0)      # lateral, on the right
            editor = window.panels["annotate"].implants.plan_editor
            self.assertTrue(editor.isVisibleTo(window))
            self.assertEqual(editor.roll_label.text(), "Face")
            self.assertFalse(editor.type_box.isVisibleTo(window))
            self.assertFalse(editor.propose_button.isVisibleTo(window))
            self.assertIn("Face looks into", editor.readout.text())
            [built] = engine.plan_objects(prism.name)
            self.assertEqual(engine.object_ctrl.obj_type[built], "merged prism")
            self.assertEqual(engine.object_mapping_status(built), CURRENT)
            self.assertEqual(engine.implant_objects(prism.implant_id), [])
            engine.show_plan_on_atlas(prism.name)
            engine.plan_overlay.refresh()
            for plane in ("coronal", "sagittal", "horizontal"):
                self.assertGreater(engine.plan_overlay.outlines_drawn(plane), 0, plane)
            # Turning the face is a staged edit like any other.
            self.assertTrue(editor.steer_key(Qt.Key.Key_O))
            editor.commit()
            self.assertEqual(engine.implant_plan(prism.implant_id).roll_deg, 91.0)

            window.run("fiber.plan")
            window.refresh()
            fiber = engine.implants.by_name("Fiber 1")
            self.assertEqual(engine.implant_plan(fiber.implant_id).kind, "fiber")
            self.assertFalse(editor.roll.isVisibleTo(window))
            self.assertEqual(engine.object_ctrl.obj_type[engine.plan_objects("Fiber 1")[0]],
                             "merged fiber")

            # The plan follows its implant's settings and name; undo takes both back.
            engine.set_implant_specs(prism.implant_id, dict(prism.specs, length_um=1000.0))
            self.assertEqual(engine.implant_plan(prism.implant_id).specs["length_um"], 1000.0)
            self.assertTrue(any("below the brain surface" in w for w in
                                engine.probe_plan_readout(prism.name)["warnings"]))
            engine.rename_implant(prism.implant_id, "Prism L")
            self.assertIsNotNone(engine.probe_plan("Prism L"))
            self.assertEqual(engine.object_ctrl.obj_name[engine.plan_objects("Prism L")[0]],
                             "Prism L plan")
            self.assertTrue(engine.undo_mapping_step())
            self.assertIsNotNone(engine.probe_plan("Prism 1"))
            self.assertIsNone(engine.probe_plan("Prism L"))
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.implant_plan(prism.implant_id).specs["length_um"], 3000.0)

            # Saved apart from the probe plans, and reopened with their implants.
            path = root / "plans.dmap"
            self.assertTrue(engine.save_project_called(path=str(path)))
            window.mark_saved()
            data, error = load_driftlessmap_file(str(path), expected_kind="project")
            self.assertIsNone(error)
            self.assertEqual(data["probe_plans"], [])
            self.assertEqual(sorted(p["kind"] for p in data["implant_plans"]),
                             ["fiber", "prism"])
            saved = [engine.probe_plan(n) for n in ("Fiber 1", "Prism 1")]
            self.answer_new_project(window, "Keep the atlas")
            window.run("project.new")
            self.assertEqual(len(engine.probe_plans), 0)
            with patch.object(file_dialogs, "get_open_file_name",
                              return_value=(str(path), "")), \
                    patch("driftlessmap.v2.shell.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.Discard), \
                    patch("driftlessmap.app.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.No):
                window.run("project.open")
            self.assertEqual([engine.probe_plan(n) for n in ("Fiber 1", "Prism 1")], saved)

            # Deleting the implant deletes its plan and planned object.
            fiber = engine.implants.by_name("Fiber 1")
            engine.delete_implant(fiber.implant_id)
            self.assertIsNone(engine.probe_plan("Fiber 1"))
            self.assertEqual(engine.plan_objects("Fiber 1"), [])

    @isolated_gui_test
    def test_review_r2_a_staged_edit_is_saved_counted_and_kept_to_its_document(self):
        from unittest.mock import patch

        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap import file_dialogs
        from driftlessmap.persistence import load_driftlessmap_file

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, engine, editor = self.planned_window(folder)
            path = root / "base.dmap"
            self.assertTrue(engine.save_project_called(path=str(path)))
            window.mark_saved()
            before = engine.probe_plan("Probe 1")
            # A steering step is staged: shown and unsaved, not yet built.
            self.assertTrue(editor.steer_key(Qt.Key.Key_W))
            shown = editor.current().tip_um
            self.assertEqual(shown[1] - before.tip_um[1], 50.0)
            self.assertTrue(window.is_dirty())
            # Saving within the settling time saves what is shown.
            window.save_project()
            data, error = load_driftlessmap_file(str(path), expected_kind="project")
            self.assertIsNone(error)
            self.assertEqual(data["probe_plans"][0]["tip_um"], shown)
            self.assertFalse(window.is_dirty())
            self.assertEqual(engine.plan_previews, {})
            [built] = engine.plan_objects("Probe 1")
            np.testing.assert_allclose(engine.object_ctrl.obj_data[built]["terminus_coords"],
                                       shown, atol=1e-6)

            # Undo within the settling time takes the staged step back, and no
            # late timer brings it back.
            saved = engine.probe_plan("Probe 1")
            editor.steer_key(Qt.Key.Key_W)
            self.assertTrue(engine.undo_mapping_step())
            QTest.qWait(700)
            self.assertEqual(engine.probe_plan("Probe 1"), saved)
            self.assertIsNotNone(engine.undo_history.redo_label())

            # A new project started within the settling time stays empty.
            editor.steer_key(Qt.Key.Key_W)
            self.answer_new_project(window, "Keep the atlas")
            with patch("driftlessmap.v2.shell.QMessageBox.question",
                       return_value=QMessageBox.StandardButton.Discard):
                window.run("project.new")
            QTest.qWait(700)
            self.assertEqual(engine.probe_plans.to_list(), [])
            self.assertEqual(engine.plan_previews, {})
            self.assertEqual(engine.object_ctrl.obj_name, [])

            # Opening another project within the settling time does not bring
            # the staged plan into it.
            window.run("probe.plan")
            window.refresh()
            editor.steer_key(Qt.Key.Key_W)
            with patch.object(file_dialogs, "get_open_file_name",
                              return_value=(str(path), "")), \
                    patch("driftlessmap.v2.shell.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.Discard), \
                    patch("driftlessmap.app.QMessageBox.question",
                          return_value=QMessageBox.StandardButton.No):
                window.run("project.open")
            QTest.qWait(700)
            self.assertEqual(engine.probe_plans.to_list(), data["probe_plans"])

    @isolated_gui_test
    def test_review_r3_a_failed_open_keeps_the_atlas_lambda_and_the_scale(self):
        with tempfile.TemporaryDirectory() as folder:
            window, engine, editor = self.planned_window(folder)
            # The fixture atlas records no Lambda: the scale is unavailable,
            # not 1.0, while an animal distance is set without an atlas one.
            engine.set_surgery_settings(bregma_lambda_um=450.0)
            self.assertIsNone(engine.surgery_scale())
            readout = engine.probe_plan_readout("Probe 1")
            self.assertTrue(any("no coordinates for the animal" in w
                                for w in readout["warnings"]))
            out = Path(folder) / "plans.csv"
            engine.export_probe_plans(str(out))
            import csv

            with out.open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["bregma_lambda_scale"], "unavailable")
            self.assertEqual(row["animal_depth_mm"], "")
            # A Lambda recorded with the atlas, as the rat atlases do.
            view = engine.atlas_view
            view.atlas_lambda = view.origin_3d + np.array([0.0, 20.0, 0.0])
            self.assertEqual(engine.atlas_bregma_lambda_um(), 500.0)
            self.assertAlmostEqual(engine.surgery_scale(), 0.9)
            line = engine.plan_coordinate_line("Probe 1")
            payload = engine.project_payload()
            payload["img_ctrl_data"] = {"current_img": np.zeros((0, 0, 3), np.uint8)}
            self.assertFalse(engine.load_project(payload))
            self.assertEqual(engine.atlas_bregma_lambda_um(), 500.0)
            self.assertAlmostEqual(engine.surgery_scale(), 0.9)
            self.assertEqual(engine.plan_coordinate_line("Probe 1"), line)
            # An entered atlas distance survives the same way (it is document state).
            engine.set_surgery_settings(bregma_lambda_um=450.0, atlas_bregma_lambda_um=4500.0)
            self.assertFalse(engine.load_project(payload))
            self.assertAlmostEqual(engine.surgery_scale(), 0.1)

    @isolated_gui_test
    def test_a_planned_neuropixels_probe_shows_its_hardware(self):
        with tempfile.TemporaryDirectory() as folder:
            window, engine, editor = self.planned_window(folder)
            editor.type_box.setCurrentIndex(2)          # Neuropixels 2.0, four shanks
            editor.commit()
            o = engine.object_ctrl
            built = engine.plan_objects("Probe 1")
            self.assertEqual(len(built), 4)
            with_parts = [i for i in built if o.obj_data[i].get("hardware")]
            self.assertEqual(len(with_parts), 1)          # drawn once, with shank 1
            names = [b["name"] for b in o.obj_data[with_parts[0]]["hardware"]["boxes"]]
            self.assertEqual(names.count("Shank"), 4)
            self.assertIn("Headstage", names)
            item = engine.object_3d_list[with_parts[0]]
            self.assertIs(item.hardware.parentItem(), item)
            self.assertIsNotNone(engine.probe_plan_readout("Probe 1")["hardware"])
            # The switch hides it everywhere and is remembered.
            editor.more.button.setChecked(True)
            self.assertTrue(editor.hardware_box.isVisibleTo(window))
            editor.hardware_box.setChecked(False)
            self.assertFalse(item.hardware.visible())
            self.assertIsNone(engine.probe_plan_readout("Probe 1")["hardware"])
            self.assertEqual(window.settings.value("plan/hardware"), "false")
            editor.hardware_box.setChecked(True)
            self.assertTrue(item.hardware.visible())
            # A fiber's plan section has no such switch.
            window.run("fiber.plan")
            implants = window.panels["annotate"].implants
            self.assertFalse(implants.plan_editor.hardware_box.isVisibleTo(window))

    @isolated_gui_test
    def test_implants_are_filled_in_3d_and_regions_can_be_see_through(self):
        from driftlessmap.implants import model_mesh
        from driftlessmap.obj_items import FERRULE_GRAY, IMPLANT_FILL_ALPHA, ImplantItem

        with tempfile.TemporaryDirectory() as folder:
            window, engine, _editor = self.planned_window(folder)
            window.run("prism.plan")
            window.run("fiber.plan")
            o = engine.object_ctrl
            for name in ("Prism 1 plan", "Fiber 1 plan"):
                index = o.obj_name.index(name)
                item = engine.object_3d_list[index]
                self.assertIsInstance(item, ImplantItem)
                self.assertIs(item.lines.parentItem(), item)
                # Colour, opacity and width from the object list reach both parts.
                o.current_obj_index = index
                engine.obj_opacity_changed(50)
                self.assertAlmostEqual(item.opts["color"][3], 0.5 * IMPLANT_FILL_ALPHA)
                self.assertAlmostEqual(item.lines.color[3], 0.5)
                engine.obj_size_changed((o.obj_type[index], 4))
                self.assertEqual(item.lines.width, 4)
            # The fiber's ferrule is gray, whatever the fiber's colour.
            fibre_item = engine.object_3d_list[o.obj_name.index("Fiber 1 plan")]
            self.assertIsNotNone(fibre_item.ferrule)
            self.assertEqual(tuple(fibre_item.ferrule.opts["color"][:3]), FERRULE_GRAY)
            self.assertIsNone(engine.object_3d_list[o.obj_name.index("Prism 1 plan")].ferrule)
            # A closed mesh: every edge is shared by exactly two faces.
            for model in (o.obj_data[o.obj_name.index("Prism 1 plan")]["report"]["model"],
                          o.obj_data[o.obj_name.index("Fiber 1 plan")]["report"]["model"]):
                _vertices, faces = model_mesh(model)
                edges = {}
                for face in faces:
                    for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                        key = (min(a, b), max(a, b))
                        edges[key] = edges.get(key, 0) + 1
                self.assertEqual(set(edges.values()), {2})
            # Region meshes: opaque at 100%, see-through below.
            self.assertTrue(engine.small_mesh_list)
            window.region_opacity.setValue(30)
            self.assertEqual(window.region_opacity_value.text(), "30%")
            for mesh in engine.small_mesh_list.values():
                self.assertAlmostEqual(mesh.opts["color"][3], 0.3)
            window.region_opacity.setValue(100)
            for mesh in engine.small_mesh_list.values():
                self.assertAlmostEqual(mesh.opts["color"][3], 0.8)
            # A checked region is one smooth surface around it and its
            # sub-regions, in the region meshes' frame, not its parts' meshes.
            tree = engine.atlas_view.label_tree
            tree.show_labels([10])                     # CH, and so GC
            self.assertEqual(tree.checked, {10, 20})
            surface = engine.region_surfaces[10]
            self.assertTrue(surface.visible())
            self.assertFalse(any(m.visible() for m in engine.small_mesh_list.values()))
            self.assertNotIn(20, engine.region_surfaces)
            vertices = surface.opts["meshdata"].vertexes()
            labels = np.transpose(engine.atlas_view.atlas_label[::-1, :, :], (1, 2, 0))
            inside = np.argwhere(np.isin(labels, [10, 20]))
            np.testing.assert_allclose(vertices.min(axis=0), inside.min(axis=0) - 0.5, atol=1.5)
            np.testing.assert_allclose(vertices.max(axis=0), inside.max(axis=0) + 0.5, atol=1.5)
            tree.labels_by_id[10]['item'].setCheckState(0, Qt.CheckState.Unchecked)
            self.assertFalse(surface.visible())

    @isolated_gui_test
    def test_regions_are_found_by_typing_and_planning_shows_the_ones_it_uses(self):
        from unittest.mock import patch

        from driftlessmap.v2 import region_picker
        from driftlessmap.v2.proposal_dialog import ProposalDialog
        from driftlessmap.v2.region_picker import RegionPicker, region_matches

        regions = [("CH", "child", 10), ("GC", "grandchild", 20), ("CHx", "other", 30)]
        self.assertEqual([r[2] for r in region_matches(regions, "ch")], [10, 30, 20])
        self.assertEqual([r[2] for r in region_matches(regions, "grand")], [20])
        self.assertEqual(region_matches(regions, "nothing"), [])
        with tempfile.TemporaryDirectory() as folder:
            window, engine, editor = self.planned_window(folder)
            tree = engine.atlas_view.label_tree
            # The Regions tree narrows to what is typed, with the parents.
            tree.search.setText("grand")
            hidden = {tree.labels_by_id[i]['item'].text(0): tree.labels_by_id[i]['item']
                      .isHidden() for i in tree.labels_by_id}
            self.assertEqual(hidden, {"root": False, "CH": False, "GC": False})
            tree.search.setText("nothing")
            self.assertTrue(all(rec['item'].isHidden() for rec in tree.labels_by_id.values()))
            tree.search.setText("CH")
            tree.select_first_match()
            self.assertEqual(tree.tree.currentItem().id, 10)
            tree.search.clear()
            self.assertFalse(any(rec['item'].isHidden() for rec in tree.labels_by_id.values()))
            # The picker narrows its list the same way.
            picker = RegionPicker(editor, editor._regions())
            picker.search.setText("grandchild")
            self.assertEqual(picker.list.count(), 1)
            picker.accept()
            self.assertEqual(picker.chosen, 20)
            # Snapping to a region shows it (checked: atlas views and 3D).
            self.assertEqual(tree.checked, set())
            with patch.object(region_picker, "pick_region", return_value=20):
                editor.snap_to_region()
            self.assertEqual(tree.checked, {20})
            lut = tree.lookup_table()
            self.assertTrue(lut[tree.display_index_by_id[20]].any())
            self.assertTrue(engine.show_child_mesh)
            # Regions to record or keep out of are shown too.
            dialog = ProposalDialog(editor)
            with patch.object(region_picker, "pick_region", return_value=10):
                dialog.add_region(dialog.avoid)
            self.assertEqual(dialog.regions(dialog.avoid), [10])
            self.assertIn(10, tree.checked)
            dialog.reject()

    @isolated_gui_test
    def test_review_r7_changed_constraints_need_a_new_search(self):
        from driftlessmap.v2.proposal_dialog import ProposalDialog

        with tempfile.TemporaryDirectory() as folder:
            window, engine, editor = self.planned_window(folder)
            dialog = ProposalDialog(editor)
            dialog._add(dialog.targets, 20)
            dialog.max_ap.setValue(0)
            dialog.max_ml.setValue(0)
            dialog.midline.setValue(0)
            dialog.find()
            self.assertGreater(dialog.table.rowCount(), 0)
            self.assertTrue(dialog.use_button.isEnabled())
            # The selected proposal is shown on the atlas and in the shank view.
            self.assertIn("Probe 1", engine.plan_candidates)
            engine.plan_overlay.refresh()
            self.assertIsNotNone(dialog.shank_view.readout)
            self.assertIn("Checked on every shank", dialog.checks.text())
            def reset():
                dialog.avoid.clear()
                dialog.side.setCurrentIndex(0)
                dialog.midline.setValue(0)
                dialog.max_ml.setValue(0)
                dialog.find()

            for change in (lambda: dialog.side.setCurrentIndex(1),
                           lambda: dialog.midline.setValue(0.1),
                           lambda: dialog.max_ml.setValue(10),
                           lambda: dialog._add(dialog.avoid, 10)):
                reset()
                self.assertTrue(dialog.use_button.isEnabled())
                change()
                self.assertEqual(dialog.table.rowCount(), 0)
                self.assertFalse(dialog.use_button.isEnabled())
                self.assertIn("Find plans again", dialog.reasons.text())
                dialog.use()
                self.assertIsNone(dialog.chosen)
                self.assertNotIn("Probe 1", engine.plan_candidates)
            # A contradictory request is refused and leaves no results.
            dialog.avoid.clear()
            dialog._add(dialog.avoid, 20)
            dialog.find()
            self.assertEqual(dialog.table.rowCount(), 0)
            self.assertIn("is also to be kept out of", dialog.reasons.text())
            dialog.reject()
            self.assertEqual(engine.plan_candidates, {})

    @isolated_gui_test
    def test_review_r8_steering_ends_when_the_plan_is_not_shown(self):
        from PyQt6.QtTest import QTest

        with tempfile.TemporaryDirectory() as folder:
            window, engine, editor = self.planned_window(folder)
            window.show()
            window.activateWindow()
            self.application.processEvents()
            before = engine.probe_plan("Probe 1")
            editor.steer_button.click()
            self.assertTrue(editor.steer_button.isChecked())
            window.go_to("project")
            self.application.processEvents()
            self.assertFalse(editor.steer_button.isChecked())
            window.setFocus()
            QTest.keyClick(window, Qt.Key.Key_W)
            QTest.qWait(700)
            self.assertEqual(engine.probe_plan("Probe 1"), before)
            # Turned on again and the key reaches a hidden editor anyway (a
            # filter left over): the key is not used and steering ends.
            window.go_to("annotate")
            self.application.processEvents()
            editor.steer_button.click()
            editor.hide()
            self.application.processEvents()
            self.assertFalse(editor.steer_button.isChecked())

    @isolated_gui_test
    def test_the_sections_card_adds_opens_renames_and_removes_sections(self):
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QInputDialog, QMessageBox

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            for name, value in (("pfc-1.png", 200), ("pfc-2.png", 120)):
                image = np.zeros((32, 24, 3), dtype=np.uint8)
                image[4:28, 4:20] = value
                cv2.imwrite(str(root / name), image)
                with patch.object(file_dialogs, "get_open_file_names",
                                  return_value=([str(root / name)], "")):
                    window.run("section.load")
            first_id = engine.sections.entries()[0].section_id
            fiber = engine.add_implant("fiber")
            engine.set_implant_outline(fiber.implant_id,
                                       [[10.0, 4.0], [14.0, 4.0], [14.0, 20.0], [10.0, 20.0]])
            self.assertTrue(engine.map_implant(fiber.implant_id)[0])
            window.go_to("project")
            panel = window.panels["project"]
            window.refresh()
            self.assertEqual(panel.section_list.count(), 2)
            self.assertIn("(open)", panel.section_list.item(1).text())
            self.assertIn("mapped: Fiber 1", panel.section_list.item(1).text())
            self.assertIn("section 2 of 2: pfc-2.png", window.rail_status["project"].text())

            # Open the first section from the list.
            panel.section_list.setCurrentRow(0)
            panel.apply_gates()
            self.assertTrue(panel.section_list.currentItem() is not None)
            panel.open_selected()
            self.assertEqual(engine.section_id, first_id)
            window.refresh()
            self.assertIn("(open)", panel.section_list.item(0).text())
            # Annotate names the other section's mapping.
            window.go_to("annotate")
            window.refresh()
            self.assertIn("Also mapped on: pfc-2.png",
                          window.panels["annotate"].mapped_note.text())
            o = engine.object_ctrl
            self.assertIn("from pfc-2.png", o.obj_list[0].toolTip())

            window.go_to("project")
            panel.section_list.setCurrentRow(0)
            with patch.object(QInputDialog, "getText", return_value=("rostral", True)):
                panel.rename_selected()
            self.assertEqual(engine.sections.names()[0], "rostral")
            panel.section_list.setCurrentRow(1)
            panel.move_selected(-1)
            self.assertEqual(engine.sections.names(), ["pfc-2.png", "rostral"])

            # Remove the other section, keeping its results.
            window.refresh()
            panel.section_list.setCurrentRow(0)

            def choose_keep(box):
                box._choice = next(b for b in box.buttons()
                                   if b.text() == "Remove, keep results")
            with patch.object(QMessageBox, "exec", choose_keep), \
                    patch.object(QMessageBox, "clickedButton", lambda box: box._choice):
                panel.remove_selected()
            self.assertEqual(engine.sections.names(), ["rostral"])
            self.assertEqual(len(engine.implant_objects(fiber.implant_id)), 1)
            window.refresh()
            self.assertIn("1 earlier section mapped without a stored image",
                          panel.orphans.text())

    @isolated_gui_test
    def test_brightness_and_contrast_change_the_adjusted_channels(self):
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "three.ome.tif"
            data = np.random.default_rng(4).integers(0, 255, (3, 30, 40), dtype=np.uint8)
            tifffile.imwrite(path, data, ome=True, metadata={"axes": "CYX"})
            window = self.make_window(folder)
            engine = window.engine
            view = engine.image_view
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            window.go_to("section")
            panel = window.panels["section"]
            panel.refresh()
            levels = lambda: [channel_display.channel_levels(view, i) for i in range(3)]  # noqa: E731

            # The controls follow the visible channels: with only the second
            # channel on screen, the sliders change it and nothing else.
            self.assertEqual(panel._adjusted, [0, 1, 2])
            panel._rows[0]["show"].setChecked(False)
            panel._rows[2]["show"].setChecked(False)
            self.assertEqual(panel._adjusted, [1])
            self.assertEqual([row["select"].isChecked() for row in panel._rows],
                             [False, True, False])
            before = levels()
            panel.brightness.setValue(700)          # right of centre: brighter
            after = levels()
            self.assertEqual(after[0], before[0])
            self.assertEqual(after[2], before[2])
            self.assertLess(after[1][1], before[1][1])

            # Ticking Adjust on several rows changes all of them together.
            panel._rows[0]["select"].setChecked(True)
            panel._rows[2]["select"].setChecked(True)
            self.assertEqual(panel._adjusted, [0, 1, 2])
            self.assertIn("(hidden)", panel.adjust_title.text())
            panel.black.setValue(40)
            self.assertEqual([lv[0] for lv in levels()], [40.0, 40.0, 40.0])
            panel.gamma.setValue(1.5)
            self.assertEqual([lv[2] for lv in levels()], [1.5, 1.5, 1.5])
            # Contrast keeps each channel's own brightness (window centre).
            centres = [(b + w) / 2 for b, w, _g in levels()]
            panel.contrast.setValue(800)
            for (b, w, _g), centre in zip(levels(), centres):
                self.assertAlmostEqual((b + w) / 2, centre, delta=1.0)
            panel._auto()
            for index in range(3):
                low, high = channel_display.auto_levels(view, index)
                self.assertEqual(levels()[index][:2], (low, high))

            # Once chosen by hand, Show no longer changes the adjusted set,
            # and the last adjusted channel cannot be unticked.
            panel._rows[0]["show"].setChecked(True)
            self.assertEqual(panel._adjusted, [0, 1, 2])
            for row in panel._rows:
                row["select"].setChecked(False)
            self.assertEqual(panel._adjusted, [2])
            self.assertTrue(panel._rows[2]["select"].isChecked())

            # Renaming keeps the choice; a new section follows Show again.
            panel._rows[2]["name"].setText("Tracer")
            panel._rename(2, "Tracer")
            panel.refresh()
            self.assertEqual(panel._adjusted, [2])
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            panel.refresh()
            self.assertEqual(panel._adjusted, panel._visible_channels())


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
            next_button = window.panels["annotate"].next_button
            self.assertFalse(next_button.isEnabled())
            self.assertIn("atlas", next_button.toolTip())

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
    def test_the_section_bar_shows_and_switches_sections_in_place(self):
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            window.refresh()
            self.assertTrue(window.section_bar.isHidden())       # no section yet
            ids = []
            for name, value in (("rostral.png", 120), ("caudal.png", 160)):
                cv2.imwrite(str(root / name), np.full((32, 24, 3), value, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(root / name), "")):
                    engine.load_image()
                ids.append(engine.section_id)
            window.go_to("register")
            window.refresh()
            bar = window.section_bar
            self.assertFalse(bar.isHidden())
            self.assertEqual([bar.combo.itemText(i) for i in range(bar.combo.count())],
                             ["1/2 · rostral.png", "2/2 · caudal.png"])
            self.assertEqual(bar.combo.currentIndex(), 1)
            self.assertFalse(bar.next.isEnabled())

            window.run("section.previous")
            self.assertEqual(engine.section_id, ids[0])
            self.assertIs(window.stack.currentWidget(), window.panels["register"])
            self.assertEqual(bar.combo.currentIndex(), 0)
            bar._chosen(1)
            self.assertEqual(engine.section_id, ids[1])

    def click_object(self, window, index):
        """Click an object row in the Objects list, then let the shell catch up."""
        row = window.engine.object_ctrl.obj_list[index]
        if hasattr(row, "text_btn_on_click"):
            row.text_btn.click()
        else:
            row.on_click()
        window.refresh()

    def selected_object(self, engine):
        o = engine.object_ctrl
        index = o.current_obj_index
        return None if index is None else (o.obj_name[index], o.obj_type[index])

    @isolated_gui_test
    def test_results_repair_two_changed_sections_by_clicking(self):
        # Review F4 and F5 of 2.6.0: the built fiber stays selected, each
        # changed section is mapped again once, in order, then one build.
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            fiber = None
            for name, value in (("pfc-1.png", 200), ("pfc-2.png", 120)):
                cv2.imwrite(str(root / name), np.full((32, 24, 3), value, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(root / name), "")):
                    engine.load_image()
                fiber = fiber or engine.add_implant("fiber", specs={"diameter_um": 100})
                engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                engine.set_implant_outline(fiber.implant_id, [[10.0, 4.0], [14.0, 4.0],
                                                              [14.0, 20.0], [10.0, 20.0]])
                self.assertTrue(engine.map_implant(fiber.implant_id)[0])
            first, second = [e.section_id for e in engine.sections.entries()]
            self.assertTrue(engine.build_implant(fiber.implant_id)[0])
            built_name = self.selected_object(engine)
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]          # pfc-2 changes
            window.section_bar.open(first)
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]          # and pfc-1
            window.go_to("results")
            panel = window.panels["results"]
            o = engine.object_ctrl
            self.click_object(window, engine.implant_objects(fiber.implant_id, built=True)[0])
            self.assertEqual(self.selected_object(engine)[1], "merged fiber")
            built_name = self.selected_object(engine)
            self.assertFalse(panel.recovery.isHidden())
            self.assertIn("2 sections to map again", panel.repair_note.text())
            self.assertIn("pfc-1.png, pfc-2.png", panel.repair_note.text())
            self.assertEqual(panel.update_button.text(), "Update mapping of pfc-1.png")
            self.assertFalse(panel.rebuild_button.isEnabled())

            panel.update_button.click()
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertEqual(engine.section_id, first)
            self.assertIn("1 section to map again", panel.repair_note.text())
            self.assertEqual(panel.update_button.text(), "Update mapping of pfc-2.png")
            self.assertFalse(panel.rebuild_button.isEnabled())

            # The user looks at another section in between.
            window.run("section.next")
            window.run("section.previous")
            window.go_to("results")
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertEqual(panel.update_button.text(), "Update mapping of pfc-2.png")

            panel.update_button.click()
            self.assertEqual(engine.section_id, second)
            self.assertEqual(self.selected_object(engine), built_name)
            for section in (first, second):
                self.assertEqual(engine.mapping_ledger.get(section, "fiber",
                                                           fiber.implant_id).revision, 2)
            self.assertTrue(panel.update_button.isHidden())
            self.assertTrue(panel.rebuild_button.isEnabled())
            self.assertIn("Every section is mapped", panel.repair_note.text())

            panel.rebuild_button.click()
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertEqual(engine.object_mapping_status(o.current_obj_index), "current")
            self.assertTrue(panel.recovery.isHidden())
            for section in (first, second):          # each mapped again exactly once
                self.assertEqual(engine.mapping_ledger.get(section, "fiber",
                                                           fiber.implant_id).revision, 2)

    @isolated_gui_test
    def test_results_repair_with_mixed_contributions(self):
        # Review F5 of 2.6.0: one section mapped again since the build, one
        # whose registration changed, and one whose mapping no longer exists.
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from driftlessmap.mapping_records import NOT_RECORDED, REGISTRATION_CHANGED
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            fiber = None
            outline = [[10.0, 4.0], [14.0, 4.0], [14.0, 20.0], [10.0, 20.0]]
            for name, value in (("a.png", 200), ("b.png", 160), ("c.png", 120)):
                cv2.imwrite(str(root / name), np.full((32, 24, 3), value, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(root / name), "")):
                    engine.load_image()
                fiber = fiber or engine.add_implant("fiber", specs={"diameter_um": 100})
                engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                engine.set_implant_outline(fiber.implant_id, outline)
                self.assertTrue(engine.map_implant(fiber.implant_id)[0])
            a, b, c = [e.section_id for e in engine.sections.entries()]
            self.assertTrue(engine.build_implant(fiber.implant_id)[0])
            # c: its mapping record is gone (as for parts from older files).
            engine.mapping_ledger.forget(engine.mapping_ledger.get(c, "fiber",
                                                                   fiber.implant_id).unit_id)
            window.section_bar.open(b)
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]        # b: registration changed
            window.section_bar.open(a)
            engine.set_implant_outline(fiber.implant_id, outline)
            self.assertTrue(engine.map_implant(fiber.implant_id)[0])   # a: mapped again
            built = engine.implant_objects(fiber.implant_id, built=True)[0]
            # The missing origin does not hide the changed section.
            self.assertEqual(engine.object_mapping_status(built), REGISTRATION_CHANGED)

            window.go_to("results")
            panel = window.panels["results"]
            self.click_object(window, built)
            built_name = self.selected_object(engine)
            self.assertIn("1 section to map again", panel.repair_note.text())
            self.assertEqual(panel.update_button.text(), "Update mapping of b.png")
            self.assertFalse(panel.rebuild_button.isEnabled())
            self.assertIn("a mapping that no longer exists", panel.mapping.text())
            panel.update_button.click()
            self.assertEqual(engine.section_id, b)
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertTrue(panel.update_button.isHidden())
            self.assertTrue(panel.rebuild_button.isEnabled())
            panel.rebuild_button.click()
            self.assertEqual(self.selected_object(engine), built_name)
            index = engine.object_ctrl.current_obj_index
            # Built from a and b as they are now; c's origin stays unrecorded.
            self.assertEqual(engine.object_mapping_status(index), NOT_RECORDED)
            self.assertIsNone(engine.stale_contribution(index))
            self.assertTrue(panel.recovery.isHidden())
            statuses = dict((record.section_id, status) for record, status
                            in engine.object_contributions(index) if record is not None)
            self.assertEqual(set(statuses), {a, b})
            self.assertTrue(set(statuses.values()) <= {"current", "another section"})

    @isolated_gui_test
    def test_results_repair_built_cells_by_clicking(self):
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((32, 24, 3), 120, np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            data = engine.working_img_data
            data["img-cells"] = [[8.0, 8.0], [12.0, 20.0]]
            data["cell_size"], data["cell_symbol"] = [5, 5], ["o", "o"]
            data["cell_layer_index"] = [0, 0]
            data["cell_count"] = [2] + [0] * (len(data["cell_count"]) - 1)
            engine.transfer_to_atlas_clicked()
            engine.transform_accept()
            engine.make_pieces_of("cells")
            engine.merge_cells()
            o = engine.object_ctrl
            self.assertEqual(o.obj_type, ["merged cells"])
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]
            window.go_to("results")
            panel = window.panels["results"]
            self.click_object(window, 0)
            self.assertFalse(panel.recovery.isHidden())
            self.assertFalse(panel.open_button.isEnabled())       # already open
            panel.update_button.click()
            self.assertEqual(self.selected_object(engine)[1], "merged cells")
            self.assertFalse(panel.recovery.isHidden())
            self.assertIn("mapped again", panel.origin.text())
            panel.rebuild_button.click()
            self.assertEqual(o.obj_type, ["merged cells"])
            self.assertEqual(self.selected_object(engine)[1], "merged cells")
            self.assertEqual(engine.object_mapping_status(0), "current")
            self.assertTrue(panel.recovery.isHidden())

    @isolated_gui_test
    def test_results_repair_a_built_probe_by_clicking(self):
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas", axis_info=True))))
            cv2.imwrite(str(root / "s.png"), np.full((40, 30, 3), 120, dtype=np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            window.go_to("annotate")
            probes = window.panels["annotate"].implants.probe_card
            probes.new_probe("NP A")
            probes.toggle_marking()
            for point in ((13.0, 5.0), (14.0, 25.0)):
                engine.img_stacks_clicked(point)
            probes.add_section()
            window.refresh()
            probes.build_button.click()
            o = engine.object_ctrl
            self.assertIn("merged probe", o.obj_type)
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]
            window.go_to("results")
            panel = window.panels["results"]
            self.click_object(window, o.obj_type.index("merged probe"))
            built_name = self.selected_object(engine)
            self.assertFalse(panel.recovery.isHidden())
            panel.update_button.click()
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertTrue(panel.rebuild_button.isEnabled())
            panel.rebuild_button.click()
            self.assertEqual(self.selected_object(engine), built_name)
            self.assertEqual(engine.object_mapping_status(o.current_obj_index), "current")
            self.assertTrue(panel.recovery.isHidden())

    @isolated_gui_test
    def test_one_button_takes_annotations_from_marks_to_built_objects(self):
        import cv2

        from driftlessmap.v2 import state as v2_state
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((32, 24, 3), 120, np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            window.go_to("annotate")
            panel = window.panels["annotate"]
            panel.refresh()
            self.assertEqual(v2_state.annotation_pipeline(engine)["next"], "mark")
            self.assertFalse(panel.next_button.isEnabled())

            data = engine.working_img_data
            data["img-cells"] = [[8.0, 8.0], [12.0, 20.0]]
            data["cell_size"], data["cell_symbol"] = [5, 5], ["o", "o"]
            data["cell_layer_index"] = [0, 0]
            data["img-contour"] = [[6.0, 6.0], [18.0, 6.0], [18.0, 26.0]]
            self.assertFalse(engine.h2a_transferred)
            expected = [("map", "Next: map to atlas"), ("parts", "Next: make parts"),
                        ("build", "Next: build"), ("inspect", "Next: inspect in Results")]
            for step, label in expected:
                panel.refresh()
                panel.apply_gates()
                self.assertEqual(v2_state.annotation_pipeline(engine)["next"], step)
                self.assertEqual(panel.next_button.text(), label)
                self.assertTrue(panel.next_button.isEnabled())
                self.assertIn("→ ", panel.stages.text())
                panel.next_step()
            self.assertIs(window.stack.currentWidget(), window.panels["results"])
            self.assertEqual(sorted(engine.object_ctrl.obj_type),
                             ["merged cells", "merged contour"])
            self.assertTrue(engine.h2a_transferred)      # prepared by the map step

    @isolated_gui_test
    def test_review_needs_the_checklist_and_offers_blink_and_checkerboard(self):
        import cv2

        from driftlessmap.v2.register_panel import checkerboard
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((32, 24, 3), 120, np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            window.go_to("register")
            panel = window.panels["register"]
            panel.refresh()
            panel.apply_gates()
            mark = [b for b in panel.findChildren(QPushButton)
                    if b.text() == "Mark review complete"][0]
            self.assertFalse(mark.isEnabled())
            self.assertIn("checklist", mark.toolTip())
            for box in panel.checklist:
                box.setChecked(True)
            panel.apply_gates()
            self.assertTrue(mark.isEnabled())
            engine.atlas_tri_inside_data[0] = [1.5, 1.0]        # another registration
            panel.refresh()
            self.assertFalse(any(box.isChecked() for box in panel.checklist))

            # Compare tools need the section-on-atlas preview.
            panel.apply_gates()
            self.assertFalse(panel.blink.isEnabled())
            engine.transfer_to_atlas_clicked()
            panel.refresh()
            panel.apply_gates()
            item = panel.compare_item()        # the overlay itself is never changed
            panel.blink.click()
            panel._blink_tick()
            self.assertFalse(item.isVisible())
            panel._blink_tick()
            self.assertTrue(item.isVisible())
            warped = np.asarray(engine.working_atlas_data["atlas-overlay"])
            panel.checker.click()
            np.testing.assert_array_equal(item.image, checkerboard(warped))
            engine.transfer_to_atlas_clicked()                 # preview removed
            panel.refresh()
            self.assertFalse(panel.blink.isChecked() or panel.checker.isChecked())

        board = checkerboard(np.ones((16, 16), np.uint8), squares=2)
        self.assertEqual(int(board.sum()), 128)
        self.assertEqual((board[0, 0], board[0, 8], board[8, 8]), (1, 0, 1))

    @isolated_gui_test
    def test_comparing_never_changes_the_saved_or_exported_preview(self):
        # Review F3 of 2.6.0: Checkerboard replaced the overlay's pixels, which
        # saving and layer export read.
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap import file_dialogs
        from driftlessmap.persistence import load_driftlessmap_file
        from driftlessmap.v2.register_panel import checkerboard
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            image = np.zeros((32, 24, 3), np.uint8)
            image[4:28, 3:21] = 90
            image[10:20, 8:16] = 220
            cv2.imwrite(str(root / "s.png"), image)
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            window.go_to("register")
            panel = window.panels["register"]
            panel.to_atlas.click()
            window.refresh()
            self.assertTrue(engine.h2a_transferred)
            warped = np.array(engine.working_atlas_data["atlas-overlay"])
            self.assertTrue(warped.any())
            overlay = panel._overlay_item()

            def canonical():
                return np.asarray(engine.get_atlas_single_layer_vis_data("atlas-overlay")["data"])

            panel.checker.click()
            compare = panel.compare_item()
            self.assertTrue(compare.isVisible())
            self.assertFalse(overlay.isVisible())
            np.testing.assert_array_equal(compare.image, checkerboard(warped))
            np.testing.assert_array_equal(canonical(), warped)
            self.assertFalse(np.array_equal(compare.image, warped))

            panel.blink.click()
            panel._blink_timer.timeout.emit()
            self.assertFalse(compare.isVisible())
            panel._blink_timer.timeout.emit()
            self.assertTrue(compare.isVisible())
            self.assertFalse(overlay.isVisible())

            # Layer export and save while comparing keep the warped section.
            engine.save_atlas_layer_data("atlas-overlay", [255, 255, 255], None,
                                         str(root / "layer"))
            layer, error = load_driftlessmap_file(str(root / "layer_atlas-overlay.dmaplayer"),
                                                  expected_kind="layer")
            self.assertIsNone(error)
            np.testing.assert_array_equal(np.asarray(layer["data"]), warped)
            project = root / "p.dmap"
            self.assertTrue(engine.save_project_called(path=str(project)))
            payload, error = load_driftlessmap_file(str(project), expected_kind="project")
            self.assertIsNone(error)
            links = payload["layer_data"]["layer_link"]
            np.testing.assert_array_equal(
                np.asarray(payload["layer_data"]["2d_data"][links.index("atlas-overlay")]),
                warped)

            # Leaving the step ends the comparison; the plain preview is back.
            window.go_to("annotate")
            self.assertFalse(panel.blink.isChecked() or panel.checker.isChecked())
            self.assertFalse(compare.isVisible())
            self.assertTrue(overlay.isVisible())
            np.testing.assert_array_equal(overlay.image, warped)
            window.go_to("register")

            # Undo a mapping step while comparing: the preview stays canonical
            # and the comparison shows the preview that is there.
            panel.checker.click()
            data = engine.working_img_data
            data["img-cells"] = [[8.0, 8.0], [12.0, 20.0]]
            data["cell_size"], data["cell_symbol"] = [5, 5], ["o", "o"]
            data["cell_layer_index"] = [0, 0]
            data["cell_count"] = [2] + [0] * (len(data["cell_count"]) - 1)
            window.run("annotate.map")
            window.run("edit.undo_step")
            window.go_to("register")
            np.testing.assert_array_equal(canonical(), warped)
            if panel.checker.isChecked():
                np.testing.assert_array_equal(
                    compare.image, checkerboard(np.asarray(engine.working_atlas_data[
                        "atlas-overlay"])))
            else:
                self.assertFalse(compare.isVisible())

            # Reopen the project saved while comparing.
            panel.checker.setChecked(True)
            panel._toggle_checker()
            with patch.object(QMessageBox, "question",
                              return_value=QMessageBox.StandardButton.No), \
                    patch.object(file_dialogs, "get_open_file_name",
                                 return_value=(str(project), "")):
                engine.load_project_called()
            window.refresh()
            np.testing.assert_array_equal(canonical(), warped)
            np.testing.assert_array_equal(overlay.image, warped)
            if panel.comparing():
                np.testing.assert_array_equal(compare.image, checkerboard(warped))
            else:
                self.assertTrue(overlay.isVisible())

    @isolated_gui_test
    def test_review_command_needs_the_checklist_on_every_route(self):
        # Review F6 of 2.6.0: the palette marked an unchecked registration reviewed.
        import cv2

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((32, 24, 3), 120, np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            window.go_to("results")             # the palette works from any step
            command = window.registry.get("register.review")
            self.assertIn("checklist", command.reason_unavailable())
            window.run("register.review")
            self.assertEqual(engine.registration_review_state(), "not reviewed")
            window.go_to("register")
            panel = window.panels["register"]
            mark = [b for b in panel.findChildren(QPushButton)
                    if b.text() == "Mark review complete"][0]
            self.assertFalse(mark.isEnabled())
            for box in panel.checklist:
                box.setChecked(True)
            window.refresh()
            self.assertIsNone(command.reason_unavailable())
            self.assertTrue(mark.isEnabled())
            mark.click()
            self.assertEqual(engine.registration_review_state(), "reviewed")

    @isolated_gui_test
    def test_add_sections_shows_progress_and_stops_between_pages(self):
        # Review F7 of 2.6.0: batch progress and a safe stop, through the menu.
        import tifffile
        from unittest.mock import patch

        from PyQt6.QtWidgets import QMessageBox, QProgressDialog

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            path = root / "stack.tif"
            stack = np.stack([np.full((32, 24), 10 * (n + 1), np.uint8) for n in range(8)])
            tifffile.imwrite(path, stack, metadata={"axes": "ZYX"}, photometric="minisblack")
            labels = []

            def each_page(box):
                return next(b for b in box.buttons() if b.text() == "Each page a section")

            def stop_after_three(dialog):
                labels.append(dialog.labelText())
                return len(engine.sections) >= 3        # the user presses Stop

            with patch.object(file_dialogs, "get_open_file_names",
                              return_value=([str(path)], "")), \
                    patch.object(QMessageBox, "exec", lambda box: 0), \
                    patch.object(QMessageBox, "clickedButton", each_page), \
                    patch.object(QProgressDialog, "wasCanceled", stop_after_three):
                window.run("section.load")
            self.assertEqual(engine.sections.names(),
                             ["stack.tif · page {}".format(n) for n in (1, 2, 3)])
            self.assertIn("Adding section 3 of 8: stack.tif · page 3", labels)
            self.assertEqual(float(engine.image_view.current_img.mean()), 30.0)
            self.assertIsNone(window.add_sections_progress)
            self.assertIn("Stopped after 3 sections", "\n".join(
                entry[2] for entry in window.activity))

    @isolated_gui_test
    def test_channel_columns_tick_all_or_none_and_colours_are_named(self):
        import tifffile

        from driftlessmap.v2.section_panel import colour_name

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "four.tif"
            stack = (np.arange(4 * 64 * 48) % 4000).astype(np.uint16).reshape(4, 64, 48)
            tifffile.imwrite(str(path), stack, metadata={"axes": "CYX"}, imagej=True)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_single_image_file(str(path), ".tif"))
            window.go_to("section")
            panel = window.panels["section"]
            panel.refresh()
            toggles = panel._column_toggles
            self.assertEqual(toggles["register"].text(), "All")
            panel.tick_all("register")
            self.assertEqual(engine.registration_input.channels, (0, 1, 2, 3))
            self.assertEqual(toggles["register"].text(), "None")
            panel.tick_all("register")
            self.assertIsNone(engine.registration_input)
            # Adjust starts on every shown channel, so its toggle offers None.
            self.assertEqual(toggles["select"].text(), "None")
            panel.tick_all("select")
            self.assertEqual(panel._adjusted, [0])
            panel.tick_all("select")
            self.assertEqual(panel._adjusted, [0, 1, 2, 3])
            engine.image_view.set_channel_visible(False, 2)
            panel._sync_rows()
            self.assertEqual(toggles["show"].text(), "All")
            panel.tick_all("show")
            self.assertTrue(all(engine.image_view.channel_visible[:4]))
            self.assertFalse(toggles["show"].isEnabled())        # cannot hide them all
            swatch = panel._channel_rows()[0]["swatch"]
            self.assertIn("Channel colour:", swatch.toolTip())
        self.assertEqual(colour_name((250, 5, 0)), "Red")
        self.assertEqual(colour_name((10, 120, 60)), "RGB 10, 120, 60")

    @isolated_gui_test
    def test_the_mapping_history_is_listed_and_clearing_it_is_reported(self):
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            for name in ("a.png", "b.png"):
                cv2.imwrite(str(root / name), np.full((32, 24, 3), 120, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(root / name), "")):
                    engine.load_image()
            first = engine.sections.entries()[0].section_id
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            engine.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            fiber = engine.add_implant("fiber")
            engine.set_implant_outline(fiber.implant_id, [[10.0, 4.0], [14.0, 4.0],
                                                          [14.0, 20.0], [10.0, 20.0]])
            self.assertTrue(engine.map_implant(fiber.implant_id)[0])
            self.assertTrue(engine.build_implant(fiber.implant_id)[0])
            text = window.mapping_history_text()
            self.assertIn("1. Build Fiber 1", text)
            self.assertIn("2. Map Fiber 1", text)
            self.assertTrue(engine.undo_mapping_step())
            self.assertEqual(engine.undo_history.labels(), (["Map Fiber 1"], ["Build Fiber 1"]))

            ok, message = engine.switch_section(first)
            self.assertTrue(ok)
            self.assertIn("history (2 steps) was cleared", message)
            ok, message = engine.switch_section(engine.sections.entries()[1].section_id)
            self.assertNotIn("cleared", message)          # nothing left to clear

    @isolated_gui_test
    def test_the_empty_window_offers_three_ways_to_start(self):
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            texts = {b.text() for b in window.findChildren(QPushButton)}
            for text in ("Load atlas folder…", "Add sections…", "Allen mouse atlas…",
                         "Waxholm rat atlas…", "SWC female rat atlas…", "Your own atlas…",
                         "Plan a probe…", "Plan a fiber…", "Plan a prism…", "Open project…"):
                self.assertIn(text, texts)
            from unittest.mock import patch

            from driftlessmap import file_dialogs

            # No atlas yet: the folder is asked for; cancelled, nothing opens.
            with patch.object(file_dialogs, "get_existing_directory",
                              return_value="") as ask:
                window.start_probe_plan()
            ask.assert_called_once()
            self.assertIn("Planning needs a volume atlas", window.message_label.text())
            self.assertIsNot(window.stack.currentWidget(), window.panels["annotate"])
            self.assertTrue(window.engine.load_volume_atlas(
                str(make_processed_atlas(Path(folder) / "atlas"))))
            window.start_probe_plan()
            self.assertIs(window.stack.currentWidget(), window.panels["annotate"])

    @isolated_gui_test
    def test_save_follows_the_open_file_and_warnings_stay_listed(self):
        import cv2
        from unittest.mock import patch

        from PyQt6.QtWidgets import QDialog, QFileDialog

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            cv2.imwrite(str(root / "s.png"), np.full((32, 24, 3), 120, np.uint8))
            self.assertTrue(engine.load_single_image_file(str(root / "s.png"), ".png"))

            first = root / "first.dmap"
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(first), "")) as ask:
                window.run("project.save")              # a new project: asks once
            ask.assert_called_once()
            self.assertEqual(engine.current_project_path, str(first))
            engine.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            with patch.object(QFileDialog, "getSaveFileName") as ask:
                window.run("project.save")              # then saves where it is
            ask.assert_not_called()
            self.assertFalse(window.is_dirty())

            second = root / "second.dmap"
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(second), "")):
                window.run("project.save_as")
            self.assertEqual(engine.current_project_path, str(second))
            portable = root / "portable.dmap"
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(portable), "")):
                window.run("project.save_portable")
            self.assertTrue(portable.exists())
            self.assertEqual(engine.current_project_path, str(second))   # still the open file

            # A warning stays listed after a later message replaces it.
            with patch.object(QDialog, "exec", return_value=0):
                window.run("session.messages")          # earlier ones seen
            engine.print_message("Something to check.", engine.reminder_color)
            window.message("All done.", "good")
            self.assertEqual(window.message_label.text(), "All done.")
            self.assertFalse(window.activity_button.isHidden())
            self.assertIn("1 message", window.activity_button.text())
            self.assertIn("Warning  Something to check.", window.activity_text())
            with patch.object(QDialog, "exec", return_value=0):
                window.run("session.messages")
            self.assertTrue(window.activity_button.isHidden())

    @isolated_gui_test
    def test_every_step_fits_its_column_in_the_smallest_window(self):
        # Review B10: the Annotate step was wider than its column, so controls
        # were cut off with no way to scroll to them.
        import tifffile

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            window.show()
            window.resize(window.minimumSize())
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            stack = (np.arange(4 * 64 * 48) % 4000).astype(np.uint16).reshape(4, 64, 48)
            tifffile.imwrite(str(root / "s.tif"), stack, metadata={"axes": "CYX"}, imagej=True)
            self.assertTrue(engine.load_single_image_file(str(root / "s.tif"), ".tif"))
            for step, panel in window.panels.items():
                with self.subTest(step):
                    window.go_to(step)
                    window.refresh()
                    self.application.processEvents()
                    self.assertLessEqual(panel.widget().minimumSizeHint().width(),
                                         panel.viewport().width())
            # The view buttons keep their full names.
            for name, view_button in window.view_buttons.items():
                self.assertGreaterEqual(view_button.width(), view_button.sizeHint().width(), name)
            # Annotate with a planned probe and its readout (review UI-4 of 2.8.3),
            # in the smallest window and at 1280 x 800.
            window.run("probe.plan")
            for size in ((window.minimumSize().width(), window.minimumSize().height()),
                         (1280, 800)):
                with self.subTest(size):
                    window.resize(*size)
                    window.go_to("annotate")
                    window.refresh()
                    self.application.processEvents()
                    panel = window.panels["annotate"]
                    self.assertTrue(panel.implants.probe_card.plan_editor.readout
                                    .isVisibleTo(window))
                    self.assertLessEqual(panel.widget().minimumSizeHint().width(),
                                         panel.viewport().width())

    @isolated_gui_test
    def test_a_narrow_window_folds_the_objects_column_away(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            window.show()
            window.resize(1480, 920)
            self.application.processEvents()
            self.assertTrue(window.toggle_inspector_item.isChecked())
            window.resize(1200, 760)
            self.application.processEvents()
            self.assertFalse(window.toggle_inspector_item.isChecked())
            self.assertIn("narrow", window.message_label.text())
            window.resize(1480, 920)
            self.application.processEvents()
            self.assertTrue(window.toggle_inspector_item.isChecked())
            # Narrower still, the step list shows numbers with titles in tooltips.
            window.resize(1100, 700)
            self.application.processEvents()
            self.assertEqual(window.rail.width(), 56)
            self.assertEqual(window.rail_buttons["register"].text(), "4")
            self.assertTrue(window.rail_status["register"].isHidden())
            self.assertIn("Register", window.rail_buttons["register"].toolTip())
            window.resize(1480, 920)
            self.application.processEvents()
            self.assertEqual(window.rail_buttons["register"].text(), "4  Register")
            # Hidden by hand, it stays hidden when the window grows.
            window.toggle_inspector_item.setChecked(False)
            window.resize(1200, 760)
            window.resize(1480, 920)
            self.application.processEvents()
            self.assertFalse(window.toggle_inspector_item.isChecked())

    @isolated_gui_test
    def test_an_unfinished_outline_stays_with_its_section(self):
        # Review B4: a draft started on one section was finished on another.
        import cv2
        from unittest.mock import patch

        from driftlessmap import file_dialogs
        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(engine.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
            ids = []
            for name, value in (("one", 120), ("two", 160)):
                path = root / (name + ".png")
                cv2.imwrite(str(path), np.full((32, 24, 3), value, np.uint8))
                with patch.object(file_dialogs, "get_open_file_name",
                                  return_value=(str(path), "")):
                    engine.load_image()
                ids.append(engine.section_id)
            fiber = engine.add_implant("fiber")
            window.go_to("annotate")
            card = window.panels["annotate"].implants
            editor = card.editor
            card.refresh(select=fiber.implant_id)
            card.draw.setChecked(True)
            card._mode("draw")
            draft = [[5.0, 5.0], [15.0, 5.0], [15.0, 20.0], [5.0, 20.0]]
            for point in draft:
                editor._clicked(point)

            # Open the other section: the draft is parked, not carried over.
            window.go_to("project")
            self.assertTrue(engine.switch_section(ids[0])[0])
            window.refresh()
            window.go_to("annotate")
            self.assertIsNone(editor.mode)
            self.assertEqual(editor.vertices, [])
            editor.finish()
            editor._clicked((7.0, 7.0))
            self.assertEqual(engine.implant_outline(fiber.implant_id)["points"], [])
            state = card.leave_state()
            self.assertNotIn("drawing", state)
            self.assertEqual(state["drafts"], [{"section_id": ids[1],
                                                "implant_id": fiber.implant_id,
                                                "vertices": draft}])

            # Back on its own section the draft continues and closes there.
            self.assertTrue(engine.switch_section(ids[1])[0])
            window.refresh()
            self.assertEqual(editor.mode, "draw")
            self.assertEqual(editor.vertices, draft)
            editor.finish()
            np.testing.assert_allclose(engine.implant_outline(fiber.implant_id)["points"], draft)
            self.assertTrue(engine.switch_section(ids[0])[0])
            window.refresh()
            self.assertEqual(engine.implant_outline(fiber.implant_id)["points"], [])

            # A saved draft of another section is restored only to that section.
            card.resume({"drafts": state["drafts"],
                         "drawing": {"implant_id": fiber.implant_id, "section_id": ids[1],
                                     "vertices": draft}})
            self.assertIsNone(editor.mode)
            self.assertIn(ids[1], editor.drafts)

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
    def test_channels_render_at_screen_size_and_add_up(self):
        from PyQt6.QtGui import QPainter

        with tempfile.TemporaryDirectory() as folder:
            stacks = self.make_window(folder).engine.image_view.img_stacks
            self.assertGreater(len(stacks.image_list), 4)
            for channel in stacks.image_list:
                self.assertTrue(channel.autoDownsample)
                self.assertEqual(channel.paintMode,
                                 QPainter.CompositionMode.CompositionMode_Plus)

    @isolated_gui_test
    def test_checked_regions_show_in_3d(self):
        class Mesh:
            def __init__(self):
                self.shown = False

            def visible(self):
                return self.shown

            def setVisible(self, shown):
                self.shown = shown

        with tempfile.TemporaryDirectory() as folder:
            window = self.make_window(folder)
            engine = window.engine
            self.assertTrue(window.regions_in_3d.isChecked())
            self.assertTrue(engine.show_child_mesh)
            # Region ids are ints in the tree and strings as mesh keys.
            engine.small_mesh_list = {"84": Mesh(), "132": Mesh(), "500": Mesh()}
            engine.atlas_view.label_tree.checked = {972, 84, 132}
            engine.sync_region_meshes()
            shown = {key for key, mesh in engine.small_mesh_list.items() if mesh.visible()}
            self.assertEqual(shown, {"84", "132"})
            window.regions_in_3d.setChecked(False)
            self.assertFalse(any(m.visible() for m in engine.small_mesh_list.values()))
            window.regions_in_3d.setChecked(True)
            engine.atlas_view.label_tree.checked = {84}
            engine.sync_region_meshes()
            shown = {key for key, mesh in engine.small_mesh_list.items() if mesh.visible()}
            self.assertEqual(shown, {"84"})

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
    def test_probe_controls_say_how_to_take_marks_back_and_undo_does(self):
        import cv2

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
            probes.new_probe("NP A")
            window.refresh()
            undo = QKeySequence("Ctrl+Z").toString(QKeySequence.SequenceFormat.NativeText)
            self.assertIn(undo, probes.mark.toolTip())
            self.assertIn("Undo mapping step", probes.add_button.toolTip())
            self.assertIn("Edit marks", probes.add_button.toolTip())
            self.assertIn("Undo mapping step", probes.build_button.toolTip())
            self.assertIn(undo, probes.undo_note.text())

            # What the tooltip promises: Undo removes the last point, one at a time.
            probes.toggle_marking()
            for point in ((13.0, 5.0), (14.0, 15.0), (15.0, 25.0)):
                engine.img_stacks_clicked(point)
            self.assertEqual(len(engine.working_img_data["img-probe"]), 3)
            engine.actionUndo.trigger()
            self.assertEqual(engine.working_img_data["img-probe"], [[13.0, 5.0], [14.0, 15.0]])
            engine.actionUndo.trigger()
            self.assertEqual(engine.working_img_data["img-probe"], [[13.0, 5.0]])
            engine.actionRedo.trigger()
            self.assertEqual(len(engine.working_img_data["img-probe"]), 2)

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
