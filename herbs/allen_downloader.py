import gzip
import os
from os.path import dirname, join
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
import pyqtgraph.opengl as gl

import nrrd
import pickle
import shutil
import numpy as np
import pandas as pd

from .atlas_loader import process_atlas_raw_data
from .uuuuuu import hex2rgb, obj_data_to_mesh3d, make_contour_img
from .obj_items import render_volume, render_small_volume
from .atlas_downloader import DownloadThread
from .atlas_transform import make_boundary_dict
from .download_utils import download_file


def _stream_unique_nrrd_values(filename, progress=None, chunk_size=8 * 1024 * 1024):
    """Return unique NRRD values without loading or sorting the whole volume."""
    with open(filename, "rb") as source:
        header = nrrd.read_header(source)
        dtype = nrrd.reader._determine_datatype(header)
        encoding = str(header["encoding"]).lower()
        total_values = int(np.prod(header["sizes"], dtype=np.int64))

        if encoding in ("gzip", "gz"):
            data_stream = gzip.GzipFile(fileobj=source)
        elif encoding == "raw":
            data_stream = source
        else:
            raise ValueError(
                "Unsupported NRRD encoding for label scan: {}".format(encoding)
            )

        unique_values = set()
        remainder = b""
        values_read = 0
        if progress is not None:
            progress(0, total_values)

        try:
            while True:
                chunk = data_stream.read(chunk_size)
                if not chunk:
                    break
                chunk = remainder + chunk
                aligned_size = len(chunk) - (len(chunk) % dtype.itemsize)
                if aligned_size:
                    values = np.frombuffer(chunk[:aligned_size], dtype=dtype)
                    unique_values.update(int(value) for value in np.unique(values))
                    values_read += values.size
                    if progress is not None:
                        progress(values_read, total_values)
                remainder = chunk[aligned_size:]
        finally:
            if data_stream is not source:
                data_stream.close()

    if remainder or values_read != total_values:
        raise ValueError(
            "Annotation data size does not match its NRRD header: "
            "{} of {} values read.".format(values_read, total_values)
        )
    return np.asarray(sorted(unique_values), dtype=dtype)


class WorkerProcessAllen(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)
    progress = pyqtSignal(float)

    def __init__(self):
        super(WorkerProcessAllen, self).__init__()
        self.saving_folder = None
        self.data_local = None
        self.segmentation_local = None
        self.label_local = None
        self.b_val = None
        self.l_val = None
        self.vox_size = None

        self.atlas_data = None
        self.atlas_info = None
        self.segmentation_data = None
        self.unique_label = None
        self.label_info = None
        self.boundary = None
        self.small_mesh_list = {}
        self.mesh_data = None

    def set_data(self, saving_folder, data_local, segmentation_local, label_local, b_val, vox_size):
        self.saving_folder = saving_folder
        self.data_local = data_local
        self.segmentation_local = segmentation_local
        self.label_local = label_local
        self.b_val = b_val
        self.vox_size = vox_size

    def progress_control(self, total_count):
        self.progress.emit(total_count)

    def run(self):
        try:
            self._run()
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit()

    def _run(self):
        self.progress.emit(1)
        segmentation_path = os.path.join(
            self.saving_folder, self.segmentation_local
        )
        self.unique_label = _stream_unique_nrrd_values(
            segmentation_path,
            progress=lambda current, total: self.progress.emit(
                1 + 8 * current / total
            ),
        )
        self.progress.emit(10)
        label_data, header = nrrd.read(segmentation_path)
        self.progress.emit(14)

        n_unique_labels = len(self.unique_label)
        mesh_path = os.path.join(self.saving_folder, 'meshes')
        if not os.path.exists(mesh_path):
            os.mkdir(mesh_path)
        self.progress.emit(15)

        atlas_size = label_data.shape

        axis_info = {'to_HERBS': (2, 0, 1), 'from_HERBS': (1, 2, 0), 'direction_change': (True, True, False),
                     'size': tuple(atlas_size)}

        outfile_axis = open(os.path.join(self.saving_folder, 'atlas_axis_info.pkl'), 'wb')
        pickle.dump(axis_info, outfile_axis)
        outfile_axis.close()

        downloaded_mesh_path = os.path.join(self.saving_folder, 'downloaded_meshes')

        progress_step = np.linspace(15, 30, n_unique_labels)
        missing_mesh_index = []
        for i in range(n_unique_labels):
            ind = self.unique_label[i]
            self.progress.emit(progress_step[i])
            if ind in [0]:
                continue

            filename = os.path.join(downloaded_mesh_path, '{}.obj'.format(ind))

            if os.path.exists(filename):
                try:
                    vertices, faces = obj_data_to_mesh3d(filename)
                    vertices = vertices / self.vox_size

                    vertices[:, 0] = atlas_size[0] - vertices[:, 0]
                    vertices[:, 1] = atlas_size[1] - vertices[:, 1]

                    verts = vertices.copy()
                    verts[:, 0] = vertices[:, 2].copy()
                    verts[:, 1] = vertices[:, 0].copy()
                    verts[:, 2] = vertices[:, 1].copy()

                    md = gl.MeshData(vertexes=verts, faces=faces)

                    outfile = open(os.path.join(mesh_path, '{}.pkl'.format(ind)), 'wb')
                    pickle.dump(md, outfile)
                    outfile.close()
                except IndexError:
                    missing_mesh_index.append(ind)
            else:
                missing_mesh_index.append(ind)

        target = os.path.join(self.saving_folder, "atlas_meshdata.pkl")
        shutil.copyfile(join(mesh_path, '997.pkl'), target)

        self.progress.emit(31)

        infile = open(os.path.join(self.saving_folder, 'atlas_meshdata.pkl'), 'rb')
        self.mesh_data = pickle.load(infile)
        infile.close()
        self.progress.emit(33)

        df = pd.read_csv(os.path.join(self.saving_folder, self.label_local))

        da_labels = df['safe_name'].values
        da_labels[da_labels == 'root'] = 'Brain'
        self.progress.emit(34)

        da_short_label = df['acronym'].values
        da_short_label[da_short_label == 'root'] = 'Brain'
        self.progress.emit(35)

        hex_colors = df['color_hex_triplet'].values
        rgb_colors = []
        for i in range(len(hex_colors)):
            r, g, b = hex2rgb(hex_colors[i])
            rgb_colors.append([r, g, b])
        rgb_colors = np.asarray(rgb_colors)

        self.progress.emit(36)

        levels = []
        structure_id_path = df['structure_id_path'].values
        for i in range(len(structure_id_path)):
            da_path = structure_id_path[i]
            da_path_split = da_path.split('/')
            for j in np.arange(len(da_path_split))[::-1]:
                if da_path_split[j] == '':
                    da_path_split.pop(j)
            levels.append(len(da_path_split))

        self.progress.emit(37)

        self.label_info = {'index': df['id'].values.astype(int),
                           'label': da_labels,
                           'parent': df['parent_structure_id'].fillna(0).values.astype(int),
                           'abbrev': da_short_label,
                           'color': rgb_colors,
                           'level_indicator': levels}

        with open(os.path.join(self.saving_folder, 'atlas_labels.pkl'), 'wb') as handle:
            pickle.dump(self.label_info, handle, protocol=pickle.HIGHEST_PROTOCOL)

        self.progress.emit(38)

        volume_data, header = nrrd.read(os.path.join(self.saving_folder, self.data_local))
        self.progress.emit(45)
        volume_data = np.transpose(volume_data[::-1, ::-1, :], (2, 0, 1))
        self.progress.emit(46)
        self.atlas_data = volume_data.copy()
        self.atlas_data = self.atlas_data - np.min(self.atlas_data)
        self.atlas_data = self.atlas_data / np.max(self.atlas_data)
        self.progress.emit(47)

        b_val = self.b_val.copy()
        if self.b_val[0] == 0:
            b_val[0] = int(atlas_size[0] / 2)
        if self.b_val[2] == 0:
            b_val[2] = int(atlas_size[2] / 2)
        self.progress.emit(48)

        self.atlas_info = [
            {'name': 'anterior', 'values': np.arange(self.atlas_data.shape[0]) * self.vox_size, 'units': 'um'},
            {'name': 'dorsal', 'values': np.arange(self.atlas_data.shape[1]) * self.vox_size, 'units': 'um'},
            {'name': 'right', 'values': np.arange(self.atlas_data.shape[2]) * self.vox_size, 'units': 'um'},
            {'vxsize': self.vox_size,
             'Bregma': [b_val[2], atlas_size[0] - 1 - b_val[0], atlas_size[1] - 1 - b_val[1]]}
        ]
        self.progress.emit(49)

        atlas = {'data': self.atlas_data, 'info': self.atlas_info}

        outfile = open(os.path.join(self.saving_folder, 'atlas_pre_made.pkl'), 'wb')
        pickle.dump(atlas, outfile)
        outfile.close()
        self.progress.emit(53)

        self.segmentation_data = np.transpose(label_data[::-1, ::-1, :], (2, 0, 1))
        self.segmentation_data = self.segmentation_data.astype(int)
        print(self.segmentation_data.shape)

        self.progress.emit(54)

        segment = {'data': self.segmentation_data, 'unique_label': self.unique_label}

        outfile = open(os.path.join(self.saving_folder, 'segment_pre_made.pkl'), 'wb')
        pickle.dump(segment, outfile)
        outfile.close()

        self.progress.emit(58)

        if missing_mesh_index:
            for da_ind in missing_mesh_index:
                render_small_volume(da_ind, mesh_path, self.atlas_data, self.segmentation_data, factor=2, level=0.1)

        self.progress.emit(60)

        file_list = os.listdir(mesh_path)
        progress_step = np.linspace(60, 68, len(file_list))
        for i in range(len(file_list)):
            self.progress.emit(progress_step[i])
            da_file = file_list[i]
            file_name = os.path.basename(da_file)
            da_name, file_extension = os.path.splitext(file_name)
            if file_extension == '.pkl':
                infile = open(os.path.join(mesh_path, da_file), 'rb')
                md = pickle.load(infile)
                infile.close()

                self.small_mesh_list[str(da_name)] = md

        outfile = open(os.path.join(self.saving_folder, 'atlas_small_meshdata.pkl'), 'wb')
        pickle.dump(self.small_mesh_list, outfile)
        outfile.close()
        self.progress.emit(70)

        segment_data_shape = self.segmentation_data.shape

        sagital_contour_img = np.zeros(segment_data_shape, 'i')
        coronal_contour_img = np.zeros(segment_data_shape, 'i')
        horizontal_contour_img = np.zeros(segment_data_shape, 'i')

        # pre-process boundary ----- todo: change this part as optional
        process_index = np.linspace(70, 78, segment_data_shape[0])
        for i in range(segment_data_shape[0]):
            self.progress.emit(process_index[i])
            da_slice = self.segmentation_data[i, :, :].copy()
            contour_img = make_contour_img(da_slice)
            sagital_contour_img[i, :, :] = contour_img

        outfile_ct = open(os.path.join(self.saving_folder, 'sagital_contour_pre_made.pkl'), 'wb')
        pickle.dump(sagital_contour_img, outfile_ct)
        outfile_ct.close()
        self.progress.emit(80)

        process_index = np.linspace(80, 88, segment_data_shape[1])
        for i in range(segment_data_shape[1]):
            self.progress.emit(process_index[i])
            da_slice = self.segmentation_data[:, i, :].copy()
            contour_img = make_contour_img(da_slice)
            coronal_contour_img[:, i, :] = contour_img

        outfile_ct = open(os.path.join(self.saving_folder, 'coronal_contour_pre_made.pkl'), 'wb')
        pickle.dump(coronal_contour_img, outfile_ct)
        outfile_ct.close()
        self.progress.emit(90)

        process_index = np.linspace(90, 98, segment_data_shape[2])
        for i in range(segment_data_shape[2]):
            self.progress.emit(process_index[i])
            da_slice = self.segmentation_data[:, :, i].copy()
            contour_img = make_contour_img(da_slice)
            horizontal_contour_img[:, :, i] = contour_img

        outfile_ct = open(os.path.join(self.saving_folder, 'horizontal_contour_pre_made.pkl'), 'wb')
        pickle.dump(horizontal_contour_img, outfile_ct)
        outfile_ct.close()
        self.progress.emit(100)

        self.boundary = make_boundary_dict(
            sagital_contour_img, coronal_contour_img, horizontal_contour_img
        )

        # target = os.path.join(self.saving_folder, 'atlas_labels.pkl')
        # if not os.path.exists(target):
        #     shutil.copyfile(join(dirname(__file__), "data/atlas_labels.pkl"), target)

        # self.progress.emit(100)

class MeshDownloader(QObject):
    finished = pyqtSignal()
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self):
        super(MeshDownloader, self).__init__()

        self.save_folder = None
        self.segmentation_local = None
        self.success = False

    def set_data(self, save_folder, segmentation_local):
        self.save_folder = save_folder
        self.segmentation_local = os.path.join(save_folder, segmentation_local)

    def run(self):
        try:
            downloaded_mesh_path = os.path.join(self.save_folder, 'downloaded_meshes')
            os.makedirs(downloaded_mesh_path, exist_ok=True)
            self.status.emit("Scanning atlas structure IDs...")
            unique_label = [
                int(value)
                for value in _stream_unique_nrrd_values(
                    self.segmentation_local, progress=self.progress.emit
                )
                if value not in (0, 545)
            ]
            total_labels = len(unique_label)

            for index, label_id in enumerate(unique_label):
                self.status.emit(
                    "Downloading mesh {} of {} (structure {})...".format(
                        index + 1, total_labels, label_id
                    )
                )
                url = (
                    'https://download.alleninstitute.org/informatics-archive/'
                    'current-release/mouse_ccf/annotation/ccf_2017/'
                    'structure_meshes/{}.obj'
                ).format(label_id)
                destination = os.path.join(
                    downloaded_mesh_path, '{}.obj'.format(label_id)
                )
                progress_maximum = max(1, total_labels * 100)
                if not os.path.isfile(destination) or os.path.getsize(destination) == 0:
                    download_file(
                        url,
                        destination,
                        progress=lambda value, base=index: self.progress.emit(
                            base * 100 + value, progress_maximum
                        ),
                    )
                self.progress.emit((index + 1) * 100, progress_maximum)
            self.success = True
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class AllenDownloader(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QVBoxLayout(self)

        self.setWindowTitle("Allen Mice Atlas Downloader")

        self.thread = QThread()
        self.worker = WorkerProcessAllen()
        self.mesh_thread = QThread()
        self.mesh_worker = MeshDownloader()

        self.continue_process = True

        self.voxel_size = 10
        self.bregma_coord = [0, 0, 0]
        radio_group = QFrame()
        radio_group.setStyleSheet('QFrame{border: 1px solid gray; border-radius: 3px}')
        radio_group_layout = QHBoxLayout(radio_group)
        radio_group_layout.setContentsMargins(5, 0, 5, 0)
        radio_group_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vs_rabnt1 = QRadioButton('10 um')
        self.vs_rabnt1.setChecked(True)
        self.vs_rabnt2 = QRadioButton('25 um')
        self.vs_rabnt3 = QRadioButton('50 um')
        radio_group_layout.addWidget(self.vs_rabnt1)
        radio_group_layout.addWidget(self.vs_rabnt2)
        radio_group_layout.addWidget(self.vs_rabnt3)

        self.vs_rabnt1.toggled.connect(self.voxel_size_radio_clicked)
        self.vs_rabnt2.toggled.connect(self.voxel_size_radio_clicked)
        self.vs_rabnt3.toggled.connect(self.voxel_size_radio_clicked)

        self.data_url = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_10.nrrd"
        self.segmentation_url = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_10.nrrd"

        self.label_local = "query.csv"
        self.data_local = "average_template_10.nrrd"
        self.segmentation_local = "annotation_10.nrrd"

        self.saving_folder = None

        self.finish = [False, False, False]
        self.process_finished = False
        self.downloading_atlas = False
        self.downloading_meshes = False
        self.download_threads = {}
        self.download_errors = {}

        self.label_bar = QProgressBar()
        self.label_bar.setMinimumWidth(400)
        self.label_bar.setValue(0)

        self.data_bar = QProgressBar()
        self.data_bar.setMinimumWidth(400)
        self.data_bar.setValue(0)

        self.segmentation_bar = QProgressBar()
        self.segmentation_bar.setMinimumWidth(400)
        self.segmentation_bar.setValue(0)

        self.mesh_bar = QProgressBar()
        self.mesh_bar.setMinimumWidth(400)
        self.mesh_bar.setValue(0)

        self.download_btn = QPushButton()
        self.download_btn. setMinimumWidth(100)
        self.download_btn.setText("Download")

        self.download_mesh_btn = QPushButton()
        self.download_mesh_btn.setMinimumWidth(100)
        self.download_mesh_btn.setText("Download Meshes")
        # self.download_mesh_btn.setEnabled(False)


        valid_input = QIntValidator(0, 99999)

        b_wrap = QFrame()
        b_layout = QHBoxLayout(b_wrap)

        b_label = QLabel('Bregma Coordinates (voxel): ')
        self.b_input1 = QLineEdit('0')
        self.b_input1.setStyleSheet('color: black')
        self.b_input1.setValidator(valid_input)
        self.b_input2 = QLineEdit('0')
        self.b_input2.setStyleSheet('color: black')
        self.b_input2.setValidator(valid_input)
        self.b_input3 = QLineEdit('0')
        self.b_input3.setStyleSheet('color: black')
        self.b_input3.setValidator(valid_input)

        b_layout.addWidget(b_label)
        b_layout.addWidget(self.b_input1)
        b_layout.addWidget(self.b_input2)
        b_layout.addWidget(self.b_input3)

        self.process_btn = QPushButton()
        self.process_btn.setMinimumWidth(100)
        self.process_btn.setText("Process")

        self.process_info = QLabel('The whole process takes some time. \n'
                                   'This window will be closed automatically when processing finished.')

        self.progress = QProgressBar(self)
        self.progress.setMinimumWidth(100)
        self.progress.setTextVisible(False)
        self.progress_label = QLabel()

        progress_wrap = QFrame()
        pw_layout = QHBoxLayout(progress_wrap)
        pw_layout.addWidget(self.progress)
        pw_layout.addWidget(self.progress_label)

        # ok button, used to close window
        ok_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        ok_btn.accepted.connect(self.accept)

        layout.addWidget(radio_group)
        # layout.addWidget(self.label_bar)
        layout.addWidget(self.data_bar)
        layout.addWidget(self.segmentation_bar)
        layout.addWidget(self.download_btn)
        layout.addWidget(self.mesh_bar)
        layout.addWidget(self.download_mesh_btn)
        layout.addWidget(b_wrap)
        layout.addWidget(self.process_info)
        layout.addWidget(self.process_btn)
        layout.addWidget(progress_wrap)
        # layout.addWidget(ok_btn)

        # Binding Button Event
        self.download_btn.clicked.connect(self.download_start)
        self.download_mesh_btn.clicked.connect(self.download_mesh_start)
        self.process_btn.clicked.connect(self.process_start)

        self.b_input1.textChanged.connect(self.bregma_input1_changed)
        self.b_input2.textChanged.connect(self.bregma_input2_changed)
        self.b_input3.textChanged.connect(self.bregma_input3_changed)

    def bregma_input1_changed(self, text):
        if self.downloading_atlas:
            return
        if text == '':
            return
        self.bregma_coord[0] = int(text)

    def bregma_input2_changed(self, text):
        if self.downloading_atlas:
            return
        if text == '':
            return
        self.bregma_coord[1] = int(text)

    def bregma_input3_changed(self, text):
        if self.downloading_atlas:
            return
        if text == '':
            return
        self.bregma_coord[2] = int(text)

    def voxel_size_radio_clicked(self):
        if self.vs_rabnt1.isChecked():
            self.voxel_size = 10
            self.data_url = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_10.nrrd"
            self.segmentation_url = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_10.nrrd"
            self.data_local = "average_template_10.nrrd"
            self.segmentation_local = "annotation_10.nrrd"
        elif self.vs_rabnt2.isChecked():
            self.voxel_size = 25
            self.data_url = 'https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_25.nrrd'
            self.segmentation_url = 'https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_25.nrrd'
            self.data_local = "average_template_25.nrrd"
            self.segmentation_local = "annotation_25.nrrd"
        else:
            self.voxel_size = 50
            self.data_url = 'https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/average_template/average_template_50.nrrd'
            self.segmentation_url = 'https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_50.nrrd'
            self.data_local = "average_template_50.nrrd"
            self.segmentation_local = "annotation_50.nrrd"

    # Download button event
    def download_start(self):
        self.saving_folder = str(QFileDialog.getExistingDirectory(self, "Select Folder to Save Atlas"))

        if self.saving_folder != '':
            self.download_btn.setVisible(False)
            self.process_info.setText('')
            self.downloading_atlas = True
            self.vs_rabnt1.setEnabled(False)
            self.vs_rabnt2.setEnabled(False)
            self.vs_rabnt3.setEnabled(False)

            target = os.path.join(self.saving_folder, self.label_local)
            if not os.path.exists(target):
                shutil.copyfile(join(dirname(__file__), "data/query.csv"), target)

            self.start_thread(self.segmentation_url, self.segmentation_local, self.set_segmentation_bar_value)
            self.start_thread(self.data_url, self.data_local, self.set_data_bar_value)

    def download_mesh_start(self):
        if self.has_active_downloads():
            self.process_info.setText('Please wait until the atlas finish downloading.')
            return

        self.process_info.setText('')

        if self.saving_folder is not None:
            saving_folder = self.saving_folder
        else:
            saving_folder = str(QFileDialog.getExistingDirectory(self, "Select Atlas Folder"))

        if saving_folder != '':
            exist_files = os.listdir(saving_folder)
            if self.data_local not in exist_files:
                self.process_info.setText('Atlas Data file is not in the selected folder. Please download atlas.')
                return
            if self.segmentation_local not in exist_files:
                self.process_info.setText('Segmentation Data file is not in the selected folder.')
                return

            self.download_mesh_btn.setVisible(False)
            self.downloading_meshes = True
            self.download_btn.setEnabled(False)
            self.mesh_bar.setValue(0)
            self.mesh_worker.set_data(saving_folder, self.segmentation_local)
            self.mesh_worker.moveToThread(self.mesh_thread)
            self.mesh_thread.started.connect(self.mesh_worker.run)
            self.mesh_worker.finished.connect(self.mesh_thread.quit)
            self.mesh_worker.finished.connect(self.mesh_download_finished)
            self.mesh_worker.finished.connect(self.mesh_worker.deleteLater)
            self.mesh_thread.finished.connect(self.mesh_thread.deleteLater)
            self.mesh_worker.progress.connect(self.mesh_report_progress)
            self.mesh_worker.status.connect(self.mesh_download_status)
            self.mesh_worker.failed.connect(self.mesh_download_failed)
            self.mesh_thread.start()

    #
    def start_thread(self, url, local, func):
        destination = os.path.join(self.saving_folder, local)
        self.download_errors.pop(local, None)
        thread = DownloadThread(url, destination, parent=self)
        self.download_threads[local] = thread
        thread.download_process_signal.connect(func)
        thread.download_error_signal.connect(
            lambda message, name=local: self.download_failed(name, message)
        )
        thread.finished.connect(
            lambda name=local: self.download_thread_finished(name)
        )
        thread.start()

    def download_failed(self, local, message):
        self.download_errors[local] = message
        self.process_info.setText('Download failed for {}: {}'.format(local, message))

    def download_thread_finished(self, local):
        thread = self.download_threads.pop(local, None)
        if thread is not None:
            thread.deleteLater()
        self.downloading_atlas = self.has_active_downloads()

    def has_active_downloads(self):
        return any(thread.isRunning() for thread in self.download_threads.values())

    def mesh_download_failed(self, message):
        self.downloading_meshes = False
        self.process_info.setText('Mesh download failed: {}'.format(message))

    def mesh_download_finished(self):
        self.downloading_meshes = False
        if self.mesh_worker.success:
            self.finish[2] = True
            self.mesh_bar.setValue(self.mesh_bar.maximum())
            self.process_info.setText('Mesh download finished.')

    # Setting progress bar
    def set_data_bar_value(self, value):
        self.data_bar.setValue(value)
        if value == 100:
            self.finish[0] = True
            if self.finish[0] and self.finish[1]:
                self.downloading_atlas = False
            return

    def set_segmentation_bar_value(self, value):
        self.segmentation_bar.setValue(value)
        if value == 100:
            self.finish[1] = True
            if self.finish[0] and self.finish[1]:
                self.downloading_atlas = False
            return

    def report_progress(self, val):
        val = np.round(val, 2)
        self.progress.setValue(int(val))
        # self.progress.setFormat("%.02f %%" % val)
        self.progress_label.setText("%.02f %%" % val)

    def mesh_report_progress(self, value, maximum):
        self.mesh_bar.setRange(0, max(1, maximum))
        self.mesh_bar.setValue(value)

    def mesh_download_status(self, message):
        self.process_info.setText(message)

    def process_start(self):
        if self.has_active_downloads() or self.downloading_meshes:
            self.process_info.setText('Please wait until finishing downloading files.')
            return
        else:
            self.process_info.setText('')

        if self.saving_folder is not None:
            saving_folder = self.saving_folder
        else:
            saving_folder = str(QFileDialog.getExistingDirectory(self, "Select Atlas Folder"))

        if saving_folder != '':
            # check files
            data_path = os.path.join(saving_folder, self.data_local)
            segmentation_path = os.path.join(saving_folder, self.segmentation_local)
            if not os.path.isfile(data_path) or os.path.getsize(data_path) == 0:
                self.process_info.setText('Atlas Data file is not in the selected folder. Please download atlas.')
                return
            if not os.path.isfile(segmentation_path) or os.path.getsize(segmentation_path) == 0:
                self.process_info.setText('Segmentation Data file is not in the selected folder.')
                return
            if not os.path.exists(os.path.join(saving_folder, self.label_local)):
                target = os.path.join(saving_folder, self.label_local)
                if not os.path.exists(target):
                    shutil.copyfile(join(dirname(__file__), "data/query.csv"), target)
            mesh_folder = os.path.join(saving_folder, 'downloaded_meshes')
            root_mesh = os.path.join(mesh_folder, '997.obj')
            if not os.path.isfile(root_mesh) or os.path.getsize(root_mesh) == 0:
                self.process_info.setText(
                    'Could not find complete downloaded meshes. Please download meshes.')
                return
            self.process_btn.setVisible(False)
            self.worker.set_data(saving_folder, self.data_local, self.segmentation_local, self.label_local,
                                 self.bregma_coord, self.voxel_size)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.finished.connect(self.on_finish)
            self.worker.failed.connect(self.process_failed)
            # self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.worker.progress.connect(self.report_progress)
            self.thread.start()

    def on_finish(self):
        self.thread.quit()
        self.process_finished = True
        self.continue_process = True
        self.accept()

    def process_failed(self, message):
        self.thread.quit()
        self.continue_process = False
        QMessageBox.warning(self, 'Atlas processing failed', message)
        self.reject()

    def closeEvent(self, event):
        if self.process_finished:
            event.accept()
            return
        if (
            self.has_active_downloads()
            or self.mesh_thread.isRunning()
            or self.thread.isRunning()
        ):
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
