"""DriftlessMap 2.0 interface: a task-oriented interface on the 1.x engine.

Run with ``driftlessmap-v2`` or ``python -m driftlessmap.v2``. It
keeps its preferences separate from the classic interface, and saves the
same project files.
"""

import sys


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    if any(argument in {"--version", "-V"} for argument in argv[1:]):
        from ..version import __version__

        print("{} (2.0 interface)".format(__version__))
        return 0
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from ..resources import resource_path
    from ..version import __version__

    app = QApplication.instance() or QApplication(argv)
    # The application name keys the 2.0 interface's saved preferences; keep it.
    app.setApplicationName("DriftlessMap-V2-preview")
    app.setApplicationDisplayName("DriftlessMap")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Mohebi & Associates")
    app.setWindowIcon(QIcon(resource_path("icons/app/driftlessmap.png")))

    from .shell import V2Window

    window = V2Window()
    window.show()
    return app.exec()


__all__ = ["main"]
