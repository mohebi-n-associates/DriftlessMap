import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

import herbs
from herbs.about_herbs import AboutHERBSWindow
from herbs.version import __version__


class VersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_public_package_version_uses_the_canonical_value(self):
        self.assertEqual(__version__, "1.0.3")
        self.assertEqual(herbs.__version__, __version__)

    def test_about_dialog_reports_version_and_current_repository(self):
        dialog = AboutHERBSWindow()
        self.assertIn("HERBS {}".format(__version__), dialog.text())
        self.assertIn("mohebi-n-associates/HERBS", dialog.text())
        self.assertNotIn("JingyiGF/HERBS", dialog.text())


if __name__ == "__main__":
    unittest.main()
