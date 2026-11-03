"""Annotate step: marking tools, mapping to the atlas and building 3D objects."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem

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
        mapping = self.add(Card(
            "Map annotations to atlas",
            "Mark → check the registration → map → make parts → build. The next step is "
            "offered below; mapping prepares the section → atlas warp preview if needed."))
        self.stages = mapping.add(QLabel(""))
        self.stages.setWordWrap(True)
        self.next_button = self.gate(button("", self.next_step, primary=True),
                                     self._needs_next_step)
        self.review_button = button("Review registration", lambda: shell.go_to("register"))
        mapping.add(grid_of([self.next_button, self.review_button], columns=2))
        self.review = mapping.add(status_label(""))
        mapping.add(hint_label(
            "Mapping copies the section's marks onto the atlas and keeps them, shown "
            "faintly on the section; mapping the same kind again replaces the earlier "
            "mapping. Mapping without a review is allowed; the result is recorded as not "
            "reviewed. Make parts turns atlas marks into parts; Build turns parts into "
            "3D objects."))

        mapped = self.add(Card(
            "Mapped marks on this section",
            "Marks mapped to the atlas are kept here and shown faintly on the section. "
            "They are out of date when the landmarks, atlas plane, page or tilt change "
            "after mapping."))
        self.mapped_list = QListWidget()
        self.mapped_list.setMaximumHeight(130)
        mapped.add(self.mapped_list)
        # A grid, not a row: three buttons side by side overflow the column.
        mapped.add(grid_of([
            self.gate(button("Update mapping", self.update_selected,
                             tooltip="Map the kept marks again with the current registration"),
                      self._needs_mapped_selection),
            self.gate(button("Edit marks", self.edit_selected,
                             tooltip="Put the kept marks back on the section to edit them"),
                      self._needs_mapped_selection),
            self.gate(button("Remove mapping", self.remove_selected,
                             tooltip="Remove this mapping and the parts made from it; "
                                     "built objects that contain one are taken apart"),
                      self._needs_mapped_selection)], columns=2))
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

    # ------------------------------------------------------------ pipeline
    NEXT_LABELS = {"mark": "Next: mark on the section", "map": "Next: map to atlas",
                   "parts": "Next: make parts", "build": "Next: build",
                   "inspect": "Next: inspect in Results"}

    def _needs_next_step(self):
        missing = self.shell.needs_atlas_and_image()
        if missing:
            return missing
        if state.annotation_pipeline(self.engine)["next"] == "mark":
            return "Mark cells, expression, contours or drawings with the tools above first."
        return None

    def next_step(self):
        """Do the pipeline's next step for every kind waiting at it."""
        engine, shell = self.engine, self.shell
        pipeline = state.annotation_pipeline(engine)
        step = pipeline["next"]
        if step == "map":
            if not engine.h2a_transferred:
                engine.transfer_to_atlas_clicked()
                if not engine.h2a_transferred:
                    shell.message("The section could not be warped onto the atlas. Place or "
                                  "check the landmarks in the Register step.", "bad")
                    return
            engine.transform_accept()
            shell.message("Mapped {} to the atlas.".format(", ".join(pipeline["marked"])),
                          "good")
        elif step == "parts":
            for kind in pipeline["mapped"]:
                engine.make_pieces_of(kind)
            shell.message("Made parts of {}.".format(", ".join(pipeline["mapped"])), "good")
        elif step == "build":
            builders = {"cells": engine.merge_cells, "expression": engine.merge_virus,
                        "contour": engine.merge_contour, "drawing": engine.merge_drawings}
            for kind in pipeline["parts"]:
                builders[kind]()
            shell.message("Built {}.".format(", ".join(pipeline["parts"])), "good")
        elif step == "inspect":
            shell.go_to("results")
            return
        shell.refresh()

    def _stage_text(self, pipeline):
        def line(done, active, text):
            return ("✓ " if done else "→ " if active else "· ") + text

        names = lambda kinds: ", ".join(kinds)   # noqa: E731
        step = pipeline["next"]
        reviewed = pipeline["review"] == "reviewed"
        return "\n".join([
            line(step != "mark", step == "mark",
                 "Mark: " + (names(pipeline["marked"]) + " on the section"
                             if pipeline["marked"] else "nothing waiting on the section")),
            line(reviewed, step == "map" and not reviewed,
                 "Check registration: " + ("reviewed" if reviewed else "not reviewed")),
            line(bool(pipeline["mapped"] or pipeline["parts"] or pipeline["built"])
                 and step != "map", step == "map",
                 "Map" + (": " + names(pipeline["mapped"]) + " on the atlas"
                          if pipeline["mapped"] else "")),
            line(bool(pipeline["parts"] or pipeline["built"]) and step not in ("map", "parts"),
                 step == "parts",
                 "Make parts" + (": " + names(pipeline["parts"]) if pipeline["parts"] else "")),
            line(bool(pipeline["built"]) and step == "inspect", step == "build",
                 "Build" + (": " + names(pipeline["built"]) + " built"
                            if pipeline["built"] else "")),
            line(False, step == "inspect", "Inspect and export in Results"),
        ])

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

    def remove_selected(self):
        unit_id = self.selected_unit()
        if unit_id is None:
            return
        ok, message = self.probes.book.remove_section(unit_id)
        self.implants.refresh()
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
        key = (rows, tuple(self.engine.mapped_section_ids()),
               tuple(self.engine.sections.names()))
        if key == self._mapped_key:
            return
        self._mapped_key = key
        selected = self.selected_unit()
        self.mapped_list.clear()
        for unit_id, text, stale in rows:
            item = QListWidgetItem(("⚠ " if stale else "") + text)
            item.setData(Qt.ItemDataRole.UserRole, unit_id)
            self.mapped_list.addItem(item)
            if unit_id == selected:
                self.mapped_list.setCurrentItem(item)
        self.mapped_list.setVisible(bool(rows))
        engine = self.engine
        others = [engine.section_name(sid) for sid in engine.mapped_section_ids()
                  if sid != engine.section_id and engine.sections.entry(sid) is not None]
        note = "" if rows else "Nothing mapped from this section yet."
        if others:
            note = (note + " " if note else "") + (
                "Also mapped on: {}. To change those, open that section with the section "
                "bar above the images.".format(", ".join(others)))
        self.mapped_note.setText(note)

    def refresh(self):
        engine = self.engine
        self.implants.refresh()
        self.refresh_mapped()
        pipeline = state.annotation_pipeline(engine)
        self.stages.setText(self._stage_text(pipeline))
        self.next_button.setText(self.NEXT_LABELS[pipeline["next"]])
        for key, widget in self.tool_buttons.items():
            widget.setChecked(engine.tool_box.checkable_btn_dict["{}_btn".format(key)].isChecked())
        review = engine.registration_review_state()
        missing = self.shell.needs_atlas_and_image()
        if missing:
            set_status(self.review, missing, "warn")
        elif review == "reviewed":
            set_status(self.review, "Registration reviewed; ready to map.", "good")
        else:
            set_status(self.review, "Registration not reviewed; mapped results will be "
                       "recorded as not reviewed.", "warn")
