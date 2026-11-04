"""Planned probes drawn on the 2-D atlas views.

Each plan's track (entry to tip) is projected onto the slice shown in the
coronal, sagittal and horizontal atlas views: dashed where it lies away from
the slice, solid within ``NEAR_UM`` of it, with the entry (open circle) and
the tip (filled) marked. Slices are mapped to 3-D with the same functions
that placed clicked points (``AtlasView.get_*_3d``), so tilted slices are
handled. A plan being edited (``engine.plan_previews``) is drawn in place of
its stored version.
"""

import json

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer, Qt

NEAR_UM = 100.0
SAMPLES = 200
POLL_MS = 400
DEFAULT_COLOUR = (232, 72, 85)


class PlanOverlay:
    def __init__(self, engine):
        self.engine = engine
        self._items = {"coronal": [], "sagittal": [], "horizontal": []}
        self._key = None
        view = engine.atlas_view
        for control in (view.cpage_ctrl, view.spage_ctrl, view.hpage_ctrl):
            control.sig_page_changed.connect(lambda *_args: self.refresh())
        for control in (view.crotation_ctrl, view.srotation_ctrl, view.hrotation_ctrl):
            control.sig_slice_rotated.connect(lambda *_args: self.refresh())
        self._timer = QTimer(view)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)

    def _poll(self):
        try:
            self.refresh()
        except RuntimeError:
            # The atlas views were deleted (the window is closing): stop.
            self._timer.stop()

    def _views(self):
        view = self.engine.atlas_view
        return {"coronal": (view.cimg, view.get_coronal_3d),
                "sagittal": (view.simg, view.get_sagittal_3d),
                "horizontal": (view.himg, view.get_horizontal_3d)}

    def tracks(self):
        """(probe, colour, entry, tip) in Bregma-relative voxels for each plan."""
        engine = self.engine
        atlas = engine.plan_atlas()
        if atlas is None:
            return []
        plans = {plan.probe: plan for plan in engine.probe_plans.plans()}
        plans.update(engine.plan_previews)
        found = []
        for probe in sorted(plans):
            readout = engine.probe_plan_readout(plans[probe])
            if readout is None or readout["entry_um"] is None:
                continue
            found.append((probe, tuple(engine.plan_colours.get(probe, DEFAULT_COLOUR)),
                          np.asarray(readout["entry_um"]) / atlas.vox_um,
                          np.asarray(plans[probe].tip_um) / atlas.vox_um))
        return found

    def refresh(self):
        view = self.engine.atlas_view
        if view.atlas_data is None or self.engine.plan_atlas() is None:
            if self._key is not None:
                self._key = None
                self.clear()
            return
        tracks = self.tracks()
        key = (view.current_coronal_index, view.current_sagital_index,
               view.current_horizontal_index, json.dumps(view.get_atlas_angles()),
               json.dumps([(p, c, e.tolist(), t.tolist()) for p, c, e, t in tracks]))
        if key == self._key:
            return
        self._key = key
        self.clear()
        vox_um = self.engine.plan_atlas().vox_um
        for plane, (stack, to_3d) in self._views().items():
            corners = np.asarray(to_3d(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])),
                                 dtype=float)
            origin, axis_x, axis_y = corners[0], corners[1] - corners[0], corners[2] - corners[0]
            normal = np.cross(axis_x, axis_y)
            if np.linalg.norm(normal) == 0:
                continue
            normal /= np.linalg.norm(normal)
            frame = np.column_stack([axis_x, axis_y, normal])
            for _probe, colour, entry, tip in tracks:
                self._draw(plane, stack, origin, frame, entry, tip, colour, vox_um)

    def _draw(self, plane, stack, origin, frame, entry, tip, colour, vox_um):
        points = entry + np.linspace(0.0, 1.0, SAMPLES)[:, None] * (tip - entry)
        uvw = np.linalg.solve(frame, (points - origin).T).T
        uv, depth = uvw[:, :2], np.abs(uvw[:, 2]) * vox_um
        near = depth <= NEAR_UM
        pen = pg.mkPen(*colour[:3], width=1.5, style=Qt.PenStyle.DashLine)
        dashed = pg.PlotDataItem(uv[[0, -1], 0], uv[[0, -1], 1], pen=pen)
        items = [dashed]
        if np.any(near):
            # One flag per point: whether it joins the next one.
            joins = np.append(near[:-1] & near[1:], False)
            solid = pg.PlotDataItem(uv[:, 0], uv[:, 1], connect=joins,
                                    pen=pg.mkPen(*colour[:3], width=3))
            items.append(solid)
        ends = pg.ScatterPlotItem(
            x=uv[[0, -1], 0], y=uv[[0, -1], 1], size=9,
            pen=[pg.mkPen(*colour[:3], width=2)] * 2,
            brush=[pg.mkBrush(0, 0, 0, 0), pg.mkBrush(*colour[:3])])
        items.append(ends)
        for item in items:
            item.setZValue(55)
            if hasattr(item, "setAcceptedMouseButtons"):
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            stack.vb.addItem(item)
            self._items[plane].append((stack, item))

    def clear(self):
        for items in self._items.values():
            for stack, item in items:
                stack.vb.removeItem(item)
            items.clear()

    def drawn(self, plane):
        """Number of tracks drawn on ``plane``'s view (for tests)."""
        return sum(1 for _stack, item in self._items[plane]
                   if isinstance(item, pg.ScatterPlotItem))
