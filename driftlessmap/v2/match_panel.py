"""Match step: find the atlas plane, depth and tilt that match the section."""

from PyQt6.QtWidgets import QLabel

from . import state
from .widgets import Card, StepPanel, button, hint_label, set_status, status_label


class MatchPanel(StepPanel):
    title = "Match"
    hint = ("Find the atlas section that matches the histology, automatically or by "
            "hand. Manual matching is always available below.")

    def build(self):
        engine, shell = self.engine, self.shell

        find = self.add(Card("Find atlas section"))
        self.recipe = find.add(status_label(""))
        find.add_row(button("Find atlas section", lambda: shell.run("match.find"),
                            primary=True),
                     button("Change channels", lambda: shell.go_to("section")), None)
        find.add(hint_label(
            "Compares the tissue outline with every plane, ranks depths by internal "
            "anatomy and tries small tilts. You choose among the candidates, "
            "including the hemisphere, before anything is applied."))

        manual = self.add(Card(
            "Plane, depth and tilt",
            "Choose the plane, then set depth with the slider under the atlas view "
            "and the tilt here. Keep Slice Angles keeps the tilt when the depth "
            "changes; it is off by default, as in 1.x. Navigation makes the other "
            "planes follow the cursor in the multi-plane view."))
        self.plane = manual.add(QLabel(""))
        view = engine.atlas_view
        # The 1.x panel sets white text inline; let the V2 theme style it.
        for radio in (view.section_rabnt1, view.section_rabnt2, view.section_rabnt3):
            radio.setStyleSheet("")
        view.radio_group.setStyleSheet("")
        manual.add(view.sidebar_wrap)

    def refresh(self):
        engine = self.engine
        recipe = engine.registration_input
        if engine.image_view.current_img is None:
            set_status(self.recipe, "Load a section first.", "warn")
        elif recipe is None:
            set_status(self.recipe, "Registration channels not chosen yet; you will be "
                       "asked, or choose them in Section.", "warn")
        else:
            set_status(self.recipe, "Registration input: " + recipe.describe(), None)
        self.plane.setText(state.plane_summary(engine))
