"""Theme the 1.x widgets that the V2 shell adopts.

The 1.x widgets carry dark inline stylesheets and white icons. In the V2
window they are restyled from the theme tokens, and the white pixels of their
icons are recoloured to the theme's text colour so the icons stay visible on
light backgrounds. Coloured icon pixels are kept. The engine is hidden in V2,
so these widgets are only ever shown in the V2 window.
"""

import numpy as np
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QAbstractButton, QGroupBox, QLabel

from .theme import TOKENS

# Pixels whose channels are all at least this bright count as "white".
WHITE_LEVEL = 200
ICON_SIZE = QSize(64, 64)


def recolour_white(pixmap, colour):
    """Return ``pixmap`` with its near-white pixels painted ``colour``."""
    if pixmap is None or pixmap.isNull():
        return pixmap
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()
    pointer = image.bits()
    pointer.setsize(image.sizeInBytes())
    pixels = np.frombuffer(pointer, np.uint8).reshape(height, image.bytesPerLine() // 4, 4)
    pixels = pixels[:, :width]
    # ARGB32 is stored as B, G, R, A in memory on little-endian machines.
    white = np.all(pixels[..., :3] >= WHITE_LEVEL, axis=-1) & (pixels[..., 3] > 0)
    target = QColor(colour)
    pixels[white, 0] = target.blue()
    pixels[white, 1] = target.green()
    pixels[white, 2] = target.red()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    return result


def recolour_icon(icon, colour):
    result = QIcon()
    for state in (QIcon.State.Off, QIcon.State.On):
        pixmap = icon.pixmap(ICON_SIZE, QIcon.Mode.Normal, state)
        result.addPixmap(recolour_white(pixmap, colour), QIcon.Mode.Normal, state)
    return result


def _recolour_widget_icons(root, colour):
    for widget in root.findChildren(QAbstractButton):
        original = getattr(widget, "_v2_original_icon", None)
        if original is None:
            if widget.icon().isNull():
                continue
            original = widget._v2_original_icon = QIcon(widget.icon())
        widget.setIcon(recolour_icon(original, colour))
    for label in root.findChildren(QLabel):
        original = getattr(label, "_v2_original_pixmap", None)
        if original is None:
            pixmap = label.pixmap()
            if pixmap is None or pixmap.isNull():
                continue
            original = label._v2_original_pixmap = QPixmap(pixmap)
        label.setPixmap(recolour_white(original, colour))


def toolbar_stylesheet(t):
    return """
QToolBar {{ background: transparent; border: none; spacing: 4px; }}
QToolBar::separator {{ background: {border}; width: 1px; margin: 6px 4px; }}
QLabel {{ color: {text}; background: transparent; }}
QPushButton {{
    background: transparent; border: 1px solid transparent; border-radius: 5px;
    min-width: 28px; min-height: 28px; padding: 0px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:checked {{ background: {accent_soft}; border-color: {accent}; }}
""".format(**t)


def label_tree_stylesheet(t):
    return """
QTreeWidget, QTreeView {{
    background: {surface}; color: {text}; border: 1px solid {border}; border-radius: 6px;
    selection-background-color: {accent_soft}; selection-color: {text};
}}
QTreeWidget::item {{ color: {text}; min-height: 20px; }}
QTreeWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
""".format(**t)


def group_box_stylesheet(t):
    return """
QGroupBox {{
    background: transparent; border: 1px solid {border}; border-radius: 6px;
    padding: 5px; margin-top: 20px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding-left: 10px; padding-right: 3px; padding-top: 10px; color: {text};
}}
""".format(**t)


def restyle(engine, theme):
    """Restyle the adopted 1.x widgets of ``engine`` for ``theme``."""
    t = TOKENS[theme]
    toolbar = engine.toolbar
    toolbar.setStyleSheet(toolbar_stylesheet(t))
    _recolour_widget_icons(toolbar, t["text"])

    tree = engine.atlas_view.label_tree
    tree.setStyleSheet(label_tree_stylesheet(t))
    tree.reset_btn.setStyleSheet("")

    view = engine.atlas_view
    for widget in (view.show_boundary_btn, view.navigation_btn, view.rotation_remain_btn):
        widget.setStyleSheet("")
    view.radio_group.setStyleSheet("")
    for radio in (view.section_rabnt1, view.section_rabnt2, view.section_rabnt3):
        radio.setStyleSheet("")
    for box in view.sidebar_wrap.findChildren(QGroupBox):
        box.setStyleSheet(group_box_stylesheet(t))
    _recolour_widget_icons(view.sidebar_wrap, t["text"])
