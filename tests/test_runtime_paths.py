import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tempfile
import types
from unittest import mock
import unittest

import driftlessmap
from driftlessmap.resources import resource_path
from driftlessmap.run_driftlessmap import run
from driftlessmap.user_settings import load_last_atlas_path, save_last_atlas_path, settings_path
from driftlessmap.uuuuuu import read_qss_file


class RuntimePathTests(unittest.TestCase):
    def test_package_import_does_not_eagerly_import_the_gui(self):
        check = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys, driftlessmap; "
                    "assert callable(driftlessmap.run); "
                    "assert driftlessmap.run_driftlessmap is driftlessmap.run; "
                    "assert 'driftlessmap.app' not in sys.modules"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_resources_resolve_outside_the_package_working_directory(self):
        previous_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                icon = Path(resource_path("icons/backward.svg"))
                style = read_qss_file("qss/main_window.qss")
            finally:
                os.chdir(previous_directory)

        self.assertTrue(icon.is_absolute())
        self.assertTrue(icon.is_file())
        self.assertIn("QMainWindow", style)

    def test_stylesheet_icon_urls_resolve_outside_the_working_directory(self):
        qss_directory = Path(resource_path("qss"))
        previous_directory = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            os.chdir(temporary_directory)
            try:
                styles = [
                    read_qss_file("qss/{}".format(path.name))
                    for path in qss_directory.glob("*.qss")
                ]
            finally:
                os.chdir(previous_directory)

        urls = []
        for style in styles:
            urls.extend(re.findall(r'url\("([^"]+)"\)', style))

        self.assertTrue(urls)
        self.assertTrue(all(Path(url).is_absolute() for url in urls))
        self.assertTrue(all(Path(url).is_file() for url in urls))

    def test_launcher_does_not_change_the_process_working_directory(self):
        observed_directories = []
        fake_gui = types.ModuleType("driftlessmap.app")

        def fake_main():
            observed_directories.append(os.getcwd())
            return 17

        fake_gui.main = fake_main
        original_directory = os.getcwd()
        with mock.patch.dict(sys.modules, {"driftlessmap.app": fake_gui}):
            result = run()

        self.assertEqual(result, 17)
        self.assertEqual(observed_directories, [original_directory])
        self.assertEqual(os.getcwd(), original_directory)

    def test_atlas_preference_uses_an_atomic_user_config_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with mock.patch.dict(
                os.environ,
                {"DRIFTLESSMAP_CONFIG_DIR": temporary_directory},
                clear=False,
            ):
                self.assertIsNone(load_last_atlas_path())
                save_last_atlas_path("/example/atlas")

                self.assertEqual(load_last_atlas_path(), "/example/atlas")
                self.assertEqual(settings_path().parent, Path(temporary_directory))
                settings = json.loads(settings_path().read_text(encoding="utf-8"))
                self.assertEqual(settings["schema_version"], 1)
                self.assertFalse(any(settings_path().parent.glob(".settings-*.tmp")))

    def test_corrupt_preferences_are_ignored(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with mock.patch.dict(
                os.environ,
                {"DRIFTLESSMAP_CONFIG_DIR": temporary_directory},
                clear=False,
            ):
                settings_path().write_text("not json", encoding="utf-8")
                self.assertIsNone(load_last_atlas_path())

    def test_legacy_config_override_remains_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with mock.patch.dict(
                os.environ,
                {
                    "DRIFTLESSMAP_CONFIG_DIR": "",
                    "HERBS_CONFIG_DIR": temporary_directory,
                },
                clear=False,
            ):
                save_last_atlas_path("/legacy/atlas")
                self.assertEqual(load_last_atlas_path(), "/legacy/atlas")
                self.assertEqual(settings_path().parent, Path(temporary_directory))


if __name__ == "__main__":
    unittest.main()
