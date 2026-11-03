"""The section bar above the images: which section is open, and switching.

Shows the open section's name and position (and the page, scene or planes
of a multi-part image file), lists every section, and opens the previous or
next one without leaving the current step. Switching goes through the
engine's ``switch_section``, exactly as Project > Sections does.
"""

from PyQt6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QToolButton


def selection_text(selection):
    """"page 2, scene 1" for a multi-part image file's shown part, or ""."""
    if not selection:
        return ""
    parts = []
    if "page" in selection:
        parts.append("page {}".format(selection["page"] + 1))
    if "scene" in selection:
        parts.append("scene {}".format(selection["scene"] + 1))
    for axis, index in (selection.get("planes") or {}).items():
        parts.append("{} {}".format(axis, index + 1))
    return ", ".join(parts)


class SectionBar(QFrame):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self.engine = shell.engine
        self.setObjectName("SectionBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)
        caption = QLabel("Section")
        caption.setObjectName("Muted")
        layout.addWidget(caption)
        self.previous = QToolButton()
        self.previous.setText("◀")
        self.previous.setToolTip("Open the previous section (Ctrl+PgUp)")
        self.previous.clicked.connect(lambda: self.step(-1))
        layout.addWidget(self.previous)
        self.combo = QComboBox()
        self.combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(18)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setToolTip("Open another section; the current step stays open")
        self.combo.activated.connect(self._chosen)
        layout.addWidget(self.combo, 1)
        self.next = QToolButton()
        self.next.setText("▶")
        self.next.setToolTip("Open the next section (Ctrl+PgDown)")
        self.next.clicked.connect(lambda: self.step(1))
        layout.addWidget(self.next)
        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.detail, 1)
        self._key = None

    def section_ids(self):
        return [entry.section_id for entry in self.engine.sections.entries()]

    def refresh(self):
        engine = self.engine
        loaded = engine.image_view.current_img is not None
        self.setVisible(loaded)
        if not loaded:
            return
        book = engine.sync_sections()
        entries = book.entries()
        key = (tuple((e.section_id, e.name) for e in entries), book.active_id)
        if key != self._key:
            self._key = key
            self.combo.blockSignals(True)
            self.combo.clear()
            for number, entry in enumerate(entries, start=1):
                self.combo.addItem("{}/{} · {}".format(number, len(entries), entry.name),
                                   entry.section_id)
            self.combo.setCurrentIndex(self.section_ids().index(book.active_id))
            self.combo.blockSignals(False)
        index = self.combo.currentIndex()
        self.previous.setEnabled(index > 0)
        self.next.setEnabled(index < self.combo.count() - 1)
        self.detail.setText(selection_text(engine.image_view.source_selection()))

    def _chosen(self, index):
        self.open(self.combo.itemData(index))

    def step(self, offset):
        ids = self.section_ids()
        index = ids.index(self.engine.sections.active_id) + offset
        if 0 <= index < len(ids):
            self.open(ids[index])

    def open(self, section_id):
        """Open ``section_id`` and stay on the current step."""
        engine = self.engine
        if section_id is None or section_id == engine.sections.active_id:
            return
        ok, message = engine.switch_section(section_id)
        self.shell.message(message, "good" if ok else "bad")
        self._key = None
        self.shell.refresh()

