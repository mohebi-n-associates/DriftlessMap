"""Project step: atlas, current section and project files."""

from PyQt6.QtWidgets import QLabel, QMenu, QPushButton

from . import state
from .widgets import Card, StepPanel, button, hint_label


class ProjectPanel(StepPanel):
    title = "Project"
    hint = ("Choose the atlas and the section to work on. The project saves every "
            "part of the work, including the exact image pixels.")

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
            ("Download Waxholm rat atlas…", engine.actionDownload),
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

        self.section_card = self.add(Card("Current section"))
        self.section_name = self.section_card.add(QLabel())
        self.section_detail = self.section_card.add(hint_label(""))
        self.load_section = button("Load section…", lambda: shell.run("section.load"),
                                   primary=True)
        self.section_card.add_row(self.load_section, None)
        self.section_card.add(hint_label(
            "Replacing the section starts a new registration for the new image. "
            "Built objects stay in the project."))

        files = self.add(Card("Project file"))
        self.file_label = files.add(hint_label(""))
        files.add_row(button("Open…", lambda: shell.run("project.open")),
                      button("Save…", lambda: shell.run("project.save"), primary=True),
                      button("Save portable copy…", lambda: shell.run("project.save_portable")),
                      None)
        files.add(hint_label(
            "A portable copy also contains the original image file. Neither copy "
            "contains the processed volume atlas, which is linked and verified."))

    def refresh(self):
        name, detail = state.atlas_summary(self.engine)
        self.atlas_name.setText(name)
        self.atlas_detail.setText(detail)
        name, detail = state.section_summary(self.engine)
        self.section_name.setText(name)
        self.section_detail.setText(detail)
        loaded = self.engine.image_view.current_img is not None
        self.load_section.setText("Replace section…" if loaded else "Load section…")
        path = self.engine.current_project_path
        self.file_label.setText("Project: {}".format(path) if path else
                                "This work has not been saved as a project yet.")
