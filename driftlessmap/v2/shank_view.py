"""The planned probe drawn to scale: the probe plane and the shank strip.

Left, the atlas in the plane of the shank's face (``probe_plans.probe_plane``)
with the probe (each shank), its entry and tip. Right, the shank itself from
the entry (top) to the tip: the regions it passes through, labelled, the
contacts as ticks and the recording window as a bracket. Hovering names the
region and the depth. Display only; the plan is edited in the Plan section.
"""

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..probe_plans import probe_plane

STRIP_WIDTH = 120
GAP = 8
HEIGHT = 320


class ShankView(QWidget):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.plan = None
        self.readout = None
        self._plane = None
        self._image = None
        self.setMinimumHeight(HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setToolTip("The planned probe to scale: left, the atlas in the plane of the "
                        "shank's face; right, the regions along the shank, the contacts and "
                        "the recording window. Hover for names and depths.")

    # ------------------------------------------------------------- data
    def show_plan(self, plan, readout):
        self.plan, self.readout = plan, readout
        self._plane = self._image = None
        atlas = self.engine.plan_atlas()
        if plan is not None and readout is not None and atlas is not None \
                and readout.get("entry_um") is not None:
            margin = 500.0
            window = readout.get("imaging_window_um")
            if window and readout.get("depth_um") is not None:
                # Room above the entry for an imaging window that reaches out.
                margin = max(margin, window[1] - readout["depth_um"] + 200.0)
            self._plane = probe_plane(atlas, plan, readout, margin_um=margin)
            if self._plane is not None:
                self._image = self._colour_image(atlas, self._plane[0])
        self.update()

    @staticmethod
    def _colour_image(atlas, labels):
        ids, inverse = np.unique(labels, return_inverse=True)
        palette = np.array([(16, 16, 20) if i == 0 else atlas.name(i)[2] for i in ids],
                           dtype=np.uint8)
        rgb = np.ascontiguousarray(palette[inverse.reshape(labels.shape)])
        height, width = labels.shape
        image = QImage(rgb.data, width, height, 3 * width, QImage.Format.Format_RGB888)
        return image.copy()

    # ----------------------------------------------------------- layout
    def _areas(self):
        height = self.height() - 2 * GAP
        strip = QRectF(self.width() - STRIP_WIDTH - GAP, GAP, STRIP_WIDTH, height)
        plane = QRectF(GAP, GAP, max(10.0, strip.left() - 2 * GAP), height)
        return plane, strip

    def _plane_rect(self, area):
        """Where the plane image goes in ``area``, keeping its proportions."""
        top, bottom, left, right = self._plane[1]
        scale = min(area.width() / (right - left), area.height() / (bottom - top))
        width, height = (right - left) * scale, (bottom - top) * scale
        return QRectF(area.left() + (area.width() - width) / 2,
                      area.top() + (area.height() - height) / 2, width, height), scale

    # ------------------------------------------------------------ paint
    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(10, 10, 14))
        readout = self.readout
        plane_area, strip = self._areas()
        if readout is None or readout.get("entry_um") is None or self._plane is None:
            painter.setPen(QColor(170, 170, 170))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "The probe does not meet the brain.")
            return
        self._paint_plane(painter, plane_area)
        self._paint_strip(painter, strip)

    def _paint_plane(self, painter, area):
        rect, scale = self._plane_rect(area)
        painter.drawImage(rect, self._image)
        top, _bottom, left, _right = self._plane[1]
        depth = float(self.readout["depth_um"])

        def point(across, along):
            return QPointF(rect.left() + (across - left) * scale,
                           rect.top() + (along - top) * scale)

        colour = QColor(*self.engine.plan_colours.get(self.plan.probe, (232, 72, 85)))
        kind = getattr(self.plan, "kind", "probe")
        if kind != "probe":
            # A fiber's or prism's outline in this plane (the prism's: its
            # imaging face, which the plane contains).
            specs = self.plan.specs
            half = specs["diameter_um"] / 2.0 if kind == "fiber" else specs["width_um"] / 2.0
            upper = top if kind == "fiber" else max(top, depth - specs["length_um"])
            fill = QColor(colour)
            fill.setAlpha(40)
            painter.setPen(QPen(colour, 1, Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawRect(QRectF(point(-half, upper), point(half, depth)))
            window = self.readout.get("imaging_window_um")
            if kind == "prism" and window and window[1] > 0:
                # The imaging window: the face's bottom, as high as the bevel
                # reflects (1.5 x 1.5 mm for the default prism).
                fill.setAlpha(110)
                painter.setPen(QPen(colour, 2))
                painter.setBrush(fill)
                painter.drawRect(QRectF(point(-half, depth - window[1]), point(half, depth)))
                painter.setPen(QColor(255, 255, 255))
                painter.setFont(QFont(painter.font().family(), 8))
                painter.drawText(point(-half, depth - window[1]) + QPointF(3, 11),
                                 "{:.1f} × {:.1f} mm".format(window[0] / 1000.0,
                                                             window[1] / 1000.0))
        for offset in (self.plan.shank_offsets_um or [0.0]) if kind == "probe" else [0.0]:
            painter.setPen(QPen(QColor(255, 255, 255), 4))
            painter.drawLine(point(offset, top), point(offset, depth))
            painter.setPen(QPen(colour, 2))
            painter.drawLine(point(offset, top), point(offset, depth))
        painter.setPen(QPen(colour, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(point(0.0, 0.0), 5, 5)
        painter.setBrush(colour)
        painter.drawEllipse(point(0.0, depth), 4, 4)
        window = self.readout.get("window_um")
        if window:
            painter.setPen(QPen(QColor(255, 220, 90), 2))
            x = max(self.plan.shank_offsets_um or [0.0]) + 120.0
            painter.drawLine(point(x, max(window[0], top)), point(x, window[1]))
        painter.setPen(QColor(200, 200, 200))
        painter.setFont(QFont(painter.font().family(), 8))
        painter.drawText(QRectF(rect.left() + 4, rect.top() + 2, rect.width() - 8, 14),
                         Qt.AlignmentFlag.AlignLeft,
                         {"fiber": "fiber plane", "prism": "imaging face plane"}.get(
                             kind, "probe plane"))
        bar = 500.0 * scale
        painter.drawLine(QPointF(rect.right() - 6 - bar, rect.bottom() - 8),
                         QPointF(rect.right() - 6, rect.bottom() - 8))
        painter.drawText(QRectF(rect.right() - 6 - bar - 40, rect.bottom() - 24, bar + 40, 14),
                         Qt.AlignmentFlag.AlignRight, "0.5 mm")

    def _strip_y(self, strip, depth_um):
        depth = max(float(self.readout["depth_um"]), 1.0)
        return strip.top() + depth_um / depth * strip.height()

    def _paint_strip(self, painter, strip):
        font = QFont(painter.font().family(), 8)
        painter.setFont(font)
        bar = QRectF(strip.left(), strip.top(), 18, strip.height())
        for run in self.readout["regions"]:
            y0, y1 = self._strip_y(strip, run["start_um"]), self._strip_y(strip, run["end_um"])
            painter.fillRect(QRectF(bar.left(), y0, bar.width(), max(1.0, y1 - y0)),
                             QColor(*run["colour"]) if run["id"] else QColor(40, 40, 44))
            if y1 - y0 >= 11 and run["id"]:
                painter.setPen(QColor(220, 220, 220))
                painter.drawText(QRectF(bar.right() + 26, y0, strip.width() - 44, y1 - y0),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                 run["acronym"])
        painter.setPen(QPen(QColor(235, 235, 235), 1))
        for depth in self.readout.get("contacts_um") or []:
            y = self._strip_y(strip, depth)
            painter.drawLine(QPointF(bar.right() + 1, y), QPointF(bar.right() + 6, y))
        window = self.readout.get("window_um")
        if window:
            y0 = self._strip_y(strip, max(window[0], 0.0))
            y1 = self._strip_y(strip, window[1])
            painter.setPen(QPen(QColor(255, 220, 90), 2))
            x = bar.right() + 12
            painter.drawLine(QPointF(x, y0), QPointF(x, y1))
            painter.drawLine(QPointF(x - 3, y0), QPointF(x + 3, y0))
            painter.drawLine(QPointF(x - 3, y1), QPointF(x + 3, y1))
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(QRectF(bar.left(), strip.top() - 2, strip.width(), 12),
                         Qt.AlignmentFlag.AlignRight, "entry")
        painter.drawText(QRectF(bar.left(), strip.bottom() - 10, strip.width(), 12),
                         Qt.AlignmentFlag.AlignRight,
                         "{:.2f} mm".format(float(self.readout["depth_um"]) / 1000.0))

    # ------------------------------------------------------------ hover
    def describe(self, x, y):
        """What lies under (x, y): a short text, or None."""
        readout = self.readout
        if readout is None or readout.get("entry_um") is None or self._plane is None:
            return None
        plane_area, strip = self._areas()
        if strip.contains(QPointF(x, y)):
            depth = (y - strip.top()) / strip.height() * float(readout["depth_um"])
            for run in readout["regions"]:
                if run["start_um"] <= depth <= run["end_um"]:
                    return "{} ({}) · {:.2f} mm deep".format(run["name"], run["acronym"],
                                                            depth / 1000.0)
            return None
        rect, scale = self._plane_rect(plane_area)
        if not rect.contains(QPointF(x, y)):
            return None
        labels, (top, _bottom, left, _right) = self._plane
        along = top + (y - rect.top()) / scale
        across = left + (x - rect.left()) / scale
        row = min(labels.shape[0] - 1, int((y - rect.top()) / rect.height() * labels.shape[0]))
        col = min(labels.shape[1] - 1, int((x - rect.left()) / rect.width() * labels.shape[1]))
        acronym, name, _colour = self.engine.plan_atlas().name(labels[row, col])
        return "{} ({}) · {:.2f} mm along the probe, {:+.2f} mm across".format(
            name, acronym, along / 1000.0, across / 1000.0)

    def mouseMoveEvent(self, event):
        text = self.describe(event.position().x(), event.position().y())
        if text:
            QToolTip.showText(event.globalPosition().toPoint(), text, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)
