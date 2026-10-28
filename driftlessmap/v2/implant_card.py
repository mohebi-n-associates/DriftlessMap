"""The Implants card of the V2 Annotate step: fibers, microprisms and probes.

All three are listed, added, renamed and deleted here. Fibers and prisms are
outlined on each section, mapped and built with the controls below the list;
a selected probe shows the probe controls instead (``probe_card``), which
keep the probe's own workflow: points along the track, mapped and built.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
)

from .. import implants as model
from .outline_editor import OutlineEditor
from .probe_card import ProbeControls
from .widgets import Card, button, grid_of, hint_label, set_status, status_label

NEUROPIXELS = "neuropixels"
PROBE_ROW = "probe:"


def _swatch(rgb):
    pixmap = QPixmap(12, 12)
    pixmap.fill(QColor(*rgb))
    return QIcon(pixmap)


class ImplantDialog(QDialog):
    """Type, name and specifications of an implant (new or existing)."""

    def __init__(self, parent, implant=None, default_names=None):
        super().__init__(parent)
        self.setWindowTitle("Implant settings" if implant else "Add implant")
        self._default_names = default_names or {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.kind = QComboBox()
        for kind in model.TYPES:
            self.kind.addItem(model.TYPE_NAMES[kind], kind)
        if implant is None:
            self.kind.addItem("Probe (Neuropixels, silicon, tetrode)", NEUROPIXELS)
        self.name = QLineEdit()
        self.diameter = QComboBox()
        self.diameter.setEditable(True)
        self.diameter.addItems(["{:g}".format(v) for v in model.FIBER_DIAMETERS_UM])
        self.na = QComboBox()
        self.na.setEditable(True)
        self.na.addItems(["{:g}".format(v) for v in model.FIBER_NAS])
        self.width = QDoubleSpinBox()
        self.depth = QDoubleSpinBox()
        for spin in (self.width, self.depth):
            spin.setRange(100, 5000)
            spin.setSingleStep(50)
            spin.setDecimals(0)
            spin.setSuffix(" µm")
        self.face = QComboBox()
        self.face.addItems(model.PRISM_FACES)
        for widget in (self.kind, self.name):
            widget.setMinimumWidth(260)
        for widget in (self.diameter, self.na):
            widget.setMinimumWidth(110)
        self.kind.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        form.addRow("Type", self.kind)
        form.addRow("Name", self.name)
        self.rows = {
            "fiber": [("Diameter (µm)", self.diameter), ("NA", self.na)],
            "prism": [("Width along the face", self.width),
                      ("Depth away from the face", self.depth), ("Imaging face", self.face)],
        }
        for rows in self.rows.values():
            for label, widget in rows:
                form.addRow(label, widget)
        self.form = form
        self.note = hint_label("")
        self.note.setMinimumWidth(380)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._fill(implant.kind if implant else model.FIBER,
                   implant.specs if implant else None)
        if implant is not None:
            self.kind.setCurrentIndex(self.kind.findData(implant.kind))
            self.kind.setEnabled(False)
            self.name.setText(implant.name)
        else:
            self.name.setText(self._default_names.get(model.FIBER, ""))
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._show_rows()

    def _fill(self, kind, specs):
        for each in model.TYPES:
            values = dict(model.DEFAULT_SPECS[each])
            if each == kind and specs:
                values.update(specs)
            if each == model.FIBER:
                self.diameter.setCurrentText("{:g}".format(values["diameter_um"]))
                self.na.setCurrentText("{:g}".format(values["na"]))
            else:
                self.width.setValue(values["width_um"])
                self.depth.setValue(values["depth_um"])
                self.face.setCurrentText(values["face"])

    def _kind_changed(self):
        self.name.setText(self._default_names.get(self.kind.currentData(), ""))
        self._show_rows()

    def _show_rows(self):
        kind = self.kind.currentData()
        for each, rows in self.rows.items():
            for _label, widget in rows:
                self.form.setRowVisible(widget, each == kind)
        self.note.setText({
            "fiber": "NA is stored for a later light-cone estimate; the tip does not use it.",
            "prism": "For a medial or lateral face, the depth is the prism's ML size.",
            NEUROPIXELS: "The probe type, site face and shank layout are set in Tool "
                         "options while Mark track is on.",
        }[kind])

    def values(self):
        """``(kind, name, specs)``; raises ValueError for invalid input."""
        kind = self.kind.currentData()
        if kind == NEUROPIXELS:
            return kind, self.name.text(), {}
        if kind == model.FIBER:
            try:
                specs = {"diameter_um": float(self.diameter.currentText()),
                         "na": float(self.na.currentText())}
            except ValueError:
                raise ValueError("Diameter and NA must be numbers.") from None
        else:
            specs = {"width_um": self.width.value(), "depth_um": self.depth.value(),
                     "face": self.face.currentText()}
        return kind, self.name.text(), model.validated_specs(kind, specs)


class ImplantCard(Card):
    """List implants; outline, map and build fibers and prisms."""

    def __init__(self, shell):
        super().__init__("Implants")
        self.shell = shell
        self.engine = shell.engine
        self.probe_card = ProbeControls(shell, self._select_probe)
        self.editor = OutlineEditor(self.engine)
        self.editor.changed.connect(self._editor_message)
        self._listing = None

        self.add(hint_label(
            "Optical fibers, microprisms and probes: on each section that shows one, outline "
            "what it left (a probe: click along its track), map the section, then build it "
            "from all its sections."))
        self.list = QListWidget()
        self.list.setMaximumHeight(118)
        self.list.currentRowChanged.connect(lambda _row: self._selection_changed())
        self.add(self.list)
        self.add_row(button("Add implant…", self.add_implant),
                     button("Settings…", self.edit_settings),
                     button("Rename…", self.rename), button("Delete…", self.delete), None)

        self.active = self.add(QLabel(""))
        self.active.setObjectName("CardTitle")
        self.specs = self.add(hint_label(""))
        self.draw = button("1  Draw outline", lambda: self._mode("draw"), checkable=True,
                           tooltip="Click around the track; click the first point to close")
        self.propose = button("Propose", lambda: self._mode("propose"), checkable=True,
                              tooltip="Click inside the track to outline the region of "
                                      "similar brightness, then correct it")
        self.point = button("Mark tip", lambda: self._mode("point"), checkable=True)
        self.clear_button = button("Clear", self.clear_outline,
                                   tooltip="Clear this implant's outline on this section")
        self.controls = grid_of([self.draw, self.propose, self.point, self.clear_button],
                                columns=2)
        self.add(self.controls)
        self.outline_state = self.add(hint_label(""))
        self.map_button = button("2  Map this section", self.map_section, primary=True)
        self.build_button = button("3  Build", self.build)
        self.add_row(self.map_button, None)
        self.add_row(self.build_button, None)
        self.status = self.add(status_label(""))
        self.report = self.add(QLabel(""))
        self.report.setWordWrap(True)
        self.report.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.results = grid_of([
            button("Report…", self.open_report),
            button("Show in 3D", lambda: shell.set_view("3d")),
            button("Export table…", self.export_table),
        ], columns=3)
        self.add(self.results)
        self.add(self.probe_card)

    # ------------------------------------------------------------ helpers
    def current(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def implant(self):
        current = self.current()
        if current is None or current.startswith(PROBE_ROW):
            return None
        return self.engine.implants.get(current)

    def _say(self, ok, message):
        set_status(self.status, message, "good" if ok else "bad")
        self.shell.message(message, "good" if ok else "warn")

    def _editor_message(self, message):
        self.shell.message(message)
        self.refresh()

    def _default_names(self):
        taken = set(self.probe_card.book.names()) | self.engine._object_group_names()
        names = {kind: self.engine.implants.default_name(kind, taken) for kind in model.TYPES}
        number = 1
        while "Probe {}".format(number) in taken:
            number += 1
        names[NEUROPIXELS] = "Probe {}".format(number)
        return names

    # ------------------------------------------------------------ actions
    def add_implant(self):
        dialog = ImplantDialog(self, default_names=self._default_names())
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                kind, name, specs = dialog.values()
                if kind == NEUROPIXELS:
                    if name.strip() in {i.name for i in self.engine.implants.implants()}:
                        raise ValueError("There is already an implant called {}.".format(name))
                    self.probe_card.new_probe(name)
                    return
                if name.strip() in self.probe_card.book.names():
                    raise ValueError("There is already a probe called {}.".format(name))
                implant = self.engine.add_implant(kind, name=name or None, specs=specs)
            except ValueError as exc:
                QMessageBox.warning(self, "Add implant", str(exc))
                continue
            self.refresh(select=implant.implant_id)
            self._say(True, "{} added. Draw its outline on each section that shows it."
                      .format(implant.name))
            return

    def edit_settings(self):
        if (self.current() or "").startswith(PROBE_ROW):
            self.shell.message("A probe's type, site face and shank layout are in Tool options "
                               "while Mark track is on; Probe settings has the rest.")
            return
        implant = self.implant()
        if implant is None:
            return
        dialog = ImplantDialog(self, implant=implant)
        while dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                _kind, name, specs = dialog.values()
                if name.strip() != implant.name:
                    self.engine.rename_implant(implant.implant_id, name)
                self.engine.set_implant_specs(implant.implant_id, specs)
            except ValueError as exc:
                QMessageBox.warning(self, "Implant settings", str(exc))
                continue
            self.refresh()
            return

    def rename(self):
        current = self.current()
        if current is None:
            return
        if current.startswith(PROBE_ROW):
            self.probe_card.rename_probe()
            return
        implant = self.implant()
        name, ok = QInputDialog.getText(self, "Rename implant", "New name:", text=implant.name)
        if not ok:
            return
        try:
            self.engine.rename_implant(implant.implant_id, name)
        except ValueError as exc:
            self._say(False, str(exc))
        self.refresh()

    def delete(self):
        current = self.current()
        if current is None:
            return
        if current.startswith(PROBE_ROW):
            self.probe_card.delete_probe()
            return
        implant = self.implant()
        count = len(self.engine.implant_objects(implant.implant_id))
        reply = QMessageBox.question(
            self, "Delete implant",
            "Delete {}{}? Undo mapping step brings it back.".format(
                implant.name, " and its {} part(s) and built object".format(count)
                if count else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.editor.select(None)
        self.engine.delete_implant(implant.implant_id)
        self.refresh()
        self.shell.refresh()

    def _mode(self, mode):
        buttons = {"draw": self.draw, "propose": self.propose, "point": self.point}
        on = buttons[mode].isChecked()
        if on:
            self.shell.clear_tools()
        if not self.editor.set_mode(mode if on else None):
            buttons[mode].setChecked(False)
        hints = {
            "draw": "Click around the track on the section; click the first point to close.",
            "propose": "Click inside the track on the section.",
            "point": "Click the {} on the section.".format(
                "fiber tip" if self.implant() and self.implant().kind == model.FIBER
                else "middle of the prism's bottom edge"),
        }
        if on:
            self.shell.message(hints[mode])
        self._sync_actions()

    def clear_outline(self):
        self.editor.clear()
        self._sync_actions()

    def map_section(self):
        implant = self.implant()
        if implant is None:
            return
        self.editor.set_mode(None)
        ok, message = self.engine.map_implant(implant.implant_id)
        self._say(ok, message)
        self.editor.sync(force=True)
        self.shell.refresh()

    def build(self):
        implant = self.implant()
        if implant is None:
            return
        ok, message = self.engine.build_implant(implant.implant_id)
        self._say(ok, message)
        self.shell.refresh()

    def open_report(self):
        implant = self.implant()
        built = self.engine.implant_objects(implant.implant_id, built=True) if implant else []
        if not built:
            self._say(False, "Build the implant first.")
            return
        self.engine.object_ctrl.current_obj_index = built[-1]
        self.engine.object_ctrl.obj_info_on_click()

    def export_table(self):
        if not any(self.engine.implant_report(i.implant_id) for i in self.engine.implants.implants()):
            self._say(False, "Build an implant first.")
            return
        path, _filter = QFileDialog.getSaveFileName(self, "Export implant table",
                                                    "implants.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            count = self.engine.export_implant_table(path)
        except OSError as exc:
            self._say(False, "Could not write the table: {}".format(exc))
            return
        self._say(True, "Wrote {} implant row{} to {}.".format(count, "" if count == 1 else "s",
                                                              path))

    # ------------------------------------------------- where the user left off
    def leave_state(self):
        """Selection, unmapped probes, Mark track and an outline being drawn."""
        engine = self.engine
        state = {"selected": self.current(),
                 "probes": self.probe_card.book.state(),
                 "marking": bool(self.probe_card.probe and engine.tool_box
                                 .checkable_btn_dict["probe_btn"].isChecked())}
        editor = self.editor
        if editor.mode == "draw" and editor.vertices and editor.implant_id:
            state["drawing"] = {"implant_id": editor.implant_id,
                                "vertices": [[float(x), float(y)] for x, y in editor.vertices]}
        return state

    def resume(self, state):
        """Restore :meth:`leave_state` after a project is opened."""
        state = state if isinstance(state, dict) else {}
        self.probe_card.book.restore(state.get("probes"))
        selected = state.get("selected")
        self.refresh(select=selected if isinstance(selected, str) else None)
        drawing = state.get("drawing")
        if isinstance(drawing, dict) and self.engine.implants.get(drawing.get("implant_id")):
            try:
                vertices = [[float(x), float(y)] for x, y in drawing.get("vertices") or []]
            except (TypeError, ValueError):
                vertices = []
            if vertices:
                self.refresh(select=drawing["implant_id"])
                self.draw.setChecked(True)
                self._mode("draw")
                self.editor.vertices = vertices
                self.editor._show_preview()
                self.shell.message("Continue the outline: click around the track; click "
                                   "the first point to close it.")
        if state.get("marking") and self.probe_card.probe and not self.engine.tool_box \
                .checkable_btn_dict["probe_btn"].isChecked():
            self.probe_card.toggle_marking()
        self._sync_actions()

    # ------------------------------------------------------------ refresh
    def _select_probe(self, probe):
        """Select ``probe`` in the list (None: keep or pick another row)."""
        self.refresh(select=PROBE_ROW + probe if probe else None)

    def _shown_probe(self):
        current = self.current() or ""
        return current[len(PROBE_ROW):] if current.startswith(PROBE_ROW) else None

    def _selection_changed(self):
        self.probe_card.show_probe(self._shown_probe())
        self.editor.select(self.implant().implant_id if self.implant() else None)
        self._sync_actions()

    def summary(self, implant):
        engine = self.engine
        if any(engine.implant_build_status(i) for i in
               engine.implant_objects(implant.implant_id, built=True)):
            return "settings changed · rebuild required"
        parts = len(engine.implant_objects(implant.implant_id, built=False))
        built = bool(engine.implant_objects(implant.implant_id, built=True))
        sections = "{} section{}".format(parts, "" if parts == 1 else "s") if parts else ""
        if built:
            return "built" + (" · {} new to build".format(sections) if parts else "")
        return "{} · not built".format(sections) if parts else "no sections yet"

    def _sync_actions(self):
        engine = self.engine
        implant = self.implant()
        probe = self._shown_probe()
        self.probe_card.setVisible(probe is not None)
        for widget in (self.specs, self.controls, self.outline_state, self.map_button,
                       self.build_button, self.status):
            widget.setVisible(implant is not None)
        if implant is None:
            self.active.setText("{} · Probe".format(probe) if probe
                                else "Nothing yet: Add implant creates a fiber, microprism "
                                     "or probe.")
            self.results.setVisible(False)
            self.report.setText("")
            self.report.setVisible(False)
            if probe is not None:
                self.probe_card.sync()
            return
        self.active.setText("{} · {}".format(implant.name, implant.type_name))
        self.specs.setText(model.describe_specs(implant.kind, implant.specs))
        self.point.setText("Mark tip" if implant.kind == model.FIBER else "Mark bottom edge")
        for mode, widget in (("draw", self.draw), ("propose", self.propose),
                             ("point", self.point)):
            widget.setChecked(self.editor.mode == mode)
        outline = engine.implant_outline(implant.implant_id)
        parts = ["outline drawn" if outline["points"] else "no outline on this section"]
        if outline["point"] is not None:
            parts.append("tip marked" if implant.kind == model.FIBER else "bottom marked")
        self.outline_state.setText(", ".join(parts).capitalize() + ".")
        reason = self.shell.needs_both()
        self.map_button.setEnabled(bool(outline["points"]) and reason is None)
        self.map_button.setToolTip(reason or ("" if outline["points"]
                                              else "Draw the outline first."))
        has_parts = bool(engine.implant_objects(implant.implant_id))
        self.build_button.setEnabled(has_parts)
        self.build_button.setText("3  Build {}".format(implant.name))
        report = engine.implant_report(implant.implant_id)
        self.results.setVisible(report is not None)
        self.report.setVisible(report is not None)
        lines = model.report_lines(report) if report else []
        if report and any(engine.implant_build_status(i) for i in
                          engine.implant_objects(implant.implant_id, built=True)):
            lines.insert(0, "OUT OF DATE — build again to use the current specifications.")
        self.report.setText("\n".join(lines))

    def refresh(self, select=None):
        engine = self.engine
        rows = [(implant.implant_id, implant.colour,
                 "{}   ·   {} · {}".format(implant.name, implant.type_name.lower(),
                                           self.summary(implant)))
                for implant in engine.implants.implants()]
        book = self.probe_card.book
        rows += [(PROBE_ROW + name, book.colour(name),
                  "{}   ·   probe · {}".format(name, book.summary(name)))
                 for name in book.names()]
        keep = select or self.current()
        if rows != self._listing:
            self._listing = rows
            self.list.blockSignals(True)
            self.list.clear()
            for key, colour, text in rows:
                item = QListWidgetItem(_swatch(colour), text)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.list.addItem(item)
            self.list.blockSignals(False)
        keys = [row[0] for row in rows]
        if keep in keys and self.current() != keep:
            self.list.setCurrentRow(keys.index(keep))
        elif self.current() is None and keys:
            self.list.setCurrentRow(0)
        if self.probe_card.probe != self._shown_probe():
            self.probe_card.show_probe(self._shown_probe())
        selected = self.implant()
        if (selected.implant_id if selected else None) != self.editor.implant_id:
            self.editor.select(selected.implant_id if selected else None)
        else:
            self.editor.sync()
        self._sync_actions()
