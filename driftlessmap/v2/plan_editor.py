"""The Plan section of a probe in the V2 Annotate step.

A planned probe is a pose (``probe_plans.ProbePlan``): the tip, the AP and ML
tilts and the roll. The fields show it, either as the tip or as the entry on
the brain surface and the depth (since 2.9.0); every change shows its readout
at once (entry, depth, the regions along the shank, the recording window),
draws it on the atlas and in the shank view, and the plan is stored and built
(one undo step) once the change settles. A plan can also be set from two
clicks on the atlas, by snapping the tip to a region, by moving the tip to the
brain surface, or steered with the keyboard.
"""

import html

import numpy as np
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from ..probe_plans import (
    MAX_TILT_DEG,
    ProbePlan,
    bank_count,
    plan_from_entry_depth,
    plan_from_points,
    plan_from_surface,
    region_summary,
    tip_to_surface,
)
from ..probe_utiles import Probe
from .shank_view import ShankView
from .widgets import Card, Disclosure, button, grid_of, hint_label, set_status, status_label

BUILD_DELAY_MS = 500
NP2_SHANKS = [-375.0, -125.0, 125.0, 375.0]
PROBE_TYPES = ("Neuropixels 1.0", "Neuropixels 2.0, one shank",
               "Neuropixels 2.0, four shanks", "Current probe settings")
EDIT_MODES = ("Tip", "Entry and depth")
# Keyboard steering: steps in um (and degrees at the same index).
STEPS_UM = (10.0, 50.0, 100.0, 500.0)
STEPS_DEG = (1.0, 1.0, 5.0, 5.0)
KEYS = {
    # key: (what, sign); positions in the steering step, angles in degrees
    Qt.Key.Key_W: ("ap", 1), Qt.Key.Key_S: ("ap", -1),
    Qt.Key.Key_D: ("ml", 1), Qt.Key.Key_A: ("ml", -1),
    Qt.Key.Key_Q: ("dv", 1), Qt.Key.Key_E: ("dv", -1),
    Qt.Key.Key_X: ("depth", 1), Qt.Key.Key_Z: ("depth", -1),
    Qt.Key.Key_I: ("ap_tilt", 1), Qt.Key.Key_K: ("ap_tilt", -1),
    Qt.Key.Key_L: ("ml_tilt", 1), Qt.Key.Key_J: ("ml_tilt", -1),
    Qt.Key.Key_O: ("roll", 1), Qt.Key.Key_U: ("roll", -1),
}
KEY_LEGEND = ("W/S AP · A/D ML · Q/E DV · Z/X depth · I/K AP tilt · J/L ML tilt · "
              "U/O roll · −/+ step · Shift: largest step · Esc: stop")
TEXT_INPUTS = (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)


def probe_type_settings(index, engine):
    """(settings, shank offsets) of a choice in ``PROBE_TYPES``."""
    if index == 3:
        settings = engine.current_probe_settings()
        offsets = list(settings.get("multi_shanks") or []) or None \
            if settings.get("probe_type") == 1 and engine.multi_shanks else None
        return settings, offsets
    probe = Probe()
    if index == 0:
        probe.set_np1()
    else:
        probe.set_np2()
    return probe.get_settings(), (list(NP2_SHANKS) if index == 2 else None)


def probe_type_index(plan):
    settings = plan.probe_settings or {}
    reference = {0: Probe().get_settings()}
    two = Probe()
    two.set_np2()
    reference[1] = two.get_settings()
    if settings == reference[0] and not plan.shank_offsets_um:
        return 0
    if settings == reference[1]:
        if not plan.shank_offsets_um:
            return 1
        if plan.shank_offsets_um == NP2_SHANKS:
            return 2
    return 3


def steered(plan, atlas, what, amount):
    """``plan`` moved by one keyboard step (positions in um, angles in degrees)."""
    if what in ("ap", "ml", "dv"):
        tip = list(plan.tip_um)
        tip[("ml", "ap", "dv").index(what)] += amount
        return plan.copy(tip_um=tip)
    if what == "depth":
        tip = np.asarray(plan.tip_um) + plan.direction * amount
        return plan.copy(tip_um=tip.tolist())
    if what == "roll":
        return plan.copy(roll_deg=(plan.roll_deg + amount) % 360.0)
    name = what + "_deg"
    value = float(np.clip(getattr(plan, name) + amount, -MAX_TILT_DEG, MAX_TILT_DEG))
    return plan.copy(**{name: value})


def _spin(minimum, maximum, step, decimals, suffix, tooltip):
    box = QDoubleSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setDecimals(decimals)
    box.setSuffix(suffix)
    box.setKeyboardTracking(False)
    box.setToolTip(tooltip)
    box.setAccelerated(True)
    return box


class _Steering(QObject):
    """Application event filter for keyboard steering (installed while on)."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        app = QApplication.instance()
        if app.activeModalWidget() is not None or app.activeWindow() is not self.editor.window():
            return False
        if isinstance(app.focusWidget(), TEXT_INPUTS):
            return False
        return self.editor.steer_key(event.key(), event.modifiers())


class PlanEditor(Card):
    """Edit the selected probe's plan; ``controls`` is the ProbeControls owner."""

    def __init__(self, shell, controls):
        super().__init__("Plan")
        self.setObjectName("CardSection")
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.shell = shell
        self.engine = shell.engine
        self.controls = controls
        self.probe = None
        self.clicking = False
        self._filling = False
        self._pending = None
        self.step_index = 1
        self.hint = self.add(hint_label(
            "Plan where the probe goes before surgery: set the tip (or the entry and the "
            "depth) and the tilts, click the entry and the tip on the atlas, snap the tip to "
            "a region, or steer it with the keys. Positions are from Bregma; ML + is the "
            "animal's right."))
        self.start_button = button("Plan this probe", self.start_plan, primary=True,
                                   tooltip="Give the probe a plan: 1 mm right of Bregma, "
                                           "3 mm deep, vertical; then move it.")
        self.add_row(self.start_button, None)

        self.fields = QWidget()
        grid = QGridLayout(self.fields)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)
        self.type_box = QComboBox()
        self.type_box.addItems(PROBE_TYPES)
        self.type_box.setToolTip("Probe model; 'Current probe settings' uses the probe "
                                 "settings (Tool options, the linear-silicon designer).")
        self.type_box.currentIndexChanged.connect(self._type_changed)
        self.mode_box = QComboBox()
        self.mode_box.addItems(EDIT_MODES)
        self.mode_box.setToolTip("Edit the tip (the tilts turn about the tip), or the entry "
                                 "on the brain surface and the depth (the tilts turn about "
                                 "the entry), as a stereotaxic frame is set.")
        self.mode_box.currentIndexChanged.connect(self._mode_changed)
        self.bank_box = QComboBox()
        self.bank_box.setToolTip("The sites recorded at once: a bank of 384 channels counted "
                                 "from the tip (Bank 0 is the lowest), or every site")
        self.bank_box.currentIndexChanged.connect(self._bank_changed)
        grid.addWidget(QLabel("Probe"), 0, 0)
        grid.addWidget(self.type_box, 0, 1, 1, 3)
        grid.addWidget(QLabel("Edit by"), 1, 0)
        grid.addWidget(self.mode_box, 1, 1)
        grid.addWidget(QLabel("Record"), 1, 2)
        grid.addWidget(self.bank_box, 1, 3)
        self.ap = _spin(-20, 20, 0.05, 3, " mm", "")
        self.ml = _spin(-20, 20, 0.05, 3, " mm", "")
        self.dv = _spin(-20, 20, 0.05, 3, " mm", "")
        self.depth = _spin(0, 30, 0.05, 3, " mm",
                           "Depth of the tip along the probe from the brain surface")
        self.ap_tilt = _spin(-MAX_TILT_DEG, MAX_TILT_DEG, 1, 1, "°",
                             "Tilt in the sagittal plane (+: the tip is anterior of the entry)")
        self.ml_tilt = _spin(-MAX_TILT_DEG, MAX_TILT_DEG, 1, 1, "°",
                             "Tilt in the coronal plane (+: the tip is to the animal's right "
                             "of the entry)")
        self.roll = _spin(0, 359.9, 15, 1, "°",
                          "Turn about the shank: 0 = contacts face anterior, 90 = they face "
                          "the animal's right")
        self.roll.setWrapping(True)
        self.ap_label, self.ml_label, self.dv_label = QLabel(), QLabel(), QLabel()
        rows = ((self.ap_label, self.ap, "AP tilt", self.ap_tilt),
                (self.ml_label, self.ml, "ML tilt", self.ml_tilt),
                (self.dv_label, self.dv, "Roll", self.roll),
                (QLabel("Depth"), self.depth, None, None))
        for row, (label_a, box_a, label_b, box_b) in enumerate(rows, start=2):
            grid.addWidget(label_a, row, 0)
            grid.addWidget(box_a, row, 1)
            if box_b is not None:
                grid.addWidget(QLabel(label_b), row, 2)
                grid.addWidget(box_b, row, 3)
        for box in (self.ap, self.ml, self.dv, self.ap_tilt, self.ml_tilt, self.roll):
            box.valueChanged.connect(self._pose_changed)
        self.depth.valueChanged.connect(self._depth_changed)
        self.add(self.fields)
        self._label_fields()

        self.click_button = button("Set from clicks", self.toggle_clicking, checkable=True,
                                   tooltip="Click the entry and then the tip on an atlas "
                                           "view; the plan goes through both points.")
        self.steer_button = button("Steer with keys", self.toggle_steering, checkable=True,
                                   tooltip="Move and turn the plan with the keyboard while "
                                           "this is on: " + KEY_LEGEND)
        self.surface_button = button("Tip to surface")
        menu = QMenu(self.surface_button)
        menu.addAction("Along the probe", lambda: self.tip_to_surface(True))
        menu.addAction("Straight down (same AP and ML)", lambda: self.tip_to_surface(False))
        self.surface_button.setMenu(menu)
        self.surface_button.setToolTip("Put the tip on the brain surface, along the probe or "
                                       "straight down, then set the depth")
        self.actions = grid_of([
            self.click_button,
            button("Snap tip to region…", self.snap_to_region,
                   tooltip="Move the tip to the centre of a region (on the tip's side of "
                           "the brain), keeping the tilts."),
            self.steer_button,
            self.surface_button,
            button("Show on atlas", self.show_on_atlas,
                   tooltip="Move the atlas pages through the tip"),
            button("Copy coordinates", self.copy_coordinates,
                   tooltip="Copy one line with the atlas, frame, entry, depth, tip, tilts, "
                           "recording window and regions"),
            button("Region table…", self.region_table,
                   tooltip="The planned probe's regions, contacts and coordinates"),
            button("Show in 3D", lambda: self.shell.set_view("3d")),
        ], columns=2)
        self.add(self.actions)
        self.legend = self.add(hint_label(""))
        self.legend.setVisible(False)
        self.readout = self.add(QLabel(""))
        self.readout.setWordWrap(True)
        self.readout.setTextFormat(Qt.TextFormat.RichText)
        self.shank_view = ShankView(self.engine)
        self.shank = self.add(Disclosure("Shank and probe plane", self.shank_view,
                                         expanded=True))
        self.status = self.add(status_label(""))
        self.remove_button = button("Remove plan", self.remove_plan,
                                    tooltip="Forget this probe's plan and its planned object; "
                                            "Undo mapping step brings it back.")
        self.add_row(self.remove_button, None)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.commit)
        self._steering = _Steering(self)

    # ------------------------------------------------------------- state
    def plan(self):
        return self.engine.probe_plan(self.probe) if self.probe else None

    def current(self):
        """The plan being edited, or the stored one."""
        return self._pending or self.plan()

    def entry_mode(self):
        return self.mode_box.currentIndex() == 1

    def set_probe(self, probe):
        if probe != self.probe:
            self.commit()
            self.engine.plan_previews.clear()
            self.clicking = False
            self.click_button.setChecked(False)
            self._set_steering(False)
            set_status(self.status, "", None)
        self.probe = probe
        self.sync()

    def _colour(self):
        return self.controls.book.colour(self.probe) if self.probe else None

    def _say(self, ok, message):
        set_status(self.status, message, "good" if ok else "warn")
        self.shell.message(message, "good" if ok else "warn")

    # -------------------------------------------------------------- sync
    def sync(self):
        engine = self.engine
        atlas = engine.plan_atlas()
        plan = self.current()
        self.setVisible(self.probe is not None)
        has_atlas = atlas is not None
        self.start_button.setVisible(plan is None)
        self.start_button.setEnabled(has_atlas)
        self.start_button.setToolTip("" if has_atlas else "Load a volume atlas first.")
        for widget in (self.fields, self.actions, self.readout, self.remove_button, self.shank):
            widget.setVisible(plan is not None)
        if self.clicking:
            self._take_clicks()
        if plan is None:
            self.readout.setText("")
            self._set_steering(False)
            return
        if self._pending is None and not any(box.hasFocus() for box in self._boxes()):
            self._fill(plan)
        self._show_readout(plan)

    def _boxes(self):
        return (self.ap, self.ml, self.dv, self.depth, self.ap_tilt, self.ml_tilt, self.roll)

    def _label_fields(self):
        where = "Entry" if self.entry_mode() else "Tip"
        self.ap_label.setText("{} AP".format(where))
        self.ml_label.setText("{} ML".format(where))
        self.dv_label.setText("{} DV".format(where))
        for box, axis in ((self.ap, "AP (+ anterior)"), (self.ml, "ML (+ the animal's right)"),
                          (self.dv, "DV (+ dorsal)")):
            box.setToolTip("{} {} from Bregma".format(where, axis))
        # The entry lies on the surface: its DV follows from AP and ML.
        self.dv.setEnabled(not self.entry_mode())
        self.depth.setToolTip(
            "Depth of the tip along the probe from the entry" if self.entry_mode() else
            "Depth of the tip along the probe from the brain surface; changing it slides "
            "the tip along the probe")

    def _fill(self, plan):
        self._filling = True
        try:
            readout = self.engine.probe_plan_readout(plan)
            entry = readout and readout["entry_um"]
            shown = entry if self.entry_mode() and entry is not None else plan.tip_um
            self.ml.setValue(shown[0] / 1000.0)
            self.ap.setValue(shown[1] / 1000.0)
            self.dv.setValue(shown[2] / 1000.0)
            self.ap_tilt.setValue(plan.ap_tilt_deg)
            self.ml_tilt.setValue(plan.ml_tilt_deg)
            self.roll.setValue(plan.roll_deg)
            depth = readout and readout["depth_um"]
            self.depth.setEnabled(depth is not None)
            if depth is not None:
                self.depth.setValue(max(0.0, depth / 1000.0))
            self.type_box.setCurrentIndex(probe_type_index(plan))
            self._fill_banks(plan)
        finally:
            self._filling = False

    def _fill_banks(self, plan):
        banks = bank_count(plan.probe_settings)
        items = (["Bank {}".format(b) for b in range(banks)] + ["Every site"]) \
            if banks > 1 else ["Every site"]
        if [self.bank_box.itemText(i) for i in range(self.bank_box.count())] != items:
            self.bank_box.clear()
            self.bank_box.addItems(items)
        if banks > 1:
            self.bank_box.setCurrentIndex(banks if plan.bank is None
                                          else min(plan.bank, banks - 1))
        else:
            self.bank_box.setCurrentIndex(0)

    def _show_readout(self, plan):
        readout = self.engine.probe_plan_readout(plan)
        self.shank_view.show_plan(plan, readout)
        if readout is None:
            self.readout.setText("Load a volume atlas to see the plan's readout.")
            return

        def triple(values):
            return "AP {:+.2f} · ML {:+.2f} · DV {:+.2f} mm".format(
                values[1] / 1000.0, values[0] / 1000.0, values[2] / 1000.0)

        lines = []
        if readout["entry_um"] is not None:
            lines.append("<b>Entry</b> {}".format(triple(readout["entry_um"])))
            lines.append("<b>Depth</b> {:.2f} mm along the probe".format(
                readout["depth_um"] / 1000.0))
        lines.append("<b>Tip</b> {} · in {}".format(
            triple(readout["tip_um"]), html.escape(readout["tip_region"][0])))
        lines.append("<b>Tilt</b> {} · contacts face {}".format(
            html.escape(readout["tilt"]), html.escape(readout["face"])))
        regions = region_summary(readout, limit=8)
        if regions:
            lines.append("<b>Along the shank</b> {}".format(html.escape(regions)))
        if readout.get("window_um"):
            top, bottom = readout["window_um"]
            cover = ", ".join("{} {:.2f} mm ({} sites)".format(
                html.escape(r["acronym"]), r["length_um"] / 1000.0, r["sites"])
                for r in readout["window_regions"][:8])
            lines.append("<b>Recording</b> {:.2f}–{:.2f} mm deep, {} of {} sites in the "
                         "brain{}".format(max(top, 0.0) / 1000.0, bottom / 1000.0,
                                          readout["window_sites_in_brain"],
                                          readout["window_sites"],
                                          ": " + cover if cover else ""))
        for warning in readout["warnings"]:
            lines.append("<span style='color:#e8a33d'>⚠ {}</span>".format(
                html.escape(warning)))
        self.readout.setText("<br>".join(lines))

    # ------------------------------------------------------------ editing
    def _fields_plan(self):
        """The plan the fields describe, or None (an entry with no brain under it)."""
        base = self.current().copy(ap_tilt_deg=self.ap_tilt.value(),
                                   ml_tilt_deg=self.ml_tilt.value(),
                                   roll_deg=self.roll.value())
        if not self.entry_mode():
            return base.copy(tip_um=[self.ml.value() * 1000.0, self.ap.value() * 1000.0,
                                     self.dv.value() * 1000.0])
        atlas = self.engine.plan_atlas()
        try:
            return plan_from_surface(base, atlas, self.ml.value() * 1000.0,
                                     self.ap.value() * 1000.0, self.depth.value() * 1000.0)
        except ValueError as exc:
            self._say(False, "No entry there: {}.".format(exc))
            return None

    def preview(self, plan):
        """Show ``plan`` (readout, atlas, shank) and store it once editing settles."""
        self._pending = plan
        self.engine.plan_previews[plan.probe] = plan
        self.engine.plan_colours[plan.probe] = self._colour()
        self._show_readout(plan)
        self.engine.plan_overlay.refresh()
        self._timer.start(BUILD_DELAY_MS)

    def _refill_derived(self, plan):
        """Show what follows from an edit (depth, or the entry's DV) without editing."""
        readout = self.engine.probe_plan_readout(plan)
        self._filling = True
        try:
            depth = readout and readout["depth_um"]
            self.depth.setEnabled(depth is not None)
            if depth is not None and not self.entry_mode():
                self.depth.setValue(max(0.0, depth / 1000.0))
            if self.entry_mode() and readout and readout["entry_um"] is not None:
                self.dv.setValue(readout["entry_um"][2] / 1000.0)
        finally:
            self._filling = False

    def _pose_changed(self):
        if self._filling or self.current() is None:
            return
        plan = self._fields_plan()
        if plan is None:
            return
        self._refill_derived(plan)
        self.preview(plan)

    def _depth_changed(self):
        if self._filling or self.current() is None:
            return
        if self.entry_mode():
            self._pose_changed()
            return
        plan = self._fields_plan()
        readout = self.engine.probe_plan_readout(plan)
        if readout is None or readout["entry_um"] is None:
            return
        plan = plan_from_entry_depth(plan, readout["entry_um"], self.depth.value() * 1000.0)
        self._filling = True
        try:
            self.ml.setValue(plan.tip_um[0] / 1000.0)
            self.ap.setValue(plan.tip_um[1] / 1000.0)
            self.dv.setValue(plan.tip_um[2] / 1000.0)
        finally:
            self._filling = False
        self.preview(plan)

    def _mode_changed(self, _index):
        self._label_fields()
        plan = self.current()
        if plan is not None:
            self._fill(plan)

    def _type_changed(self, index):
        if self._filling or self.current() is None:
            return
        settings, offsets = probe_type_settings(index, self.engine)
        self.preview(self.current().copy(probe_settings=settings, shank_offsets_um=offsets))
        self._fill_banks(self._pending)
        self.commit()

    def _bank_changed(self, index):
        if self._filling or self.current() is None or index < 0:
            return
        plan = self.current()
        banks = bank_count(plan.probe_settings)
        bank = None if banks <= 1 or index >= banks else index
        if bank != plan.bank:
            self.preview(plan.copy(bank=bank))
            self.commit()

    def commit(self):
        """Store and build the plan being edited (one undo step)."""
        self._timer.stop()
        plan, self._pending = self._pending, None
        self.engine.plan_previews.pop(plan.probe if plan else None, None)
        if plan is None or plan == self.engine.probe_plan(plan.probe):
            return
        ok, message = self.engine.set_probe_plan(plan, colour=self._colour())
        self._say(ok, message)
        self.shell.refresh()

    # ---------------------------------------------------------- steering
    def toggle_steering(self):
        self._set_steering(self.steer_button.isChecked())

    def _set_steering(self, on):
        app = QApplication.instance()
        on = bool(on and self.current() is not None)
        if self.steer_button.isChecked() != on:
            self.steer_button.setChecked(on)
        app.removeEventFilter(self._steering)
        if on:
            app.installEventFilter(self._steering)
            focus = app.focusWidget()
            if isinstance(focus, TEXT_INPUTS):
                focus.clearFocus()
        self.legend.setVisible(on)
        self._show_step()
        if not on:
            self.commit()

    def _show_step(self):
        self.legend.setText("Step {:g} µm, {:g}°. {}".format(
            STEPS_UM[self.step_index], STEPS_DEG[self.step_index], KEY_LEGEND))

    def steer_key(self, key, modifiers=Qt.KeyboardModifier.NoModifier):
        """Apply one steering key; returns True when the key was used."""
        if key == Qt.Key.Key_Escape:
            self._set_steering(False)
            return True
        if key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.step_index = max(0, self.step_index - 1)
            self._show_step()
            return True
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.step_index = min(len(STEPS_UM) - 1, self.step_index + 1)
            self._show_step()
            return True
        if key not in KEYS or self.current() is None:
            return False
        what, sign = KEYS[key]
        index = len(STEPS_UM) - 1 if modifiers & Qt.KeyboardModifier.ShiftModifier \
            else self.step_index
        amount = sign * (STEPS_DEG[index] if what in ("ap_tilt", "ml_tilt", "roll")
                         else STEPS_UM[index])
        plan = steered(self.current(), self.engine.plan_atlas(), what, amount)
        self.preview(plan)
        self._fill(plan)
        return True

    # ------------------------------------------------------------ actions
    def start_plan(self):
        probe = self.probe
        if probe is None or self.engine.plan_atlas() is None:
            self._say(False, "Load a volume atlas first.")
            return
        ok, message = self.engine.set_probe_plan(self.engine.default_probe_plan(probe),
                                                 colour=self._colour())
        self.engine.show_plan_on_atlas(probe)
        self._say(ok, message if not ok else
                  "{} planned at a starting point; set the tip and the tilts, click it on "
                  "the atlas or snap it to a region.".format(probe))
        self.shell.refresh()

    def toggle_clicking(self):
        self.clicking = self.click_button.isChecked()
        engine = self.engine
        tool = engine.tool_box.checkable_btn_dict["probe_btn"]
        if self.clicking:
            engine.clear_atlas_probe_marks()
            if not tool.isChecked():
                self.controls.book.use_colour(self.probe)
                self.shell.toggle_tool("probe")
            self.shell.message("Click the entry and then the tip on an atlas view.")
        elif tool.isChecked():
            self.shell.toggle_tool("probe")
        self.controls.sync()

    def _take_clicks(self):
        engine = self.engine
        points = engine.atlas_probe_marks_um()
        if len(points) < 2:
            return
        plan = self.plan()
        try:
            if plan is None:
                settings, offsets = probe_type_settings(0, engine)
                keep = {"probe_settings": settings, "shank_offsets_um": offsets}
            else:
                keep = {"roll_deg": plan.roll_deg, "probe_settings": plan.probe_settings,
                        "shank_offsets_um": plan.shank_offsets_um, "bank": plan.bank}
            new = plan_from_points(self.probe, points[0], points[1], **keep)
        except ValueError as exc:
            engine.clear_atlas_probe_marks()
            self._say(False, "Those two points cannot make a plan: {}.".format(exc))
            return
        engine.clear_atlas_probe_marks()
        self.clicking = False
        self.click_button.setChecked(False)
        if engine.tool_box.checkable_btn_dict["probe_btn"].isChecked():
            self.shell.toggle_tool("probe")
        ok, message = engine.set_probe_plan(new, colour=self._colour())
        self._say(ok, message if not ok else
                  "{} now runs through the two points; the entry is where it meets the "
                  "brain.".format(self.probe))
        self._fill(new)

    def _regions(self):
        info = self.engine.atlas_view.label_info
        if info is None:
            return []
        return sorted(((str(a), str(n), int(i)) for i, a, n in zip(
            np.ravel(info["index"]), info["abbrev"], info["label"])), key=lambda r: r[0])

    def snap_to_region(self, region_id=None):
        self.commit()
        plan = self.plan()
        if plan is None:
            return
        if region_id is None:
            regions = self._regions()
            if not regions:
                self._say(False, "The atlas has no region names.")
                return
            items = ["{} · {}".format(a, n) for a, n, _i in regions]
            current = self.engine.atlas_view.label_tree.tree.currentItem()
            start = 0
            if current is not None and getattr(current, "id", None) is not None:
                ids = [i for _a, _n, i in regions]
                if int(current.id) in ids:
                    start = ids.index(int(current.id))
            choice, ok = QInputDialog.getItem(self, "Snap tip to region",
                                              "Region (the tip goes to its centre):",
                                              items, start, True)
            if not ok or choice not in items:
                return
            region_id = regions[items.index(choice)][2]
        side = 1 if plan.tip_um[0] >= 0 else -1
        centre = self.engine.region_centre_um(region_id, side=side) \
            or self.engine.region_centre_um(region_id)
        if centre is None:
            self._say(False, "That region is not in the atlas volume.")
            return
        new = plan.copy(tip_um=centre)
        ok, message = self.engine.set_probe_plan(new, colour=self._colour())
        self.engine.show_plan_on_atlas(self.probe)
        self._fill(new)
        self._say(ok, message)

    def tip_to_surface(self, along_probe=True):
        self.commit()
        plan = self.plan()
        atlas = self.engine.plan_atlas()
        if plan is None or atlas is None:
            return
        try:
            new = tip_to_surface(plan, atlas, along_probe=along_probe)
        except ValueError as exc:
            self._say(False, "Cannot move the tip to the surface: {}.".format(exc))
            return
        # Stored as one undo step; not built (a tip on the surface has no shank
        # in the brain), so the readout says to set the depth.
        self.engine.set_probe_plan(new, colour=self._colour())
        self._fill(new)
        self._say(True, "The tip is on the brain surface ({}); set the depth to go in.".format(
            "along the probe" if along_probe else "straight down"))

    def show_on_atlas(self):
        if not self.engine.show_plan_on_atlas(self.probe):
            self._say(False, "Plan the probe first.")

    def copy_coordinates(self):
        self.commit()
        line = self.engine.plan_coordinate_line(self.probe)
        if line is None:
            self._say(False, "Plan the probe on a volume atlas first.")
            return
        QApplication.clipboard().setText(line)
        self._say(True, "Copied the coordinates of {}.".format(self.probe))

    def region_table(self):
        self.commit()
        built = self.engine.plan_objects(self.probe)
        if not built:
            self._say(False, "The plan has no built probe; see the warnings above.")
            return
        self.engine.object_ctrl.current_obj_index = built[-1]
        self.engine.object_ctrl.info_btn.click()

    def remove_plan(self):
        if self.probe is None:
            return
        self._timer.stop()
        self._pending = None
        self._set_steering(False)
        self.engine.plan_previews.pop(self.probe, None)
        with self.engine.undoable("Remove {} plan".format(self.probe)):
            self.engine.remove_probe_plan(self.probe)
        book = self.controls.book
        if self.probe not in book.names():
            book._empty.append(self.probe)     # the probe stays listed
        self._say(True, "Removed the plan of {}.".format(self.probe))
        self.shell.refresh()


__all__ = ["PlanEditor", "ProbePlan"]
