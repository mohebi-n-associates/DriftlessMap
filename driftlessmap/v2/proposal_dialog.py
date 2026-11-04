"""Propose a probe plan from the regions it should record (since 2.8.3).

Choose the target regions (and regions to keep out of), the side of the brain
and the tilts the rig allows; Find plans searches the atlas
(``probe_plans.propose_plans``) with progress and Stop, and lists the best
plans with their entry, tilts, depth, the length of each target in the
recording window (summed over the shanks) and their checks. Selecting a row
shows that proposal on the atlas (in white) and in the shank view below; Use
this plan sets the probe's plan. Results belong to the constraints they were
searched with: changing any constraint clears them (review R7 of 2.8.3). The
search knows the atlas only: vessels, the sinus and the skull are not in it.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressDialog,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..probe_plans import ProposalRequest, plan_readout
from .plan_editor import _spin
from .shank_view import ShankView
from .widgets import button, hint_label

SIDES = ("Either side", "The animal's right", "The animal's left")
COLUMNS = ("Entry AP", "Entry ML", "AP tilt", "ML tilt", "Depth", "Targets in the window",
           "Checks")


def checked_regions(label_tree):
    """The regions checked in the Regions tree, without their checked sub-regions."""
    checked = {int(i) for i in label_tree.checked}
    tops = []
    for label in sorted(checked):
        parent = label_tree.labels_by_id.get(label, {}).get("parent")
        try:
            parent = int(parent)
        except (TypeError, ValueError):
            parent = None
        if parent not in checked:
            tops.append(label)
    return tops


class ProposalDialog(QDialog):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.engine = editor.engine
        self.probe = editor.probe
        self.proposals = []
        self.searched = None        # the request the listed proposals answer
        self.chosen = None
        self.setWindowTitle("Propose a plan for {}".format(self.probe))
        self.resize(820, 760)
        layout = QVBoxLayout(self)
        layout.addWidget(hint_label(
            "Choose the regions the probe should record; the search tries straight tracks "
            "through them within the tilts you allow, checks every shank, and slides the "
            "recording window to its best depth on each. It samples tracks, so it can miss "
            "some; it knows the atlas only: vessels, the sinus and the skull are not in it, "
            "and real brains differ from the atlas."))
        lists = QGridLayout()
        self.targets = QListWidget()
        self.avoid = QListWidget()
        for column, (title, widget) in enumerate((("Record", self.targets),
                                                  ("Keep out of", self.avoid))):
            lists.addWidget(QLabel(title), 0, column)
            widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            widget.setMaximumHeight(110)     # the results table gets the room
            widget.model().rowsInserted.connect(self._inputs_changed)
            widget.model().rowsRemoved.connect(self._inputs_changed)
            lists.addWidget(widget, 1, column)
            row = QHBoxLayout()
            row.addWidget(button("Add…", lambda _c=False, w=widget: self.add_region(w)))
            row.addWidget(button("Checked regions",
                                 lambda _c=False, w=widget: self.add_checked(w)))
            row.addWidget(button("Remove", lambda _c=False, w=widget: self.remove(w)))
            lists.addLayout(row, 2, column)
        layout.addLayout(lists)
        limits = QGridLayout()
        self.side = QComboBox()
        self.side.addItems(SIDES)
        plan = self.engine.probe_plan(self.probe)
        if plan is not None:
            self.side.setCurrentIndex(1 if plan.tip_um[0] >= 0 else 2)
        self.midline = _spin(0, 5, 0.05, 2, " mm", "Keep every shank at least this far from "
                                                    "the midline (the sinus is not in the "
                                                    "atlas)")
        self.midline.setValue(0.2)
        self.max_ap = _spin(0, 80, 5, 0, "°", "The largest AP tilt the rig allows (0: none)")
        self.max_ml = _spin(0, 80, 5, 0, "°", "The largest ML tilt the rig allows (0: none)")
        self.max_ap.setValue(30)
        self.max_ml.setValue(30)
        self.use_hole = QCheckBox("Every shank enters through the probe's craniotomy")
        hole = self.engine.craniotomies.get(plan.craniotomy) if plan and plan.craniotomy else None
        self.use_hole.setEnabled(hole is not None)
        self.use_hole.setChecked(hole is not None)
        for column, (label, widget) in enumerate((("Side", self.side),
                                                  ("Midline margin", self.midline),
                                                  ("Largest AP tilt", self.max_ap),
                                                  ("Largest ML tilt", self.max_ml))):
            limits.addWidget(QLabel(label), column // 2, (column % 2) * 2)
            limits.addWidget(widget, column // 2, (column % 2) * 2 + 1)
        limits.addWidget(self.use_hole, 2, 0, 1, 4)
        layout.addLayout(limits)
        self.side.currentIndexChanged.connect(self._inputs_changed)
        for box in (self.midline, self.max_ap, self.max_ml):
            box.valueChanged.connect(self._inputs_changed)
        self.use_hole.toggled.connect(self._inputs_changed)
        self.find_button = button("Find plans", self.find, primary=True)
        row = QHBoxLayout()
        row.addWidget(self.find_button)
        row.addStretch(1)
        layout.addLayout(row)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            len(COLUMNS) - 2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection)
        self.table.cellDoubleClicked.connect(lambda *_args: self.use())
        layout.addWidget(self.table, 1)
        self.reasons = QLabel("")
        self.reasons.setWordWrap(True)
        self.reasons.setObjectName("StatusWarn")
        layout.addWidget(self.reasons)
        self.checks = QLabel("")
        self.checks.setWordWrap(True)
        layout.addWidget(self.checks)
        self.shank_view = ShankView(self.engine)
        self.shank_view.setMinimumHeight(220)
        layout.addWidget(self.shank_view)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.use_button = buttons.addButton("Use this plan",
                                            QDialogButtonBox.ButtonRole.AcceptRole)
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self.use)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if plan is not None:
            for region in plan.targets:
                self._add(self.targets, region)
            for region in plan.avoid:
                self._add(self.avoid, region)
        self.finished.connect(lambda *_args: self._show_candidate(None))

    # ------------------------------------------------------------ regions
    def _name(self, region):
        atlas = self.engine.plan_atlas()
        acronym, name, _colour = atlas.name(region) if atlas else (str(region), "", None)
        return "{} · {}".format(acronym, name)

    def _add(self, widget, region):
        region = int(region)
        if region in self.regions(widget):
            return
        item = QListWidgetItem(self._name(region))
        item.setData(Qt.ItemDataRole.UserRole, region)
        widget.addItem(item)

    @staticmethod
    def regions(widget):
        return [int(widget.item(i).data(Qt.ItemDataRole.UserRole))
                for i in range(widget.count())]

    def add_region(self, widget):
        regions = self.editor._regions()
        items = ["{} · {}".format(a, n) for a, n, _i in regions]
        if not items:
            return
        choice, ok = QInputDialog.getItem(self, "Add a region", "Region:", items, 0, True)
        if ok and choice in items:
            self._add(widget, regions[items.index(choice)][2])

    def add_checked(self, widget):
        for region in checked_regions(self.engine.atlas_view.label_tree):
            self._add(widget, region)

    def remove(self, widget):
        for item in widget.selectedItems():
            widget.takeItem(widget.row(item))

    # ------------------------------------------------------------ search
    def request(self):
        side = (None, 1, -1)[self.side.currentIndex()]
        plan = self.engine.probe_plan(self.probe)
        hole = None
        if self.use_hole.isChecked() and plan is not None and plan.craniotomy:
            hole = self.engine.craniotomies.get(plan.craniotomy)
        return ProposalRequest(self.regions(self.targets), self.regions(self.avoid), side=side,
                               midline_um=self.midline.value() * 1000.0,
                               max_ap_tilt_deg=self.max_ap.value(),
                               max_ml_tilt_deg=self.max_ml.value(), craniotomy=hole)

    def _clear(self, message=""):
        self.proposals = []
        self.searched = None
        self.chosen = None
        self.table.setRowCount(0)
        self.use_button.setEnabled(False)
        self.checks.setText("")
        self._show_candidate(None)
        self.reasons.setText(message)

    def _inputs_changed(self, *_args):
        """Results answer the constraints they were found with; new ones need a search."""
        if self.searched is not None:
            self._clear("The constraints changed: Find plans again.")

    def find(self):
        try:
            request = self.request()
        except ValueError as exc:
            self._clear(str(exc).capitalize() + ".")
            return
        self._clear()
        progress = QProgressDialog("Searching for probe plans…", "Stop", 0, 100, self)
        progress.setWindowTitle("Propose a plan")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)

        def report(done, total, stage):
            progress.setLabelText("{}… ({} of {})".format(stage, done, total))
            progress.setMaximum(total)
            progress.setValue(done)
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            proposals, reasons = self.engine.propose_probe_plans(self.probe, request,
                                                                 progress=report)
        finally:
            progress.reset()
        self.proposals = proposals
        self.searched = request.describe()
        self.table.setRowCount(len(proposals))
        n = len(request.targets)
        for row, proposal in enumerate(proposals):
            plan = proposal["plan"]
            reached = "{}/{}: ".format(proposal["reached"], n) if n > 1 else ""
            notes = proposal["warnings"]
            cells = ("{:+.2f} mm".format(proposal["entry_um"][1] / 1000.0),
                     "{:+.2f} mm".format(proposal["entry_um"][0] / 1000.0),
                     "{:+.1f}°".format(plan.ap_tilt_deg), "{:+.1f}°".format(plan.ml_tilt_deg),
                     "{:.2f} mm".format(proposal["depth_um"] / 1000.0),
                     reached + ", ".join("{} {:.2f} mm".format(name, length / 1000.0)
                                         for name, length in proposal["coverage"]),
                     "passed" if not notes else
                     "passed, {} note{}".format(len(notes), "" if len(notes) == 1 else "s"))
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column < 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if column == len(COLUMNS) - 1 and notes:
                    item.setToolTip("\n".join(notes))
                self.table.setItem(row, column, item)
        self.reasons.setText(" ".join(reasons) if reasons else
                             ("" if proposals else "No plan found that records any target."))
        if proposals:
            self.table.selectRow(0)

    # ------------------------------------------------------------ choosing
    def _row(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        return rows[0] if len(rows) == 1 and rows[0] < len(self.proposals) else None

    def _selection(self):
        row = self._row()
        self.use_button.setEnabled(row is not None and self.searched is not None)
        self._show_candidate(None if row is None else self.proposals[row])

    def _show_candidate(self, proposal):
        """Show a proposal on the atlas (white) and in the shank view, before use."""
        engine = self.engine
        engine.plan_candidates.pop(self.probe, None)
        if proposal is None:
            self.shank_view.show_plan(None, None)
            engine.plan_overlay.refresh()
            return
        plan = proposal["plan"]
        engine.plan_candidates[self.probe] = plan
        atlas = engine.plan_atlas()
        self.shank_view.show_plan(plan, plan_readout(plan, atlas))
        engine.plan_overlay.refresh()
        point = atlas.to_vox(plan.tip_um)
        view = engine.atlas_view
        for control, page in ((view.spage_ctrl, point[0]), (view.cpage_ctrl, point[1]),
                              (view.hpage_ctrl, point[2])):
            control.set_val(int(min(max(round(page), 0), control.page_slider.maximum())))
        per_shank = proposal.get("shank_coverage") or []
        lines = []
        if len(per_shank) > 1:
            names = [name for name, _length in proposal["coverage"]]
            for number, lengths in enumerate(per_shank):
                lines.append("Shank {}: {}".format(number + 1, ", ".join(
                    "{} {:.2f} mm".format(name, length / 1000.0)
                    for name, length in zip(names, lengths))))
        lines.append("Checked on every shank: tip in the brain, no region to keep out of, "
                     "the side, the midline margin and the craniotomy.")
        lines += ["Note: " + w for w in proposal["warnings"]]
        self.checks.setText("\n".join(lines))

    def use(self):
        row = self._row()
        if row is None or self.searched is None:
            return
        try:
            current = self.request().describe()
        except ValueError:
            current = None
        if current != self.searched:
            self._clear("The constraints changed: Find plans again.")
            return
        self.chosen = self.proposals[row]["plan"]
        self.accept()


__all__ = ["ProposalDialog", "checked_regions"]
