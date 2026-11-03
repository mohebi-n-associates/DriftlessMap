"""Project step: atlas, the project's sections and project files."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
)

from . import state
from .widgets import Card, StepPanel, button, hint_label

IMPLANT_KINDS = ("fiber", "prism")


class ProjectPanel(StepPanel):
    title = "Project"
    hint = ("Choose the atlas and the sections to work on. The project saves every "
            "part of the work, including every section's exact image pixels.")

    def build(self):
        engine = self.engine
        shell = self.shell

        self.atlas_card = self.add(Card("Atlas"))
        self.atlas_name = self.atlas_card.add(QLabel())
        self.atlas_detail = self.atlas_card.add(hint_label(""))
        tools = QPushButton("Atlas tools")
        menu = QMenu(tools)
        for text, action in (
            ("Download Allen mouse atlas…", engine.actionDownload_Allen_Mice_Atlas),
            ("Download Waxholm rat atlas (v4.01)…", engine.actionDownload),
            ("Download SWC female rat atlas…", engine.actionDownload_SWC_Female_Rat_Atlas),
            ("Process a custom volume atlas…", engine.actionAtlas_Processor),
            (None, None),
            ("Load 2D slice atlas plate…", engine.actionLoad_Image_Atlas),
            ("Register slice information…", engine.actionRegister_Slice_Info),
            ("Pick Bregma on the slice", engine.actionBregma_Picker),
            ("Crop the slice atlas", engine.actionCrop),
            ("Create slice layer", engine.actionCreate_Slice_Layer),
            ("Save processed slice…", engine.actionSave_Slice),
            (None, None),
            ("Switch between volume and slice atlas", engine.actionSwitch_Atlas),
        ):
            if text is None:
                menu.addSeparator()
            else:
                menu.addAction(text, action.trigger)
        tools.setMenu(menu)
        self.atlas_card.add_row(
            button("Load atlas…", lambda: shell.run("atlas.load"), primary=True), tools, None)

        self.section_card = self.add(Card(
            "Sections",
            "Each section keeps its image, display, landmarks, atlas page and tilt, "
            "and marks. Open one to work on it; implants, probes and objects are "
            "built from the mapped sections together."))
        self.section_name = self.section_card.add(QLabel())
        self.section_detail = self.section_card.add(hint_label(""))
        self.section_list = QListWidget()
        self.section_list.setWordWrap(True)
        self.section_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.section_list.setMinimumHeight(110)
        self.section_list.setMaximumHeight(220)
        self.section_list.itemDoubleClicked.connect(lambda _item: self.open_selected())
        self.section_list.currentItemChanged.connect(lambda *_args: self.apply_gates())
        self.section_card.add(self.section_list)
        self.load_section = button("Add section…", lambda: shell.run("section.load"),
                                   primary=True,
                                   tooltip="Load an image as a new section; the open "
                                           "section is kept")
        self.section_card.add_row(
            self.load_section,
            self.gate(button("Open", self.open_selected,
                             tooltip="Work on the selected section (double-click)"),
                      self._needs_other_section),
            self.gate(button("Rename…", self.rename_selected), self._needs_section), None)
        self.section_card.add_row(
            self.gate(button("Move up", lambda: self.move_selected(-1)), self._needs_section),
            self.gate(button("Move down", lambda: self.move_selected(1)), self._needs_section),
            self.gate(button("Remove…", self.remove_selected,
                             tooltip="Remove the selected section from the project"),
                      self._needs_other_section), None)
        self.orphans = self.section_card.add(hint_label(""))
        self._sections_key = None

        files = self.add(Card("Project file"))
        self.file_label = files.add(hint_label(""))
        files.add_row(button("Open…", lambda: shell.run("project.open")),
                      button("Save…", lambda: shell.run("project.save"), primary=True),
                      button("Save portable copy…", lambda: shell.run("project.save_portable")),
                      None)
        files.add(hint_label(
            "Every section's image is saved in the project. A portable copy also "
            "contains each section's original image file. Neither copy contains the "
            "processed volume atlas, which is linked and verified."))

    # ------------------------------------------------------------ sections
    def selected_section(self):
        item = self.section_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _needs_section(self):
        return None if self.selected_section() else "Select a section in the list first."

    def _needs_other_section(self):
        selected = self.selected_section()
        if selected is None:
            return "Select a section in the list first."
        if selected == self.engine.sections.active_id:
            return "This section is open."
        return None

    def _mapped_text(self, section_id):
        engine = self.engine
        names = []
        for record in engine.mapping_ledger.records():
            if record.section_id != section_id:
                continue
            if record.kind in IMPLANT_KINDS:
                implant = engine.implants.get(record.probe)
                name = implant.name if implant is not None else record.kind
            elif record.kind == "probe" and record.probe:
                name = record.probe
            else:
                name = record.kind
            if name not in names:
                names.append(name)
        return ", ".join(names)

    def _row_text(self, entry, active):
        summary = self.engine.section_summary(entry)
        parts = []
        if summary.get("plane"):
            page = summary.get("page")
            parts.append("{}{}".format(str(summary["plane"]).capitalize(),
                                       " page {}".format(page) if page is not None else ""))
        pairs = summary.get("pairs")
        if pairs is not None:
            parts.append("{} landmark pair{}".format(pairs, "" if pairs == 1 else "s"))
        if summary.get("review"):
            parts.append(str(summary["review"]).replace("_", " "))
        mapped = self._mapped_text(entry.section_id)
        if mapped:
            parts.append("mapped: " + mapped)
        name = entry.name or "Section"
        return "{}{}\n   {}".format("▶ " if active else "", name + ("  (open)" if active else ""),
                                     " · ".join(parts) or "nothing done yet")

    def refresh_sections(self):
        engine = self.engine
        book = engine.sync_sections()
        has_image = engine.image_view.current_img is not None
        entries = book.entries() if has_image or len(book) > 1 else []
        rows = [(entry.section_id, self._row_text(entry, entry.section_id == book.active_id))
                for entry in entries]
        if rows != self._sections_key:
            selected = self.selected_section()
            self._sections_key = rows
            self.section_list.clear()
            for section_id, text in rows:
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, section_id)
                if section_id == book.active_id:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                self.section_list.addItem(item)
                if section_id == selected:
                    self.section_list.setCurrentItem(item)
        self.section_list.setVisible(bool(rows))
        orphans = engine.sections_without_image()
        self.orphans.setVisible(bool(orphans))
        self.orphans.setText(
            "{} earlier section{} mapped without a stored image (before projects kept "
            "every section, or removed with results kept): {} results stay in the "
            "project.".format(len(orphans), "" if len(orphans) == 1 else "s",
                              "their" if len(orphans) > 1 else "its"))

    def open_selected(self):
        section_id = self.selected_section()
        if section_id is None or section_id == self.engine.sections.active_id:
            return
        ok, message = self.engine.switch_section(section_id)
        self.shell.message(message, "good" if ok else "bad")
        self.shell.refresh()

    def rename_selected(self):
        section_id = self.selected_section()
        if section_id is None:
            return
        entry = self.engine.sections.entry(section_id)
        name, ok = QInputDialog.getText(self, "Rename section", "Name:", text=entry.name)
        if ok and name.strip():
            self.engine.rename_section(section_id, name.strip())
            self.shell.refresh()

    def move_selected(self, step):
        section_id = self.selected_section()
        if section_id is None:
            return
        self.engine.sections.move(section_id, step)
        self.shell.refresh()

    def remove_selected(self):
        engine = self.engine
        section_id = self.selected_section()
        if section_id is None or section_id == engine.sections.active_id:
            return
        entry = engine.sections.entry(section_id)
        mapped = self._mapped_text(section_id)
        box = QMessageBox(self)
        box.setWindowTitle("Remove section")
        box.setText("Remove {} from the project?".format(entry.name))
        box.setInformativeText(
            "Its image, landmarks and marks are removed. " + (
                "It has mapped results ({}). Keep them, or remove them with the parts "
                "made from them? Built objects that use them are taken apart; parts "
                "from other sections stay to be built again.".format(mapped) if mapped else
                "Nothing was mapped from it."))
        keep = box.addButton("Remove, keep results" if mapped else "Remove",
                             QMessageBox.ButtonRole.AcceptRole)
        drop = box.addButton("Remove with results",
                             QMessageBox.ButtonRole.DestructiveRole) if mapped else None
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked not in (keep, drop) or clicked is None:
            return
        ok, message = engine.remove_section(section_id, delete_results=clicked is drop)
        self.shell.message(message, "good" if ok else "bad")
        self.shell.refresh()

    def refresh(self):
        name, detail = state.atlas_summary(self.engine)
        self.atlas_name.setText(name)
        self.atlas_detail.setText(detail)
        name, detail = state.section_summary(self.engine)
        number, count, _section = self.engine.section_position()
        if count > 1:
            name = "Open: section {} of {} · {}".format(number, count, name)
        self.section_name.setText(name)
        self.section_detail.setText(detail)
        self.refresh_sections()
        path = self.engine.current_project_path
        self.file_label.setText("Project: {}".format(path) if path else
                                "This work has not been saved as a project yet.")
