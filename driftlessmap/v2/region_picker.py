"""Choose an atlas region by typing part of its acronym or name (2.8.5).

Snap tip to region and the proposal dialog's Add… use it instead of a long
drop-down list: the list narrows as you type, exact and leading acronym
matches first.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


def region_matches(regions, text, limit=None):
    """``regions`` (acronym, name, id) matching ``text``, best first.

    Every word of ``text`` must appear in the acronym or the name (any case).
    An exact acronym comes first, then acronyms starting with the text, then
    the rest, each in acronym order.
    """
    words = text.lower().split()
    query = text.strip().lower()
    found = []
    for acronym, name, region in regions:
        haystack = "{} {}".format(acronym, name).lower()
        if all(word in haystack for word in words):
            low = acronym.lower()
            rank = 0 if low == query else 1 if query and low.startswith(query) else 2
            found.append((rank, low, (acronym, name, region)))
    found.sort(key=lambda item: (item[0], item[1]))
    result = [item[2] for item in found]
    return result if limit is None else result[:limit]


class RegionPicker(QDialog):
    def __init__(self, parent, regions, title="Choose a region", prompt="Region:", start=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.regions = list(regions)
        self.chosen = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type part of an acronym or a name, e.g. PL or prelimbic")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumSize(380, 300)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.refilter)
        self.search.returnPressed.connect(self.accept)
        self.list.itemDoubleClicked.connect(lambda _item: self.accept())
        self.refilter("")
        if start is not None:
            for row in range(self.list.count()):
                if self.list.item(row).data(Qt.ItemDataRole.UserRole) == start:
                    self.list.setCurrentRow(row)
                    self.list.scrollToItem(self.list.item(row))
                    break

    def refilter(self, text):
        self.list.clear()
        for acronym, name, region in region_matches(self.regions, text):
            item = QListWidgetItem("{} · {}".format(acronym, name))
            item.setData(Qt.ItemDataRole.UserRole, region)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def accept(self):
        item = self.list.currentItem()
        if item is None:
            return
        self.chosen = int(item.data(Qt.ItemDataRole.UserRole))
        super().accept()


def pick_region(parent, regions, title="Choose a region", prompt="Region:", start=None):
    """The id of the region chosen, or None when cancelled."""
    dialog = RegionPicker(parent, regions, title, prompt, start)
    return dialog.chosen if dialog.exec() == QDialog.DialogCode.Accepted else None
