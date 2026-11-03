"""File > Sections… in the classic interface: list, open, rename, order and
remove the sections of a project (the 2.0 interface has a Sections card)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class SectionsDialog(QDialog):
    def __init__(self, engine):
        super().__init__(engine)
        self.engine = engine
        self.setWindowTitle("Sections")
        self.resize(460, 360)
        layout = QVBoxLayout(self)
        note = QLabel("Each section keeps its image, landmarks, atlas page and tilt, and "
                      "marks. File > Load Image adds a section.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        layout.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, handler in (("Open", self.open_selected), ("Rename…", self.rename_selected),
                              ("Move up", lambda: self.move_selected(-1)),
                              ("Move down", lambda: self.move_selected(1)),
                              ("Remove…", self.remove_selected), ("Close", self.accept)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            row.addWidget(button)
        layout.addLayout(row)
        self.refresh()

    def refresh(self, select=None):
        book = self.engine.sync_sections()
        self.list.clear()
        for entry in book.entries():
            active = entry.section_id == book.active_id
            item = QListWidgetItem("{}{}".format(entry.name or "Section",
                                                 "  (open)" if active else ""))
            item.setData(Qt.ItemDataRole.UserRole, entry.section_id)
            self.list.addItem(item)
            if entry.section_id == (select or book.active_id):
                self.list.setCurrentItem(item)

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def open_selected(self):
        section_id = self.selected()
        if section_id is None or section_id == self.engine.sections.active_id:
            return
        ok, message = self.engine.switch_section(section_id)
        self.engine.print_message(message, self.engine.normal_color if ok
                                  else self.engine.error_message_color)
        self.refresh()

    def rename_selected(self):
        section_id = self.selected()
        if section_id is None:
            return
        name, ok = QInputDialog.getText(self, "Rename section", "Name:",
                                        text=self.engine.sections.entry(section_id).name)
        if ok and name.strip():
            self.engine.rename_section(section_id, name.strip())
            self.refresh(select=section_id)

    def move_selected(self, step):
        section_id = self.selected()
        if section_id is not None:
            self.engine.sections.move(section_id, step)
            self.refresh(select=section_id)

    def remove_selected(self):
        engine = self.engine
        section_id = self.selected()
        if section_id is None:
            return
        if section_id == engine.sections.active_id:
            QMessageBox.information(self, "Remove section",
                                    "Open another section before removing this one.")
            return
        mapped = bool(engine.section_mappings(section_id))
        box = QMessageBox(self)
        box.setWindowTitle("Remove section")
        box.setText("Remove {} from the project?".format(engine.sections.entry(section_id).name))
        box.setInformativeText(
            "Its image, landmarks and marks are removed. Keep its mapped results, or "
            "remove them with the parts made from them? Built objects that use them "
            "are taken apart; parts from other sections stay to be built again." if mapped
            else "Nothing was mapped from it.")
        keep = box.addButton("Remove, keep results" if mapped else "Remove",
                             QMessageBox.ButtonRole.AcceptRole)
        drop = box.addButton("Remove with results",
                             QMessageBox.ButtonRole.DestructiveRole) if mapped else None
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() not in (keep, drop) or box.clickedButton() is None:
            return
        ok, message = engine.remove_section(section_id, delete_results=box.clickedButton() is drop)
        engine.print_message(message, engine.normal_color if ok else engine.error_message_color)
        self.refresh()
