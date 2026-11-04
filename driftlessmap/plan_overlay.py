"""Planned probes drawn on the 2-D atlas views.

Each plan's track (entry to tip) is projected onto the slice shown in the
coronal, sagittal and horizontal atlas views: dashed where it lies away from
the slice, solid within ``NEAR_UM`` of it, with the entry (open circle) and
the tip (filled) marked. Slices are mapped to 3-D with the same functions
that placed clicked points (``AtlasView.get_*_3d``), so tilted slices are
handled. A plan being edited (``engine.plan_previews``) is drawn in place of
its stored version. A planned fiber or prism (2.8.5) is also outlined, dashed,
wherever the slice cuts it.
"""

import json

import cv2
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QPolygonF
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsPolygonItem

from .implants import model_section

NEAR_UM = 100.0
SAMPLES = 200
POLL_MS = 400
DEFAULT_COLOUR = (232, 72, 85)
FERRULE_GRAY = (184, 184, 184)


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
        """(probe, colour, entry, tip, model) for each plan: entry and tip in
        Bregma-relative voxels; model the planned fiber or prism to outline
        (``implants.model_section``), or None for a probe."""
        engine = self.engine
        atlas = engine.plan_atlas()
        if atlas is None:
            return []
        plans = {plan.probe: plan for plan in engine.probe_plans.plans()}
        plans.update(engine.plan_previews)
        # A proposal being inspected is drawn in white beside the plan.
        for probe, candidate in engine.plan_candidates.items():
            plans[probe + " (proposal)"] = candidate
        found = []
        for probe in sorted(plans):
            readout = engine.probe_plan_readout(plans[probe], others=False)
            if readout is None or readout["entry_um"] is None:
                continue
            plan = plans[probe]
            implant = engine.implants.get(plan.implant_id) if plan.implant_id else None
            colour = (255, 255, 255) if probe.endswith(" (proposal)") \
                else engine.plan_colours.get(probe, implant.colour if implant is not None
                                             else DEFAULT_COLOUR)
            model = readout.get("model")
            if readout.get("hardware") is not None:
                model = {"type": "hardware", "hardware": readout["hardware"]}
            found.append((probe, tuple(colour),
                          np.asarray(readout["entry_um"]) / atlas.vox_um,
                          np.asarray(plan.tip_um) / atlas.vox_um, model))
        return found

    def refresh(self):
        view = self.engine.atlas_view
        if view.atlas_data is None or self.engine.plan_atlas() is None:
            if self._key is not None:
                self._key = None
                self.clear()
            return
        tracks = self.tracks()
        holes = [c.to_dict() for c in self.engine.craniotomies.craniotomies()]
        key = (view.current_coronal_index, view.current_sagital_index,
               view.current_horizontal_index, json.dumps(view.get_atlas_angles()),
               json.dumps([(p, c, e.tolist(), t.tolist(), m) for p, c, e, t, m in tracks],
                          default=float),
               json.dumps(holes))
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
            shape = self._shape(plane)
            for _probe, colour, entry, tip, model in tracks:
                self._draw(plane, stack, origin, frame, entry, tip, colour, vox_um)
                if model is not None:
                    # The device in its colour, a fiber's ferrule gray.
                    ferrule = model.get("ferrule")
                    body = {k: v for k, v in model.items() if k != "ferrule"}
                    if model["type"] == "hardware":
                        # A probe's hardware is gray (2.8.6); its track is drawn above.
                        body, ferrule = None, model["hardware"]
                    for part, tint in ((body, colour), (ferrule, FERRULE_GRAY)):
                        if not isinstance(part, dict):
                            continue
                        mask = model_section(part, origin, axis_x, axis_y, shape)
                        if mask is not None:
                            self._outline(plane, stack, mask, tint)
            if plane == "horizontal":
                for hole in holes:
                    self._draw_hole(stack, origin, frame, hole, vox_um)

    def _shape(self, plane):
        size = self.engine.atlas_view.atlas_size
        return {"coronal": (size[0], size[1]), "sagittal": (size[0], size[2]),
                "horizontal": (size[1], size[2])}[plane]

    def _outline(self, plane, stack, mask, colour):
        """A planned fiber's or prism's cross-section on the slice, as the
        built implants are drawn (``ImplantOverlay``), with a lighter fill."""
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        pen = pg.mkPen(*colour[:3], width=2, style=Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        fill = QColor(*colour[:3])
        fill.setAlpha(45)
        for contour in contours:
            points = contour.reshape(-1, 2).astype(float)
            item = QGraphicsPolygonItem(QPolygonF([QPointF(x + 0.5, y + 0.5)
                                                   for x, y in points]))
            item.setPen(pen)
            item.setBrush(QBrush(fill))
            item.setZValue(53)
            stack.vb.addItem(item)
            self._items[plane].append((stack, item))

    def outlines_drawn(self, plane):
        """Number of planned implant outlines on ``plane``'s view (for tests)."""
        return sum(1 for _stack, item in self._items[plane]
                   if isinstance(item, QGraphicsPolygonItem))

    def _draw_hole(self, stack, origin, frame, hole, vox_um):
        """A craniotomy as a dashed circle on the horizontal view."""
        centre = np.array([hole["centre_um"][0] / vox_um, hole["centre_um"][1] / vox_um,
                           origin[2]])
        u, v, _w = np.linalg.solve(frame, centre - origin)
        radius = hole["diameter_um"] / 2.0 / vox_um / np.linalg.norm(frame[:, 0])
        item = QGraphicsEllipseItem(u - radius, v - radius, 2 * radius, 2 * radius)
        pen = pg.mkPen(255, 255, 255, width=1.5, style=Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setZValue(54)
        item.setToolTip(hole["name"])
        stack.vb.addItem(item)
        self._items["horizontal"].append((stack, item))

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

    def holes_drawn(self):
        """Number of craniotomies drawn on the horizontal view (for tests)."""
        return sum(1 for _stack, item in self._items["horizontal"]
                   if isinstance(item, QGraphicsEllipseItem))

    def drawn(self, plane):
        """Number of tracks drawn on ``plane``'s view (for tests)."""
        return sum(1 for _stack, item in self._items[plane]
                   if isinstance(item, pg.ScatterPlotItem))
