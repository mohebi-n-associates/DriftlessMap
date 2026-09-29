"""Section step: channels, brightness/contrast, registration input, orientation."""

import colorsys

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QRadioButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import registration_input
from ..registration_input import RegistrationInput
from . import channel_display as display
from .widgets import Card, Disclosure, StepPanel, button, grid_of, hint_label, set_status, status_label

PRESET_COLOURS = [
    ("Gray", (200, 200, 200)), ("Blue", (0, 90, 255)), ("Green", (0, 255, 0)),
    ("Red", (255, 0, 0)), ("Cyan", (0, 255, 255)), ("Magenta", (255, 0, 255)),
    ("Yellow", (255, 255, 0)), ("Orange", (255, 128, 0)),
]


def _hsv(rgb):
    h, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    return (h, s, v)


def _rgb(hsv):
    if hsv is None:
        return (128, 128, 128)
    r, g, b = colorsys.hsv_to_rgb(*hsv)
    return (int(r * 255), int(g * 255), int(b * 255))


class InputPreview(QDialog):
    """Shows the analysis plane that automatic registration will use."""

    def __init__(self, plane, description, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registration input: " + description)
        layout = QVBoxLayout(self)
        array = np.asarray(plane, dtype=np.float32)
        if array.ndim == 3:
            array = array[..., :3].mean(axis=2)
        low, high = float(array.min()), float(array.max())
        array = ((array - low) / (high - low) * 255 if high > low else array * 0).astype(np.uint8)
        array = np.ascontiguousarray(array)
        image = QImage(array.data, array.shape[1], array.shape[0], array.shape[1],
                       QImage.Format.Format_Grayscale8).copy()
        label = QLabel()
        label.setPixmap(QPixmap.fromImage(image).scaled(
            720, 520, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(label)
        layout.addWidget(hint_label(
            "This grayscale plane is what Find atlas section and Suggest landmarks "
            "use. Display colours, brightness and visibility are not part of it."))


class SectionPanel(StepPanel):
    title = "Section"
    hint = ("Adjust how the channels look, choose which channels registration uses, "
            "and orient the image. Display changes never alter the pixel values.")

    def build(self):
        engine, view = self.engine, self.engine.image_view
        self._channel_key = None
        self._rows = []
        self._headers = []
        self._last_channels = None   # restored when leaving Legacy mode
        self._selected = 0
        self._updating = False

        self.image_card = self.add(Card("Image"))
        self.image_summary = self.image_card.add(hint_label(""))
        # Scene and read-scale controls of the image view (CZI, multi-series TIFF).
        self.image_card.add(view.check_scenes)
        self.image_card.add(view.scale_wrap)
        self.image_card.add(view.scene_wrap)
        self.page_note = self.image_card.add(hint_label(""))

        self.channel_card = self.add(Card(
            "Channels", "Show: visible on screen. Register: used by automatic "
            "registration. Select a row to adjust its brightness and contrast."))
        self.channel_grid_host = QWidget()
        self.channel_grid = QGridLayout(self.channel_grid_host)
        self.channel_grid.setContentsMargins(0, 0, 0, 0)
        self.channel_grid.setHorizontalSpacing(6)
        self.channel_card.add(self.channel_grid_host)
        self.empty_note = self.channel_card.add(hint_label("Load a section to see its channels."))
        self.select_group = QButtonGroup(self)
        self.select_group.idClicked.connect(self._select)

        # Brightness and contrast of the selected channel.
        adjust = QWidget()
        grid = QGridLayout(adjust)
        grid.setContentsMargins(0, 4, 0, 0)
        self.adjust_title = QLabel("")
        grid.addWidget(self.adjust_title, 0, 0, 1, 4)
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.contrast = QSlider(Qt.Orientation.Horizontal)
        for slider in (self.brightness, self.contrast):
            slider.setRange(0, 1000)
            slider.valueChanged.connect(self._bc_changed)
        grid.addWidget(QLabel("Brightness"), 1, 0)
        grid.addWidget(self.brightness, 1, 1, 1, 3)
        grid.addWidget(QLabel("Contrast"), 2, 0)
        grid.addWidget(self.contrast, 2, 1, 1, 3)
        self.black = QSpinBox()
        self.white = QSpinBox()
        for box in (self.black, self.white):
            box.setRange(0, 65535)
            box.setKeyboardTracking(False)
            box.valueChanged.connect(self._range_changed)
        self.gamma = QDoubleSpinBox()
        self.gamma.setRange(0.01, 16.0)
        self.gamma.setSingleStep(0.05)
        self.gamma.setKeyboardTracking(False)
        self.gamma.valueChanged.connect(self._range_changed)
        grid.addWidget(QLabel("Min"), 3, 0)
        grid.addWidget(self.black, 3, 1)
        grid.addWidget(QLabel("Max"), 3, 2)
        grid.addWidget(self.white, 3, 3)
        grid.addWidget(QLabel("Gamma"), 4, 0)
        grid.addWidget(self.gamma, 4, 1)
        self.auto_note = hint_label("")
        grid.addWidget(self.auto_note, 5, 0, 1, 4)
        self.adjust = adjust
        self.channel_card.add(adjust)
        self.channel_card.add_row(
            button("Auto", self._auto, tooltip="Saturate 0.35% of samples, as ImageJ Auto"),
            button("Reset", self._reset, tooltip="Full data range, gamma 1"),
            button("Auto all", self._auto_all), None)
        self.channel_card.add(Disclosure("Curve editor and histogram", view.curve_widget))

        self.reg_card = self.add(Card(
            "Registration input",
            "Find atlas section and Suggest landmarks use only these channels."))
        self.reg_mode = QComboBox()
        self.reg_mode.addItems(["Channels ticked under Register",
                                "Legacy: all channels, as DriftlessMap 1.6"])
        self.reg_mode.currentIndexChanged.connect(self._reg_mode_changed)
        self.reg_card.add(self.reg_mode)
        self.reg_status = self.reg_card.add(status_label(""))
        self.reg_card.add_row(button("Preview input…", self._preview_input), None)

        orient = self.add(Card("Orientation", "Rotations and flips apply to every channel."))
        orient.add(grid_of([
            button("Rotate 90° left", engine.action90_Counter_Clockwise.trigger),
            button("Rotate 90° right", engine.action90_Clockwise.trigger),
            button("Rotate 1° left", engine.action1_Counter_Clockwise.trigger),
            button("Rotate 1° right", engine.action1_Clockwise.trigger),
            button("Rotate 180°", engine.action180.trigger),
            button("Flip horizontally", engine.actionFlip_Horizontal.trigger),
            button("Flip vertically", engine.actionFlip_Vertical.trigger),
        ], columns=2))

        clean = self.add(Card(
            "Crop and clean up",
            "Crop: draw a closed lasso around the tissue, then Crop to lasso. "
            "Make cleaned copy creates an editable copy for background removal."))
        self.lasso_button = button("Lasso", lambda: self.shell.toggle_tool("lasso"),
                                   checkable=True)
        clean.add(grid_of([
            self.lasso_button,
            button("Crop to lasso", engine.actionCut.trigger),
            button("Make cleaned copy", engine.actionProcess_Image.trigger),
            button("Reset image", engine.actionReset_Image.trigger),
        ], columns=2))

    # ---------------------------------------------------------------- rows
    def _rebuild_rows(self):
        view = self.engine.image_view
        for widget in [w for row in self._rows for w in row.values()] + self._headers:
            self.channel_grid.removeWidget(widget)
            widget.deleteLater()
        self._rows = []
        self._headers = []
        for button_ in list(self.select_group.buttons()):
            self.select_group.removeButton(button_)
        count = display.channel_count(view)
        self.empty_note.setVisible(count == 0)
        self.adjust.setVisible(count > 0)
        if count == 0:
            return
        names = list(getattr(view.image_file, "channel_name", []) or [])
        names += ["Channel {}".format(i + 1) for i in range(len(names), count)]
        for column, text in enumerate(("", "Name", "Colour", "Show", "Register", "Range")):
            header = QLabel(text)
            header.setObjectName("Muted")
            self.channel_grid.addWidget(header, 0, column)
            self._headers.append(header)
        for index in range(count):
            row = {}
            select = QRadioButton()
            select.setToolTip("Adjust this channel")
            self.select_group.addButton(select, index)
            name = QLineEdit(names[index])
            name.setToolTip("Display name; the original channel index is kept")
            name.editingFinished.connect(lambda i=index, w=name: self._rename(i, w.text()))
            swatch = QToolButton()
            swatch.setFixedWidth(34)
            swatch.setToolTip("Channel colour")
            menu = QMenu(swatch)
            for label, rgb in PRESET_COLOURS:
                menu.addAction(label, lambda i=index, c=rgb: self._set_colour(i, c))
            menu.addSeparator()
            menu.addAction("Custom…", lambda i=index: self._pick_colour(i))
            swatch.setMenu(menu)
            swatch.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            show = QCheckBox()
            show.toggled.connect(lambda checked, i=index: self._show(i, checked))
            register = QCheckBox()
            register.toggled.connect(lambda _checked: self._register_changed())
            span = QLabel("")
            span.setObjectName("Muted")
            for column, widget in enumerate((select, name, swatch, show, register, span)):
                self.channel_grid.addWidget(widget, index + 1, column)
            row.update(select=select, name=name, swatch=swatch, show=show,
                       register=register, span=span)
            self._rows.append(row)
        self._selected = min(self._selected, count - 1)
        self.select_group.button(self._selected).setChecked(True)
        self._sync_rows()
        self._sync_adjust()

    def _channel_rows(self):
        return self._rows

    def _sync_rows(self):
        view = self.engine.image_view
        recipe = self.engine.registration_input
        self._updating = True
        for index, row in enumerate(self._channel_rows()):
            row["show"].setChecked(bool(view.channel_visible[index]))
            rgb = _rgb(view.channel_color[index])
            row["swatch"].setStyleSheet(
                "QToolButton {{ background: rgb({},{},{}); border-radius: 4px; }}".format(*rgb))
            row["register"].setChecked(bool(recipe is not None and recipe.mode == "channels"
                                            and index in recipe.channels))
            row["register"].setEnabled(recipe is None or recipe.mode == "channels")
            black, white, gamma = display.channel_levels(view, index)
            row["span"].setText("{:.0f} – {:.0f}{}".format(
                black, white, "" if abs(gamma - 1) < 1e-6 else "  γ {:.2f}".format(gamma)))
        self.reg_mode.blockSignals(True)
        self.reg_mode.setCurrentIndex(1 if recipe is not None and recipe.mode == "legacy" else 0)
        self.reg_mode.blockSignals(False)
        self._updating = False

    def _sync_adjust(self):
        view = self.engine.image_view
        if display.channel_count(view) == 0:
            return
        index = self._selected
        limit = display.intensity_limit(view)
        black, white, gamma = display.channel_levels(view, index)
        brightness, contrast = display.brightness_contrast(black, white, limit)
        names = [row["name"].text() for row in self._channel_rows()]
        self.adjust_title.setText("Adjusting: {}  (0 – {})".format(names[index], limit))
        self._updating = True
        for box in (self.black, self.white):
            box.setMaximum(limit)
        self.black.setValue(int(round(black)))
        self.white.setValue(int(round(white)))
        self.gamma.setValue(gamma)
        self.brightness.setValue(int(round(brightness * 10)))
        self.contrast.setValue(int(round(contrast * 10)))
        self._updating = False

    # ------------------------------------------------------------- actions
    def _select(self, index):
        self._selected = index
        self._sync_adjust()

    def _apply(self, black, white, gamma=None):
        view = self.engine.image_view
        display.set_channel_levels(view, self._selected, black, white, gamma)
        self._sync_rows()
        self._sync_adjust()

    def _bc_changed(self, _value):
        if self._updating:
            return
        limit = display.intensity_limit(self.engine.image_view)
        black, white = display.window_from_brightness_contrast(
            self.brightness.value() / 10.0, self.contrast.value() / 10.0, limit)
        self._apply(black, white)

    def _range_changed(self, _value):
        if self._updating:
            return
        self._apply(self.black.value(), self.white.value(), self.gamma.value())

    def _auto(self):
        view = self.engine.image_view
        if display.channel_count(view) == 0:
            return
        low, high = display.auto_levels(view, self._selected)
        self._apply(low, high)
        self.auto_note.setText("Auto: {:.0f} – {:.0f}, saturating {}% of samples. Pixel "
                               "values are unchanged.".format(low, high, display.AUTO_SATURATION))

    def _auto_all(self):
        view = self.engine.image_view
        current = self._selected
        for index in range(display.channel_count(view)):
            self._selected = index
            low, high = display.auto_levels(view, index)
            display.set_channel_levels(view, index, low, high)
        self._selected = current
        self._sync_rows()
        self._sync_adjust()

    def _reset(self):
        view = self.engine.image_view
        if display.channel_count(view) == 0:
            return
        low, high, gamma = display.reset_levels(view, self._selected)
        self._apply(low, high, gamma)
        self.auto_note.setText("")

    def _show(self, index, checked):
        if self._updating:
            return
        view = self.engine.image_view
        view.set_channel_visible(checked, index)
        # The 1.x selector keeps the last visible channel on; mirror its state.
        actual = bool(view.channel_visible[index])
        selector = view.chn_widget_list[index]
        selector.vis_btn.setChecked(not actual)
        selector.set_checked(not actual)
        if actual != checked:
            self.shell.message("At least one channel stays visible.", "warn")
        self._sync_rows()

    def _set_colour(self, index, rgb):
        self.engine.image_view.channel_color_changed(_hsv(rgb), index)
        self._sync_rows()

    def _pick_colour(self, index):
        colour = QColorDialog.getColor(QColor(*_rgb(self.engine.image_view.channel_color[index])),
                                       self, "Channel colour")
        if colour.isValid():
            self._set_colour(index, (colour.red(), colour.green(), colour.blue()))

    def _rename(self, index, text):
        view = self.engine.image_view
        text = text.strip() or "Channel {}".format(index + 1)
        names = list(view.image_file.channel_name)
        names += ["Channel {}".format(i + 1) for i in range(len(names), index + 1)]
        names[index] = text
        view.image_file.channel_name = names
        view.chn_widget_list[index].vis_btn.setText(text)
        recipe = self.engine.registration_input
        if recipe is not None and recipe.mode == "channels" and index in recipe.channels:
            self._register_changed()
        self._sync_adjust()

    def _register_changed(self):
        if self._updating:
            return
        chosen = [i for i, row in enumerate(self._channel_rows()) if row["register"].isChecked()]
        names = [self._channel_rows()[i]["name"].text() for i in chosen]
        self.engine.registration_input = (
            RegistrationInput.from_channels(chosen, names) if chosen else None)
        self._last_channels = self.engine.registration_input
        self.refresh_registration()

    def _reg_mode_changed(self, index):
        if self._updating:
            return
        if index == 1:
            current = self.engine.registration_input
            if current is not None and current.mode == "channels":
                self._last_channels = current
            self.engine.registration_input = RegistrationInput.legacy()
        else:
            self.engine.registration_input = self._last_channels
        self._sync_rows()
        self.refresh_registration()

    def _preview_input(self):
        engine = self.engine
        if engine.image_view.current_img is None:
            self.shell.message("Load a section first.", "warn")
            return
        section = engine.registration_section()
        if section is None:
            return
        InputPreview(section, engine.registration_input.describe(), self).exec()

    # -------------------------------------------------------------- refresh
    def refresh_registration(self):
        recipe = self.engine.registration_input
        if self.engine.image_view.current_img is None:
            set_status(self.reg_status, "No section loaded.", None)
        elif recipe is None:
            set_status(self.reg_status, "Not chosen: tick the channels to register on "
                       "(for example DAPI).", "warn")
        else:
            names, _ = self.engine._histology_channels()
            try:
                registration_input.check(recipe, len(names))
                set_status(self.reg_status, "Uses: " + recipe.describe(), "good")
            except ValueError as exc:
                set_status(self.reg_status, str(exc), "bad")

    def refresh(self):
        view = self.engine.image_view
        key = (id(view.image_file), display.channel_count(view),
               tuple(getattr(view.image_file, "channel_name", []) or []))
        if key != self._channel_key:
            self._channel_key = key
            self._rebuild_rows()
        elif self._rows and not self._updating:
            self._sync_rows()
        from . import state
        self.image_summary.setText(" · ".join(state.section_summary(self.engine)))
        view.check_scenes.setVisible(bool(getattr(view.image_file, "is_czi", False)))
        pages = getattr(view.image_file, "n_pages", 1) if view.image_file is not None else 1
        self.page_note.setVisible(pages > 1)
        if pages > 1:
            self.page_note.setText("Browse the {} {} planes with the slider under the image."
                                   .format(pages, getattr(view.image_file, "page_axis", None)
                                           or "page"))
        self.lasso_button.setChecked(
            self.engine.tool_box.checkable_btn_dict["lasso_btn"].isChecked())
        self.refresh_registration()
