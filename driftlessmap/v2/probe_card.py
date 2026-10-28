"""Probe controls of the V2 Implants card.

Probes are listed, added, renamed and deleted with the other implants; this
section marks, maps and builds the probe selected in that list. A probe keeps
its own workflow (points along the track, the 1.x probe settings and
reconstruction); only where it is shown changed.
"""

from PyQt6.QtWidgets import QInputDialog, QLabel, QMenu, QMessageBox

from .probes import ProbeBook
from .widgets import Card, button, grid_of, hint_label, set_status, status_label


class ProbeControls(Card):
    """Mark the track, map each section and build the selected probe."""

    def __init__(self, shell, select):
        super().__init__()
        self.setObjectName("CardSection")
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.shell = shell
        self.engine = shell.engine
        self.book = ProbeBook(self.engine)
        self._select = select       # selects a probe (or nothing) in the Implants list
        self.probe = None

        self.guide = self.add(hint_label(""))
        self.mark = button("1  Mark track", self.toggle_marking, checkable=True,
                           tooltip="Click along the probe track in the image")
        self.marks = QLabel("")
        self.marks.setObjectName("Muted")
        self.add_row(self.mark, self.marks, None)
        self.add_button = button("2  Map this section", self.add_section, primary=True)
        self.add_row(self.add_button, None)
        self.build_button = button("3  Build probe", self.build_probe)
        self.add_row(self.build_button, None)
        self.status = self.add(status_label(""))
        self.results = grid_of([
            button("Region table…", self.region_table),
            button("Show in 3D", lambda: shell.set_view("3d")),
        ], columns=2)
        self.add(self.results)

        engine = self.engine
        self.settings_button = button("Probe settings")
        menu = QMenu(self.settings_button)
        menu.addAction("Multi-probe layout…", engine.actionMulti_Probe_Planning.trigger)
        menu.addAction("Save probe settings…", engine.actionSave_Probe_Setting.trigger)
        menu.addAction("Load probe settings…", engine.actionLoad_Probe_Setting.trigger)
        self.settings_button.setMenu(menu)
        self.add_row(self.settings_button, None)
        self.add(hint_label(
            "Probe type, site face and multi-shank layout appear in Tool options above "
            "the image while Mark track is on."))

    # ----------------------------------------------------------- helpers
    def current(self):
        return self.probe

    def _say(self, ok, message):
        set_status(self.status, message, "good" if ok else "bad")
        self.shell.message(message, "good" if ok else "warn")

    def _need_probe(self):
        if self.probe is None:
            self._select(self.book.new())
        return self.probe

    def show_probe(self, probe):
        """Show ``probe`` (a name, or None); called when the list selection changes."""
        if probe != self.probe:
            set_status(self.status, "", None)
        self.probe = probe
        if probe is not None and self.engine.tool_box.checkable_btn_dict["probe_btn"].isChecked():
            self.book.use_colour(probe)
        self.sync()

    # ----------------------------------------------------------- actions
    def new_probe(self, name=None):
        probe = self.book.new()
        if name and name.strip() and name.strip() != probe:
            probe = self.book.rename(probe, name)
        self._select(probe)
        set_status(self.status, "{} added. Mark its track on each section that shows it."
                   .format(probe), None)
        return probe

    def rename_probe(self):
        probe = self.probe
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
        self._select(new)

    def delete_probe(self):
        probe = self.probe
        if probe is None:
            return
        parts = len(self.book.parts(probe))
        if parts or self.book.built(probe):
            reply = QMessageBox.question(
                self, "Delete probe",
                "Delete {} and its {} section part{} and built object?".format(
                    probe, parts, "" if parts == 1 else "s"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.book.delete(probe)
        self.probe = None
        self._select(None)

    def toggle_marking(self):
        probe = self._need_probe()
        tool = self.engine.tool_box.checkable_btn_dict["probe_btn"]
        if not tool.isChecked():
            self.book.use_colour(probe)
        self.shell.toggle_tool("probe")
        self.sync()

    def add_section(self):
        probe = self._need_probe()
        ok, message = self.book.add_section(probe)
        self._select(probe)
        self._say(ok, message)

    def build_probe(self):
        probe = self.probe
        if probe is None:
            return
        ok, message = self.book.build(probe)
        self._select(probe)
        self._say(ok, message)

    def region_table(self):
        probe = self.probe
        if probe is None or not self.book.select_built(probe):
            self._say(False, "Build the probe first.")
            return
        self.engine.object_ctrl.info_btn.click()

    # ----------------------------------------------------------- refresh
    def sync(self):
        engine = self.engine
        probe = self.probe
        pre_plan = engine.image_view.image_file is None
        self.guide.setText(
            "Plan a probe: switch on Mark track, click the entry point and then the tip "
            "on the atlas, add the points to the probe, then build it."
            if pre_plan else
            "On each section that shows the track: switch on Mark track, click along "
            "the track, then map the section. Build the probe when all its sections "
            "are mapped.")
        on_section, on_atlas = self.book.marks()
        parts = []
        if on_section:
            parts.append("{} point{} on the section".format(on_section, "" if on_section == 1 else "s"))
        if on_atlas:
            parts.append("{} on the atlas".format(on_atlas))
        self.marks.setText(", ".join(parts) or "no points marked")
        self.mark.setChecked(engine.tool_box.checkable_btn_dict["probe_btn"].isChecked())
        self.add_button.setText("2  Add the points to {}".format(probe or "the probe") if pre_plan
                                else "2  Map this section")
        self.add_button.setEnabled(bool(on_section or on_atlas))
        has_parts = bool(probe and self.book.parts(probe))
        built = bool(probe and self.book.built(probe))
        self.build_button.setText("3  {} {}".format("Rebuild" if built and has_parts else "Build",
                                                    probe) if probe else "3  Build probe")
        self.build_button.setEnabled(has_parts)
        self.results.setVisible(built)
