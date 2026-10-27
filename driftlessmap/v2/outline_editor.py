"""Drawing and editing implant outlines on the section (V2 Annotate step).

The editor only draws: every outline and point it shows is read from, and
written straight back to, the engine's ``implant_outlines``, so undo, saving
and mapping always see what is on screen.

Modes:

* ``draw``: each click adds a vertex; clicking the first vertex again (or
  Finish) closes the outline, which then becomes editable (drag vertices,
  click an edge to add one).
* ``propose``: a click inside the track selects the connected region of
  similar brightness and turns it into an editable outline.
* ``point``: a click places the tip (fiber) or bottom-edge (prism) point.
"""

import cv2
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QObject, QPointF, Qt, pyqtSignal

# Brightness tolerance of Propose outline, as a fraction of the image range.
PROPOSE_TOLERANCE = 0.12
# Vertices kept by Propose outline, roughly (polygon simplification).
PROPOSE_VERTICES = 40
# Gaps in the tissue up to this fraction of the image size count as inside
# the brain (a track is narrower; the background around the brain is wider).
ENVELOPE_FRACTION = 0.04
MAX_REGION_FRACTION = 0.05


def _fill_holes(mask):
    """``mask`` with every region not connected to the image border filled."""
    padded = np.pad(mask, 1)
    outside = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
    cv2.floodFill(padded.copy(), outside, (0, 0), 1, 0, 0,
                  4 | cv2.FLOODFILL_MASK_ONLY | (1 << 8))
    return (outside[2:-2, 2:-2] == 0).astype(np.uint8)


def propose_outline(image, x, y, tolerance=PROPOSE_TOLERANCE):
    """Outline of the connected similar-brightness region around ``(x, y)``.

    Returns ``(N, 2)`` vertices in image coordinates (pixel centres), or None.
    """
    image = np.asarray(image)
    grey = image.astype(float).mean(axis=2) if image.ndim == 3 else image.astype(float)
    low, high = np.percentile(grey, (1, 99))
    if high <= low:
        return None
    grey = np.clip((grey - low) / (high - low) * 255.0, 0, 255).astype(np.uint8)
    grey = cv2.GaussianBlur(grey, (5, 5), 0)
    row, col = int(y), int(x)
    if not (0 <= row < grey.shape[0] and 0 <= col < grey.shape[1]):
        return None
    difference = int(round(tolerance * 255))
    seed = int(grey[row, col])
    similar = (np.abs(grey.astype(int) - seed) <= difference).astype(np.uint8)
    # A track opens onto the background at the brain surface, which is just as
    # bright: keep the fill inside the brain's envelope, the tissue closed
    # over gaps narrower than ``ENVELOPE_FRACTION`` of the image.
    tissue = (np.abs(grey.astype(int) - seed) > difference).astype(np.uint8)
    radius = max(3, int(ENVELOPE_FRACTION * max(grey.shape)))
    disk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    envelope = _fill_holes(cv2.morphologyEx(tissue, cv2.MORPH_CLOSE, disk))
    similar &= envelope
    similar = cv2.morphologyEx(similar, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    count, labels = cv2.connectedComponents(similar, connectivity=4)
    if count < 2 or labels[row, col] == 0:
        return None
    region = (labels == labels[row, col]).astype(np.uint8)
    # A region reaching the image edge or this large is not a track.
    if (region[0].any() or region[-1].any() or region[:, 0].any() or region[:, -1].any()
            or region.sum() > MAX_REGION_FRACTION * region.size):
        return None
    contours, _hierarchy = cv2.findContours(region, cv2.RETR_EXTERNAL,
                                            cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) < 9:
        return None
    epsilon = 0.5
    simplified = cv2.approxPolyDP(contour, epsilon, True)
    while len(simplified) > PROPOSE_VERTICES:
        epsilon *= 1.5
        simplified = cv2.approxPolyDP(contour, epsilon, True)
    if len(simplified) < 3:
        return None
    return simplified.reshape(-1, 2).astype(float) + 0.5


class OutlineEditor(QObject):
    """Shows the section's implant outlines and edits the selected one."""

    changed = pyqtSignal(str)       # a message for the user

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.vb = engine.image_view.img_stacks.vb
        self.mode = None
        self.implant_id = None
        self.vertices = []
        self._roi = None
        self._roi_points = None
        self._others = {}
        self.preview = pg.PlotDataItem(symbol="o", symbolSize=7, connect="all")
        self.preview.setZValue(20)
        self.preview.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.points = pg.ScatterPlotItem(symbol="star", size=16, pxMode=True)
        self.points.setZValue(21)
        self.points.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        for item in (self.preview, self.points):
            self.vb.addItem(item)
        engine.image_view.img_stacks.sig_mouse_clicked.connect(self._clicked)

    # ------------------------------------------------------------ helpers
    def _implant(self):
        return self.engine.implants.get(self.implant_id) if self.implant_id else None

    def _pen(self, colour, dashed=False, width=2):
        return pg.mkPen(*colour, width=width,
                        style=Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine)

    def _close_distance(self):
        size = self.vb.viewPixelSize()
        return 8 * max(abs(size[0]), abs(size[1]), 1e-6)

    # -------------------------------------------------------------- modes
    def set_mode(self, mode):
        """Start ``draw``, ``propose`` or ``point`` for the selected implant, or stop."""
        if mode is not None and self._implant() is None:
            self.changed.emit("Add or select a fiber or prism first.")
            return False
        if mode is None and self.mode == "draw" and len(self.vertices) >= 3:
            self.finish()
        self.mode = mode
        self.vertices = []
        self._show_preview()
        return True

    def finish(self):
        """Close the outline being drawn."""
        if self.mode != "draw":
            return
        if len(self.vertices) < 3:
            self.changed.emit("An outline needs at least three points.")
            return
        self._store(np.asarray(self.vertices))
        self.vertices = []
        self.mode = None
        self._show_preview()
        self.changed.emit("Outline closed. Drag its corners to adjust it, then map it.")

    def _store(self, points):
        try:
            self.engine.set_implant_outline(self.implant_id, points)
        except ValueError as exc:
            self.changed.emit(str(exc))
            return
        self.sync(force=True)

    def _clicked(self, pos):
        if self.mode is None or self._implant() is None:
            return
        x, y = float(pos[0]), float(pos[1])
        if self.mode == "point":
            self.engine.set_implant_point(self.implant_id, [x, y])
            self.mode = None
            self.sync(force=True)
            self.changed.emit("Point placed.")
        elif self.mode == "propose":
            image = self.engine.image_view.current_img
            outline = propose_outline(image, x, y) if image is not None else None
            if outline is None:
                self.changed.emit("No clearly bounded region there (the track may be as "
                                  "bright as the tissue around it). Click a brighter part of "
                                  "the track, or draw the outline.")
                return
            self.mode = None
            self._store(outline)
            self.changed.emit("Proposed an outline: check it, drag corners to correct it, "
                              "then map it.")
        elif self.mode == "draw":
            if len(self.vertices) >= 3 and np.hypot(
                    x - self.vertices[0][0], y - self.vertices[0][1]) <= self._close_distance():
                self.finish()
                return
            self.vertices.append([x, y])
            self._show_preview()

    # ------------------------------------------------------------ display
    def _show_preview(self):
        implant = self._implant()
        if not self.vertices or implant is None:
            self.preview.setData([], [])
            return
        points = np.asarray(self.vertices)
        self.preview.setData(points[:, 0], points[:, 1], pen=self._pen(implant.colour),
                             symbolBrush=pg.mkBrush(*implant.colour),
                             symbolPen=pg.mkPen(20, 20, 20))

    def select(self, implant_id):
        if implant_id != self.implant_id:
            self.set_mode(None)
            self.implant_id = implant_id
        self.sync(force=True)

    def sync(self, force=False):
        """Redraw from the engine's outlines (after undo, load or mapping)."""
        engine = self.engine
        outlines = engine.implant_outlines
        # Other implants' outlines: fixed, dashed in their colours.
        for implant_id in list(self._others):
            if implant_id == self.implant_id or implant_id not in outlines \
                    or engine.implants.get(implant_id) is None:
                self.vb.removeItem(self._others.pop(implant_id))
        for implant_id, entry in outlines.items():
            implant = engine.implants.get(implant_id)
            if implant is None or implant_id == self.implant_id or not entry["points"]:
                continue
            item = self._others.get(implant_id)
            if item is None:
                item = self._others[implant_id] = pg.PlotDataItem()
                item.setZValue(15)
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.vb.addItem(item)
            points = np.asarray(entry["points"] + entry["points"][:1])
            item.setData(points[:, 0], points[:, 1], pen=self._pen(implant.colour, dashed=True))

        # Marked points of every implant.
        spots = []
        for implant_id, entry in outlines.items():
            implant = engine.implants.get(implant_id)
            if implant is not None and entry.get("point") is not None:
                spots.append({"pos": entry["point"], "brush": pg.mkBrush(*implant.colour),
                              "pen": pg.mkPen(20, 20, 20)})
        self.points.setData(spots)

        # The selected implant's outline: editable.
        implant = self._implant()
        points = outlines.get(self.implant_id, {}).get("points") if implant else None
        key = None if not points else (tuple(map(tuple, points)), implant.colour)
        if not force and key == self._roi_points:
            return
        self._roi_points = key
        if self._roi is not None:
            self.vb.removeItem(self._roi)
            self._roi = None
        if key is None:
            return
        self._roi = pg.PolyLineROI([QPointF(*p) for p in points], closed=True,
                                   pen=self._pen(implant.colour, width=3))
        self._roi.setZValue(18)
        self._roi.sigRegionChangeFinished.connect(self._roi_edited)
        self.vb.addItem(self._roi)

    def _roi_edited(self):
        roi = self._roi
        if roi is None or self._implant() is None:
            return
        points = [roi.mapToParent(handle["item"].pos()) for handle in roi.handles]
        points = np.array([[p.x(), p.y()] for p in points])
        try:
            self.engine.set_implant_outline(self.implant_id, points)
        except ValueError as exc:
            self.changed.emit(str(exc))
            self.sync(force=True)
            return
        self._roi_points = (tuple(map(tuple, points.tolist())), self._implant().colour)

    def clear(self):
        """Clear the selected implant's outline and point on this section."""
        if self._implant() is None:
            return
        self.set_mode(None)
        self.engine.set_implant_outline(self.implant_id, None)
        self.engine.set_implant_point(self.implant_id, None)
        self.sync(force=True)
