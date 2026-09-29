"""Results step: inspect objects, 3D view, export and import."""

from PyQt6.QtWidgets import QLabel

from .widgets import Card, StepPanel, button, grid_of, hint_label


class ResultsPanel(StepPanel):
    title = "Results"
    hint = ("Inspect region tables and object details, then export. Opening this step "
            "never changes the results.")

    def build(self):
        engine, shell = self.engine, self.shell
        o = engine.object_ctrl

        selected = self.add(Card("Selected object"))
        self.selected = selected.add(QLabel(""))
        self.mapping = selected.add(hint_label(""))
        selected.add(grid_of([
            button("Region table…", o.info_btn.click),
            button("Show on plane", o.vis2d_btn.click),
            button("Compare…", o.compare_btn.click),
            button("Show 3D view", lambda: shell.set_view("3d")),
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
            "Object files (.dmapobj) are for sharing; the project already contains "
            "every object. Probe exports write the localisation CSVs."))
        export.add(grid_of([
            button("Selected object…", engine.actionSave_Current.trigger),
            button("All probes…", engine.actionSave_Probes.trigger),
            button("All cells…", engine.actionSave_Cells.trigger),
            button("All expression…", engine.actionSave_Virus.trigger),
            button("All contours…", engine.actionSave_Contours.trigger),
            button("All drawings…", engine.actionSave_Drawings.trigger),
            button("Current layer…", engine.actionCurrent_Layer.trigger),
            button("All layers…", engine.actionAll_Layer.trigger),
        ], columns=2))

        imports = self.add(Card("Import"))
        imports.add(grid_of([
            button("Objects…", engine.actionLoad_Objects.trigger),
            button("Layers…", engine.actionLoad_Layers.trigger),
            button("Cell points…", engine.actionExternal_Cells.trigger),
        ], columns=2))

    def refresh(self):
        o = self.engine.object_ctrl
        index = o.current_obj_index
        if index is None or index >= len(o.obj_name):
            self.selected.setText("No object selected.")
        else:
            self.selected.setText("{} · {}".format(o.obj_name[index], o.obj_type[index]))
        state = self.engine.mapping_review_state
        self.mapping.setText({
            "reviewed": "Last mapping used a reviewed registration.",
            "not reviewed": "Last mapping used a registration that was not reviewed.",
            "not recorded": "Last mapping's review state was not recorded.",
        }.get(state, "Nothing mapped to the atlas in this session yet."))
