"""Annotate step: marking tools, mapping to the atlas and building 3D objects."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidget, QListWidgetItem

from . import state
from .implant_card import ImplantCard
from .widgets import Card, StepPanel, button, grid_of, hint_label, set_status, status_label

KIND_NAMES = {"cells": "Cells", "probe": "Probe", "drawing": "Drawing",
              "contour": "Contour", "expression": "Expression"}
IMPLANT_KINDS = ("fiber", "prism")


def record_label(record, status, engine=None):
    if record.kind in IMPLANT_KINDS:
        name = engine.implant_record_name(record) if engine is not None else record.kind
        return "{} · outline · {}".format(name, state.mapping_status_text(status))
    if record.kind == "probe" and record.probe:
        name = "Probe {}".format(record.probe)
    else:
        name = KIND_NAMES.get(record.kind, record.kind)
    if "points" in record.source:
        count = len(record.source["points"])
        size = "{} mark{}".format(count, "" if count == 1 else "s")
    else:
        size = "{} pixels".format(int((record.source["mask"] != 0).sum()))
    return "{} · {} · {}".format(name, size, state.mapping_status_text(status))

TOOLS = (
    ("loc", "Cells", "Click cells, select one cell body, or detect similar cells."),
    ("magic_wand", "Detect by colour", "Expression or contour: click a colour; set tolerance "
                                       "under Tool options, then register it."),
    ("pencil", "Draw", "Draw a line or closed region."),
    ("eraser", "Erase", "Erase marks. With landmarks shown, click a landmark to delete it."),
    ("lasso", "Lasso", "Select a region."),
    ("ruler", "Measure", "Click two points to measure a distance. (M)"),
)


class AnnotatePanel(StepPanel):
    title = "Annotate"
    hint = ("Mark implants (fibers, microprisms, probes), cells, expression, contours and "
            "drawings on the section "
            "or directly on the atlas. Tool settings appear under Tool options above the "
            "image.")

    def build(self):
        engine, shell = self.engine, self.shell
        self.tool_buttons = {}
        self.implants = self.add(ImplantCard(shell))
        self.probes = self.implants.probe_card
        self.gate(self.probes.mark, shell.needs_either)
        tools = self.add(Card("Other annotations",
                              "Cells, expression, contours and drawings. Map them to the "
                              "atlas and make parts below."))
        widgets = []
        for key, label, tip in TOOLS:
            widget = self.gate(button(label, lambda k=key: shell.toggle_tool(k),
                                      checkable=True, tooltip=tip), shell.needs_either)
            self.tool_buttons[key] = widget
            widgets.append(widget)
        tools.add(grid_of(widgets, columns=2))
        mapping = self.add(Card("Map annotations to atlas"))
        self.review = mapping.add(status_label(""))
        self.map_button = mapping.add_row(
            self.gate(button("Mark reviewed", lambda: shell.run("register.review")),
                      lambda: shell.panels["register"]._needs_review_pairs()),
            self.gate(button("Map to atlas", lambda: shell.run("annotate.map"), primary=True),
                      shell.command_reason("annotate.map")), None)
        mapping.add(hint_label(
            "Requires the section → atlas warp preview. Mapping copies the section's marks "
            "onto the atlas and keeps them, shown faintly on the section; mapping the same "
            "kind again replaces the earlier mapping. Mapping without a review "
            "is allowed; the result is recorded as not reviewed."))

        mapped = self.add(Card(
            "Mapped marks on this section",
            "Marks mapped to the atlas are kept here and shown faintly on the section. "
            "They are out of date when the landmarks, atlas plane, page or tilt change "
            "after mapping."))
        self.mapped_list = QListWidget()
        self.mapped_list.setMaximumHeight(130)
        mapped.add(self.mapped_list)
        mapped.add_row(
            self.gate(button("Update mapping", self.update_selected,
                             tooltip="Map the kept marks again with the current registration"),
                      self._needs_mapped_selection),
            self.gate(button("Edit marks", self.edit_selected,
                             tooltip="Put the kept marks back on the section to edit them"),
                      self._needs_mapped_selection), None)
        self.mapped_note = mapped.add(hint_label(""))
        self._mapped_key = None

        objects = self.add(Card(
            "Parts and 3D objects",
            "Make parts turns this section's atlas marks into parts; Build turns parts "
            "into a 3D object. Building replaces the parts with the object; Edit parts restores them."))
        o = engine.object_ctrl
        objects.add(grid_of([
            button("Make parts", lambda: shell.run("annotate.parts")),
            button("Build cells", o.merge_cell_btn.click),
            button("Build expression", o.merge_virus_btn.click),
            button("Build contour", o.merge_contour_btn.click),
            button("Build drawing", o.merge_drawing_btn.click),
            button("Edit parts", o.unmerge_btn.click),
            button("Delete object", o.delete_object_btn.click),
        ], columns=2))
        objects.add(hint_label("Select objects in the Objects list on the right first."))

    def selected_unit(self):
        item = self.mapped_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _needs_mapped_selection(self):
        return None if self.selected_unit() else "Select a mapping in the list first."

    def update_selected(self):
        unit_id = self.selected_unit()
        if unit_id is None:
            return
        ok, message = self.probes.book.update_section(unit_id)
        self.shell.message(message, "good" if ok else "bad")
        self.shell.refresh()

    def edit_selected(self):
        unit_id = self.selected_unit()
        if unit_id is None:
            return
        record = self.engine.mapping_ledger.by_unit(unit_id)
        if self.engine.edit_mapped_marks(unit_id):
            if record is not None and record.kind == "probe" and record.probe:
                self.implants.refresh(select="probe:" + record.probe)
            if record is not None and record.kind in IMPLANT_KINDS:
                self.implants.refresh(select=record.probe)
            self.shell.message("Edit the marks on the section, then map them again to "
                               "replace this mapping.", "good")
        self.shell.refresh()

    def refresh_mapped(self):
        records, _objects = self.engine.mapping_overview()
        rows = [(record.unit_id, record_label(record, status, self.engine),
                 state.is_out_of_date(status))
                for record, status in records]
        if rows == self._mapped_key:
            return
        self._mapped_key = rows
        selected = self.selected_unit()
        self.mapped_list.clear()
        for unit_id, text, stale in rows:
            item = QListWidgetItem(("⚠ " if stale else "") + text)
            item.setData(Qt.ItemDataRole.UserRole, unit_id)
            self.mapped_list.addItem(item)
            if unit_id == selected:
                self.mapped_list.setCurrentItem(item)
        self.mapped_list.setVisible(bool(rows))
        self.mapped_note.setText("" if rows else "Nothing mapped from this section yet.")

    def refresh(self):
        engine = self.engine
        self.implants.refresh()
        self.refresh_mapped()
        for key, widget in self.tool_buttons.items():
            widget.setChecked(engine.tool_box.checkable_btn_dict["{}_btn".format(key)].isChecked())
        review = engine.registration_review_state()
        missing = self.shell.needs_atlas_and_image()
        if missing:
            set_status(self.review, missing, "warn")
        elif not engine.h2a_transferred:
            set_status(self.review, "Preview the section on the atlas first (Register step).",
                       "warn")
        elif review == "reviewed":
            set_status(self.review, "Registration reviewed; ready to map.", "good")
        else:
            set_status(self.review, "Registration not reviewed; mapped results will be "
                       "recorded as not reviewed.", "warn")
