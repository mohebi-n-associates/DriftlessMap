"""A redesigned Allen mouse atlas download dialog for the V2 interface.

It reuses :class:`AllenDownloader` for every download, mesh and processing
step (threads, atomic downloads, checksum manifest, validation and error
handling); only the layout and guidance are new. Files already downloaded
into the chosen folder, as recorded in the download manifest for the same
URL, are not downloaded again.
"""

import os
import shutil
from os.path import dirname, join

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..allen_downloader import AllenDownloader
from ..download_utils import read_download_manifest, thread_is_running
from .widgets import Card, hint_label

RESOLUTIONS = (
    ("10 µm", "Finest detail", "Very large download; needs a machine with a lot of memory."),
    ("25 µm", "Detailed", "A good balance of detail, size and speed for most work."),
    ("50 µm", "Fast", "Small and quick; for trying things out and coarse work."),
)


class _Tile(QFrame):
    """A selectable resolution tile wrapping one of the dialog's radio buttons."""

    def __init__(self, radio, title, subtitle, detail):
        super().__init__()
        self.setObjectName("Tile")
        self.radio = radio
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(4)
        radio.setText("")
        head = QHBoxLayout()
        head.addWidget(radio)
        big = QLabel(title)
        big.setObjectName("TileTitle")
        head.addWidget(big)
        head.addStretch(1)
        layout.addLayout(head)
        name = QLabel(subtitle)
        name.setObjectName("CardTitle")
        layout.addWidget(name)
        layout.addWidget(hint_label(detail))
        radio.toggled.connect(self._refresh)
        self._refresh()

    def mousePressEvent(self, event):
        if self.radio.isEnabled():
            self.radio.setChecked(True)
        super().mousePressEvent(event)

    def _refresh(self, *_args):
        self.setProperty("selected", self.radio.isChecked())
        self.style().unpolish(self)
        self.style().polish(self)


class AllenDownloadDialog(AllenDownloader):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Allen mouse brain atlas")
        self.setMinimumWidth(760)
        self._then_meshes = False
        self._found = set()

        # Move the original controls out of the 1.x layout into the new one.
        # Old containers stay hidden children of the dialog, so nothing they
        # hold is deleted; the controls are moved into the new layout below.
        old = self.layout()
        self._old_containers = []
        while old.count():
            item = old.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                self._old_containers.append(item.widget())
        QWidget().setLayout(old)
        for field in (self.b_input1, self.b_input2, self.b_input3):
            field.setStyleSheet("")
        for bar in (self.data_bar, self.segmentation_bar, self.mesh_bar, self.progress):
            bar.setTextVisible(False)
            bar.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        title = QLabel("Allen mouse brain atlas (CCFv3, 2017)")
        title.setObjectName("StepTitle")
        layout.addWidget(title)
        layout.addWidget(hint_label(
            "Downloads the average template, the region annotation and the 3D region "
            "meshes from the Allen Institute, then processes them into an atlas folder "
            "that DriftlessMap opens directly."))

        resolution = Card("1  Resolution")
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        # The radios live in separate tiles now, so group them explicitly.
        self.resolution_group = QButtonGroup(self)
        for radio, (label, subtitle, detail) in zip(
                (self.vs_rabnt1, self.vs_rabnt2, self.vs_rabnt3), RESOLUTIONS):
            self.resolution_group.addButton(radio)
            tiles.addWidget(_Tile(radio, label, subtitle, detail), 1)
        resolution.layout.addLayout(tiles)
        layout.addWidget(resolution)

        folder = Card("2  Folder")
        self.folder_field = QLineEdit()
        self.folder_field.setReadOnly(True)
        self.folder_field.setPlaceholderText("Choose an empty folder, or one with an earlier download")
        self.folder_button = QPushButton("Choose…")
        self.folder_button.clicked.connect(self.choose_folder)
        folder.add_row(self.folder_field, self.folder_button)
        self.folder_note = folder.add(hint_label(""))
        layout.addWidget(folder)

        download = Card("3  Download")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._rows = []
        for row, (name, bar) in enumerate((("Template image", self.data_bar),
                                          ("Region annotation", self.segmentation_bar),
                                          ("3D region meshes", self.mesh_bar))):
            label = QLabel(name)
            status = QLabel("")
            status.setObjectName("Muted")
            status.setMinimumWidth(170)
            grid.addWidget(label, row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(status, row, 2)
            self._rows.append(status)
        grid.setColumnStretch(1, 1)
        download.layout.addLayout(grid)
        self.everything_button = QPushButton("Download everything")
        self.everything_button.setProperty("primary", True)
        self.everything_button.clicked.connect(self.download_everything)
        self.download_btn.setText("Atlas files only")
        self.download_mesh_btn.setText("Meshes only")
        download.add_row(self.everything_button, self.download_btn, self.download_mesh_btn, None)
        layout.addWidget(download)

        bregma = Card("4  Bregma", "The estimated Bregma position, in atlas voxels at the chosen "
                                    "resolution. DriftlessMap reports Bregma-relative coordinates "
                                    "from it. Keep the estimate unless you have a better one.")
        fields = QHBoxLayout()
        for name, field in (("AP", self.b_input1), ("DV", self.b_input2), ("ML", self.b_input3)):
            caption = QLabel(name)
            caption.setObjectName("Muted")
            fields.addWidget(caption)
            field.setMaximumWidth(90)
            fields.addWidget(field)
            fields.addSpacing(8)
        reset = QPushButton("Reset to Allen estimate")
        reset.clicked.connect(self.set_default_bregma_coordinates)
        fields.addStretch(1)
        fields.addWidget(reset)
        bregma.layout.addLayout(fields)
        layout.addWidget(bregma)

        footer = QFrame()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        self.process_info.setWordWrap(True)
        self.process_info.setText("")
        footer_layout.addWidget(self.process_info)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_label)
        footer_layout.addLayout(progress_row)
        buttons = QHBoxLayout()
        buttons.addWidget(hint_label("Processing can take a long time at 10 µm. The atlas opens "
                                     "when it finishes."), 1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        self.process_btn.setText("Process and open atlas")
        self.process_btn.setProperty("primary", True)
        buttons.addWidget(close)
        buttons.addWidget(self.process_btn)
        footer_layout.addLayout(buttons)
        layout.addWidget(footer)

        for widget in (self.data_bar, self.segmentation_bar, self.mesh_bar, self.download_btn,
                       self.download_mesh_btn, self.process_info, self.process_btn,
                       self.progress, self.progress_label):
            widget.show()   # they were hidden with the 1.x layout
        for radio in (self.vs_rabnt1, self.vs_rabnt2, self.vs_rabnt3):
            radio.toggled.connect(lambda _checked: self._scan_folder())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(300)
        self._refresh()

    # ------------------------------------------------------------ folder
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Folder for the Allen atlas",
                                                  self.saving_folder or "")
        if folder:
            self.saving_folder = folder
            self.folder_field.setText(folder)
            self._scan_folder()

    def _verified(self, local, url):
        """True if ``local`` was fully downloaded from ``url`` into the folder."""
        if not self.saving_folder:
            return False
        path = os.path.join(self.saving_folder, local)
        entry = read_download_manifest(self.saving_folder).get(local) or {}
        return os.path.isfile(path) and os.path.getsize(path) > 0 and entry.get("url") == url

    def _scan_folder(self):
        if self.downloading_atlas or self.downloading_meshes:
            return
        self._found = set()
        self.finish[0] = self.finish[1] = False
        for local, url, bar in ((self.data_local, self.data_url, self.data_bar),
                                (self.segmentation_local, self.segmentation_url,
                                 self.segmentation_bar)):
            done = self._verified(local, url)
            bar.setValue(100 if done else 0)
            if done:
                self._found.add(local)
        self.finish[0] = self.data_local in self._found
        self.finish[1] = self.segmentation_local in self._found
        meshes = os.path.join(self.saving_folder or "", "downloaded_meshes", "997.obj")
        self.mesh_bar.setRange(0, 100)
        self.mesh_bar.setValue(100 if self.saving_folder and os.path.isfile(meshes) else 0)
        if not self.saving_folder:
            self.folder_note.setText("")
        elif len(self._found) == 2:
            self.folder_note.setText("The atlas files for this resolution are already in this "
                                     "folder and will not be downloaded again.")
        elif self._found:
            self.folder_note.setText("Part of this resolution is already here; only the rest "
                                     "will be downloaded.")
        else:
            self.folder_note.setText("Nothing downloaded here yet for this resolution.")

    # ---------------------------------------------------------- downloads
    def download_everything(self):
        self._then_meshes = True
        self.download_start()

    def download_start(self):
        if not self.saving_folder:
            self.choose_folder()
            if not self.saving_folder:
                self._then_meshes = False
                return
        self.process_info.setText("")
        self.downloading_atlas = True
        for radio in (self.vs_rabnt1, self.vs_rabnt2, self.vs_rabnt3):
            radio.setEnabled(False)
        self.folder_button.setEnabled(False)
        target = os.path.join(self.saving_folder, self.label_local)
        if not os.path.exists(target):
            shutil.copyfile(join(dirname(dirname(__file__)), "data", "query.csv"), target)
        started = False
        for url, local, setter in ((self.segmentation_url, self.segmentation_local,
                                    self.set_segmentation_bar_value),
                                   (self.data_url, self.data_local, self.set_data_bar_value)):
            if self._verified(local, url):
                setter(100)
            else:
                self.start_thread(url, local, setter)
                started = True
        if not started:
            self.downloading_atlas = False

    # ------------------------------------------------------------ refresh
    def _row_status(self, local, bar, finished):
        if local in self.download_errors:
            return "Failed: " + self.download_errors[local]
        if finished:
            return "Already downloaded" if local in self._found else "Done"
        thread = self.download_threads.get(local)
        if thread is not None and thread_is_running(thread):
            return "Downloading… {}%".format(bar.value())
        return "Not downloaded"

    def _refresh(self):
        self._rows[0].setText(self._row_status(self.data_local, self.data_bar, self.finish[0]))
        self._rows[1].setText(self._row_status(self.segmentation_local, self.segmentation_bar,
                                               self.finish[1]))
        if self.downloading_meshes:
            maximum = max(1, self.mesh_bar.maximum())
            self._rows[2].setText("Downloading… {:.0f}%".format(100 * self.mesh_bar.value() / maximum))
        elif self.finish[2] or (self.mesh_bar.value() and self.mesh_bar.value() >= self.mesh_bar.maximum()):
            self._rows[2].setText("Done")
        else:
            self._rows[2].setText("Not downloaded")
        busy = self.has_active_downloads() or self.downloading_meshes or \
            thread_is_running(self.thread)
        self.everything_button.setEnabled(not busy)
        if not busy and not thread_is_running(self.thread):
            self.folder_button.setEnabled(True)
        atlas_ready = self.finish[0] and self.finish[1]
        errors = bool(self.download_errors)
        if self._then_meshes and atlas_ready and not busy:
            self._then_meshes = False
            if not errors:
                self.download_mesh_start()
        if errors:
            self._then_meshes = False
