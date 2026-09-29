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
    from PyQt6.QtWidgets import QApplication

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
                              and a.menu() is None]
            reachable = {c.handler for c in window.registry.all()}
            for action in engine_actions:
                with self.subTest(action.text()):
                    self.assertIn(action.trigger, reachable)
            self.assertIn("Suggest landmarks", names)
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
