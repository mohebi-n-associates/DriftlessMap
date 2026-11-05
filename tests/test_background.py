import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import QTimer

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

    def test_successful_cleanup_does_not_signal_cancellation(self):
        cancelled = threading.Event()
        self.assertEqual(run_in_background(QWidget(), "Working...", lambda: 42,
                                           cancel_event=cancelled), 42)
        self.assertFalse(cancelled.is_set())

    def test_event_loop_can_cancel_running_work(self):
        cancelled = threading.Event()
        beats = []
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: (beats.append(True), cancelled.set()))
        timer.start(10)
        result = run_in_background(QWidget(), "Working...",
                                   lambda: cancelled.wait(2), cancel_event=cancelled)
        self.assertTrue(result)
        self.assertEqual(beats, [True])

    def test_exceptions_are_raised_in_the_caller(self):
        def fail():
            raise ValueError("bad input")

        with self.assertRaisesRegex(ValueError, "bad input"):
            run_in_background(QWidget(), "Working...", fail)


if __name__ == "__main__":
    unittest.main()
