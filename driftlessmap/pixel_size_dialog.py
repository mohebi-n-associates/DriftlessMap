"""Dialog for the histology pixel size."""

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QLabel,
    QVBoxLayout,
)

from .image_reader import PIXEL_SIZE_RANGE_UM

# Results of :class:`PixelSizeDialog`.
SET, FROM_FILE, UNKNOWN = "set", "file", "unknown"


class PixelSizeDialog(QDialog):
    """Enter micrometres per pixel of the full-resolution image.

    ``file_size`` is the size recorded in the file (offered back with "Use the
    file's value"); ``allow_unknown`` adds "I don't know". After ``exec``,
    :attr:`choice` is :data:`SET` (with :attr:`size_um`), :data:`FROM_FILE`,
    :data:`UNKNOWN` or None when cancelled.
    """

    def __init__(self, current=None, file_size=None, allow_unknown=False,
                 message=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pixel Size")
        self.choice = None
        self.size_um = None
        layout = QVBoxLayout(self)
        text = message or "Micrometres per pixel of the full-resolution image."
        if file_size is not None:
            text += "\nThe file records {:.4g} µm.".format(file_size)
        else:
            text += "\nThe file does not record it."
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(4)
        self.spin.setRange(*PIXEL_SIZE_RANGE_UM)
        self.spin.setSuffix(" µm / pixel")
        self.spin.setValue(current if current is not None else file_size or 1.0)
        layout.addWidget(self.spin)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        if file_size is not None:
            self.file_button = buttons.addButton(
                "Use the file's value", QDialogButtonBox.ButtonRole.ResetRole)
            self.file_button.clicked.connect(lambda: self._finish(FROM_FILE))
        if allow_unknown:
            self.unknown_button = buttons.addButton(
                "I don't know", QDialogButtonBox.ButtonRole.ActionRole)
            self.unknown_button.clicked.connect(lambda: self._finish(UNKNOWN))
        buttons.accepted.connect(lambda: self._finish(SET))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _finish(self, choice):
        self.choice = choice
        self.size_um = self.spin.value() if choice == SET else None
        self.accept()
