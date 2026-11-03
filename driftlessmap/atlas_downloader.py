import numpy as np
from . import file_dialogs
from .persistence import write_cache_pickle
import os
from os.path import dirname, join
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)
from PyQt6.QtCore import QObject, QThread, pyqtSignal
import shutil
from .atlas_loader import (
    begin_atlas_processing,
    finish_atlas_processing,
    process_atlas_raw_data,
)
from .obj_items import load_mesh_file, render_volume, render_small_volume
from .persistence import load_legacy_pickle
from .download_utils import DownloadCancelled, download_file, thread_is_running
from .rat_atlases import PREPARE, WAXHOLM, WHS_BREGMA, WHS_LAMBDA, WHS_VOXEL_UM


class DownloadThread(QThread):
    download_process_signal = pyqtSignal(int)
    download_error_signal = pyqtSignal(str)
    download_finished_signal = pyqtSignal(str)

    def __init__(self, url, destination, expected_sha256=None, parent=None):
        super(DownloadThread, self).__init__(parent)
        self.url = url
        self.destination = destination
        self.expected_sha256 = expected_sha256

    def run(self):
        try:
            download_file(
                self.url,
                self.destination,
                progress=self.download_process_signal.emit,
                cancelled=self.isInterruptionRequested,
                expected_sha256=self.expected_sha256,
            )
        except DownloadCancelled:
            return
        except Exception as exc:
            self.download_error_signal.emit(str(exc))
            return
        self.download_finished_signal.emit(self.destination)


class WorkerProcessData(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int)

    def __init__(self):
        super(WorkerProcessData, self).__init__()
        self.saving_folder = None
        self.data_local = None
        self.segmentation_local = None
        self.mask_local = None
        self.b_val = None
        self.l_val = None
        self.vox_size = None

        self.atlas_data = None
        self.atlas_info = None
        self.segmentation_data = None
        self.unique_label = None
        self.label_info = None
        self.boundary = None
        self.small_mesh_list = None
        self.mesh_data = None
        self.success = False
        self.message = None
        self.prepare = None

    def set_data(self, saving_folder, data_local, segmentation_local, mask_local, b_val, l_val,
                 vox_size, prepare=None):
        """``prepare(folder)``, when given, turns the downloaded files into the
        template, annotation, mask and ``atlas_labels.pkl`` processing reads."""
        self.prepare = prepare
        self.saving_folder = saving_folder
        self.data_local = data_local
        self.segmentation_local = segmentation_local
        self.mask_local = mask_local
        self.b_val = b_val
        self.l_val = l_val
        self.vox_size = vox_size

    def run(self):
        # Always report back: an exception escaping a worker thread would
        # leave the dialog waiting forever and can abort the application.
        try:
            begin_atlas_processing(self.saving_folder)
            self._run()
            if self.success:
                finish_atlas_processing(self.saving_folder)
        except Exception as exc:
            self.success = False
            self.message = 'Atlas processing failed: {}'.format(exc)
        finally:
            self.finished.emit()

    def _run(self):
        target = os.path.join(self.saving_folder, 'atlas_labels.pkl')
        if self.prepare is not None:
            self.prepare(self.saving_folder)
        elif not os.path.exists(target):
            # Folders downloaded before 2.5.0 (Waxholm v4) use the packaged labels.
            shutil.copyfile(join(dirname(__file__), "data/atlas_labels.pkl"), target)

        self.progress.emit(1)

        self.label_info, label_error = load_legacy_pickle(
            os.path.join(self.saving_folder, 'atlas_labels.pkl'))
        if label_error is not None:
            raise ValueError(label_error)

        self.progress.emit(5)

        self.atlas_data, self.atlas_info, self.segmentation_data, self.unique_label, self.boundary, msg = \
            process_atlas_raw_data(self.saving_folder, data_file=self.data_local,
                                   segmentation_file=self.segmentation_local, mask_file=self.mask_local,
                                   bregma_coordinates=self.b_val, lambda_coordinates=self.l_val,
                                   voxel_size=self.vox_size)
        self.message = msg

        if msg == 'Atlas loaded successfully.':
            self.progress.emit(40)
            self.mesh_data = render_volume(self.atlas_data, self.saving_folder, factor=2, level=0.1)
            self.progress.emit(50)
            save_path = os.path.join(self.saving_folder, 'meshes')
            if not os.path.exists(save_path):
                os.mkdir(save_path)

            n_label = len(self.unique_label)
            progress_step = np.linspace(50, 95, n_label)

            for i in range(n_label):
                self.progress.emit(int(progress_step[i]))
                label_id = int(self.unique_label[i])

                if label_id == 0:
                    continue
                render_small_volume(label_id, save_path, self.atlas_data, self.segmentation_data, factor=2, level=0.1)

            self.small_mesh_list = {}
            file_list = os.listdir(save_path)
            for da_file in file_list:
                file_name = os.path.basename(da_file)
                da_name, file_extension = os.path.splitext(file_name)
                if file_extension == '.pkl':
                    md = load_mesh_file(os.path.join(save_path, da_file))

                    self.small_mesh_list[str(da_name)] = md

            self.progress.emit(97)
            write_cache_pickle(os.path.join(self.saving_folder, 'atlas_small_meshdata.pkl'), self.small_mesh_list)

            self.progress.emit(100)
            self.success = True


class AtlasDownloader(QDialog):
    """Download and process one of the rat atlases in :mod:`rat_atlases`."""

    def __init__(self, *args, atlas=WAXHOLM, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QVBoxLayout(self)
        self.atlas = atlas
        self.setWindowTitle(atlas.title)

        self.continue_process = True
        self.saving_folder = None

        self.thread = QThread()
        self.worker = WorkerProcessData()

        self.b_val = WHS_BREGMA
        self.l_val = WHS_LAMBDA
        self.vox_size = WHS_VOXEL_UM

        self.finish = [False] * len(atlas.files)
        self.process_finished = False
        self.download_threads = {}
        self.download_errors = {}

        self.bars = []
        for item in atlas.files:
            bar = QProgressBar()
            bar.setMinimumWidth(400)
            bar.setValue(0)
            bar.setFormat("{}: %p%".format(item.role))
            self.bars.append(bar)

        self.agree = QCheckBox("I agree")
        self.agreement = QLabel(atlas.agreement)
        self.agreement.setWordWrap(True)
        self.agreement.setVisible(bool(atlas.agreement))
        self.agree.setVisible(bool(atlas.agreement))

        self.download_btn = QPushButton()
        self.download_btn.setMinimumWidth(100)
        self.download_btn.setText("Download")

        self.process_btn = QPushButton()
        self.process_btn.setMinimumWidth(100)
        self.process_btn.setText("Process")

        self.process_label = QLabel()
        self.process_label.setMinimumWidth(100)
        self.process_label.setText("")

        self.progress = QProgressBar(self)
        self.progress.setMinimumWidth(100)

        self.process_info = QLabel('The whole process takes around 40 min - 1 hour. \n'
                                   'This window will be closed automatically when processing finished.\n')

        for bar in self.bars:
            layout.addWidget(bar)
        layout.addWidget(self.agreement)
        layout.addWidget(self.agree)
        layout.addWidget(self.download_btn)
        layout.addWidget(self.process_info)
        layout.addWidget(self.process_btn)
        layout.addWidget(self.progress)
        layout.addWidget(self.process_label)

        self.download_btn.clicked.connect(self.download_start)
        self.process_btn.clicked.connect(self.process_start)

    # Download button event
    def download_start(self):
        if self.atlas.agreement and not self.agree.isChecked():
            self.process_info.setText("Tick \"I agree\" to accept the atlas terms first.")
            return
        self.saving_folder = str(file_dialogs.get_existing_directory(self, "Select Folder to Save Atlas"))
        if self.saving_folder != '':
            self.download_btn.setVisible(False)
            for index in range(len(self.atlas.files)):
                self.start_download(index)

    def start_download(self, index):
        item = self.atlas.files[index]
        destination = os.path.join(self.saving_folder, item.local)
        self.download_errors.pop(item.local, None)
        self.finish[index] = False
        thread = DownloadThread(item.url, destination, expected_sha256=item.sha256, parent=self)
        self.download_threads[item.local] = thread
        thread.download_process_signal.connect(
            lambda value, index=index: self.set_bar_value(index, value))
        thread.download_error_signal.connect(
            lambda message, name=item.local: self.download_failed(name, message))
        thread.download_finished_signal.connect(
            lambda _path, index=index: self.set_bar_value(index, 100))
        thread.finished.connect(lambda name=item.local: self.download_thread_finished(name))
        thread.start()

    def download_failed(self, local, message):
        self.download_errors[local] = message
        self.process_info.setText('Download failed for {}: {}'.format(local, message))

    def download_thread_finished(self, local):
        thread = self.download_threads.pop(local, None)
        if thread is not None:
            thread.deleteLater()

    def has_active_downloads(self):
        return any(thread_is_running(thread) for thread in self.download_threads.values())

    def set_bar_value(self, index, value):
        self.bars[index].setValue(value)
        if value == 100:
            self.finish[index] = True

    def report_progress(self, i):
        self.progress.setValue(i)

    def missing_files(self, folder):
        return [item.local for item in self.atlas.files
                if not os.path.isfile(os.path.join(folder, item.local))
                or os.path.getsize(os.path.join(folder, item.local)) == 0]

    def process_start(self):
        if self.has_active_downloads():
            self.process_info.setText('Please wait until all downloads finish.')
            return
        if self.saving_folder is not None:
            saving_folder = self.saving_folder
        else:
            saving_folder = str(file_dialogs.get_existing_directory(self, "Select Atlas Folder"))

        if saving_folder != '':
            missing_files = self.missing_files(saving_folder)
            if missing_files:
                self.process_info.setText(
                    'Missing or empty atlas files: {}'.format(', '.join(missing_files))
                )
                return
            self.saving_folder = saving_folder
            self.process_btn.setVisible(False)
            self.worker.set_data(saving_folder, self.atlas.template, self.atlas.annotation,
                                 self.atlas.mask, self.b_val, self.l_val, self.vox_size,
                                 prepare=PREPARE[self.atlas.key])
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.on_finish)
            self.thread.finished.connect(self.thread.deleteLater)
            self.worker.progress.connect(self.report_progress)
            self.thread.start()

    def on_finish(self):
        self.thread.quit()
        if not self.worker.success:
            self.continue_process = False
            QMessageBox.warning(
                self,
                'Atlas processing failed',
                self.worker.message or 'Atlas processing did not complete.',
            )
            self.reject()
            return
        self.process_finished = True
        self.continue_process = True
        self.accept()

    def closeEvent(self, event):
        if self.process_finished:
            event.accept()
            return
        if self.has_active_downloads() or thread_is_running(self.thread):
            QMessageBox.information(
                self, 'Operation in progress', 'Please wait for the active operation to finish.'
            )
            event.ignore()
            return
        reply = QMessageBox.question(self, 'Message',
                                     "Do you want to leave?", QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            self.continue_process = False
            event.accept()
        else:
            event.ignore()
