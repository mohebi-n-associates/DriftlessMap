"""Annotate step: marking tools, mapping to the atlas and building 3D objects."""

from .widgets import Card, StepPanel, button, grid_of, hint_label, set_status, status_label

TOOLS = (
    ("probe", "Probe track", "Click points along a probe track (probe type and site face "
                             "appear under Tool options)."),
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
    hint = ("Mark probe tracks, cells, expression, contours and drawings on the section "
            "or directly on the atlas. Tool settings appear under Tool options above the "
            "image.")

    def build(self):
        engine, shell = self.engine, self.shell
        self.tool_buttons = {}
        tools = self.add(Card("Tools"))
        widgets = []
        for key, label, tip in TOOLS:
            widget = button(label, lambda k=key: shell.toggle_tool(k), checkable=True,
                            tooltip=tip)
            self.tool_buttons[key] = widget
            widgets.append(widget)
        tools.add(grid_of(widgets, columns=2))
        probe = self.add(Card("Probe settings"))
        probe.add(grid_of([
            button("Multi-probe…", engine.actionMulti_Probe_Planning.trigger),
            button("Save settings…", engine.actionSave_Probe_Setting.trigger),
            button("Load settings…", engine.actionLoad_Probe_Setting.trigger),
        ], columns=2))
        probe.add(hint_label(
            "Probe settings files restore geometry, faces and multi-probe offsets. Save "
            "Project keeps the complete plan with atlas and objects."))

        mapping = self.add(Card("Map annotations to atlas"))
        self.review = mapping.add(status_label(""))
        self.map_button = mapping.add_row(
            button("Mark reviewed", lambda: shell.run("register.review")),
            button("Map to atlas", lambda: shell.run("annotate.map"),
                   primary=True), None)
        mapping.add(hint_label(
            "Requires the section → atlas warp preview. Mapping moves the section's marks "
            "onto the atlas: they are removed from the section. Mapping without a review "
            "is allowed; the result is recorded as not reviewed."))

        objects = self.add(Card(
            "Parts and 3D objects",
            "Make parts turns this section's atlas marks into parts; Build turns parts "
            "into a 3D object. Building replaces the parts with the object; Edit parts restores them."))
        o = engine.object_ctrl
        objects.add(grid_of([
            button("Make parts", lambda: shell.run("annotate.parts")),
            button("Build probe", o.merge_probe_btn.click),
            button("Build cells", o.merge_cell_btn.click),
            button("Build expression", o.merge_virus_btn.click),
            button("Build contour", o.merge_contour_btn.click),
            button("Build drawing", o.merge_drawing_btn.click),
            button("Edit parts", o.unmerge_btn.click),
            button("Delete object", o.delete_object_btn.click),
        ], columns=2))
        objects.add(hint_label("Select objects in the Objects list on the right first."))

    def refresh(self):
        engine = self.engine
        for key, widget in self.tool_buttons.items():
            widget.setChecked(engine.tool_box.checkable_btn_dict["{}_btn".format(key)].isChecked())
        review = engine.registration_review_state()
        if not engine.h2a_transferred:
            set_status(self.review, "Preview the section on the atlas first (Register step).",
                       "warn")
        elif review == "reviewed":
            set_status(self.review, "Registration reviewed; ready to map.", "good")
        else:
            set_status(self.review, "Registration not reviewed; mapped results will be "
                       "recorded as not reviewed.", "warn")
