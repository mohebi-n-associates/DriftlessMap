import os
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
        self.assertEqual(__version__, "1.1.0")
        self.assertEqual(driftlessmap.__version__, __version__)

    def test_about_dialog_reports_version_and_current_repository(self):
        dialog = AboutDriftlessMapWindow()
        self.assertIn("DriftlessMap {}".format(__version__), dialog.text())
        self.assertIn("mohebi-n-associates/DriftlessMap", dialog.text())
        self.assertIn("Whitlock-Group/HERBS", dialog.text())
        self.assertIn("not affiliated with or endorsed", dialog.text())


if __name__ == "__main__":
    unittest.main()
