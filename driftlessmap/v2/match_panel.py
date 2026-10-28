"""Match step: find the atlas plane, depth and tilt that match the section."""

from PyQt6.QtWidgets import QComboBox, QLabel

from ..atlas_matching import plane_from_name
from . import state
from .widgets import Card, StepPanel, button, hint_label, set_status, status_label


PLANE_LABELS = (("Coronal", "coronal"), ("Sagittal", "sagittal"),
                ("Horizontal", "horizontal"), ("Not sure: detect", "auto"))


class MatchPanel(StepPanel):
    title = "Match"
    hint = ("Find the atlas section that matches the histology, automatically or by "
            "hand. Manual matching is always available below.")

    def build(self):
        engine, shell = self.engine, self.shell
        self.require(shell.needs_both)

        find = self.add(Card("Find atlas section"))
        self.recipe = find.add(status_label(""))
        self.plane_choice = QComboBox()
        for label, choice in PLANE_LABELS:
            self.plane_choice.addItem(label, choice)
        self.plane_choice.setToolTip("The plane the section is cut in. The search stays "
                                     "in this plane; Not sure compares all three.")
        self.plane_choice.activated.connect(self._plane_chosen)
        self._named_for = None
        find.add_row(QLabel("Section plane"), self.plane_choice, None)
        find.add_row(self.gate(button("Find atlas section", lambda: shell.run("match.find"),
                                      primary=True), shell.needs_both),
                     button("Change channels", lambda: shell.go_to("section")), None)
        find.add(hint_label(
            "Compares the tissue outline with slices of the chosen plane (all planes "
            "if you are not sure), ranks depths by internal anatomy and tries small "
            "tilts. The plane is read from the file name when it says coronal, "
            "sagittal or horizontal. You choose among the candidates, "
            "including the hemisphere, before anything is applied."))

        manual = self.add(Card(
            "Plane, depth and tilt",
            "Choose the plane, then set depth with the slider under the atlas view "
            "and the tilt here. Keep Slice Angles keeps the tilt when the depth "
            "changes; it is off by default, as in 1.x. Navigation makes the other "
            "planes follow the cursor in the multi-plane view."))
        self.plane = manual.add(QLabel(""))
        view = engine.atlas_view
        # The V2 theme restyles these 1.x controls (see adopted.py).
        manual.add(self.gate(view.sidebar_wrap, shell.needs_volume))

    def chosen_plane(self):
        return self.plane_choice.currentData()

    def _plane_chosen(self, _index=None):
        self.engine.section_plane = self.chosen_plane()

    def _show_plane(self, choice):
        index = self.plane_choice.findData(choice)
        if index >= 0:
            self.plane_choice.setCurrentIndex(index)

    def refresh(self):
        engine = self.engine
        # A new image whose file name names its plane selects that plane;
        # otherwise the last choice stays.
        path = engine.current_img_path
        if path != self._named_for:
            self._named_for = path
            named = plane_from_name(path)
            if named is not None:
                engine.section_plane = named
        if engine.section_plane is not None and engine.section_plane != self.chosen_plane():
            self._show_plane(engine.section_plane)
        recipe = engine.registration_input
        if engine.image_view.current_img is None:
            set_status(self.recipe, "Load a section first.", "warn")
        elif recipe is None:
            set_status(self.recipe, "Registration channels not chosen yet; you will be "
                       "asked, or choose them in Section.", "warn")
        else:
            set_status(self.recipe, "Registration input: " + recipe.describe(), None)
        self.plane.setText(state.plane_summary(engine))
