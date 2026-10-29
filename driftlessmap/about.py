from PyQt6.QtWidgets import QMessageBox
from .version import __version__


class AboutDriftlessMapWindow(QMessageBox):
    def __init__(self):
        super().__init__()

        self.setIcon(QMessageBox.Icon.NoIcon)
        self.setWindowTitle("About DriftlessMap")
        self.setText(
            "DriftlessMap {}\n\n".format(__version__)
            + "Interactive histology registration and brain-atlas mapping.\n\n"
            + "Developed by Mohebi & Associates, Ali Mohebi and "
            + "Esther Lara Gonzalez.\n\n"
            + "Acknowledgements: DriftlessMap grew out of HERBS, now a legacy "
            + "project, created by Jingyi Guo Fuglstad, Pearl Saldanha, "
            + "Jacopo Paglia and Jonathan R. Whitlock "
            + "(https://github.com/Whitlock-Group/HERBS).\n\n"
            + "DriftlessMap issues and discussions:\n"
            + "https://github.com/mohebi-n-associates/DriftlessMap\n\n"
            + "Licensed under the MIT License. DriftlessMap is not affiliated "
            + "with or endorsed by the original HERBS developers."
        )
        self.setStandardButtons(QMessageBox.StandardButton.Close)
