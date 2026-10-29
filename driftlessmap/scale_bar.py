"""A scale bar that keeps a round length as the view zooms."""

import math

import pyqtgraph as pg
from PyQt6.QtCore import QPointF, QRectF

# The bar aims at this fraction of the view's width.
TARGET_FRACTION = 0.2


def nice_length(target_um):
    """The largest 1, 2 or 5 x 10^n um length not above ``target_um``."""
    if not target_um > 0 or not math.isfinite(target_um):
        return None
    power = 10.0 ** math.floor(math.log10(target_um))
    for step in (5, 2, 1):
        if step * power <= target_um:
            return step * power
    return power


def length_label(length_um):
    if length_um >= 1000:
        return "{:g} mm".format(round(length_um / 1000, 6))
    return "{:g} µm".format(round(length_um, 6))


class ScaleBar(pg.ScaleBar):
    """Bottom-right bar for a :class:`pyqtgraph.ViewBox` in data units.

    ``set_unit(um)`` gives the micrometres per data unit (an image pixel or
    an atlas voxel); with None the bar is hidden.
    """

    def __init__(self, view_box):
        super().__init__(1.0, width=4, brush=(255, 255, 255, 220),
                         pen=(0, 0, 0, 160), suffix="", offset=(-16, -16))
        self.um_per_unit = None
        self.length_um = None
        self.setZValue(1e6)
        self.setParentItem(view_box)
        self.setVisible(False)

    def set_unit(self, um_per_unit):
        try:
            um_per_unit = float(um_per_unit)
        except (TypeError, ValueError):
            um_per_unit = None
        if um_per_unit is not None and not (math.isfinite(um_per_unit) and um_per_unit > 0):
            um_per_unit = None
        self.um_per_unit = um_per_unit
        self.setVisible(um_per_unit is not None)
        self.updateBar()

    def updateBar(self):
        view = self.parentItem()
        if view is None or self.um_per_unit is None:
            return
        (x0, x1), _ = view.viewRange()
        length = nice_length(abs(x1 - x0) * self.um_per_unit * TARGET_FRACTION)
        if length is None:
            return
        self.length_um = length
        self.size = length / self.um_per_unit
        p1 = view.mapFromViewToItem(self, QPointF(0, 0))
        p2 = view.mapFromViewToItem(self, QPointF(self.size, 0))
        width = abs((p2 - p1).x())
        self.bar.setRect(QRectF(-width, 0, width, self._width))
        self.text.setText(length_label(length))
        self.text.setPos(-width / 2.0, 0)
