"""Register step: suggested and manual landmarks, mesh, review and warp preview."""

import numpy as np
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QLineEdit, QTableWidget, QTableWidgetItem

from .widgets import Card, StepPanel, button, grid_of, hint_label, set_status, status_label

KIND_LABELS = {"outline": "Outline", "internal": "Internal", "suggested": "Suggested"}


def _point(values):
    return "{:.0f}, {:.0f}".format(float(values[0]), float(values[1]))


class RegisterPanel(StepPanel):
    title = "Register"
    hint = ("Pair landmarks between the atlas and the section. Suggestions are a "
            "starting point: check each pair and drag any that are off.")

    def build(self):
        engine, shell = self.engine, self.shell
        self._table_key = None

        points = self.add(Card("Landmarks"))
        points.add_row(button("Suggest landmarks", lambda: shell.run("register.suggest"),
                              primary=True), None)
        self.add_point = button("Add or move points", lambda: shell.toggle_tool("triang"),
                                checkable=True,
                                tooltip="Click the atlas, then the matching place in the "
                                        "section. Drag points to move them. (P)")
        points.add(grid_of([
            self.add_point,
            button("Delete pair", self._delete_selected,
                   tooltip="Delete / Backspace"),
            button("Centre on pair", self._centre_selected),
            button("Mesh lines", engine.tool_box.triang_vis_btn.click),
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
        review.add_row(button("Mark review complete", lambda: shell.run("register.review")),
                       None)
        review.add(hint_label(
            "Mark the registration reviewed after checking internal anatomy as well as "
            "the outline. Moving any landmark or changing the atlas plane clears it."))

        warp = self.add(Card("Warp preview"))
        self.warp_status = warp.add(status_label(""))
        self.to_atlas = button("Section on atlas", engine.tool_box.toa_btn.trigger,
                               checkable=True)
        self.to_section = button("Atlas on section", engine.tool_box.toh_btn.trigger,
                                 checkable=True)
        warp.add(grid_of([self.to_atlas, self.to_section], columns=2))
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
            button("Fit frame to tissue", engine.tool_box.triang_match_bnd.click),
            button("Import landmarks…", engine.actionLoad_Triangulation_Points.trigger),
            button("Export landmarks…", engine.actionSave_Triangulation_Points.trigger),
        ], columns=2))

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
        self.to_section.setEnabled(not engine.h2a_transferred)
        self.to_atlas.setEnabled(not engine.a2h_transferred)
        if engine.h2a_transferred:
            set_status(self.warp_status, "Showing the section warped onto the atlas.", "good")
        elif engine.a2h_transferred:
            set_status(self.warp_status, "Showing the atlas warped onto the section.", "good")
        else:
            set_status(self.warp_status, "No preview.", None)
