"""The Plan section of a probe in the V2 Annotate step.

A planned probe is a pose (``probe_plans.ProbePlan``): the tip, the AP and ML
tilts and the roll. The fields show it; every change shows its readout at
once (entry on the brain surface, depth along the probe, the regions along the
shank) and draws it on the atlas, and the plan is stored and built (one undo
step) once the change settles. A plan can also be set from two clicks on the
atlas (entry, then tip) or by snapping the tip to a region.
"""

import html

import numpy as np
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QInputDialog,
    QLabel,
    QWidget,
)

from ..probe_plans import (
    MAX_TILT_DEG,
    ProbePlan,
    plan_from_entry_depth,
    plan_from_points,
    region_summary,
)
from ..probe_utiles import Probe
from .widgets import Card, button, grid_of, hint_label, set_status, status_label

BUILD_DELAY_MS = 500
NP2_SHANKS = [-375.0, -125.0, 125.0, 375.0]
PROBE_TYPES = ("Neuropixels 1.0", "Neuropixels 2.0, one shank",
               "Neuropixels 2.0, four shanks", "Current probe settings")


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
        self.hint = self.add(hint_label(
            "Plan where the probe goes before surgery: set the tip and the tilts, click the "
            "entry and the tip on the atlas, or snap the tip to a region. Positions are from "
            "Bregma; ML + is the animal's right."))
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
        grid.addWidget(QLabel("Probe"), 0, 0)
        grid.addWidget(self.type_box, 0, 1, 1, 3)
        self.ap = _spin(-20, 20, 0.05, 3, " mm", "Tip AP from Bregma (+ anterior)")
        self.ml = _spin(-20, 20, 0.05, 3, " mm", "Tip ML from Bregma (+ the animal's right)")
        self.dv = _spin(-20, 20, 0.05, 3, " mm", "Tip DV from Bregma (+ dorsal)")
        self.depth = _spin(0, 30, 0.05, 3, " mm",
                           "Depth of the tip along the probe from the brain surface; "
                           "changing it slides the tip along the probe")
        self.ap_tilt = _spin(-MAX_TILT_DEG, MAX_TILT_DEG, 1, 1, "°",
                             "Tilt in the sagittal plane (+: the tip is anterior of the entry)")
        self.ml_tilt = _spin(-MAX_TILT_DEG, MAX_TILT_DEG, 1, 1, "°",
                             "Tilt in the coronal plane (+: the tip is to the animal's right "
                             "of the entry)")
        self.roll = _spin(0, 359.9, 15, 1, "°",
                          "Turn about the shank: 0 = contacts face anterior, 90 = they face "
                          "the animal's right")
        self.roll.setWrapping(True)
        rows = (("Tip AP", self.ap, "AP tilt", self.ap_tilt),
                ("Tip ML", self.ml, "ML tilt", self.ml_tilt),
                ("Tip DV", self.dv, "Roll", self.roll),
                ("Depth", self.depth, None, None))
        for row, (label_a, box_a, label_b, box_b) in enumerate(rows, start=1):
            grid.addWidget(QLabel(label_a), row, 0)
            grid.addWidget(box_a, row, 1)
            if box_b is not None:
                grid.addWidget(QLabel(label_b), row, 2)
                grid.addWidget(box_b, row, 3)
        for box in (self.ap, self.ml, self.dv, self.ap_tilt, self.ml_tilt, self.roll):
            box.valueChanged.connect(self._pose_changed)
        self.depth.valueChanged.connect(self._depth_changed)
        self.add(self.fields)

        self.click_button = button("Set from clicks", self.toggle_clicking, checkable=True,
                                   tooltip="Click the entry and then the tip on an atlas "
                                           "view; the plan goes through both points.")
        self.actions = grid_of([
            self.click_button,
            button("Snap tip to region…", self.snap_to_region,
                   tooltip="Move the tip to the centre of a region (on the tip's side of "
                           "the brain), keeping the tilts."),
            button("Show on atlas", self.show_on_atlas,
                   tooltip="Move the atlas pages through the tip"),
            button("Copy coordinates", self.copy_coordinates,
                   tooltip="Copy one line with the atlas, frame, entry, depth, tip, tilts "
                           "and regions"),
            button("Region table…", self.region_table,
                   tooltip="The planned probe's regions, contacts and coordinates"),
            button("Show in 3D", lambda: self.shell.set_view("3d")),
        ], columns=2)
        self.add(self.actions)
        self.readout = self.add(QLabel(""))
        self.readout.setWordWrap(True)
        self.readout.setTextFormat(Qt.TextFormat.RichText)
        self.status = self.add(status_label(""))
        self.remove_button = button("Remove plan", self.remove_plan,
                                    tooltip="Forget this probe's plan and its planned object; "
                                            "Undo mapping step brings it back.")
        self.add_row(self.remove_button, None)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.commit)
        self._pending = None

    # ------------------------------------------------------------- state
    def plan(self):
        return self.engine.probe_plan(self.probe) if self.probe else None

    def set_probe(self, probe):
        if probe != self.probe:
            self.commit()
            self.engine.plan_previews.clear()
            self.clicking = False
            self.click_button.setChecked(False)
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
        plan = self._pending or self.plan()
        self.setVisible(self.probe is not None)
        has_atlas = atlas is not None
        self.start_button.setVisible(plan is None)
        self.start_button.setEnabled(has_atlas)
        self.start_button.setToolTip("" if has_atlas else "Load a volume atlas first.")
        for widget in (self.fields, self.actions, self.readout, self.remove_button):
            widget.setVisible(plan is not None)
        if self.clicking:
            self._take_clicks()
        if plan is None:
            self.readout.setText("")
            return
        if self._pending is None and not any(box.hasFocus() for box in self._boxes()):
            self._fill(plan)
        self._show_readout(plan)

    def _boxes(self):
        return (self.ap, self.ml, self.dv, self.depth, self.ap_tilt, self.ml_tilt, self.roll)

    def _fill(self, plan):
        self._filling = True
        try:
            self.ml.setValue(plan.tip_um[0] / 1000.0)
            self.ap.setValue(plan.tip_um[1] / 1000.0)
            self.dv.setValue(plan.tip_um[2] / 1000.0)
            self.ap_tilt.setValue(plan.ap_tilt_deg)
            self.ml_tilt.setValue(plan.ml_tilt_deg)
            self.roll.setValue(plan.roll_deg)
            readout = self.engine.probe_plan_readout(plan)
            depth = readout and readout["depth_um"]
            self.depth.setEnabled(depth is not None)
            if depth is not None:
                self.depth.setValue(max(0.0, depth / 1000.0))
            self.type_box.setCurrentIndex(probe_type_index(plan))
        finally:
            self._filling = False

    def _show_readout(self, plan):
        readout = self.engine.probe_plan_readout(plan)
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
        for warning in readout["warnings"]:
            lines.append("<span style='color:#e8a33d'>⚠ {}</span>".format(
                html.escape(warning)))
        self.readout.setText("<br>".join(lines))

    # ------------------------------------------------------------ editing
    def _fields_plan(self):
        plan = self._pending or self.plan()
        return plan.copy(
            tip_um=[self.ml.value() * 1000.0, self.ap.value() * 1000.0,
                    self.dv.value() * 1000.0],
            ap_tilt_deg=self.ap_tilt.value(), ml_tilt_deg=self.ml_tilt.value(),
            roll_deg=self.roll.value())

    def preview(self, plan):
        """Show ``plan`` (readout, atlas) and store it once editing settles."""
        self._pending = plan
        self.engine.plan_previews[plan.probe] = plan
        self.engine.plan_colours[plan.probe] = self._colour()
        self._show_readout(plan)
        self.engine.plan_overlay.refresh()
        self._timer.start(BUILD_DELAY_MS)

    def _pose_changed(self):
        if self._filling or self.plan() is None:
            return
        plan = self._fields_plan()
        readout = self.engine.probe_plan_readout(plan)
        self._filling = True
        try:
            depth = readout and readout["depth_um"]
            self.depth.setEnabled(depth is not None)
            if depth is not None:
                self.depth.setValue(max(0.0, depth / 1000.0))
        finally:
            self._filling = False
        self.preview(plan)

    def _depth_changed(self):
        if self._filling or self.plan() is None:
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

    def _type_changed(self, index):
        if self._filling or self.plan() is None:
            return
        settings, offsets = probe_type_settings(index, self.engine)
        self.preview(self._fields_plan().copy(probe_settings=settings,
                                              shank_offsets_um=offsets))
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
            keep = {} if plan is None else {
                "roll_deg": plan.roll_deg, "probe_settings": plan.probe_settings,
                "shank_offsets_um": plan.shank_offsets_um}
            if plan is None:
                settings, offsets = probe_type_settings(0, engine)
                keep = {"probe_settings": settings, "shank_offsets_um": offsets}
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
        self.engine.plan_previews.pop(self.probe, None)
        with self.engine.undoable("Remove {} plan".format(self.probe)):
            self.engine.remove_probe_plan(self.probe)
        book = self.controls.book
        if self.probe not in book.names():
            book._empty.append(self.probe)     # the probe stays listed
        self._say(True, "Removed the plan of {}.".format(self.probe))
        self.shell.refresh()


__all__ = ["PlanEditor", "ProbePlan"]
