"""The Probes card of the V2 Annotate step."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
)

from .probes import ProbeBook
from .widgets import Card, button, grid_of, hint_label, set_status, status_label


def _swatch(rgb):
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(*rgb))
    return QIcon(pixmap)


class ProbeCard(Card):
    """Name probes, mark each section's track, add sections, build."""

    def __init__(self, shell):
        super().__init__("Probes")
        self.shell = shell
        self.engine = shell.engine
        self.book = ProbeBook(self.engine)
        self._listing = None

        self.guide = self.add(hint_label(""))
        self.list = QListWidget()
        self.list.setMaximumHeight(118)
        self.list.currentRowChanged.connect(lambda _row: self._selection_changed())
        self.add(self.list)
        self.add_row(button("New probe", self.new_probe),
                     button("Rename…", self.rename_probe),
                     button("Delete…", self.delete_probe), None)

        self.active = self.add(QLabel(""))
        self.active.setObjectName("CardTitle")
        self.mark = button("1  Mark track", self.toggle_marking, checkable=True,
                           tooltip="Click along the probe track in the image")
        self.marks = QLabel("")
        self.marks.setObjectName("Muted")
        self.add_row(self.mark, self.marks, None)
        self.add_button = button("2  Add this section", self.add_section, primary=True)
        self.add_row(self.add_button, None)
        self.build_button = button("3  Build probe", self.build_probe)
        self.add_row(self.build_button, None)
        self.status = self.add(status_label(""))
        self.results = grid_of([
            button("Region table…", self.region_table),
            button("Show in 3D", lambda: shell.set_view("3d")),
        ], columns=2)
        self.add(self.results)
        self.add(hint_label(
            "Probe type, site face and multi-shank layout appear in Tool options while "
            "Mark track is on."))
        engine = self.engine
        self.add(grid_of([
            button("Multi-probe…", engine.actionMulti_Probe_Planning.trigger),
            button("Save settings…", engine.actionSave_Probe_Setting.trigger),
            button("Load settings…", engine.actionLoad_Probe_Setting.trigger),
        ], columns=3))

    # ----------------------------------------------------------- helpers
    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _say(self, ok, message):
        set_status(self.status, message, "good" if ok else "bad")
        self.shell.message(message, "good" if ok else "warn")

    def _need_probe(self):
        probe = self.current()
        if probe is None:
            probe = self.book.new()
            self.refresh(select=probe)
        return probe

    # ----------------------------------------------------------- actions
    def new_probe(self):
        probe = self.book.new()
        self.refresh(select=probe)
        set_status(self.status, "{} created. Mark its track, then add the section.".format(probe),
                   None)

    def rename_probe(self):
        probe = self.current()
        if probe is None:
            return
        name, ok = QInputDialog.getText(self, "Rename probe", "New name:", text=probe)
        if not ok:
            return
        try:
            new = self.book.rename(probe, name)
        except ValueError as exc:
            self._say(False, str(exc))
            return
        self.refresh(select=new)

    def delete_probe(self):
        probe = self.current()
        if probe is None:
            return
        count = len(self.book.parts(probe)) + len(self.book.built(probe))
        if count:
            reply = QMessageBox.question(
                self, "Delete probe",
                "Delete {} and its {} section part{} and built object?".format(
                    probe, len(self.book.parts(probe)),
                    "" if len(self.book.parts(probe)) == 1 else "s"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.book.delete(probe)
        self.refresh()

    def toggle_marking(self):
        probe = self._need_probe()
        tool = self.engine.tool_box.checkable_btn_dict["probe_btn"]
        if not tool.isChecked():
            self.book.use_colour(probe)
        self.shell.toggle_tool("probe")

    def add_section(self):
        probe = self._need_probe()
        ok, message = self.book.add_section(probe)
        self._say(ok, message)
        self.refresh(select=probe)

    def build_probe(self):
        probe = self.current()
        if probe is None:
            return
        ok, message = self.book.build(probe)
        self._say(ok, message)
        self.refresh(select=probe)

    def region_table(self):
        probe = self.current()
        if probe is None or not self.book.select_built(probe):
            self._say(False, "Build the probe first.")
            return
        self.engine.object_ctrl.info_btn.click()

    # ----------------------------------------------------------- refresh
    def _selection_changed(self):
        probe = self.current()
        if probe is not None and self.engine.tool_box.checkable_btn_dict["probe_btn"].isChecked():
            self.book.use_colour(probe)
        self._sync_actions()

    def _sync_actions(self):
        engine = self.engine
        probe = self.current()
        pre_plan = engine.image_view.image_file is None
        self.guide.setText(
            "Plan a probe: switch on Mark track, click the entry point and then the tip "
            "on the atlas, add the points to the probe, then build it."
            if pre_plan else
            "For each section that shows the track: switch on Mark track, click along "
            "the track in the section, then Add this section. Build the probe when all "
            "its sections are added.")
        self.active.setText(probe or "No probe yet: Mark track creates one.")
        on_section, on_atlas = self.book.marks()
        parts = []
        if on_section:
            parts.append("{} point{} on the section".format(on_section, "" if on_section == 1 else "s"))
        if on_atlas:
            parts.append("{} on the atlas".format(on_atlas))
        self.marks.setText(", ".join(parts) or "no points marked")
        self.mark.setChecked(engine.tool_box.checkable_btn_dict["probe_btn"].isChecked())
        self.add_button.setText("2  Add this section to {}".format(probe) if probe
                                else "2  Add this section")
        self.add_button.setEnabled(bool(on_section or on_atlas))
        has_parts = bool(probe and self.book.parts(probe))
        built = bool(probe and self.book.built(probe))
        self.build_button.setText("3  {} {}".format("Rebuild" if built and has_parts else "Build",
                                                    probe) if probe else "3  Build probe")
        self.build_button.setEnabled(has_parts)
        self.results.setVisible(built)

    def refresh(self, select=None):
        names = self.book.names()
        listing = [(name, self.book.summary(name)) for name in names]
        keep = select or self.current()
        if listing != self._listing:
            self._listing = listing
            self.list.blockSignals(True)
            self.list.clear()
            for name, summary in listing:
                item = QListWidgetItem(_swatch(self.book.colour(name)),
                                       "{}   ·   {}".format(name, summary))
                item.setData(Qt.ItemDataRole.UserRole, name)
                self.list.addItem(item)
            self.list.blockSignals(False)
        rows = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        if keep in rows and self.current() != keep:
            self.list.setCurrentRow(rows.index(keep))
        elif self.current() is None and rows:
            self.list.setCurrentRow(0)
        self._sync_actions()
