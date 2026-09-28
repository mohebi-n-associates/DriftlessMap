import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QWidget

from driftlessmap.background import run_in_background


class BackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_work_runs_off_the_gui_thread_and_returns_its_result(self):
        parent = QWidget()
        gui_thread = threading.get_ident()
        seen = []

        def work(value, *, scale):
            seen.append(threading.get_ident())
            return value * scale

        self.assertEqual(run_in_background(parent, "Working...", work, 6, scale=7), 42)
        self.assertNotEqual(seen[0], gui_thread)

    def test_exceptions_are_raised_in_the_caller(self):
        def fail():
            raise ValueError("bad input")

        with self.assertRaisesRegex(ValueError, "bad input"):
            run_in_background(QWidget(), "Working...", fail)


if __name__ == "__main__":
    unittest.main()
