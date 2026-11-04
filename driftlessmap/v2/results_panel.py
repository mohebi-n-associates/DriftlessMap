"""Results step: inspect objects, 3D view, export and import."""

import os
import time

from PyQt6.QtWidgets import QLabel, QMessageBox

from .. import file_dialogs
from . import state as v2_state
from .widgets import (
    Card,
    Disclosure,
    StepPanel,
    button,
    grid_of,
    hint_label,
    set_status,
    status_label,
)


class ResultsPanel(StepPanel):
    title = "Results"
    hint = ("Inspect region tables and object details, then export. Opening this step "
            "never changes the results.")

    def build(self):
        engine, shell = self.engine, self.shell
        o = engine.object_ctrl

        selected = self.add(Card("Selected object"))
        self.selected = selected.add(QLabel(""))
        self.origin = selected.add(status_label(""))
        self.mapping = selected.add(hint_label(""))
        # Repair an out-of-date object from here (review U3).
        self.open_button = button("Open the affected section", self.open_affected)
        self.review_button = button("Review registration", self.review_affected)
        self.update_button = button("Update mapping", self.update_affected,
                                    tooltip="Map the affected section's kept marks again "
                                            "with its current registration and remake the part")
        self.rebuild_button = button("Build again", self.rebuild_selected)
        self.recovery = selected.add(grid_of([self.open_button, self.review_button,
                                              self.update_button, self.rebuild_button],
                                             columns=2))
        self.repair_note = selected.add(hint_label(""))
        selected.add(grid_of([
            button("Region table…", o.info_btn.click),
            button("Show on plane", o.vis2d_btn.click),
            button("Compare…", o.compare_btn.click),
            self.gate(button("Show 3D view", lambda: shell.set_view("3d")),
                      shell.needs_volume),
        ], columns=2))
        selected.add(hint_label("Select an object in the Objects list on the right."))

        view3d = self.add(Card("3D view"))
        view3d.add(grid_of([
            button("Dark / light 3D", engine.action3D_Mode_Dark.trigger),
            button("Planes on / off", engine.actionPlanes_On.trigger),
            button("Axes on / off", engine.actionAxes_On.trigger),
        ], columns=2))

        export = self.add(Card(
            "Export",
            "Export all results writes everything available into one new folder: a copy "
            "of the project, each built object (.dmapobj), each probe's localisation "
            "CSVs, the implant table and the layers."))
        self.export_all_button = self.gate(
            button("Export all results…", self.export_all, primary=True),
            self._needs_anything)
        export.add_row(self.export_all_button, None)
        self.export_status = export.add(status_label(""))
        export.add(Disclosure("Individual files", grid_of([
            button("Selected object…", engine.actionSave_Current.trigger),
            button("All probes…", engine.actionSave_Probes.trigger),
            button("All cells…", engine.actionSave_Cells.trigger),
            button("All expression…", engine.actionSave_Virus.trigger),
            button("All contours…", engine.actionSave_Contours.trigger),
            button("All drawings…", engine.actionSave_Drawings.trigger),
            button("All fibers…", lambda: engine.save_merged_object("fiber")),
            button("All prisms…", lambda: engine.save_merged_object("prism")),
            button("Implant table…", lambda: shell.run("implant.export")),
            button("Current layer…", engine.actionCurrent_Layer.trigger),
            button("All layers…", engine.actionAll_Layer.trigger),
        ], columns=2)))

        imports = self.add(Card("Import"))
        imports.add(grid_of([
            button("Objects…", engine.actionLoad_Objects.trigger),
            button("Layers…", engine.actionLoad_Layers.trigger),
            button("Cell points…", engine.actionExternal_Cells.trigger),
        ], columns=2))

    def _needs_anything(self):
        engine = self.engine
        if (engine.atlas_view.atlas_data is None and engine.atlas_view.slice_image_data is None
                and engine.image_view.current_img is None):
            return "Load an atlas or a section first."
        return None

    def export_all(self):
        engine = self.engine
        parent = file_dialogs.get_existing_directory(
            self, "Choose where to put the results folder",
            os.path.dirname(engine.current_project_path or engine.current_img_path or "")
            or os.path.expanduser("~"))
        if not parent:
            return
        stem = (os.path.splitext(os.path.basename(engine.current_project_path))[0]
                if engine.current_project_path else "DriftlessMap")
        folder = os.path.join(parent, "{} results {}".format(
            stem, time.strftime("%Y-%m-%d %H%M")))
        number = 2
        while os.path.exists(folder):
            folder = "{} ({})".format(folder.rsplit(" (", 1)[0], number)
            number += 1
        try:
            paths, notes = engine.export_all_results(folder)
        except OSError as exc:
            set_status(self.export_status, "Could not export: {}".format(exc), "bad")
            return
        text = "Exported {} file{} to {}.".format(len(paths), "" if len(paths) == 1 else "s",
                                                 folder)
        set_status(self.export_status, " ".join([text] + notes), "warn" if notes else "good")
        self.shell.message(text, "warn" if notes else "good")
        if notes:
            QMessageBox.information(self, "Export all results", "\n\n".join([text] + notes))

    # --------------------------------------------------------- recovery
    def _selected_index(self):
        o = self.engine.object_ctrl
        index = o.current_obj_index
        return index if index is not None and index < len(o.obj_name) else None

    def _affected(self):
        index = self._selected_index()
        if index is None:
            return None
        # Out of date first; otherwise a section whose registration is unknown.
        return (self.engine.stale_contribution(index)
                or self.engine.unverified_contribution(index))

    # The object being repaired stays selected through every repair action,
    # also when they open another section or replace parts (review F4).
    def _target(self):
        index = self._selected_index()
        if index is None:
            return None
        o = self.engine.object_ctrl
        return o.obj_id[index], o.obj_name[index], o.obj_type[index]

    def _reselect(self, target):
        if target is None:
            return
        o = self.engine.object_ctrl
        index = o.index_of_id(target[0])
        if index is None:          # built again: the new object of that name and kind
            index = next((i for i in reversed(range(len(o.obj_name)))
                          if (o.obj_name[i], o.obj_type[i]) == target[1:]), None)
        o.select_object(index)

    def _open(self, record):
        if record.section_id != self.engine.section_id:
            target = self._target()
            self.shell.section_bar.open(record.section_id)
            self._reselect(target)
        return record.section_id == self.engine.section_id

    def open_affected(self):
        record = self._affected()
        if record is not None:
            self._open(record)
            self.shell.refresh()

    def review_affected(self):
        record = self._affected()
        if record is None or self._open(record):
            self.shell.go_to("register")

    def update_affected(self):
        engine = self.engine
        target, record = self._target(), self._affected()
        if record is None or not self._open(record):
            return
        name = engine.section_name(record.section_id)
        ok, message = self.shell.panels["annotate"].probes.book.update_section(record.unit_id)
        if ok and record.kind in ("cells", "drawing", "contour", "expression"):
            # Replace the part made from the earlier mapping.
            engine.make_pieces_of(record.kind)
        self._reselect(target)
        index = self._selected_index()
        if ok and index is not None:
            plan = engine.repair_plan(index)
            if plan["remap"]:
                left = plan["remap"]
                message = "Updated the mapping of {}. Next: {} ({} section{} left).".format(
                    name, engine.section_name(left[0].section_id), len(left),
                    "" if len(left) == 1 else "s")
            elif plan["rebuild"]:
                message = ("Updated the mapping of {}. Every section is mapped again: build "
                           "again to use them.".format(name))
        self.shell.message(message, "good" if ok else "bad")
        self.shell.refresh()

    def rebuild_selected(self):
        engine = self.engine
        o = engine.object_ctrl
        index = self._selected_index()
        if index is None:
            return
        target = self._target()
        left = engine.repair_plan(index)["remap"]
        if left:
            self.shell.message("Update the mapping of {} first.".format(
                ", ".join(engine.section_name(r.section_id) for r in left)), "bad")
            return
        kind, name, data = o.obj_type[index], o.obj_name[index], o.obj_data[index]
        if isinstance(data, dict) and data.get("implant_id"):
            ok, message = engine.build_implant(data["implant_id"])
        elif kind == "merged probe":
            from .probes import group_of, probe_of

            ok, message = self.shell.panels["annotate"].probes.book.build(
                probe_of(group_of(name)))
        else:
            merge = {"merged cells": engine.merge_cells, "merged virus": engine.merge_virus,
                     "merged contour": engine.merge_contour,
                     "merged drawing": engine.merge_drawings}.get(kind)
            if merge is None:
                return
            with engine.undoable("Build {}".format(kind.split(" ", 1)[1])):
                o.current_obj_index = index
                o.unmerge_objects()        # parts replaced by newer mappings are left out
                merge()
            ok, message = True, "Built {} again.".format(kind.split(" ", 1)[1])
        self._reselect(target)
        self.shell.message(message, "good" if ok else "bad")
        self.shell.refresh()

    def _sync_recovery(self, index):
        engine = self.engine
        status = engine.object_mapping_status(index) if index is not None else None
        stale = v2_state.is_out_of_date(status)
        unverified = status == v2_state.UNVERIFIED
        self.recovery.setVisible(stale or unverified)
        self.repair_note.setVisible(stale)
        if not (stale or unverified):
            return
        record = self._affected()
        built = engine.object_ctrl.obj_type[index].startswith("merged")
        plan = engine.repair_plan(index) if stale else {"remap": [], "rebuild": False}
        left = plan["remap"]
        # Not verified: opening the section is the check; nothing to update yet.
        # Out of date: map each changed section again, then build once (review F5).
        self.update_button.setVisible(bool(left))
        self.rebuild_button.setVisible(stale and built)
        here = record is not None and record.section_id == engine.section_id
        name = engine.section_name(record.section_id) if record is not None else ""
        self.open_button.setText("Open {}".format(name) if record is not None
                                 else "Open the affected section")
        self.open_button.setEnabled(record is not None and not here
                                    and engine.sections.entry(record.section_id) is not None)
        self.review_button.setEnabled(record is not None)
        self.update_button.setText("Update mapping of {}".format(name) if left
                                   else "Update mapping")
        self.update_button.setEnabled(bool(left))
        self.rebuild_button.setEnabled(not left)
        if left:
            names = [engine.section_name(r.section_id) for r in left]
            self.rebuild_button.setToolTip("Update the mapping of {} first.".format(
                ", ".join(names)))
            self.repair_note.setText(
                "{} section{} to map again with {} current registration: {}. Build again "
                "once {} updated.".format(
                    len(left), "" if len(left) == 1 else "s",
                    "its" if len(left) == 1 else "their", ", ".join(names),
                    "it is" if len(left) == 1 else "all are"))
        else:
            self.rebuild_button.setToolTip("Build the object again from its current parts")
            self.repair_note.setText(
                "Every section is mapped with its current registration; build again to "
                "use the new parts." if built else
                "This part comes from an earlier mapping; make parts again in Annotate.")

    def _contributions_text(self, index):
        engine = self.engine
        lines = []
        for record, status in engine.object_contributions(index):
            if record is None:
                lines.append("a mapping that no longer exists")
                continue
            gone = status == v2_state.OTHER_SECTION and \
                engine.sections.entry(record.section_id) is None
            lines.append("{}: {}; registration {}".format(
                engine.section_name(record.section_id),
                "as mapped (the section is not in the project, so it cannot change)" if gone
                else "current" if status in (v2_state.CURRENT, v2_state.OTHER_SECTION)
                else v2_state.mapping_status_text(status),
                "reviewed" if record.review == "reviewed" else "not reviewed"))
        return "Made from: " + "; ".join(lines) + "." if lines else ""

    def refresh(self):
        o = self.engine.object_ctrl
        index = self._selected_index()
        self._sync_recovery(index)
        if index is None:
            self.selected.setText("No object selected.")
            set_status(self.origin, "", None)
            self.mapping.setText("")
        else:
            self.selected.setText("{} · {}".format(o.obj_name[index], o.obj_type[index]))
            status = self.engine.object_mapping_status(index)
            kind = ("warn" if v2_state.is_out_of_date(status) or status == v2_state.UNVERIFIED
                    else "good" if status == v2_state.CURRENT else None)
            text = "Mapping: " + v2_state.mapping_status_text(status)
            if v2_state.is_out_of_date(status):
                reason = self.engine.out_of_date_reason(index)
                text = "Mapping out of date: {}{}.".format(reason[:1].upper(), reason[1:])
            elif status == v2_state.UNVERIFIED:
                text = "Mapping not verified: {}.".format(self.engine.unverified_reason(index))
            set_status(self.origin, text, kind)
            # Per section, not the session's last mapping (review U3).
            self.mapping.setText(self._contributions_text(index))
