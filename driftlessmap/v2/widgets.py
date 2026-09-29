"""Small building blocks shared by the V2 step panels."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """A titled group of related controls."""

    def __init__(self, title=None, hint=None, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 10, 12, 12)
        self.layout.setSpacing(8)
        if title:
            self.title = QLabel(title)
            self.title.setObjectName("CardTitle")
            self.layout.addWidget(self.title)
        if hint:
            self.layout.addWidget(hint_label(hint))

    def add(self, widget, stretch=0):
        self.layout.addWidget(widget, stretch)
        return widget

    def add_row(self, *widgets, stretch_last=False):
        row = QHBoxLayout()
        row.setSpacing(6)
        for widget in widgets:
            if widget is None:
                row.addStretch(1)
            else:
                row.addWidget(widget)
        if stretch_last:
            row.addStretch(1)
        self.layout.addLayout(row)
        return row


class Disclosure(QWidget):
    """A section that expands when its header is clicked."""

    def __init__(self, title, content, expanded=False, parent=None):
        super().__init__(parent)
        self.button = QToolButton()
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.content = content
        content.setVisible(expanded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.button)
        layout.addWidget(content)
        self.button.toggled.connect(self._toggle)

    def _toggle(self, checked):
        self.content.setVisible(checked)
        self.button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)


def hint_label(text):
    label = QLabel(text)
    label.setObjectName("Hint")
    label.setWordWrap(True)
    return label


def status_label(text="", kind=None):
    label = QLabel(text)
    label.setWordWrap(True)
    set_status(label, text, kind)
    return label


def set_status(label, text, kind=None):
    """kind: "good", "warn", "bad" or None (plain)."""
    label.setText(text)
    name = {"good": "StatusGood", "warn": "StatusWarn", "bad": "StatusBad"}.get(kind, "")
    if label.objectName() != name:
        label.setObjectName(name)
        label.style().unpolish(label)
        label.style().polish(label)


def button(text, handler=None, primary=False, tooltip=None, checkable=False):
    widget = QPushButton(text)
    if primary:
        widget.setProperty("primary", True)
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCheckable(checkable)
    if handler is not None:
        widget.clicked.connect(lambda *_args: handler())
    return widget


def grid_of(widgets, columns=2):
    frame = QWidget()
    grid = QGridLayout(frame)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(6)
    for index, widget in enumerate(widgets):
        grid.addWidget(widget, index // columns, index % columns)
    return frame


class StepPanel(QScrollArea):
    """A scrollable step panel with a title, a hint and cards."""

    title = ""
    hint = ""

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.engine = shell.engine
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("TaskColumn")
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(14, 14, 14, 14)
        self.body.setSpacing(12)
        heading = QLabel(self.title)
        heading.setObjectName("StepTitle")
        self.body.addWidget(heading)
        if self.hint:
            self.body.addWidget(hint_label(self.hint))
        self.setWidget(body)
        self.build()
        self.body.addStretch(1)

    def add(self, widget):
        self.body.addWidget(widget)
        return widget

    def build(self):
        raise NotImplementedError

    def refresh(self):
        """Update from the engine; called periodically and after commands."""
