"""Command registry and command palette for the V2 interface.

Every user action is registered once with a stable id, a name, synonyms
(including 1.x menu names such as "merge" or "triangulation"), an optional
shortcut and a handler. Menus, step panels, shortcuts and the palette all
call the same commands. Availability is a function returning ``None`` when
the command can run, or a reason when it cannot.
"""

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


@dataclass
class Command:
    id: str
    name: str
    handler: object
    group: str = ""
    synonyms: tuple = ()
    shortcut: str = ""
    available: object = None          # callable -> None or reason string
    keywords: str = field(init=False, default="")

    def __post_init__(self):
        self.keywords = " ".join((self.name, self.group) + tuple(self.synonyms)).lower()

    def reason_unavailable(self):
        if self.available is None:
            return None
        try:
            return self.available()
        except Exception as exc:  # availability checks must never break the palette
            return str(exc)


class CommandRegistry:
    def __init__(self):
        self._commands = {}

    def add(self, command):
        if command.id in self._commands:
            raise ValueError("Duplicate command id: {}".format(command.id))
        self._commands[command.id] = command
        return command

    def get(self, command_id):
        return self._commands[command_id]

    def run(self, command_id):
        """Run a command; return the reason if it is unavailable."""
        command = self._commands[command_id]
        reason = command.reason_unavailable()
        if reason:
            return reason
        command.handler()
        return None

    def all(self):
        return list(self._commands.values())

    def search(self, text):
        """Commands whose name, group or synonyms contain every word of ``text``."""
        words = text.lower().split()
        matches = [c for c in self._commands.values() if all(w in c.keywords for w in words)]
        # Names that start with the query rank first.
        query = text.lower().strip()
        return sorted(matches, key=lambda c: (not c.name.lower().startswith(query), c.group, c.name))


class CommandPalette(QDialog):
    """Ctrl/Cmd+K: search every command by name or 1.x synonym."""

    def __init__(self, registry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.setWindowTitle("Search commands")
        self.setModal(True)
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Type a command, e.g. \"suggest landmarks\" or \"merge\"")
        self.results = QListWidget()
        self.reason = QLabel("")
        self.reason.setObjectName("Hint")
        self.reason.setWordWrap(True)
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        layout.addWidget(self.reason)
        self.query.textChanged.connect(self._refresh)
        self.query.returnPressed.connect(self._run_current)
        self.results.itemActivated.connect(lambda _item: self._run_current())
        self.results.currentItemChanged.connect(self._show_reason)
        self.query.installEventFilter(self)
        self.chosen = None
        self._refresh("")

    def eventFilter(self, obj, event):
        if obj is self.query and event.type() == event.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.results.currentRow() + (1 if event.key() == Qt.Key.Key_Down else -1)
                self.results.setCurrentRow(max(0, min(row, self.results.count() - 1)))
                return True
        return super().eventFilter(obj, event)

    def _refresh(self, text):
        self.results.clear()
        for command in self.registry.search(text):
            reason = command.reason_unavailable()
            label = command.name
            if command.group:
                label = "{}  ·  {}".format(command.name, command.group)
            if command.shortcut:
                label += "    {}".format(command.shortcut)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, command.id)
            if reason:
                item.setForeground(Qt.GlobalColor.gray)
                item.setToolTip(reason)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def _show_reason(self, item, _previous=None):
        if item is None:
            self.reason.setText("")
            return
        command = self.registry.get(item.data(Qt.ItemDataRole.UserRole))
        reason = command.reason_unavailable()
        self.reason.setText("Not available: {}".format(reason) if reason else "")

    def _run_current(self):
        item = self.results.currentItem()
        if item is None:
            return
        command_id = item.data(Qt.ItemDataRole.UserRole)
        if self.registry.get(command_id).reason_unavailable():
            return
        self.chosen = command_id
        self.accept()
