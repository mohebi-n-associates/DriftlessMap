"""Design tokens and the Qt stylesheet of the V2 interface.

The tokens are the single source of colour, type size and spacing; the
stylesheet and custom-drawn widgets read them. Themes never change how images
are rendered: channel colours, LUTs and scientific rendering modes stay with
the image views.
"""

TOKENS = {
    "dark": {
        "bg": "#15171b",
        "surface": "#1d2026",
        "surface_alt": "#252930",
        "raised": "#2d323b",
        "border": "#353b46",
        "text": "#e7e9ec",
        "muted": "#9aa2ad",
        "accent": "#5b93ff",
        "accent_text": "#0b1220",
        "accent_soft": "#23324d",
        "success": "#3fb97a",
        "warning": "#e0a33a",
        "error": "#ef6a62",
        "canvas": "#0d0e10",
    },
    "light": {
        "bg": "#f3f4f6",
        "surface": "#ffffff",
        "surface_alt": "#f0f2f5",
        "raised": "#e7eaef",
        "border": "#d4d9e1",
        "text": "#1a1e23",
        "muted": "#5b6470",
        "accent": "#2f6fe4",
        "accent_text": "#ffffff",
        "accent_soft": "#dde8fb",
        "success": "#1f8a55",
        "warning": "#a86b00",
        "error": "#c9362d",
        "canvas": "#0d0e10",
    },
}

TYPE_SCALE = {"small": 11, "body": 13, "label": 12, "title": 15, "heading": 18}
SPACING = 4  # base grid in logical pixels
RADIUS = 8


def colour(theme, name):
    return TOKENS[theme][name]


def stylesheet(theme="dark"):
    t = TOKENS[theme]
    s = TYPE_SCALE
    return """
QMainWindow, QDialog {{ background: {bg}; }}
QWidget {{ color: {text}; font-size: {body}px; }}
QWidget#V2Root, QWidget#TaskColumn, QWidget#InspectorColumn {{ background: {bg}; }}
QFrame#Card {{
    background: {surface}; border: 1px solid {border}; border-radius: {radius}px;
}}
QLabel#CardTitle {{ font-size: {title}px; font-weight: 600; }}
QLabel#StepTitle {{ font-size: {heading}px; font-weight: 600; }}
QLabel#Muted, QLabel#Hint {{ color: {muted}; font-size: {label}px; }}
QLabel#StatusGood {{ color: {success}; font-weight: 600; }}
QLabel#StatusWarn {{ color: {warning}; font-weight: 600; }}
QLabel#StatusBad {{ color: {error}; font-weight: 600; }}
QLabel#Badge {{
    background: {raised}; border-radius: 9px; padding: 2px 8px; font-size: {label}px;
}}

QPushButton, QToolButton {{
    background: {raised}; border: 1px solid {border}; border-radius: 6px;
    padding: 5px 10px; color: {text};
}}
QPushButton:hover, QToolButton:hover {{ border-color: {accent}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {accent_soft}; }}
QPushButton:checked, QToolButton:checked {{
    background: {accent_soft}; border-color: {accent}; color: {text};
}}
QPushButton:disabled, QToolButton:disabled {{ color: {muted}; border-color: {surface_alt}; }}
QPushButton[primary="true"] {{
    background: {accent}; border-color: {accent}; color: {accent_text}; font-weight: 600;
}}
QPushButton[primary="true"]:disabled {{ background: {raised}; color: {muted}; }}

QToolButton#RailButton {{
    background: transparent; border: none; border-radius: 6px; padding: 8px 10px;
    text-align: left; color: {muted};
}}
QToolButton#RailButton:hover {{ background: {surface_alt}; color: {text}; }}
QToolButton#RailButton:checked {{ background: {accent_soft}; color: {text}; }}
QFrame#Rail {{ background: {surface}; border-right: 1px solid {border}; }}

QToolButton#Segment {{ border-radius: 0; padding: 5px 12px; }}
QToolButton#Segment:checked {{ background: {accent}; color: {accent_text}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {surface_alt}; border: 1px solid {border}; border-radius: 5px;
    padding: 3px 6px; selection-background-color: {accent};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {accent};
}}
QComboBox QAbstractItemView {{ background: {surface}; border: 1px solid {border}; }}

QTableWidget, QListWidget, QTreeView, QTreeWidget {{
    background: {surface}; border: 1px solid {border}; border-radius: 6px;
    gridline-color: {border}; alternate-background-color: {surface_alt};
}}
QHeaderView::section {{
    background: {surface_alt}; color: {muted}; border: none;
    border-bottom: 1px solid {border}; padding: 4px 6px; font-size: {label}px;
}}
QTableWidget::item:selected, QListWidget::item:selected {{
    background: {accent_soft}; color: {text};
}}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 6px 12px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {text}; border-bottom-color: {accent}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {raised}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

QSlider::groove:horizontal {{ height: 4px; background: {raised}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {accent}; width: 14px; margin: -6px 0; border-radius: 7px;
}}

QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}

QMenu {{ background: {surface}; border: 1px solid {border}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {accent_soft}; }}
QMenuBar {{ background: {surface}; }}
QMenuBar::item:selected {{ background: {accent_soft}; }}

QFrame#StatusLine {{ background: {surface}; border-top: 1px solid {border}; }}
QFrame#CanvasHeader {{ background: {surface}; border-bottom: 1px solid {border}; }}
QFrame#ToolOptions {{ background: {surface_alt}; border-bottom: 1px solid {border}; }}
QWidget#Canvas {{ background: {canvas}; }}
QSplitter::handle {{ background: {border}; }}
QToolTip {{
    background: {surface}; color: {text}; border: 1px solid {border}; padding: 4px;
}}
""".format(radius=RADIUS, small=s["small"], body=s["body"], label=s["label"],
           title=s["title"], heading=s["heading"], **t)
