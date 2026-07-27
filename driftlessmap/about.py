from PyQt6.QtWidgets import *
from .version import __version__


class AboutDriftlessMapWindow(QMessageBox):
    def __init__(self):
        super().__init__()

        self.setIcon(QMessageBox.Icon.NoIcon)
        self.setWindowTitle("About DriftlessMap")
        self.setText(
            "DriftlessMap {}\n\n".format(__version__)
            + "Interactive histology registration and brain-atlas mapping.\n\n"
            + "DriftlessMap is independently maintained and began as a fork "
            + "of HERBS, created by Jingyi Guo Fuglstad, Pearl Saldanha, "
            + "Jacopo Paglia, Jonathan R. Whitlock, and contributors.\n\n"
            + "Original HERBS project:\n"
            + "https://github.com/Whitlock-Group/HERBS\n\n"
            + "DriftlessMap issues and discussions:\n"
            + "https://github.com/mohebi-n-associates/DriftlessMap\n\n"
            + "Licensed under the MIT License. DriftlessMap is not affiliated "
            + "with or endorsed by the original HERBS developers."
        )
        self.setStandardButtons(QMessageBox.StandardButton.Close)
