"""The Plan section of a probe in the V2 Annotate step.

A planned probe is a pose (``probe_plans.ProbePlan``): the tip, the AP and ML
tilts and the roll. The fields show it, either as the tip or as the entry on
the brain surface and the depth (since 2.8.1); every change shows its readout
at once (entry, depth, the regions along the shank, the recording window),
draws it on the atlas and in the shank view, and the plan is stored and built
(one undo step) once the change settles. A plan can also be set from two
clicks on the atlas, by snapping the tip to a region, by moving the tip to the
brain surface, or steered with the keyboard.
"""

import html

import numpy as np
from PyQt6.QtCore import QEvent, QObject, Qt
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
    CLEARANCE_UM,
    MAX_TILT_DEG,
    ProbePlan,
    arm_from_tilts,
    tilts_from_arm,
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

NP2_SHANKS = [-375.0, -125.0, 125.0, 375.0]
PROBE_TYPES = ("Neuropixels 1.0", "Neuropixels 2.0, one shank",
               "Neuropixels 2.0, four shanks", "Current probe settings")
EDIT_MODES = ("Tip", "Entry and depth")
ANGLE_MODES = ("AP/ML tilts", "Arm angles")
NO_CRANIOTOMY = "None"
NEW_CRANIOTOMY = "New at this entry…"
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
    # An explicit minimum keeps the Plan section within its column; the text
    # still fits (review UI-4 of 2.8.3).
    box.setMinimumWidth(72)
    return box


def _narrow(combo, characters=3):
    """A combo box that does not widen the column to its longest item."""
    combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(characters)
    return combo


class _Steering(QObject):
    """Application event filter for keyboard steering (installed while on)."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        if not self.editor.isVisible():
            # The Plan section is not shown (another step, the task column
            # hidden, another document): steering ends (review R8 of 2.8.3).
            self.editor._set_steering(False)
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
        self.step_index = 1
        self.hint = self.add(hint_label(
            "Plan where the probe goes before surgery: set the tip (or the entry and the "
            "depth) and the tilts, click the entry and the tip on the atlas, snap the tip to "
            "a region, or steer it with the keys. Positions are from Bregma; ML + is the "
            "animal's right."))
        self.start_button = button("Plan this probe", self.start_plan, primary=True,
                                   tooltip="Give the probe a plan: 1 mm right of Bregma, "
                                           "3 mm deep, vertical; then move it.")
        self.start_propose = button("Propose a plan…", self.propose,
                                    tooltip="Choose the regions to record; the search proposes "
                                            "tracks through them")
        self.add_row(self.start_button, self.start_propose, None)

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
        self.first_angle_label, self.second_angle_label = QLabel(), QLabel()
        self.angle_box = QComboBox()
        self.angle_box.addItems(ANGLE_MODES)
        self.angle_box.setToolTip("Enter the tilts in the sagittal and coronal planes, or as "
                                  "an arm is set: azimuth (the direction the tip leans, from "
                                  "anterior towards the animal's right) and elevation (from "
                                  "vertical)")
        rows = ((self.ap_label, self.ap, self.first_angle_label, self.ap_tilt),
                (self.ml_label, self.ml, self.second_angle_label, self.ml_tilt),
                (self.dv_label, self.dv, QLabel("Roll"), self.roll),
                (QLabel("Depth"), self.depth, None, None))
        for row, (label_a, box_a, label_b, box_b) in enumerate(rows, start=2):
            grid.addWidget(label_a, row, 0)
            grid.addWidget(box_a, row, 1)
            if box_b is not None:
                grid.addWidget(label_b, row, 2)
                grid.addWidget(box_b, row, 3)
        self.hole_box = QComboBox()
        self.hole_box.setToolTip("The craniotomy this probe goes through; the readout warns "
                                 "when any shank enters outside it")
        self.hole_box.activated.connect(self._hole_chosen)
        for combo in (self.type_box, self.mode_box, self.bank_box, self.angle_box,
                      self.hole_box):
            _narrow(combo)
        arm = str(self.shell.settings.value("plan/angles", ANGLE_MODES[0]))
        self.angle_box.setCurrentIndex(ANGLE_MODES.index(arm) if arm in ANGLE_MODES else 0)
        self.angle_box.currentIndexChanged.connect(self._angles_changed)
        self._label_angles()
        for box in (self.ap, self.ml, self.dv, self.ap_tilt, self.ml_tilt, self.roll):
            box.valueChanged.connect(self._pose_changed)
        self.depth.valueChanged.connect(self._depth_changed)
        self.add(self.fields)
        self._label_fields()
        # The readout follows the fields, so the plan's state stays in view.
        self.readout = self.add(QLabel(""))
        self.readout.setWordWrap(True)
        self.readout.setTextFormat(Qt.TextFormat.RichText)

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
        self.surgery_button = button("Surgery")
        surgery = QMenu(self.surgery_button)
        surgery.addAction("New craniotomy at this entry", self.new_craniotomy)
        surgery.addAction("Edit the craniotomy…", self.edit_craniotomy)
        surgery.addAction("Fit the craniotomy to its probes", self.fit_craniotomy)
        surgery.addAction("Remove the craniotomy", self.remove_craniotomy)
        surgery.addSeparator()
        surgery.addAction("Bregma–Lambda distance…", self.edit_bregma_lambda)
        self.surgery_button.setMenu(surgery)
        self.surgery_button.setToolTip("Craniotomies, and scaling the coordinates to this "
                                       "animal's Bregma–Lambda distance")
        self.actions = grid_of([
            self.click_button,
            button("Snap tip to region…", self.snap_to_region,
                   tooltip="Move the tip to the centre of a region (on the tip's side of "
                           "the brain), keeping the tilts."),
            button("Propose…", self.propose,
                   tooltip="Propose plans that record chosen regions (and keep out of "
                           "others) within the tilts the rig allows"),
            self.steer_button,
            button("Show on atlas", self.show_on_atlas,
                   tooltip="Move the atlas pages through the tip"),
            button("Copy coordinates", self.copy_coordinates,
                   tooltip="Copy one line with the atlas, frame, entry, depth, tip, tilts, "
                           "recording window and regions"),
        ], columns=2)
        self.add(self.actions)
        self.legend = self.add(hint_label(""))
        self.legend.setVisible(False)
        # Less frequent settings and actions fold away (review UI-4 of 2.8.3).
        more = QWidget()
        more_grid = QGridLayout(more)
        more_grid.setContentsMargins(0, 0, 0, 0)
        more_grid.setSpacing(6)
        more_grid.addWidget(QLabel("Angles"), 0, 0)
        more_grid.addWidget(self.angle_box, 0, 1)
        more_grid.addWidget(QLabel("Craniotomy"), 1, 0)
        more_grid.addWidget(self.hole_box, 1, 1)
        more_grid.addWidget(grid_of([
            self.surface_button,
            self.surgery_button,
            button("Region table…", self.region_table,
                   tooltip="The planned probe's regions, contacts and coordinates"),
            button("Show in 3D", lambda: self.shell.set_view("3d")),
        ], columns=2), 2, 0, 1, 2)
        self.more = self.add(Disclosure("Surgery and more", more, expanded=False))
        self.shank_view = ShankView(self.engine)
        self.shank = self.add(Disclosure("Shank and probe plane", self.shank_view,
                                         expanded=True))
        self.status = self.add(status_label(""))
        self.remove_button = button("Remove plan", self.remove_plan,
                                    tooltip="Forget this probe's plan and its planned object; "
                                            "Undo mapping step brings it back.")
        self.add_row(self.remove_button, None)
        self._steering = _Steering(self)

    def hideEvent(self, event):
        # Leaving the Plan section ends steering (review R8 of 2.8.3).
        if self.steer_button.isChecked():
            self._set_steering(False)
        super().hideEvent(event)

    # ------------------------------------------------------------- state
    def plan(self):
        return self.engine.probe_plan(self.probe) if self.probe else None

    def current(self):
        """The plan being edited, or the stored one."""
        if self.probe is None:
            return None
        return self.engine.plan_previews.get(self.probe) or self.plan()

    def entry_mode(self):
        return self.mode_box.currentIndex() == 1

    def set_probe(self, probe):
        if probe != self.probe:
            self.commit()
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
        self.start_propose.setVisible(plan is None)
        self.start_propose.setEnabled(has_atlas)
        self.start_button.setToolTip("" if has_atlas else "Load a volume atlas first.")
        for widget in (self.fields, self.actions, self.readout, self.remove_button, self.shank,
                       self.more):
            widget.setVisible(plan is not None)
        if self.clicking:
            self._take_clicks()
        if plan is None:
            self.readout.setText("")
            self._set_steering(False)
            return
        staged = self.probe in self.engine.plan_previews
        if not staged and not any(box.hasFocus() for box in self._boxes()):
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
            first, second = (arm_from_tilts(plan.ap_tilt_deg, plan.ml_tilt_deg)
                             if self.arm_mode() else (plan.ap_tilt_deg, plan.ml_tilt_deg))
            self.ap_tilt.setValue(first)
            self.ml_tilt.setValue(second)
            self._fill_holes(plan)
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
        if readout.get("targets"):
            from ..probe_plans import REACHED_UM

            parts = []
            for name, length in readout["targets"]:
                text = "{} {:.2f} mm".format(html.escape(name), length / 1000.0)
                parts.append(text if length >= REACHED_UM else
                             "<span style='color:#e8a33d'>{} (missed)</span>".format(text))
            lines.append("<b>Targets in the window</b> " + ", ".join(parts))
        if readout.get("arm"):
            lines.append("<b>Arm</b> azimuth {:.1f}° · elevation {:.1f}°".format(*readout["arm"]))
        hole = readout.get("craniotomy")
        if hole and readout["entry_um"] is not None:
            from ..probe_plans import Craniotomy
            distance = Craniotomy.from_dict(hole).distance_um(readout["entry_um"])
            lines.append("<b>Craniotomy</b> {} · entry {:.2f} mm from its centre ({:.2f} mm "
                         "across)".format(html.escape(hole["name"]), distance / 1000.0,
                                          hole["diameter_um"] / 1000.0))
        closest = readout.get("closest")
        if closest and closest["distance_um"] >= CLEARANCE_UM:
            other = [p for p in closest["probes"] if p != plan.probe][0]
            lines.append("<b>Closest probe</b> {} at {:.2f} mm".format(
                html.escape(other), closest["distance_um"] / 1000.0))
        scale = readout.get("scale", 1.0)
        if scale is not None and abs(scale - 1.0) > 1e-9 and readout["entry_um"] is not None:
            entry = [v * scale for v in readout["entry_um"]]
            lines.append("<b>For this animal</b> (×{:.3f}) entry {} · depth {:.2f} mm".format(
                scale, triple(entry), readout["depth_um"] * scale / 1000.0))
        for warning in readout["warnings"]:
            lines.append("<span style='color:#e8a33d'>⚠ {}</span>".format(
                html.escape(warning)))
        self.readout.setText("<br>".join(lines))

    # ------------------------------------------------------------ editing
    def _fields_plan(self):
        """The plan the fields describe, or None (an entry with no brain under it)."""
        ap_tilt, ml_tilt = (tilts_from_arm(self.ap_tilt.value(), self.ml_tilt.value())
                            if self.arm_mode() else (self.ap_tilt.value(), self.ml_tilt.value()))
        base = self.current().copy(ap_tilt_deg=ap_tilt, ml_tilt_deg=ml_tilt,
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
        """Show ``plan`` (readout, atlas, shank) at once; the engine stages it as
        unsaved work and stores and builds it when edits settle, or before any
        save, export, undo or other action (review R2 of 2.8.3)."""
        self.engine.stage_probe_plan(plan, self._colour())
        self._show_readout(plan)
        self.engine.plan_overlay.refresh()

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

    def arm_mode(self):
        return self.angle_box.currentIndex() == 1

    def _label_angles(self):
        arm = self.arm_mode()
        self.first_angle_label.setText("Azimuth" if arm else "AP tilt")
        self.second_angle_label.setText("Elevation" if arm else "ML tilt")
        self._filling = True
        try:
            if arm:
                self.ap_tilt.setRange(0.0, 359.9)
                self.ap_tilt.setWrapping(True)
                self.ap_tilt.setToolTip("The direction the tip leans, from anterior (0°) "
                                        "towards the animal's right (90°)")
                self.ml_tilt.setRange(0.0, MAX_TILT_DEG)
                self.ml_tilt.setToolTip("The angle of the probe from vertical")
            else:
                self.ap_tilt.setWrapping(False)
                self.ap_tilt.setRange(-MAX_TILT_DEG, MAX_TILT_DEG)
                self.ap_tilt.setToolTip("Tilt in the sagittal plane (+: the tip is anterior "
                                        "of the entry)")
                self.ml_tilt.setRange(-MAX_TILT_DEG, MAX_TILT_DEG)
                self.ml_tilt.setToolTip("Tilt in the coronal plane (+: the tip is to the "
                                        "animal's right of the entry)")
        finally:
            self._filling = False

    def _angles_changed(self, _index):
        self.shell.settings.setValue("plan/angles", self.angle_box.currentText())
        self._label_angles()
        plan = self.current()
        if plan is not None:
            self._fill(plan)

    # ------------------------------------------------------------ surgery
    def _fill_holes(self, plan):
        holes = self.engine.craniotomies.craniotomies()
        items = [NO_CRANIOTOMY] + [h.name for h in holes] + [NEW_CRANIOTOMY]
        if [self.hole_box.itemText(i) for i in range(self.hole_box.count())] != items:
            self.hole_box.clear()
            self.hole_box.addItems(items)
        ids = [None] + [h.craniotomy_id for h in holes]
        self.hole_box.setCurrentIndex(ids.index(plan.craniotomy)
                                      if plan.craniotomy in ids else 0)

    def _hole_chosen(self, index):
        plan = self.current()
        if plan is None:
            return
        holes = self.engine.craniotomies.craniotomies()
        if self.hole_box.itemText(index) == NEW_CRANIOTOMY:
            self.new_craniotomy()
            return
        chosen = None if index == 0 else holes[index - 1].craniotomy_id
        if chosen != plan.craniotomy:
            self.preview(plan.copy(craniotomy=chosen))
            self.commit()

    def _hole(self):
        plan = self.current()
        return self.engine.craniotomies.get(plan.craniotomy) if plan and plan.craniotomy \
            else None

    def new_craniotomy(self, diameter_um=1000.0):
        """A craniotomy centred on this probe's entry, which then goes through it."""
        self.commit()
        plan = self.plan()
        readout = self.engine.probe_plan_readout(plan, others=False) if plan else None
        if readout is None or readout["entry_um"] is None:
            self._say(False, "The probe needs an entry on the brain first.")
            self._fill_holes(plan) if plan else None
            return None
        hole = self.engine.add_craniotomy(readout["entry_um"][:2], diameter_um)
        self.engine.set_probe_plan(plan.copy(craniotomy=hole.craniotomy_id),
                                   colour=self._colour())
        self._fill(self.plan())
        self._say(True, "{} ({:.1f} mm across) is centred on the entry of {}.".format(
            hole.name, diameter_um / 1000.0, plan.probe))
        self.shell.refresh()
        return hole

    def edit_craniotomy(self):
        hole = self._hole()
        if hole is None:
            self._say(False, "Choose the probe's craniotomy first.")
            return
        values = craniotomy_dialog(self, hole)
        if values is None:
            return
        try:
            self.engine.edit_craniotomy(hole.craniotomy_id, **values)
        except ValueError as exc:
            self._say(False, "Not changed: {}.".format(exc))
            return
        self._fill(self.current())
        self._show_readout(self.current())
        self.shell.refresh()

    def fit_craniotomy(self):
        hole = self._hole()
        if hole is None:
            self._say(False, "Choose the probe's craniotomy first.")
            return
        self.commit()
        fitted = self.engine.fit_craniotomy_to_plans(hole.craniotomy_id)
        if fitted is None:
            self._say(False, "No planned probe enters the brain through {}.".format(hole.name))
            return
        self._show_readout(self.current())
        self._say(True, "{} now holds the entries of its probes: centre AP {:+.2f}, ML {:+.2f} "
                  "mm, {:.2f} mm across.".format(fitted.name, fitted.centre_um[1] / 1000.0,
                                                 fitted.centre_um[0] / 1000.0,
                                                 fitted.diameter_um / 1000.0))
        self.shell.refresh()

    def remove_craniotomy(self):
        hole = self._hole()
        if hole is None:
            self._say(False, "Choose the probe's craniotomy first.")
            return
        self.commit()
        self.engine.remove_craniotomy(hole.craniotomy_id)
        self._fill(self.plan())
        self._say(True, "Removed {}; its probes keep their places.".format(hole.name))
        self.shell.refresh()

    def edit_bregma_lambda(self):
        values = bregma_lambda_dialog(self, self.engine)
        if values is None:
            return
        self.engine.set_surgery_settings(**values)
        scale = self.engine.surgery_scale()
        if self.current() is not None:
            self._show_readout(self.current())
        if scale is None:
            self._say(False, "The atlas's Bregma–Lambda distance is unknown, so coordinates "
                             "for this animal cannot be given; enter it too.")
            return
        self._say(True, "Coordinates for this animal are scaled ×{:.3f}.".format(scale)
                  if abs(scale - 1.0) > 1e-9 else
                  "Coordinates are not scaled (set both distances to scale them).")

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
        self._fill_banks(self.current())
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
        """Store and build the staged edit now (one undo step)."""
        results = self.engine.flush_plan_edits()
        if results:
            ok, message = results[-1]
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

    def propose(self):
        """Open the proposal dialog; the chosen proposal becomes the plan."""
        from .proposal_dialog import ProposalDialog

        self.commit()
        if self.probe is None or self.engine.plan_atlas() is None:
            self._say(False, "Load a volume atlas first.")
            return
        dialog = self.proposal_dialog = ProposalDialog(self)
        accepted = dialog.exec() == ProposalDialog.DialogCode.Accepted
        self.proposal_dialog = None
        if not accepted or dialog.chosen is None:
            return
        ok, message = self.engine.set_probe_plan(dialog.chosen, colour=self._colour())
        self.engine.show_plan_on_atlas(self.probe)
        self._fill(dialog.chosen)
        self._say(ok, message if not ok else
                  "{} now follows the proposal; adjust it as you like.".format(self.probe))
        self.shell.refresh()

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


def craniotomy_dialog(parent, hole):
    """Ask for a craniotomy's name, centre and diameter; a dict of changes or None."""
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout

    dialog = QDialog(parent)
    dialog.setWindowTitle("Craniotomy")
    form = QFormLayout(dialog)
    name = QLineEdit(hole.name)
    ap = _spin(-20, 20, 0.05, 3, " mm", "Centre AP from Bregma (+ anterior)")
    ml = _spin(-20, 20, 0.05, 3, " mm", "Centre ML from Bregma (+ the animal's right)")
    across = _spin(0.05, 20, 0.1, 2, " mm", "Diameter of the opening")
    ap.setValue(hole.centre_um[1] / 1000.0)
    ml.setValue(hole.centre_um[0] / 1000.0)
    across.setValue(hole.diameter_um / 1000.0)
    for label, widget in (("Name", name), ("Centre AP", ap), ("Centre ML", ml),
                          ("Diameter", across)):
        form.addRow(label, widget)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return {"name": name.text().strip() or hole.name,
            "centre_um": [ml.value() * 1000.0, ap.value() * 1000.0],
            "diameter_um": across.value() * 1000.0}


def bregma_lambda_dialog(parent, engine):
    """Ask for this animal's and the atlas's Bregma-Lambda distances; a dict or None."""
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout

    settings = engine.surgery_settings
    known = engine.atlas_bregma_lambda_um()
    dialog = QDialog(parent)
    dialog.setWindowTitle("Bregma–Lambda distance")
    form = QFormLayout(dialog)
    form.addRow(hint_label(
        "Coordinates for this animal are the atlas coordinates scaled by its measured "
        "Bregma–Lambda distance over the atlas's. Leave a distance at 0 to not scale."
        + ("" if known else " This atlas does not record Lambda: enter its Bregma–Lambda "
                            "distance from its documentation.")))
    animal = _spin(0, 20, 0.01, 3, " mm", "Measured on this animal's skull")
    atlas = _spin(0, 20, 0.01, 3, " mm", "The atlas's own Bregma–Lambda distance")
    animal.setValue((settings.get("bregma_lambda_um") or 0.0) / 1000.0)
    atlas.setValue((settings.get("atlas_bregma_lambda_um") or known or 0.0) / 1000.0)
    form.addRow("This animal", animal)
    form.addRow("The atlas", atlas)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    atlas_um = atlas.value() * 1000.0 or None
    return {"bregma_lambda_um": animal.value() * 1000.0 or None,
            # The atlas's recorded distance is used without storing it.
            "atlas_bregma_lambda_um": None if known and atlas_um is not None
            and abs(atlas_um - known) < 1.0 else atlas_um}
