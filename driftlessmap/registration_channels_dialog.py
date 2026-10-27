"""Dialog for choosing the channels used by automatic registration."""

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)

from .registration_input import RegistrationInput


class RegistrationChannelsDialog(QDialog):
    """Choose Legacy input or explicit channels, e.g. DAPI only."""

    def __init__(self, channel_names, current=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registration Channels")
        self._names = [str(name) for name in channel_names]
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Choose the channels that Suggest Atlas Section and Propose Landmarks "
            "use. Display settings and channel visibility are not used."
        ))
        self.mode_group = QButtonGroup(self)
        self.channels_mode = QRadioButton("Selected channels")
        self.legacy_mode = QRadioButton("Legacy (all channels, as in DriftlessMap 1.6)")
        self.mode_group.addButton(self.channels_mode)
        self.mode_group.addButton(self.legacy_mode)
        layout.addWidget(self.channels_mode)
        self.boxes = []
        for index, name in enumerate(self._names):
            box = QCheckBox("{}  (channel {})".format(name, index + 1))
            box.setContentsMargins(24, 0, 0, 0)
            box.toggled.connect(self._update_ok)
            self.boxes.append(box)
            layout.addWidget(box)
        layout.addWidget(self.legacy_mode)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.mode_group.buttonToggled.connect(self._update_ok)

        if current is not None and current.mode == "legacy":
            self.legacy_mode.setChecked(True)
        else:
            self.channels_mode.setChecked(True)
            selected = set(current.channels) if current is not None else set()
            for index, box in enumerate(self.boxes):
                box.setChecked(index in selected)
        self._update_ok()

    def _update_ok(self, *args):
        channel_mode = self.channels_mode.isChecked()
        for box in self.boxes:
            box.setEnabled(channel_mode)
        chosen = [box for box in self.boxes if box.isChecked()]
        ok = not channel_mode or bool(chosen)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        self.note.setText("" if ok else "Select at least one channel.")

    def recipe(self):
        """The chosen :class:`RegistrationInput`."""
        if self.legacy_mode.isChecked():
            return RegistrationInput.legacy()
        chosen = [index for index, box in enumerate(self.boxes) if box.isChecked()]
        return RegistrationInput.from_channels(chosen, [self._names[i] for i in chosen])
