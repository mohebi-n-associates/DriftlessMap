from PyQt6.QtWidgets import *
from .version import __version__


class AboutHERBSWindow(QMessageBox):
    def __init__(self):
        super().__init__()

        self.setIcon(QMessageBox.Icon.NoIcon)
        self.setWindowTitle("About HERBS")
        self.setText("HERBS {}\n\n".format(__version__) +
                     "HERBS is aiming to provide a pleasant platform "
                     "for histological image registration in neuroscience. \n"
                     "\n"
                     "If you have any requests or questions ---- \n"
                     "\n"
                     "Please contact maintainers: \n"
                     "jingyi.g.fuglstad@gmail.com \n"
                     "\n"
                     "Or leave an issue/discussion on HERBS GitHub: \n"
                     "https://github.com/mohebi-n-associates/HERBS \n"
                     "\n"
                     "Please always read the Update Log after updating: \n"
                     "https://github.com/mohebi-n-associates/HERBS/blob/main/UpdateLog.md")
        self.setStandardButtons(QMessageBox.StandardButton.Close)
