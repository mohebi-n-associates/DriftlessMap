import tests.settings_isolation  # noqa: F401  (before the app reads settings)
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QFileDialog

from driftlessmap import file_dialogs, user_settings


class FileDialogFolderTests(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.TemporaryDirectory()
        self.work = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ, {"DRIFTLESSMAP_CONFIG_DIR": self.config.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.config.cleanup)
        self.addCleanup(self.work.cleanup)
        file_dialogs._last.update(folder=None, loaded=False)
        self.addCleanup(file_dialogs._last.update, folder=None, loaded=False)
        self.home = os.path.expanduser("~")

    def test_default_starts_follow_the_last_folder(self):
        work = self.work.name
        # Nothing remembered yet: dialogs start where they asked to.
        self.assertEqual(file_dialogs.start_in(self.home), self.home)
        file_dialogs.remember(os.path.join(work, "section.tif"))
        self.assertEqual(file_dialogs.start_in(""), os.path.abspath(work))
        self.assertEqual(file_dialogs.start_in(None), os.path.abspath(work))
        self.assertEqual(file_dialogs.start_in(self.home), os.path.abspath(work))
        # A suggested name in the home folder keeps its name.
        self.assertEqual(file_dialogs.start_in(os.path.join(self.home, "p.dmap")),
                         os.path.join(os.path.abspath(work), "p.dmap"))
        # A specific folder, such as the image's, is kept.
        specific = Path(work) / "images"
        specific.mkdir()
        self.assertEqual(file_dialogs.start_in(str(specific)), str(specific))
        self.assertEqual(file_dialogs.start_in(str(specific / "s.png")),
                         str(specific / "s.png"))
        # A folder that is gone falls back to the last one.
        self.assertEqual(file_dialogs.start_in(os.path.join(work, "gone", "x.dmap")),
                         os.path.join(os.path.abspath(work), "x.dmap"))

    def test_the_folder_is_remembered_between_sessions(self):
        file_dialogs.remember(self.work.name)
        file_dialogs._last.update(folder=None, loaded=False)  # a new session
        self.assertEqual(file_dialogs.last_folder(), os.path.abspath(self.work.name))
        # The atlas path and the folder share the settings file.
        user_settings.save_last_atlas_path("/example/atlas")
        self.assertEqual(user_settings.load_last_folder(), os.path.abspath(self.work.name))
        self.assertEqual(user_settings.load_last_atlas_path(), "/example/atlas")

    def test_dialogs_start_there_and_remember_the_choice(self):
        first = Path(self.work.name) / "first"
        first.mkdir()
        chosen = first / "project.dmap"
        with patch.object(QFileDialog, "getSaveFileName",
                          return_value=(str(chosen), "")) as dialog:
            file_dialogs.get_save_file_name(None, "Save", self.home, "*.dmap")
        self.assertEqual(dialog.call_args[0][2], self.home)  # nothing remembered yet
        with patch.object(QFileDialog, "getExistingDirectory", return_value="") as dialog:
            file_dialogs.get_existing_directory(None, "Folder")
        self.assertEqual(dialog.call_args[0][2], str(first))
        with patch.object(QFileDialog, "getOpenFileNames",
                          return_value=([str(Path(self.work.name) / "a.dmaplayer")], "")):
            file_dialogs.get_open_file_names(None, "Open", self.home, "*")
        self.assertEqual(file_dialogs.last_folder(), os.path.abspath(self.work.name))


if __name__ == "__main__":
    unittest.main()
