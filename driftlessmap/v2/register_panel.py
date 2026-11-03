"""Register step: suggested and manual landmarks, mesh, review and warp preview."""

import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
)

from .widgets import Card, StepPanel, button, grid_of, hint_label, set_status, status_label

KIND_LABELS = {"outline": "Outline", "internal": "Internal", "suggested": "Suggested"}

# Short: check boxes do not wrap, and the step column is narrow.
CHECKLIST = (
    "Hemisphere and orientation are right",
    "Internal anatomy lines up too",
    "Region boundaries follow the tissue",
    "Torn or missing tissue is not stretched",
)
BLINK_MS = 500
CHECKER_SQUARES = 8     # squares along the longer side


def checkerboard(image, squares=CHECKER_SQUARES):
    """``image`` with every other square blanked (the atlas shows through)."""
    image = np.asarray(image)
    height, width = image.shape[:2]
    size = max(1, int(np.ceil(max(height, width) / squares)))
    rows = (np.arange(height) // size)[:, None]
    columns = (np.arange(width) // size)[None, :]
    keep = (rows + columns) % 2 == 0
    if image.ndim == 3:
        keep = keep[..., None]
    return np.where(keep, image, 0).astype(image.dtype)


def _point(values):
    return "{:.0f}, {:.0f}".format(float(values[0]), float(values[1]))


class RegisterPanel(StepPanel):
    title = "Register"
    hint = ("Pair landmarks between the atlas and the section. Suggestions are a "
            "starting point: check each pair and drag any that are off.")

    def build(self):
        engine, shell = self.engine, self.shell
        self._table_key = None
        self.require(shell.needs_atlas_and_image)
        needs_both = shell.needs_both
        needs_pair_views = shell.needs_atlas_and_image

        points = self.add(Card("Landmarks"))
        points.add_row(self.gate(button("Suggest landmarks", lambda: shell.run("register.suggest"),
                                        primary=True), needs_both), None)
        self.add_point = button("Add or move points", lambda: shell.toggle_tool("triang"),
                                checkable=True,
                                tooltip="Click the atlas, then the matching place in the "
                                        "section. Drag points to move them. (P)")
        points.add(grid_of([
            self.gate(self.add_point, needs_pair_views),
            self.gate(button("Delete pair", self._delete_selected,
                             tooltip="Delete / Backspace"), self._needs_selection),
            self.gate(button("Centre on pair", self._centre_selected), self._needs_selection),
            self.gate(button("Mesh lines", engine.tool_box.triang_vis_btn.click),
                      needs_pair_views),
        ], columns=2))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Kind", "Atlas x, y", "Section x, y"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(180)
        self.table.cellDoubleClicked.connect(lambda row, _col: self._centre(row))
        points.add(self.table)
        self.points_note = points.add(hint_label(""))

        mesh = self.add(Card("Mesh"))
        self.mesh_status = mesh.add(status_label(""))
        mesh.add(hint_label(
            "Mesh valid / review / invalid checks the triangle geometry only. It does "
            "not say whether the anatomy matches."))

        review = self.add(Card("Review"))
        self.review_status = review.add(status_label(""))
        # What to look at before marking a review (review U9); the ticks clear
        # whenever the registration changes.
        self.checklist = [QCheckBox(text) for text in CHECKLIST]
        for box in self.checklist:
            review.add(box)
        self._checked_fingerprint = None
        review.add(hint_label(
            "Check with the section-on-atlas preview, using Blink and Checkerboard "
            "below to compare internal edges, not only the outline."))
        review.add_row(self.gate(button("Mark review complete",
                                        lambda: shell.run("register.review")),
                                 self._needs_review_checks), None)
        review.add(hint_label(
            "Moving any landmark or changing the atlas plane, page or tilt clears the "
            "review and the checklist."))

        warp = self.add(Card("Warp preview"))
        self.warp_status = warp.add(status_label(""))
        self.to_atlas = button("Section on atlas", engine.tool_box.toa_btn.trigger,
                               checkable=True)
        self.to_section = button("Atlas on section", engine.tool_box.toh_btn.trigger,
                                 checkable=True)
        warp.add(grid_of([self.gate(self.to_atlas, self._needs_warp_atlas),
                          self.gate(self.to_section, self._needs_warp_section)], columns=2))
        self.blink = button("Blink", self._toggle_blink, checkable=True,
                            tooltip="Flip the warped section on and off over the atlas")
        self.checker = button("Checkerboard", self._toggle_checker, checkable=True,
                              tooltip="Show section and atlas in alternating squares, so "
                                      "their edges can be followed across square borders")
        warp.add(grid_of([self.gate(self.blink, self._needs_section_preview),
                          self.gate(self.checker, self._needs_section_preview)], columns=2))
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(BLINK_MS)
        self._blink_timer.timeout.connect(self._blink_tick)
        warp.add(hint_label(
            "Previewing shows a warped image only. Annotations move to the atlas only "
            "with Map annotations to atlas, in the Annotate step. Press the active "
            "preview again to remove it."))

        advanced = self.add(Card("Frame and landmark files"))
        self.frame_points = engine.tool_box.bound_pnts_num
        frame_box = QLineEdit()
        frame_box.setText(self.frame_points.text())
        frame_box.setMaximumWidth(60)
        frame_box.editingFinished.connect(lambda: self._set_frame_points(frame_box.text()))
        self.frame_box = frame_box
        advanced.add_row(hint_label("Frame points per side"), frame_box, None)
        advanced.add(grid_of([
            self.gate(button("Fit frame to tissue", engine.tool_box.triang_match_bnd.click),
                      needs_pair_views),
            button("Import landmarks…", engine.actionLoad_Triangulation_Points.trigger),
            button("Export landmarks…", engine.actionSave_Triangulation_Points.trigger),
        ], columns=2))

    # --------------------------------------------------------- availability
    def _needs_pairs(self, minimum=1):
        engine = self.engine
        atlas, histology = engine.atlas_tri_inside_data, engine.histo_tri_inside_data
        if len(atlas) != len(histology) or len(atlas) < minimum:
            return self.shell.needs_atlas_and_image() or (
                "Place at least {} complete landmark pair{} first.".format(
                    minimum, "" if minimum == 1 else "s"))
        return None

    def _needs_review_pairs(self):
        return self._needs_pairs(3)

    def _needs_review_checks(self):
        reason = self._needs_review_pairs()
        if reason is None and not all(box.isChecked() for box in self.checklist):
            reason = "Tick each point of the checklist first."
        return reason

    def _needs_section_preview(self):
        return None if self.engine.h2a_transferred else \
            "Show the section on the atlas first (Section on atlas)."

    # ------------------------------------------------------------- compare
    def _overlay_item(self):
        return self.engine.atlas_view.working_atlas.image_dict["atlas-overlay"]

    def _toggle_blink(self):
        if self.blink.isChecked() and self.engine.h2a_transferred:
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._overlay_item().setVisible(True)

    def _blink_tick(self):
        item = self._overlay_item()
        item.setVisible(not item.isVisible())

    def _toggle_checker(self):
        engine = self.engine
        warped = engine.working_atlas_data.get("atlas-overlay")
        if warped is None or not len(warped):
            self.checker.setChecked(False)
            return
        warped = np.asarray(warped)
        if self.checker.isChecked():
            self._overlay_item().setImage(checkerboard(warped))
        else:
            self._overlay_item().setImage(warped)

    def stop_compare(self):
        """Back to the plain preview (also when the preview goes)."""
        self._blink_timer.stop()
        for widget in (self.blink, self.checker):
            widget.setChecked(False)
        warped = self.engine.working_atlas_data.get("atlas-overlay")
        item = self._overlay_item()
        item.setVisible(True)
        if self.engine.h2a_transferred and warped is not None and len(warped):
            item.setImage(np.asarray(warped))

    def _needs_selection(self):
        return (None if self._selected_row() is not None
                else "Select a landmark pair in the list first.")

    def _needs_warp_atlas(self):
        if self.engine.a2h_transferred:
            return "Remove the atlas-on-section preview first."
        return self.shell.needs_atlas_and_image()

    def _needs_warp_section(self):
        if self.engine.h2a_transferred:
            return "Remove the section-on-atlas preview first."
        return self.shell.needs_atlas_and_image()

    # -------------------------------------------------------------- helpers
    def _kinds(self):
        engine = self.engine
        atlas, histology = engine.atlas_tri_inside_data, engine.histo_tri_inside_data
        kinds = ["Manual"] * len(atlas)
        suggested = engine.suggested_landmarks
        if suggested:
            s_atlas, s_hist, s_kinds = suggested
            for index in range(min(len(atlas), len(s_atlas))):
                same = (np.allclose(atlas[index], s_atlas[index], atol=0.01)
                        and index < len(histology)
                        and np.allclose(histology[index], s_hist[index], atol=0.01))
                if same:
                    kinds[index] = KIND_LABELS.get(s_kinds[index], s_kinds[index].capitalize())
                elif index < len(s_atlas):
                    kinds[index] = "Edited"
        return kinds

    def _selected_row(self):
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def delete_selected(self):
        self._delete_selected()

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            self.shell.message("Select a landmark pair in the list first.", "warn")
            return
        engine = self.engine
        if engine.a2h_transferred or engine.h2a_transferred:
            self.shell.message("Remove the warp preview before deleting landmarks.", "warn")
            return
        engine._delete_paired_triangulation_landmark(row)
        self.refresh()

    def _centre_selected(self):
        row = self._selected_row()
        if row is None:
            self.shell.message("Select a landmark pair in the list first.", "warn")
            return
        self._centre(row)

    def _centre(self, row):
        engine = self.engine
        if row >= len(engine.atlas_tri_inside_data) or row >= len(engine.histo_tri_inside_data):
            return
        for vb, point, shape in (
            (engine.atlas_view.working_atlas.vb, engine.atlas_tri_inside_data[row],
             np.shape(engine.atlas_view.working_atlas.img.image)),
            (engine.image_view.img_stacks.vb, engine.histo_tri_inside_data[row],
             np.shape(engine.image_view.current_img)),
        ):
            radius = 0.15 * max(shape[:2]) if len(shape) >= 2 else 20
            x, y = float(point[0]), float(point[1])
            vb.setRange(xRange=(x - radius, x + radius), yRange=(y - radius, y + radius),
                        padding=0)

    def _set_frame_points(self, text):
        self.frame_points.setText(text)
        self.frame_points.editingFinished.emit()

    # -------------------------------------------------------------- refresh
    def refresh(self):
        engine = self.engine
        fingerprint = engine.current_registration_fingerprint()
        if fingerprint != self._checked_fingerprint:
            # Another registration: its checks start again.
            self._checked_fingerprint = fingerprint
            for box in self.checklist:
                box.setChecked(engine.registration_review_state() == "reviewed")
        if not engine.h2a_transferred and (self.blink.isChecked() or self.checker.isChecked()):
            self.stop_compare()
        atlas, histology = engine.atlas_tri_inside_data, engine.histo_tri_inside_data
        key = (tuple(map(tuple, np.round(np.asarray(atlas, float), 1).tolist())) if atlas else (),
               tuple(map(tuple, np.round(np.asarray(histology, float), 1).tolist()))
               if histology else (), repr(engine.suggested_landmarks)[:100])
        if key != self._table_key:
            self._table_key = key
            selected = self._selected_row()
            kinds = self._kinds()
            count = max(len(atlas), len(histology))
            self.table.setRowCount(count)
            for row in range(count):
                values = [str(row + 1), kinds[row] if row < len(kinds) else "Manual",
                          _point(atlas[row]) if row < len(atlas) else "—",
                          _point(histology[row]) if row < len(histology) else "(place in section)"]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, QTableWidgetItem(value))
            if selected is not None and selected < count:
                self.table.selectRow(selected)
        pairs = min(len(atlas), len(histology))
        unpaired = abs(len(atlas) - len(histology))
        note = "{} pair{}".format(pairs, "" if pairs == 1 else "s")
        if unpaired:
            note += " · finish the incomplete pair (place its {} point)".format(
                "section" if len(atlas) > len(histology) else "atlas")
        self.points_note.setText(note)
        self.add_point.setChecked(engine.tool_box.checkable_btn_dict["triang_btn"].isChecked())
        self.frame_box.setText(self.frame_points.text()) if not self.frame_box.hasFocus() else None

        text = engine.tool_box.triang_quality_label.text()
        lowered = text.lower()
        kind = ("bad" if "invalid" in lowered else "warn" if "review" in lowered
                else "good" if "good" in lowered or "valid" in lowered else None)
        set_status(self.mesh_status, text, kind)

        review = engine.registration_review_state()
        set_status(self.review_status, {
            "reviewed": ("Reviewed by you for the current landmarks and plane.", "good"),
            "not reviewed": ("Not reviewed.", "warn"),
            "not recorded": ("Review not recorded (older project).", None),
        }[review][0], {"reviewed": "good", "not reviewed": "warn"}.get(review))

        self.to_atlas.setChecked(bool(engine.h2a_transferred))
        self.to_section.setChecked(bool(engine.a2h_transferred))
        if engine.h2a_transferred:
            set_status(self.warp_status, "Showing the section warped onto the atlas.", "good")
        elif engine.a2h_transferred:
            set_status(self.warp_status, "Showing the atlas warped onto the section.", "good")
        else:
            set_status(self.warp_status, "No preview.", None)
