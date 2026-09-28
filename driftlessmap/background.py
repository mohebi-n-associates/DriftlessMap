"""Run long, GUI-free computations without freezing the interface."""

from PyQt6.QtCore import QEventLoop, QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QProgressDialog


class _Worker(QObject):
    done = pyqtSignal(object, object)

    def __init__(self, function, args, kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.function(*self.args, **self.kwargs)
        except BaseException as exc:  # re-raised on the caller's thread
            self.done.emit(None, exc)
        else:
            self.done.emit(result, None)


def run_in_background(parent, message, function, *args, **kwargs):
    """Call ``function`` on a worker thread and return its result.

    The caller waits in a local event loop, so the window keeps repainting
    while a window-modal progress dialog blocks further input. Exceptions are
    re-raised in the caller. ``function`` must not touch Qt widgets.

    Without a running application, or when called off the GUI thread, the
    function simply runs inline.
    """
    application = QApplication.instance()
    if application is None or QThread.currentThread() is not application.thread():
        return function(*args, **kwargs)

    thread = QThread()
    worker = _Worker(function, args, kwargs)
    worker.moveToThread(thread)
    outcome = {}
    loop = QEventLoop()

    def finished(result, error):
        outcome["result"] = result
        outcome["error"] = error
        loop.quit()

    worker.done.connect(finished, Qt.ConnectionType.QueuedConnection)
    thread.started.connect(worker.run)

    dialog = QProgressDialog(message, None, 0, 0, parent)
    dialog.setWindowTitle("DriftlessMap")
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(400)
    dialog.setCancelButton(None)

    thread.start()
    try:
        if not outcome:
            loop.exec()
    finally:
        thread.quit()
        thread.wait()
        dialog.close()
        dialog.deleteLater()
        worker.deleteLater()

    if outcome.get("error") is not None:
        raise outcome["error"]
    return outcome.get("result")
