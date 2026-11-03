"""The V2 download dialog for the rat atlases (Waxholm, SWC female rat).

It reuses :class:`AtlasDownloader` for every download and processing step
(threads, atomic checksummed downloads, preparation and processing); only the
layout and guidance are new, as in :mod:`allen_download_dialog`. Files
already in the chosen folder with the expected checksum are not downloaded
again.
"""


from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import file_dialogs
from ..atlas_downloader import AtlasDownloader
from ..download_utils import thread_is_running
from .widgets import Card, hint_label


def _size(count):
    return "{:.0f} MB".format(count / 1e6) if count >= 1e6 else "{:.0f} kB".format(count / 1e3)


class RatAtlasDownloadDialog(AtlasDownloader):
    def __init__(self, atlas, parent=None):
        super().__init__(parent, atlas=atlas)
        self.setMinimumWidth(720)
        self._found = set()

        # Move the controls out of the 1.x layout (as the Allen dialog does).
        old = self.layout()
        while old.count():
            item = old.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
        QWidget().setLayout(old)
        for bar in self.bars + [self.progress]:
            bar.setTextVisible(False)
            bar.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        title = QLabel(atlas.title)
        title.setObjectName("StepTitle")
        layout.addWidget(title)
        layout.addWidget(hint_label(
            atlas.summary + " Downloads {} and processes it into an atlas folder that "
            "DriftlessMap opens directly. Cite: {}.".format(_size(atlas.download_size),
                                                           atlas.citation)))

        step = 1
        if atlas.agreement:
            terms = Card("{}  Terms".format(step))
            terms.add(hint_label(atlas.agreement))
            self.agree.setText("I agree to these terms")
            terms.add(self.agree)
            layout.addWidget(terms)
            step += 1

        folder = Card("{}  Folder".format(step))
        self.folder_field = QLineEdit()
        self.folder_field.setReadOnly(True)
        self.folder_field.setPlaceholderText("Choose an empty folder, or one with an earlier download")
        self.folder_button = QPushButton("Choose…")
        self.folder_button.clicked.connect(self.choose_folder)
        folder.add_row(self.folder_field, self.folder_button)
        self.folder_note = folder.add(hint_label(""))
        layout.addWidget(folder)
        step += 1

        download = Card("{}  Download".format(step))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self._rows = []
        for row, (item, bar) in enumerate(zip(atlas.files, self.bars)):
            status = QLabel("")
            status.setObjectName("Muted")
            status.setMinimumWidth(170)
            grid.addWidget(QLabel("{} ({})".format(item.role, _size(item.size))), row, 0)
            grid.addWidget(bar, row, 1)
            grid.addWidget(status, row, 2)
            self._rows.append(status)
        grid.setColumnStretch(1, 1)
        download.layout.addLayout(grid)
        self.download_btn.setText("Download")
        self.download_btn.setProperty("primary", True)
        download.add_row(self.download_btn, None)
        layout.addWidget(download)

        footer = QFrame()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 4, 0, 0)
        self.process_info.setWordWrap(True)
        self.process_info.setText("")
        footer_layout.addWidget(self.process_info)
        footer_layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addWidget(hint_label("Processing takes half an hour or more, mostly for the 3D "
                                     "region meshes. The atlas opens when it finishes."), 1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        self.process_btn.setText("Process and open atlas")
        self.process_btn.setProperty("primary", True)
        buttons.addWidget(close)
        buttons.addWidget(self.process_btn)
        footer_layout.addLayout(buttons)
        layout.addWidget(footer)

        for widget in self.bars + [self.download_btn, self.process_info, self.process_btn,
                                   self.progress, self.agree]:
            widget.show()   # they were hidden with the 1.x layout
        self.agree.setVisible(bool(atlas.agreement))
        self.agree.toggled.connect(lambda _checked: self._refresh())
        # Word-wrapped hints make the layout's minimum too small for the
        # download rows, which then overlap; start at the full height.
        self.setMinimumHeight(self.sizeHint().height())
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(300)
        self._refresh()

    # ------------------------------------------------------------ folder
    def choose_folder(self):
        folder = file_dialogs.get_existing_directory(
            self, "Folder for the {}".format(self.atlas.title), self.saving_folder or "")
        if folder:
            self.saving_folder = folder
            self.folder_field.setText(folder)
            self._scan_folder()

    def _matching(self):
        """Files in the folder whose current bytes match the release."""
        return self.matching_files(self.saving_folder) if self.saving_folder else set()

    def _scan_folder(self):
        if self.has_active_downloads():
            return
        self._found = self._matching()
        for index, item in enumerate(self.atlas.files):
            done = item.local in self._found
            self.bars[index].setValue(100 if done else 0)
            self.finish[index] = done
        if not self.saving_folder:
            self.folder_note.setText("")
        elif len(self._found) == len(self.atlas.files):
            self.folder_note.setText("Everything is downloaded here; process it to open the "
                                     "atlas.")
        elif self._found:
            self.folder_note.setText("Part of the atlas is already here; only the rest will be "
                                     "downloaded.")
        else:
            self.folder_note.setText("Nothing downloaded here yet.")

    # ---------------------------------------------------------- downloads
    def download_start(self):
        if self.atlas.agreement and not self.agree.isChecked():
            self.process_info.setText("Tick \"I agree\" to accept the atlas terms first.")
            return
        if not self.saving_folder:
            self.choose_folder()
            if not self.saving_folder:
                return
        self.process_info.setText("")
        self.folder_button.setEnabled(False)
        matching = self._matching()
        for index, item in enumerate(self.atlas.files):
            if item.local in matching:
                self.set_bar_value(index, 100)
            else:
                self.start_download(index)

    def process_start(self):
        if not self.saving_folder:
            self.choose_folder()
            if not self.saving_folder:
                return
        matching = self._matching()
        missing = [item.role for item in self.atlas.files if item.local not in matching]
        if missing:
            self.process_info.setText("Download first: {}.".format(", ".join(missing)))
            return
        super().process_start()

    # ------------------------------------------------------------ refresh
    def _row_status(self, index):
        item = self.atlas.files[index]
        if item.local in self.download_errors:
            return "Failed: " + self.download_errors[item.local]
        if self.finish[index]:
            return "Already downloaded" if item.local in self._found else "Done"
        thread = self.download_threads.get(item.local)
        if thread is not None and thread_is_running(thread):
            return "Downloading… {}%".format(self.bars[index].value())
        return "Not downloaded"

    def _refresh(self):
        for index, status in enumerate(self._rows):
            status.setText(self._row_status(index))
        busy = self.has_active_downloads() or thread_is_running(self.thread)
        agreed = not self.atlas.agreement or self.agree.isChecked()
        self.download_btn.setEnabled(not busy and agreed and not all(self.finish))
        self.process_btn.setEnabled(not busy)
        if not busy:
            self.folder_button.setEnabled(True)
        if self.saving_folder and all(self.finish):
            self.folder_note.setText("Everything is downloaded here; process it to open the "
                                     "atlas.")
