"""Per-channel brightness above the histology image.

A compact strip at the top of the histology view: one brightness slider per
channel, in the channel's colour, plus Auto and Reset for all channels. It
writes the same per-channel display state as the Section step's controls
(:mod:`.channel_display`), so both stay in step and saving restores it.
Display only: pixel values and registration input are never touched.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import channel_display as display

# Width each channel needs in the strip; the strip puts as many channels in a
# row as fit (at most MAX_PER_ROW).
CHANNEL_WIDTH = 200
MAX_PER_ROW = 4


def slider_brightness(value):
    """Brightness (0-100, window centre) for a slider position (0-1000).

    The slider brightens to the right: further right moves the display window
    down, so more of the channel shows bright, as ImageJ's slider does.
    """
    return 100.0 - value / 10.0


def brightness_slider(brightness):
    return int(round((100.0 - brightness) * 10))


class ChannelStrip(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.engine = shell.engine
        self.setObjectName("ChannelStrip")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(2)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("Muted")
        self.toggle.setCheckable(True)
        self.toggle.setChecked(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow)
        self.toggle.setText("Brightness")
        self.toggle.setToolTip("Show or hide the per-channel brightness sliders")
        self.toggle.toggled.connect(self._expand)
        head.addWidget(self.toggle)
        head.addStretch(1)
        self.auto_button = QToolButton()
        self.auto_button.setText("Auto")
        self.auto_button.setToolTip("Set every channel's display range from its pixels "
                                    "(saturating {}%)".format(display.AUTO_SATURATION))
        self.auto_button.clicked.connect(self.auto_all)
        self.reset_button = QToolButton()
        self.reset_button.setText("Reset")
        self.reset_button.setToolTip("Show every channel over its full data range")
        self.reset_button.clicked.connect(self.reset_all)
        head.addWidget(self.auto_button)
        head.addWidget(self.reset_button)
        outer.addLayout(head)
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(2)
        outer.addWidget(self.body)
        self.rows = []          # [{"swatch", "name", "slider"}]
        self._per_row = None
        self._key = None
        self._updating = False
        self.setVisible(False)

    # ------------------------------------------------------------ building
    def _expand(self, shown):
        self.body.setVisible(shown)
        self.auto_button.setVisible(shown)
        self.reset_button.setVisible(shown)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)

    def _names(self, count):
        file = self.engine.image_view.image_file
        names = list(getattr(file, "channel_name", []) or [])
        return names[:count] + ["Channel {}".format(i + 1) for i in range(len(names), count)]

    def _rebuild(self, count):
        for row in self.rows:
            for widget in row.values():
                self.grid.removeWidget(widget)
                widget.deleteLater()
        self.rows = []
        names = self._names(count)
        for index in range(count):
            swatch = QLabel()
            swatch.setFixedSize(10, 10)
            name = QLabel(names[index])
            name.setObjectName("Muted")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1000)
            slider.setMinimumWidth(70)
            slider.setAccessibleName("{} brightness".format(names[index]))
            slider.setToolTip("{} brightness: right is brighter (display only)".format(
                names[index]))
            slider.valueChanged.connect(lambda value, i=index: self._moved(i, value))
            self.rows.append({"swatch": swatch, "name": name, "slider": slider})
        self._per_row = None
        self._place()

    def per_row(self):
        return max(1, min(MAX_PER_ROW, self.width() // CHANNEL_WIDTH))

    def _place(self):
        """Lay the channels out in rows that fit the view's width."""
        per_row = self.per_row()
        if per_row == self._per_row:
            return
        self._per_row = per_row
        for row in self.rows:
            for widget in row.values():
                self.grid.removeWidget(widget)
        for column in range(MAX_PER_ROW * 3):
            self.grid.setColumnStretch(column, 0)
        for index, row in enumerate(self.rows):
            line, column = divmod(index, per_row)
            self.grid.addWidget(row["swatch"], line, column * 3)
            self.grid.addWidget(row["name"], line, column * 3 + 1)
            self.grid.addWidget(row["slider"], line, column * 3 + 2)
            self.grid.setColumnStretch(column * 3 + 2, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.rows:
            self._place()

    # ------------------------------------------------------------ refresh
    def refresh(self):
        view = self.engine.image_view
        count = display.channel_count(view)
        self.setVisible(count > 0)
        if count == 0:
            self._key = None
            return
        key = (id(view.image_file), count, tuple(self._names(count)))
        if key != self._key:
            self._key = key
            self._rebuild(count)
        if self._updating:
            return
        from .section_panel import _rgb

        limit = display.intensity_limit(view)
        self._updating = True
        try:
            for index, row in enumerate(self.rows):
                black, white, _gamma = display.channel_levels(view, index)
                brightness, _contrast = display.brightness_contrast(black, white, limit)
                row["slider"].setValue(brightness_slider(brightness))
                rgb = _rgb(view.channel_color[index])
                row["swatch"].setStyleSheet(
                    "background: rgb({},{},{}); border-radius: 2px;".format(*rgb))
                visible = bool(view.channel_visible[index])
                row["name"].setEnabled(visible)
                row["slider"].setEnabled(visible)
        finally:
            self._updating = False

    def _changed(self):
        """Bring the Section step's controls and the rest of the shell in step."""
        section = self.shell.panels.get("section")
        if section is not None:
            section.refresh()
            if section._rows:
                section._sync_adjust()
        self.shell._dirty_check_pending = True
        self.refresh()

    # ------------------------------------------------------------- actions
    def _moved(self, index, value):
        if self._updating:
            return
        view = self.engine.image_view
        limit = display.intensity_limit(view)
        black, white, _gamma = display.channel_levels(view, index)
        _brightness, contrast = display.brightness_contrast(black, white, limit)
        black, white = display.window_from_brightness_contrast(
            slider_brightness(value), contrast, limit)
        self._updating = True
        try:
            display.set_channel_levels(view, index, black, white)
        finally:
            self._updating = False
        self._changed()

    def set_brightness(self, index, value):
        """Move channel ``index``'s slider to ``value`` (0-1000), as dragging does."""
        self.rows[index]["slider"].setValue(int(value))

    def auto_all(self):
        view = self.engine.image_view
        for index in range(display.channel_count(view)):
            low, high = display.auto_levels(view, index)
            display.set_channel_levels(view, index, low, high)
        self._changed()

    def reset_all(self):
        view = self.engine.image_view
        for index in range(display.channel_count(view)):
            display.set_channel_levels(view, index, *display.reset_levels(view, index))
        self._changed()
