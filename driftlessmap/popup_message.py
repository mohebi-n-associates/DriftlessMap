import PyQt6
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *


class PopupMessage(QMessageBox):

    def __init__(self, parent=None):
        QMessageBox.__init__(self)

        self.setWindowTitle("Caution!")
        self.setText('Histological image: is oversized.')
        button = self.exec()
        if button == QMessageBox.StandardButton.Ok:
            print('222')