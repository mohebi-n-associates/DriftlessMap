import os
import subprocess
import sys
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

import driftlessmap
from driftlessmap.about import AboutDriftlessMapWindow
from driftlessmap.version import __version__


class VersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_public_package_version_uses_the_canonical_value(self):
        self.assertEqual(__version__, "1.4.0")
        self.assertEqual(driftlessmap.__version__, __version__)

    def test_main_window_displays_the_version(self):
        from driftlessmap.app import DriftlessMap

        window = DriftlessMap()
        self.assertIn("DriftlessMap {}".format(__version__), window.windowTitle())
        self.assertEqual(window.version_label.text(), "DriftlessMap {}".format(__version__))
        self.assertFalse(window.windowIcon().isNull())
        window.close()

    def test_about_dialog_reports_version_and_current_repository(self):
        dialog = AboutDriftlessMapWindow()
        self.assertIn("DriftlessMap {}".format(__version__), dialog.text())
        self.assertIn("mohebi-n-associates/DriftlessMap", dialog.text())
        self.assertIn("Whitlock-Group/HERBS", dialog.text())
        self.assertIn("not affiliated with or endorsed", dialog.text())

    def test_module_version_flag_does_not_launch_the_gui(self):
        result = subprocess.run(
            [sys.executable, "-m", "driftlessmap", "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), __version__)


if __name__ == "__main__":
    unittest.main()
