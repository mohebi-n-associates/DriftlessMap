"""Built fibers and prisms drawn on the 2-D atlas views.

Wherever the slice shown in the coronal, sagittal or horizontal atlas view cuts
a built implant's fitted model, its cross-section is outlined in the implant's
colour. The slices are mapped to 3-D with the same functions that placed the
section outlines (``AtlasView.get_*_3d``), so tilted slices are handled and the
drawing lines up with where the outlines were mapped.
"""

import json

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtGui import QBrush, QColor, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPolygonItem

from .implants import model_section

# Checked this often for builds, deletions, undo and visibility changes; page
# and tilt changes redraw at once.
POLL_MS = 400


class ImplantOverlay:
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
        self._timer.timeout.connect(self.refresh)
        self._timer.start(POLL_MS)

    # ----------------------------------------------------------- geometry
    def _views(self):
        view = self.engine.atlas_view
        size = view.atlas_size
        return {
            "coronal": (view.cimg, view.get_coronal_3d, (size[0], size[1])),
            "sagittal": (view.simg, view.get_sagittal_3d, (size[0], size[2])),
            "horizontal": (view.himg, view.get_horizontal_3d, (size[1], size[2])),
        }

    def built_models(self):
        """(name, colour, model) of each visible built fiber or prism."""
        engine = self.engine
        o = engine.object_ctrl
        models = []
        for implant in engine.implants.implants():
            built = engine.implant_objects(implant.implant_id, built=True)
            if not built or not getattr(o.obj_list[built[-1]], "vis", True):
                continue
            model = (o.obj_data[built[-1]].get("report") or {}).get("model")
            if model:
                models.append((implant.name, tuple(implant.colour), model))
        return models

    def _state(self):
        view = self.engine.atlas_view
        if view.atlas_data is None:
            return None
        models = self.built_models()
        return (view.current_coronal_index, view.current_sagital_index,
                view.current_horizontal_index, json.dumps(view.get_atlas_angles()),
                json.dumps([(name, colour, model) for name, colour, model in models],
                           default=float)), models

    # ------------------------------------------------------------ drawing
    def refresh(self):
        state = self._state()
        key = None if state is None else state[0]
        if key == self._key:
            return
        self._key = key
        self.clear()
        if state is None:
            return
        for plane, (stack, to_3d, shape) in self._views().items():
            corners = np.asarray(to_3d(np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])),
                                 dtype=float)
            origin, axis_x, axis_y = corners[0], corners[1] - corners[0], corners[2] - corners[0]
            for _name, colour, model in state[1]:
                mask = model_section(model, origin, axis_x, axis_y, shape)
                if mask is not None:
                    self._draw(plane, stack, mask, colour)

    def _draw(self, plane, stack, mask, colour):
        contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        pen = QPen(QColor(*colour[:3]))
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        fill = QColor(*colour[:3])
        fill.setAlpha(70)
        for contour in contours:
            points = contour.reshape(-1, 2).astype(float)
            # Contours run along pixel indexes; outline the pixels' edges.
            polygon = QPolygonF([QPointF(x + 0.5, y + 0.5) for x, y in points])
            item = QGraphicsPolygonItem(polygon)
            item.setPen(pen)
            item.setBrush(QBrush(fill))
            item.setZValue(50)
            stack.vb.addItem(item)
            self._items[plane].append((stack, item))

    def clear(self):
        for items in self._items.values():
            for stack, item in items:
                stack.vb.removeItem(item)
            items.clear()

    def drawn(self, plane):
        """Number of outlines drawn on ``plane``'s view (for tests)."""
        return len(self._items[plane])
