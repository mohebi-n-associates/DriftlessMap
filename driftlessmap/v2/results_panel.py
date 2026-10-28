"""Results step: inspect objects, 3D view, export and import."""

import os
import time

from PyQt6.QtWidgets import QFileDialog, QLabel, QMessageBox

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
        parent = QFileDialog.getExistingDirectory(
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

    def refresh(self):
        o = self.engine.object_ctrl
        index = o.current_obj_index
        if index is None or index >= len(o.obj_name):
            self.selected.setText("No object selected.")
            set_status(self.origin, "", None)
        else:
            self.selected.setText("{} · {}".format(o.obj_name[index], o.obj_type[index]))
            status = self.engine.object_mapping_status(index)
            kind = ("warn" if v2_state.is_out_of_date(status)
                    else "good" if status == v2_state.CURRENT else None)
            text = "Mapping: " + v2_state.mapping_status_text(status)
            if status == v2_state.BUILD_CHANGED:
                text += ". Build the implant again to use its current specifications."
            elif v2_state.is_out_of_date(status):
                text += ". Update the mapping in Annotate, then make parts (and build) again."
            set_status(self.origin, text, kind)
        state = self.engine.mapping_review_state
        self.mapping.setText({
            "reviewed": "Last mapping used a reviewed registration.",
            "not reviewed": "Last mapping used a registration that was not reviewed.",
            "not recorded": "Last mapping's review state was not recorded.",
        }.get(state, "Nothing mapped to the atlas in this session yet."))
