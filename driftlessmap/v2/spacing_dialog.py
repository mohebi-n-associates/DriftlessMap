"""Space out planned devices that come too close (2.8.8).

Choose the plans that may move (the fibers, prisms or probes of the kind
being edited are ticked), the gap to keep and the largest ML and AP tilts.
Space out tilts them about their tips (``DriftlessMap.space_out_plans``):
vertical where they can stay so, ML tilts before AP tilts, the largest tilt
as small as possible. The result is one undoable step.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from ..probe_plans import CLEARANCE_UM
from .widgets import hint_label

KIND_NAMES = {"probe": "probe", "fiber": "fiber", "prism": "prism"}


class SpacingDialog(QDialog):
    def __init__(self, parent, engine, kind="fiber"):
        from .plan_editor import _spin

        super().__init__(parent)
        self.setWindowTitle("Space out plans")
        self.engine = engine
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label(
            "Tilt the ticked plans about their tips so that every plan keeps the gap "
            "below from the others, ferrules, prism bodies and probe hardware included. "
            "Plans stay vertical where they can; ML tilts are used before AP tilts, and "
            "the largest tilt is kept as small as possible. Undo mapping step reverses it."))
        layout.addWidget(QLabel("Plans that may move:"))
        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        clashing = self._clashing()
        for plan in sorted(engine.probe_plans.plans(), key=lambda p: p.probe):
            item = QListWidgetItem("{} ({}{})".format(
                plan.probe, KIND_NAMES.get(plan.kind, plan.kind),
                ", too close" if plan.probe in clashing else ""))
            item.setData(Qt.ItemDataRole.UserRole, plan.probe)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if plan.kind == kind
                               else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list)
        grid = QGridLayout()
        self.gap = _spin(0.0, 5.0, 0.05, 2, " mm", "Distance to keep between the surfaces "
                         "of any two plans")
        self.gap.setValue(CLEARANCE_UM / 1000.0)
        self.max_ml = _spin(0.0, 45.0, 1.0, 0, "°", "No plan is tilted more than this in ML")
        self.max_ml.setValue(30.0)
        self.max_ap = _spin(0.0, 45.0, 1.0, 0, "°", "AP tilts are used only when ML tilts "
                            "cannot help; never more than this")
        self.max_ap.setValue(30.0)
        for row, (label, box) in enumerate((("Keep apart by", self.gap),
                                            ("Largest ML tilt", self.max_ml),
                                            ("Largest AP tilt", self.max_ap))):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(box, row, 1)
        layout.addLayout(grid)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.run_button = buttons.addButton("Space out",
                                            QDialogButtonBox.ButtonRole.ActionRole)
        self.run_button.clicked.connect(self.run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.report = None

    def _clashing(self):
        names = set()
        for pair in self.engine.plan_clearances():
            if pair["distance_um"] < CLEARANCE_UM:
                names.update(pair["probes"])
        return names

    def chosen(self):
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.list.count())
                if self.list.item(row).checkState() == Qt.CheckState.Checked]

    def run(self):
        names = self.chosen()
        if not names:
            self.status.setText("Tick the plans that may move.")
            return
        from PyQt6.QtGui import QGuiApplication

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = self.engine.space_out_plans(
                names, self.gap.value() * 1000.0, self.max_ml.value(), self.max_ap.value())
        finally:
            QGuiApplication.restoreOverrideCursor()
        self.report = report
        self.status.setText(spacing_summary(self.engine, report))


def spacing_summary(engine, report):
    """What Space out did, in words."""
    if report is None:
        return "Load an atlas first."
    if report.get("cancelled"):
        return "Spacing cancelled. No poses were changed."
    if report.get("stale"):
        return "The project changed during spacing. Run Space out again."
    lines = []
    if report["moved"]:
        parts = []
        for name in report["moved"]:
            plan = engine.probe_plans.get(name)
            parts.append("{} ML {:+.0f}°{}".format(
                name, plan.ml_tilt_deg,
                ", AP {:+.0f}°".format(plan.ap_tilt_deg) if plan.ap_tilt_deg else ""))
        lines.append("Tilted " + "; ".join(parts) + ".")
    else:
        lines.append("Nothing needed to move." if not report["clashes"]
                     else "No tilt within the limits helps.")
    for pair in report["clashes"]:
        lines.append("⚠ {} and {} are still {:.2f} mm apart.".format(
            pair["probes"][0], pair["probes"][1], pair["distance_um"] / 1000.0))
    if report["moved"]:
        lines.append("Tilting moves the entries: check the craniotomy and the regions "
                     "along each plan.")
    return " ".join(lines)
