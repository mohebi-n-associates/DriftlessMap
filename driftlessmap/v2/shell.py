"""The DriftlessMap V2 window.

The shell hosts the 1.x application object as a hidden *engine*: every
scientific operation, file format and dialog is the engine's own, so the new
interface cannot silently change results. The shell moves the engine's image
views, tool options and panels into a task-oriented layout, adds concrete
status, a command palette and a theme, and never keeps its own copy of
scientific state.
"""

import os

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..app import DriftlessMap
from ..interfaces import start_interface
from ..version import __version__
from . import adopted, state
from .annotate_panel import AnnotatePanel
from .commands import Command, CommandPalette, CommandRegistry
from .match_panel import MatchPanel
from .project_panel import ProjectPanel
from .register_panel import RegisterPanel
from .results_panel import ResultsPanel
from .section_panel import SectionPanel
from .theme import stylesheet
from .widgets import Card, button, hint_label

STEPS = (
    ("project", "Project", ProjectPanel),
    ("section", "Section", SectionPanel),
    ("match", "Match", MatchPanel),
    ("register", "Register", RegisterPanel),
    ("annotate", "Annotate", AnnotatePanel),
    ("results", "Results", ResultsPanel),
)
VIEWS = (
    ("compare", "Compare", "Atlas and section side by side"),
    ("atlas", "Atlas", "The atlas plane only"),
    ("section", "Section", "The section only"),
    ("3d", "3D", "The atlas in 3D with objects"),
    ("multi", "Multi-plane", "Coronal, sagittal, horizontal and 3D"),
)
PREVIEW_LABEL = "DriftlessMap 2.0 preview (development build of {})".format(__version__)


# Events after which the saved-state check runs at the next refresh.
EDIT_EVENTS = frozenset({QEvent.Type.MouseButtonRelease, QEvent.Type.KeyRelease,
                         QEvent.Type.Wheel, QEvent.Type.Drop, QEvent.Type.TouchEnd})


class V2Window(QMainWindow):
    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings or QSettings("Mohebi & Associates", "DriftlessMap-V2-preview")
        self.theme = self.settings.value("theme", "dark")
        self.setWindowTitle(PREVIEW_LABEL)
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)

        # The 1.x application is the engine; it stays hidden but alive, and is
        # a child of this window so its dialogs open over it.
        self.engine = DriftlessMap()
        self.engine.setParent(self, Qt.WindowType.Widget)
        self.engine.hide()
        self._wrap_engine_messages()

        engine = self.engine
        self.registry = CommandRegistry()
        self._saved_digest = None
        self._last_message_kind = None
        # The V2 atlas download dialog replaces the 1.x one in this window.
        engine.actionDownload_Allen_Mice_Atlas.triggered.disconnect()
        engine.actionDownload_Allen_Mice_Atlas.triggered.connect(self.download_allen_atlas)
        self._build_ui()
        self._register_commands()
        self._build_menus()
        self._build_shortcuts()
        self.apply_theme(self.theme)
        self.go_to("project")
        # Projects remember where the user left off and reopen there.
        engine.interface_state_provider = self.leave_state
        engine.on_project_loaded = self.resume

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(600)
        QApplication.instance().installEventFilter(self)
        self._dirty_check_pending = True
        self._dirty_status = False
        self.mark_saved()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        engine = self.engine
        root = QWidget()
        root.setObjectName("V2Root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        outer.addWidget(body, 1)

        # Task column: rail and the current step's panel.
        task = QWidget()
        task.setObjectName("TaskColumn")
        task_layout = QHBoxLayout(task)
        task_layout.setContentsMargins(0, 0, 0, 0)
        task_layout.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(158)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(8, 10, 8, 10)
        rail_layout.setSpacing(2)
        brand = QLabel("DriftlessMap")
        brand.setObjectName("CardTitle")
        rail_layout.addWidget(brand)
        preview = QLabel("2.0 preview")
        preview.setObjectName("Muted")
        rail_layout.addWidget(preview)
        rail_layout.addSpacing(10)
        self.rail_group = QButtonGroup(self)
        self.rail_buttons, self.rail_status, self.panels = {}, {}, {}
        self.stack = QStackedWidget()
        for number, (key, title, panel_class) in enumerate(STEPS, start=1):
            rail_button = QToolButton()
            rail_button.setObjectName("RailButton")
            rail_button.setText("{}  {}".format(number, title))
            rail_button.setCheckable(True)
            rail_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            rail_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            rail_button.setToolTip("{} (shortcut {})".format(title, number))
            rail_button.clicked.connect(lambda _checked, k=key: self.go_to(k))
            self.rail_group.addButton(rail_button)
            status = QLabel("")
            status.setObjectName("Muted")
            status.setWordWrap(True)
            status.setContentsMargins(12, 0, 4, 6)
            rail_layout.addWidget(rail_button)
            rail_layout.addWidget(status)
            self.rail_buttons[key] = rail_button
            self.rail_status[key] = status
            panel = panel_class(self)
            self.panels[key] = panel
            self.stack.addWidget(panel)
        rail_layout.addStretch(1)
        palette_hint = QLabel("Ctrl/Cmd+K\nsearch commands")
        palette_hint.setObjectName("Muted")
        rail_layout.addWidget(palette_hint)
        task_layout.addWidget(rail)
        self.stack.setMinimumWidth(410)
        task_layout.addWidget(self.stack, 1)
        body.addWidget(task)

        # Canvas: view switcher, tool options and the engine's image views.
        canvas = QWidget()
        canvas.setObjectName("Canvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("CanvasHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(0)
        self.view_group = QButtonGroup(self)
        self.view_buttons = {}
        for key, title, tip in VIEWS:
            view_button = QToolButton()
            view_button.setObjectName("Segment")
            view_button.setText(title)
            view_button.setToolTip(tip)
            view_button.setCheckable(True)
            view_button.clicked.connect(lambda _checked, k=key: self.set_view(k))
            self.view_group.addButton(view_button)
            self.view_buttons[key] = view_button
            header_layout.addWidget(view_button)
        header_layout.addSpacing(16)
        self.plane_label = QLabel("")
        self.plane_label.setObjectName("Muted")
        header_layout.addWidget(self.plane_label)
        header_layout.addStretch(1)
        canvas_layout.addWidget(header)

        self.tool_options = QFrame()
        self.tool_options.setObjectName("ToolOptions")
        options_layout = QHBoxLayout(self.tool_options)
        options_layout.setContentsMargins(10, 2, 10, 2)
        self.tool_label = QLabel("")
        self.tool_label.setObjectName("Muted")
        options_layout.addWidget(self.tool_label)
        toolbar = engine.toolbar
        engine.removeToolBar(toolbar)
        wraps = set(engine.toolbar_wrap_action_dict.values())
        for action in toolbar.actions():
            if action not in wraps:
                action.setVisible(False)
        toolbar.setParent(self.tool_options)
        toolbar.show()
        options_layout.addWidget(toolbar, 1)
        canvas_layout.addWidget(self.tool_options)

        views = engine.splitter_3
        views.setParent(canvas)
        canvas_layout.addWidget(views, 1)
        self.views = views
        self.empty_canvas = self._build_empty_canvas()
        canvas_layout.addWidget(self.empty_canvas, 1)
        body.addWidget(canvas)

        # Inspector column: objects, layers and atlas regions.
        inspector = QWidget()
        inspector.setObjectName("InspectorColumn")
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        self.inspector_tabs = QTabWidget()
        objects = QWidget()
        objects_layout = QVBoxLayout(objects)
        objects_layout.setContentsMargins(0, 6, 0, 0)
        self.objects_empty = hint_label(
            "No objects yet. Parts made in Annotate, built 3D objects and imported "
            "objects appear here.")
        objects_layout.addWidget(self.objects_empty, 0, Qt.AlignmentFlag.AlignTop)
        objects_layout.addWidget(engine.object_ctrl.outer_frame)
        self.inspector_tabs.addTab(objects, "Objects")
        layers = QWidget()
        layers_layout = QVBoxLayout(layers)
        layers_layout.setContentsMargins(0, 6, 0, 0)
        self.layers_empty = hint_label(
            "No layers yet. Loading a section, warp previews and annotations add layers "
            "here.")
        layers_layout.addWidget(self.layers_empty, 0, Qt.AlignmentFlag.AlignTop)
        layers_layout.addWidget(engine.layer_ctrl)
        self.inspector_tabs.addTab(layers, "Layers")
        regions = QWidget()
        regions_layout = QVBoxLayout(regions)
        regions_layout.setContentsMargins(0, 6, 0, 0)
        self.regions_empty = hint_label("Load an atlas to browse its regions.")
        regions_layout.addWidget(self.regions_empty, 0, Qt.AlignmentFlag.AlignTop)
        regions_layout.addWidget(engine.atlas_view.label_tree)
        self.inspector_tabs.addTab(regions, "Regions")
        inspector_layout.addWidget(self.inspector_tabs)
        inspector.setMinimumWidth(280)
        body.addWidget(inspector)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([570, 640, 280])
        self.body_splitter = body
        self.task_column = task
        self.inspector_column = inspector

        # Status line.
        status = QFrame()
        status.setObjectName("StatusLine")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(12, 4, 12, 4)
        self.message_label = QLabel("")
        self.message_label.setMinimumWidth(200)
        status_layout.addWidget(self.message_label, 1)
        self.context_label = QLabel("")
        self.context_label.setObjectName("Muted")
        status_layout.addWidget(self.context_label)
        status_layout.addSpacing(16)
        self.save_label = QLabel("")
        status_layout.addWidget(self.save_label)
        status_layout.addSpacing(12)
        self.theme_button = QToolButton()
        self.theme_button.clicked.connect(self.toggle_theme)
        status_layout.addWidget(self.theme_button)
        outer.addWidget(status)
        self.setCentralWidget(root)

    def _build_empty_canvas(self):
        """Shown instead of the empty 1.x views until an atlas or section is loaded."""
        frame = QWidget()
        frame.setObjectName("Canvas")
        layout = QVBoxLayout(frame)
        layout.addStretch(1)
        card = Card("Nothing to show yet",
                    "Load a processed atlas and a histology section, or open a project. "
                    "Without a section, probes can be planned on the atlas alone.")
        card.setMaximumWidth(460)
        card.add_row(button("Load atlas…", lambda: self.run("atlas.load"), primary=True),
                     button("Load section…", lambda: self.run("section.load")),
                     button("Open project…", lambda: self.run("project.open")), None)
        card.add_row(button("Download Allen mouse atlas…", self.download_allen_atlas), None)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(2)
        return frame

    def _name_undo_steps(self):
        history = self.engine.undo_history
        for menu_item, label, verb in ((self.undo_step_item, history.undo_label(), "Undo"),
                                       (self.redo_step_item, history.redo_label(), "Redo")):
            menu_item.setText("{} {}".format(verb, label) if label
                              else "{} mapping step".format(verb))
            menu_item.setEnabled(label is not None)

    def _sync_object_tooltips(self):
        """Name each object's mapping status in its tooltip in the Objects list."""
        o = self.engine.object_ctrl
        _records, statuses = self.engine.mapping_overview()
        for widget, name, status in zip(o.obj_list, o.obj_name, statuses):
            text = "{} · mapping {}".format(name, state.mapping_status_text(status))
            if widget.toolTip() != text:
                widget.setToolTip(text)

    def _sync_empty_states(self):
        engine = self.engine
        view = engine.atlas_view
        has_atlas = view.atlas_data is not None or getattr(view, "slice_image_data", None) is not None
        nothing = not has_atlas and engine.image_view.current_img is None
        self.views.setVisible(not nothing)
        self.empty_canvas.setVisible(nothing)
        no_objects = not engine.object_ctrl.obj_list
        self.objects_empty.setVisible(no_objects)
        engine.object_ctrl.outer_frame.setVisible(not no_objects)
        no_layers = not engine.layer_ctrl.layer_list
        self.layers_empty.setVisible(no_layers)
        engine.layer_ctrl.setVisible(not no_layers)
        self.regions_empty.setVisible(view.atlas_data is None)
        view.label_tree.setVisible(view.atlas_data is not None)

    # ------------------------------------------------------------ messages
    def _wrap_engine_messages(self):
        engine = self.engine
        original = engine.print_message

        def relay(msg, col):
            self._dirty_check_pending = True
            original(msg, col)
            kind = None
            if col == engine.error_message_color:
                kind = "bad"
            elif col == getattr(engine, "reminder_color", None):
                kind = "warn"
            self._show_message(msg, kind)

        self._relaying = False
        engine.print_message = relay
        engine.statusbar.messageChanged.connect(
            lambda text: self._show_message(text, None) if text and not self._relaying else None)

    def _show_message(self, text, kind):
        text = " ".join(str(text).split())
        self.message_label.setText(text)
        self.message_label.setToolTip(text)
        colour = {"bad": "error", "warn": "warning", "good": "success"}.get(kind)
        from .theme import TOKENS
        self.message_label.setStyleSheet(
            "color: {};".format(TOKENS[self.theme][colour]) if colour else "")

    def message(self, text, kind=None):
        self._relaying = True
        self._show_message(text, kind)
        self._relaying = False

    # ---------------------------------------------------------- navigation
    def go_to(self, step):
        self.stack.setCurrentWidget(self.panels[step])
        self.rail_buttons[step].setChecked(True)
        self.panels[step].refresh()
        self.panels[step].apply_gates()
        if step in ("annotate", "results") and self.inspector_tabs.currentIndex() != 0:
            self.inspector_tabs.setCurrentIndex(0)

    def set_view(self, key):
        engine = self.engine
        has_volume = engine.atlas_view.atlas_data is not None
        has_slice = engine.current_atlas == "slice"
        has_image = engine.image_view.current_img is not None
        if key == "compare":
            if has_slice:
                engine.show_slice_and_histology()
            elif has_volume and has_image:
                engine.show_2_windows()
            elif has_image:
                engine.show_only_image_window()
            elif has_volume:
                self.set_view("atlas")
                return
        elif key == "atlas":
            if not has_volume:
                self.message("Load a volume atlas to show it.", "warn")
            else:
                {"coronal": engine.show_only_coronal_window,
                 "sagittal": engine.show_only_sagital_window,
                 "horizontal": engine.show_only_horizontal_window}.get(
                    engine.atlas_display, engine.show_only_coronal_window)()
        elif key == "section":
            if not has_image:
                self.message("Load a section to show it.", "warn")
            else:
                engine.show_only_image_window()
        elif key == "3d":
            if not has_volume:
                self.message("Load a volume atlas to show it in 3D.", "warn")
            else:
                engine.show_only_3d_window()
        elif key == "multi":
            if not has_volume:
                self.message("Load a volume atlas to show several planes.", "warn")
            else:
                engine.show_4_windows()
        self._balance_views()
        self._sync_view_buttons()

    def _balance_views(self):
        """Give the visible view frames equal widths."""
        splitter = self.engine.splitter_3
        widths = []
        for index in range(splitter.count()):
            widget = splitter.widget(index)
            if isinstance(widget, QSplitter):
                visible = any(widget.widget(i).isVisibleTo(splitter)
                              for i in range(widget.count()))
            else:
                visible = widget.isVisibleTo(splitter)
            widths.append(1 if visible else 0)
        total = max(sum(widths), 1)
        width = max(splitter.width(), 600)
        splitter.setSizes([int(width * w / total) for w in widths])

    def _sync_view_buttons(self):
        layout = self.engine.current_layout
        key = {"volume-histology": "compare", "slice-histology": "compare",
               "coronal": "atlas", "sagittal": "atlas", "horizontal": "atlas",
               "slice": "atlas", "image": "section", "3d": "3d",
               "four-atlas-windows": "multi", "volume-3d-histology": "multi"}.get(layout)
        for name, view_button in self.view_buttons.items():
            view_button.setChecked(name == key)

    def toggle_tool(self, key):
        action = self.engine.tool_box.checkable_btn_dict["{}_btn".format(key)]
        action.trigger()
        self.refresh()

    def clear_tools(self):
        engine = self.engine
        for key in engine.tool_box.toolbox_btn_keys:
            action = engine.tool_box.checkable_btn_dict[key]
            if action.isChecked():
                action.trigger()
        self.refresh()

    # ------------------------------------------------------------ commands
    def run(self, command_id):
        reason = self.registry.run(command_id)
        self._dirty_check_pending = True
        if reason:
            self.message(reason, "warn")
        self.refresh()

    # Availability checks: None when possible, otherwise the reason.
    def needs_image(self):
        return None if self.engine.image_view.current_img is not None else "Load a section first."

    def needs_volume(self):
        return (None if self.engine.atlas_view.atlas_data is not None
                else "Load a volume atlas first.")

    def needs_both(self):
        if self.needs_volume() and self.needs_image():
            return "Load a volume atlas and a section first."
        return self.needs_volume() or self.needs_image()

    def needs_atlas_and_image(self):
        """Manual landmarks and warping also work on a calibrated slice atlas."""
        view = self.engine.atlas_view
        no_atlas = view.atlas_data is None and getattr(view, "slice_image_data", None) is None
        if no_atlas and self.needs_image():
            return "Load an atlas and a section first."
        return "Load an atlas first." if no_atlas else self.needs_image()

    def command_reason(self, command_id):
        """A check for StepPanel.gate that follows a registered command."""
        return lambda: self.registry.get(command_id).reason_unavailable()

    def needs_either(self):
        if self.needs_volume() and self.needs_image():
            return "Load a volume atlas or a section first."
        return None

    def _register_commands(self):
        engine = self.engine
        add = self.registry.add
        needs_both = self.needs_both

        add(Command("atlas.load", "Load atlas…", engine.actionAtlas.trigger, "Project",
                    ("open atlas", "volume atlas"), "Ctrl+Shift+A"))
        add(Command("section.load", "Load section…", engine.actionSingle_Image.trigger,
                    "Project", ("load image", "open image", "histology", "replace section"),
                    "Ctrl+Shift+I"))
        add(Command("project.open", "Open project…", self.open_project, "Project",
                    ("load project",), "Ctrl+O"))
        add(Command("project.save", "Save project…", self.save_project, "Project",
                    ("save",), "Ctrl+S"))
        add(Command("project.save_portable", "Save portable copy…",
                    lambda: self.save_project(portable=True), "Project",
                    ("portable project",), "Ctrl+Shift+S"))
        add(Command("section.channels", "Choose registration channels",
                    lambda: self.go_to("section"), "Section",
                    ("registration channels", "dapi", "registration input")))
        add(Command("match.find", "Find atlas section", engine.suggest_atlas_section, "Match",
                    ("suggest atlas section", "automatic matching"), available=needs_both))
        add(Command("register.suggest", "Suggest landmarks",
                    engine.propose_registration_landmarks, "Register",
                    ("propose landmarks", "automatic landmarks", "triangulation"),
                    available=needs_both))
        add(Command("register.add_points", "Add or move landmark points",
                    lambda: self.toggle_tool("triang"), "Register",
                    ("triangulation", "landmark tool"), "P"))
        add(Command("register.review", "Mark review complete", engine.mark_registration_reviewed,
                    "Register", ("review", "confirm registration")))
        add(Command("register.delete_pair", "Delete selected landmark pair",
                    self.panels["register"].delete_selected, "Register",
                    ("remove landmark",), "Delete"))
        add(Command("register.preview_to_atlas", "Preview section on atlas",
                    engine.tool_box.toa_btn.trigger, "Register",
                    ("transform to atlas", "warp", "overlay"), available=needs_both))
        add(Command("register.preview_to_section", "Preview atlas on section",
                    engine.tool_box.toh_btn.trigger, "Register",
                    ("transform to histology", "warp"), available=needs_both))
        add(Command("annotate.map", "Map annotations to atlas", engine.tool_box.check_btn.trigger,
                    "Annotate", ("accept and transfer", "transfer", "map"),
                    available=lambda: None if engine.h2a_transferred else
                    "Preview the section on the atlas first (Register step)."))
        annotate = self.panels["annotate"]
        add(Command("annotate.update_mapping", "Update mapping",
                    lambda: (self.go_to("annotate"), annotate.update_selected()), "Annotate",
                    ("remap", "map again", "out of date"),
                    available=annotate._needs_mapped_selection))
        add(Command("annotate.edit_marks", "Edit mapped marks",
                    lambda: (self.go_to("annotate"), annotate.edit_selected()), "Annotate",
                    ("edit marks", "unmap"), available=annotate._needs_mapped_selection))
        add(Command("annotate.parts", "Make parts from atlas marks",
                    engine.object_ctrl.add_object_btn.click, "Annotate",
                    ("add piece", "pieces", "add object")))
        probes = self.panels["annotate"].probes
        add(Command("probe.new", "New probe", lambda: (self.go_to("annotate"), probes.new_probe()),
                    "Probes", ("add probe", "probe track")))
        add(Command("probe.mark", "Mark probe track", lambda: (self.go_to("annotate"),
                                                               probes.toggle_marking()),
                    "Probes", ("probe marker", "probe tool")))
        add(Command("probe.add_section", "Map this section to the probe",
                    lambda: (self.go_to("annotate"), probes.add_section()), "Probes",
                    ("add this section", "make probe piece", "add piece", "transfer probe")))
        add(Command("annotate.build_probe", "Build 3D probe",
                    lambda: (self.go_to("annotate"), probes.build_probe()), "Probes",
                    ("merge probe", "merge")))
        implants = self.panels["annotate"].implants
        add(Command("implant.add", "Add implant (fiber, microprism, probe)…",
                    lambda: (self.go_to("annotate"), implants.add_implant()), "Implants",
                    ("optical fiber", "microprism", "prism", "cannula", "implant")))
        add(Command("implant.draw", "Draw implant outline",
                    lambda: (self.go_to("annotate"), implants.draw.click()), "Implants",
                    ("outline", "fiber track", "prism footprint")))
        add(Command("implant.map", "Map implant outline on this section",
                    lambda: (self.go_to("annotate"), implants.map_section()), "Implants",
                    ("map fiber", "map prism"), available=self.needs_both))
        add(Command("implant.build", "Build implant",
                    lambda: (self.go_to("annotate"), implants.build()), "Implants",
                    ("fiber tip", "prism bottom", "fit implant")))
        add(Command("implant.export", "Export implant table…", implants.export_table,
                    "Implants", ("implant csv", "fiber csv", "prism csv")))
        add(Command("results.export_all", "Export all results…",
                    lambda: (self.go_to("results"), self.panels["results"].export_all()),
                    "Results", ("export everything", "export project", "save results"),
                    available=self.panels["results"]._needs_anything))
        add(Command("annotate.unmerge", "Edit parts (unmerge)", engine.object_ctrl.unmerge_btn.click,
                    "Annotate", ("unmerge", "split object")))
        add(Command("tool.measure", "Measure", lambda: self.toggle_tool("ruler"), "Tools",
                    ("ruler", "distance"), "M"))
        add(Command("tool.none", "Select (no tool)", self.clear_tools, "Tools",
                    ("pointer", "cancel tool"), "V"))
        add(Command("edit.undo", "Undo", engine.actionUndo.trigger, "Edit", (), "Ctrl+Z"))
        add(Command("edit.redo", "Redo", engine.actionRedo.trigger, "Edit", (), "Ctrl+Shift+Z"))
        add(Command("edit.undo_step", "Undo mapping step", engine.undo_mapping_step, "Edit",
                    ("undo map", "undo build", "undo parts"), "Ctrl+Alt+Z",
                    available=lambda: None if engine.undo_history.undo_label()
                    else "Nothing to undo: Map, Update mapping, Make parts and Build are "
                         "undoable."))
        add(Command("edit.redo_step", "Redo mapping step", engine.redo_mapping_step, "Edit",
                    ("redo map", "redo build"), "Ctrl+Alt+Shift+Z",
                    available=lambda: None if engine.undo_history.redo_label()
                    else "Nothing to redo."))
        add(Command("palette", "Search commands", self.open_palette, "Help", ("command palette",),
                    "Ctrl+K"))
        add(Command("view.theme", "Switch light / dark theme", self.toggle_theme, "View",
                    ("dark mode", "light mode")))
        add(Command("view.boundaries", "Show / hide region boundaries", self.toggle_boundaries,
                    "View", ("outlines", "borders", "structures", "contours on atlas"), "B",
                    available=self.needs_volume))
        add(Command("help.manual", "Open the user manual", self.open_manual, "Help", ("docs",)))
        add(Command("help.shortcuts", "Keyboard shortcuts", self.show_shortcuts, "Help", ()))
        add(Command("help.about", "About DriftlessMap", engine.actionAbout_HERBS.trigger, "Help"))
        add(Command("help.classic", "Open the classic interface", self.open_classic, "Help",
                    ("1.x interface", "stable interface", "old interface")))
        for number, (key, title, _panel) in enumerate(STEPS, start=1):
            add(Command("step." + key, "Go to {}".format(title), lambda k=key: self.go_to(k),
                        "Steps", (title.lower(),), str(number)))
        for key, title, tip in VIEWS:
            add(Command("view." + key, "{} view".format(title), lambda k=key: self.set_view(k),
                        "View", (tip.lower(),)))

        # Every 1.x menu command stays reachable, under its 1.x name.
        seen = {id(engine.actionSingle_Image), id(engine.actionAtlas)}
        for action in engine.findChildren(QAction):
            text = action.text().replace("&", "").strip()
            if not text or action.isSeparator() or action.menu() is not None or id(action) in seen:
                continue
            if action.property("classic_only"):
                continue
            seen.add(id(action))
            self.registry.add(Command("legacy.{}".format(action.objectName() or id(action)),
                                      text.rstrip("."), action.trigger, "1.x menu",
                                      (text.lower(),)))

    def _build_menus(self):
        bar = self.menuBar()

        def item(menu, command_id, text=None):
            command = self.registry.get(command_id)
            action = menu.addAction(text or command.name)
            action.triggered.connect(lambda: self.run(command_id))
            return action

        file_menu = bar.addMenu("&File")
        for command_id in ("project.open", "atlas.load", "section.load"):
            item(file_menu, command_id)
        file_menu.addSeparator()
        item(file_menu, "project.save")
        item(file_menu, "project.save_portable")
        file_menu.addSeparator()
        export = file_menu.addMenu("Export")
        for text, action in (("Selected object…", self.engine.actionSave_Current),
                             ("All probes…", self.engine.actionSave_Probes),
                             ("All cells…", self.engine.actionSave_Cells),
                             ("All expression…", self.engine.actionSave_Virus),
                             ("All contours…", self.engine.actionSave_Contours),
                             ("All drawings…", self.engine.actionSave_Drawings),
                             ("Current layer…", self.engine.actionCurrent_Layer),
                             ("All layers…", self.engine.actionAll_Layer),
                             ("Landmarks…", self.engine.actionSave_Triangulation_Points),
                             ("Probe settings…", self.engine.actionSave_Probe_Setting)):
            export.addAction(text, action.trigger)
        imports = file_menu.addMenu("Import")
        for text, action in (("Objects…", self.engine.actionLoad_Objects),
                             ("Layers…", self.engine.actionLoad_Layers),
                             ("External cell points…", self.engine.actionExternal_Cells),
                             ("Landmarks…", self.engine.actionLoad_Triangulation_Points),
                             ("Probe settings…", self.engine.actionLoad_Probe_Setting)):
            imports.addAction(text, action.trigger)
        file_menu.addSeparator()
        quit_action = file_menu.addAction("Quit")
        quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        quit_action.triggered.connect(self.close)

        edit_menu = bar.addMenu("&Edit")
        item(edit_menu, "edit.undo")
        item(edit_menu, "edit.redo")
        edit_menu.addSeparator()
        self.undo_step_item = item(edit_menu, "edit.undo_step")
        self.redo_step_item = item(edit_menu, "edit.redo_step")
        edit_menu.aboutToShow.connect(self._name_undo_steps)

        view_menu = bar.addMenu("&View")
        for key, _title, _tip in VIEWS:
            item(view_menu, "view." + key)
        view_menu.addSeparator()
        self.boundaries_item = item(view_menu, "view.boundaries", "Show region boundaries")
        self.boundaries_item.setCheckable(True)
        boundary_button = self.engine.atlas_view.show_boundary_btn
        boundary_button.toggled.connect(self.boundaries_item.setChecked)
        self.boundaries_item.setChecked(boundary_button.isChecked())
        # Without an atlas the command does nothing; keep the tick truthful.
        self.boundaries_item.triggered.connect(
            lambda: self.boundaries_item.setChecked(boundary_button.isChecked()))
        item(view_menu, "view.theme")
        toggle_task = view_menu.addAction("Show task column")
        toggle_task.setCheckable(True)
        toggle_task.setChecked(True)
        toggle_task.toggled.connect(self.task_column.setVisible)
        toggle_inspector = view_menu.addAction("Show objects and layers")
        toggle_inspector.setCheckable(True)
        toggle_inspector.setChecked(True)
        toggle_inspector.toggled.connect(self.inspector_column.setVisible)

        help_menu = bar.addMenu("&Help")
        item(help_menu, "palette")
        item(help_menu, "help.shortcuts")
        item(help_menu, "help.manual")
        help_menu.addSeparator()
        item(help_menu, "help.classic")
        about = item(help_menu, "help.about")
        about.setMenuRole(QAction.MenuRole.AboutRole)

    def _build_shortcuts(self):
        self._shortcuts = []
        for command in self.registry.all():
            if not command.shortcut:
                continue
            shortcut = QShortcut(QKeySequence(command.shortcut), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            single_key = len(command.shortcut) == 1 or command.shortcut == "Delete"
            shortcut.activated.connect(
                lambda c=command.id, s=single_key: self._shortcut(c, s))
            self._shortcuts.append(shortcut)
        backspace = QShortcut(QKeySequence("Backspace"), self)
        backspace.activated.connect(lambda: self._shortcut("register.delete_pair", True))
        escape = QShortcut(QKeySequence("Escape"), self)
        escape.activated.connect(self.clear_tools)
        self._shortcuts += [backspace, escape]

    def _shortcut(self, command_id, single_key):
        # Single keys never fire while text or numbers are being edited.
        if single_key and isinstance(QApplication.focusWidget(),
                                     (QLineEdit, QAbstractSpinBox, QTextEdit, QPlainTextEdit)):
            return
        if command_id == "register.delete_pair" and self.stack.currentWidget() is not \
                self.panels["register"]:
            return
        self.run(command_id)

    # ----------------------------------------------------------- files
    def open_project(self):
        if not self.confirm_discard("open another project"):
            return
        self.engine.load_project_called()

    # ------------------------------------------------- where the user left off
    def leave_state(self):
        """Where the user is working, saved with the project (see :meth:`resume`)."""
        step = next((key for key, panel in self.panels.items()
                     if panel is self.stack.currentWidget()), "project")
        view = next((key for key, b in self.view_buttons.items() if b.isChecked()), "compare")
        return {"interface": "v2", "step": step, "view": view,
                "implants": self.panels["annotate"].implants.leave_state()}

    def resume(self, state):
        """After a project is opened, return to the step, view and work in progress."""
        state = state if isinstance(state, dict) else {}
        self.clear_tools()
        step = state.get("step") if state.get("step") in self.panels else "project"
        view = state.get("view") if state.get("view") in self.view_buttons else "compare"
        self.set_view(view)
        self.go_to(step)
        self.panels["annotate"].implants.resume(state.get("implants"))
        self.mark_saved()
        self.refresh()
        if state:
            self.message("Opened where you left off.", "good")

    def save_project(self, portable=False):
        if self.engine.save_project_called(portable=portable):
            self.mark_saved()
            self.message("Project saved.", "good")

    def _digest(self):
        return state.scientific_digest(self.engine)

    def eventFilter(self, watched, event):
        # This filter sees every event of the application, so it stays cheap.
        # Do not rescan microscopy rasters on idle timer ticks. User edits
        # request one check at the next refresh; close/open always check in
        # full, including edits performed by scripts or late worker results.
        kind = event.type()
        if kind in EDIT_EVENTS:
            self._dirty_check_pending = True
        elif kind == QEvent.Type.Show and watched.isWidgetType() and watched.isWindow():
            self._theme_window(watched)
        return False

    def _theme_window(self, window):
        """Give a separate window (a dialog, menu or tooltip) the current theme.

        The theme is set on this window, not on the application: an
        application stylesheet restyles every widget of the program, hidden
        ones included, which made switching themes slow. Windows parented to
        this one inherit the theme; others receive it when they are shown.
        """
        if window is self:
            return
        parent = window.parentWidget()
        while parent is not None:
            if parent is self:
                return
            parent = parent.parentWidget()
        if window.property("v2_theme") != self.theme:
            window.setProperty("v2_theme", self.theme)
            window.setStyleSheet(stylesheet(self.theme))

    def mark_saved(self):
        try:
            self._saved_digest = self._digest()
            self._dirty_status = False
            self._dirty_check_pending = False
        except Exception:
            self._saved_digest = None
            self._dirty_status = True
            self._dirty_check_pending = False

    def is_dirty(self):
        if getattr(self.engine, "_project_recovery", None) is not None:
            return True
        try:
            return self._digest() != self._saved_digest
        except Exception:
            # A failed check cannot establish that work is saved.
            return True

    def confirm_discard(self, action):
        if not self.is_dirty():
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "The current work has unsaved changes. Save them before you {}?".format(action),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            if not self.engine.save_project_called():
                return False
            self.mark_saved()
        return True

    def closeEvent(self, event):
        if not self.confirm_discard("close DriftlessMap"):
            event.ignore()
            return
        self._timer.stop()
        QApplication.instance().removeEventFilter(self)
        event.accept()

    # ------------------------------------------------------------- helpers
    def download_allen_atlas(self):
        from .allen_download_dialog import AllenDownloadDialog

        dialog = AllenDownloadDialog(self)
        dialog.exec()
        if dialog.continue_process and dialog.process_finished:
            self.engine._open_downloaded_atlas(dialog)
            self.set_view("compare")

    def open_classic(self):
        """Start the classic interface in its own process and window."""
        if start_interface("classic"):
            self.message("Opening the classic interface in a new window.")
        else:
            self.message("The classic interface could not be started.", "bad")

    def open_palette(self):
        palette = CommandPalette(self.registry, self)
        if palette.exec() and palette.chosen:
            self.run(palette.chosen)

    def open_manual(self):
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        manual = os.path.join(here, "MANUAL.md")
        url = QUrl.fromLocalFile(manual) if os.path.exists(manual) else QUrl(
            "https://github.com/mohebi-n-associates/DriftlessMap/blob/main/MANUAL.md")
        QDesktopServices.openUrl(url)

    def show_shortcuts(self):
        lines = ["{:<16} {}".format(c.shortcut, c.name) for c in
                 sorted(self.registry.all(), key=lambda c: c.group) if c.shortcut]
        lines += ["{:<16} {}".format("Escape", "Stop the current tool"),
                  "{:<16} {}".format("Backspace", "Delete selected landmark pair")]
        box = QMessageBox(self)
        box.setWindowTitle("Keyboard shortcuts")
        box.setText("Single-key shortcuts do not fire while you type in a field.")
        box.setDetailedText("\n".join(lines))
        box.setInformativeText("\n".join(lines[:14]))
        box.exec()

    def apply_theme(self, theme):
        self.theme = theme
        self.settings.setValue("theme", theme)
        self.theme_button.setText("Light theme" if theme == "dark" else "Dark theme")
        self.setStyleSheet(stylesheet(theme))
        adopted.restyle(self.engine, theme)
        # Separate windows that already have a theme switch with this one.
        for window in QApplication.topLevelWidgets():
            if window.property("v2_theme") not in (None, theme):
                self._theme_window(window)

    def toggle_theme(self):
        self.apply_theme("light" if self.theme == "dark" else "dark")

    def toggle_boundaries(self, visible=None):
        """Show or hide the region boundaries on the atlas (the 1.x Show Boundary)."""
        button = self.engine.atlas_view.show_boundary_btn
        button.setChecked(not button.isChecked() if visible is None else bool(visible))
        self.engine.vis_atlas_boundary()

    # ------------------------------------------------------------- refresh
    def refresh(self):
        engine = self.engine
        if getattr(engine, "_project_loading", False):
            return
        try:
            statuses = state.step_status(engine)
        except Exception:
            statuses = {}
        for key, label in self.rail_status.items():
            label.setText(statuses.get(key, ""))
        current = self.stack.currentWidget()
        if current is not None:
            current.refresh()
            current.apply_gates()
        self.plane_label.setText(state.plane_summary(engine))
        tool = engine.current_checked_tool
        self.tool_options.setVisible(tool is not None)
        self.tool_label.setText("{} options".format({
            "triang": "Landmark", "loc": "Cell", "magic_wand": "Colour detection",
            "ruler": "Measure", "probe": "Probe", "pencil": "Drawing", "eraser": "Eraser",
            "lasso": "Lasso"}.get(tool, str(tool).capitalize())) if tool else "")
        self._sync_view_buttons()
        self._sync_empty_states()
        self._sync_object_tooltips()
        atlas, _ = state.atlas_summary(engine)
        section, _ = state.section_summary(engine)
        self.context_label.setText("{} · {}".format(atlas, section))
        if self._dirty_check_pending:
            self._dirty_status = self.is_dirty()
            self._dirty_check_pending = False
        dirty = self._dirty_status
        self.save_label.setText("Unsaved changes" if dirty else "All changes saved"
                                if engine.current_project_path else "Not saved yet")
        self.save_label.setObjectName("StatusWarn" if dirty else "Muted")
        self.save_label.style().unpolish(self.save_label)
        self.save_label.style().polish(self.save_label)
        name = os.path.basename(engine.current_project_path) if engine.current_project_path \
            else "Untitled"
        self.setWindowTitle("{}{} — {}".format(name, " •" if dirty else "", PREVIEW_LABEL))
