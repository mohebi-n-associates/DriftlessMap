import copy
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
import numpy as np
from .uuuuuu import read_qss_file
from .resources import resource_path

dialog_style = '''
QDialog {
    background-color: rgb(50, 50, 50);
    color: white;
    font-size: 12px;
    width: 50px;
}

QLabel {
    color: white;
    width: 50px;
}
'''


class LayerSettingDialog(QDialog):
    def __init__(self, window_name, min_val, max_val, val):
        super().__init__()

        self.setWindowTitle(window_name)
        self.setStyleSheet(dialog_style)

        val = int(min(max(val, min_val), max_val))
        self.val = val

        # The range must be set before the value, or larger values clamp.
        self.val_slider = QSlider(Qt.Orientation.Horizontal)
        self.val_slider.setRange(min_val, max_val)
        self.val_slider.setValue(val)
        self.val_slider.setSingleStep(1)
        self.val_slider.valueChanged.connect(self.val_spinbox_changed)

        self.val_spinbox = QSpinBox()
        self.val_spinbox.setRange(min_val, max_val)
        self.val_spinbox.setValue(val)
        self.val_spinbox.setSingleStep(1)
        self.val_spinbox.valueChanged.connect(self.value_changed)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QHBoxLayout()
        layout.addWidget(self.val_slider)
        layout.addWidget(self.val_spinbox)
        layout.addSpacing(10)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def val_spinbox_changed(self):
        val = self.val_slider.value()
        self.val = val
        self.val_spinbox.setValue(val)

    def value_changed(self):
        val = self.val_spinbox.value()
        self.val = val
        self.val_slider.setValue(val)


class SliceSettingDialog(QDialog):
    CUTS = ['Coronal', 'Sagittal', 'Horizontal']

    def __init__(self, cut='Coronal', width=0, height=0, distance=0):
        super().__init__()

        self.setWindowTitle('Current Slice Settings')
        self.setStyleSheet(dialog_style)

        self.cut = cut if cut in self.CUTS else 'Coronal'
        self.width = float(width or 0)
        self.height = float(height or 0)
        self.distance = float(distance or 0)

        self.cut_combo = QComboBox()
        self.cut_combo.addItems(self.CUTS)
        self.cut_combo.setCurrentText(self.cut)
        self.cut_combo.currentIndexChanged.connect(self.cut_changed)

        width_label = QLabel('Width (mm):')
        height_label = QLabel('Height (mm):')
        distance_label = QLabel('Distance w.r.t. Bregma (mm):')

        self.width_val = QDoubleSpinBox()
        self.width_val.setRange(-50, 50)
        self.width_val.setValue(self.width)
        self.width_val.valueChanged.connect(self.width_val_changed)
        self.height_val = QDoubleSpinBox()
        self.height_val.setRange(-50, 50)
        self.height_val.setValue(self.height)
        self.height_val.valueChanged.connect(self.height_val_changed)
        self.distance_val = QDoubleSpinBox()
        self.distance_val.setRange(-50, 50)
        self.distance_val.setValue(self.distance)
        self.distance_val.valueChanged.connect(self.distance_val_changed)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        content_frame = QFrame()
        content_layout = QGridLayout(content_frame)
        content_layout.addWidget(self.cut_combo, 0, 0, 1, 2)
        content_layout.addWidget(width_label, 1, 0, 1, 1)
        content_layout.addWidget(self.width_val, 1, 1, 1, 1)
        content_layout.addWidget(height_label, 2, 0, 1, 1)
        content_layout.addWidget(self.height_val, 2, 1, 1, 1)
        content_layout.addWidget(distance_label, 3, 0, 1, 1)
        content_layout.addWidget(self.distance_val, 3, 1, 1, 1)

        layout = QVBoxLayout()
        layout.addWidget(content_frame)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def cut_changed(self):
        self.cut = self.cut_combo.currentText()

    def width_val_changed(self):
        self.width = self.width_val.value()

    def height_val_changed(self):
        self.height = self.height_val.value()

    def distance_val_changed(self):
        self.distance = self.distance_val.value()


class QDoubleButton(QPushButton):
    right_clicked = pyqtSignal()
    left_clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super(QDoubleButton, self).__init__(*args, **kwargs)

        btn_style = read_qss_file('qss/object_text_button.qss')
        self.setStyleSheet(btn_style)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.timeout)

        self.is_double = False
        self.is_left_click = True

        self.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if not self.timer.isActive():
                self.timer.start()

            self.is_left_click = False
            if event.button() == Qt.MouseButton.LeftButton:
                self.is_left_click = True

            return True

        elif event.type() == QEvent.Type.MouseButtonDblClick:
            self.is_double = True
            return True

        return False

    def timeout(self):
        if self.is_double:
            self.double_clicked.emit()
        else:
            if self.is_left_click:
                self.left_clicked.emit()
            else:
                self.right_clicked.emit()

        self.is_double = False


class QLabelClickable(QLabel):
    # doubleClicked = pyqtSignal(object)
    clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super(QLabelClickable, self).__init__(parent)

    def mousePressEvent(self, event):
        self.ultimo = 'Click'

    def mouseReleaseEvent(self, event):
        if self.ultimo == 'Click':
            QTimer.singleShot(QApplication.instance().doubleClickInterval(),
                              self.performSingleClickAction)
        else:
            self.ultimo = 'doubleClick'
            self.clicked.emit(self.ultimo)

    def mouseDoubleClickEvent(self, event):
        self.ultimo = 'doubleClick'

    def performSingleClickAction(self):
        if self.ultimo == 'Click':
            self.clicked.emit(self.ultimo)
            self.update()


class QFrameClickable(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, parent=None):
        super(QFrameClickable, self).__init__(parent)

    # def mousePressEvent(self, QMouseEvent):
    #     if QMouseEvent.button() == Qt.MouseButton.LeftButton:
    #         self.clicked.emit()
    #     elif QMouseEvent.button() == Qt.MouseButton.RightButton:
    #         self.clicked.emit()
    #     self.update()

    def mousePressEvent(self, event):
        self.ultimo = 'Click'

    def mouseReleaseEvent(self, event):
        if self.ultimo == 'Click':
            QTimer.singleShot(QApplication.instance().doubleClickInterval(),
                              self.performSingleClickAction)
        else:
            self.ultimo = 'doubleClick'
            self.clicked.emit(self.ultimo)

    def mouseDoubleClickEvent(self, event):
        self.ultimo = 'doubleClick'

    def performSingleClickAction(self):
        if self.ultimo == 'Click':
            self.clicked.emit(self.ultimo)
            self.update()


class LineEditEntered(QLineEdit):
    sig_return_pressed = pyqtSignal()

    def __init__(self):
        QLineEdit.__init__(self)

    def keyPressEvent(self, event):
        super(LineEditEntered, self).keyPressEvent(event)

        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.sig_return_pressed.emit()


class IntLineEdit(QLineEdit):
    sig_text_changed = pyqtSignal(object)
    def __init__(self, w_id, text=None, parent=None):
        QLineEdit.__init__(self)
        self.id = w_id
        if text is not None:
            self.setText(text)
        self.setValidator(QIntValidator())
        self.textChanged.connect(self.editing_text)

    def editing_text(self, text_val):
        self.sig_text_changed.emit((self.id, text_val))


class FaceCombo(QComboBox):
    sig_text_changed = pyqtSignal(object)
    def __init__(self, w_id, parent=None):
        QComboBox.__init__(self)
        self.id = w_id
        self.currentIndexChanged.connect(self.index_changed)

    def index_changed(self, index):
        self.sig_text_changed.emit((self.id, index))


class LinearSiliconInfoDialog(QDialog):
    def __init__(self, pss):
        super().__init__()

        self.setWindowTitle('Linear Silicon Probe Geometry Setting Window')
        self.setStyleSheet(dialog_style)

        btn_box = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.button_box = QDialogButtonBox(btn_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        if pss is None:
            self.probe_settings = {'probe_length': 0,
                                   'probe_thickness': 0,
                                   'tip_length': 0,
                                   'site_height': 0,
                                   'site_width': 0,
                                   'per_max_sites': [0],
                                   'sites_distance': [0],
                                   'x_bias': [0],
                                   'y_bias': [0]}
        else:
            # Edit a private copy so Cancel leaves the caller's settings intact.
            self.probe_settings = copy.deepcopy(pss)

        n_column = len(self.probe_settings['x_bias'])

        fig_label = QLabel()
        pixmap = QPixmap(resource_path('icons/toolbar/linear_silicon.png'))
        fig_label.setPixmap(pixmap)
        fig_label.setFixedHeight(300)

        right_frame = QFrame()
        self.right_layout = QGridLayout(right_frame)

        probe_length_label = QLabel('A Probe Length (um): ')
        self.probe_length_input = IntLineEdit(0, str(self.probe_settings['probe_length']))
        self.probe_length_input.sig_text_changed.connect(self.probe_length_changed)

        thickness_label = QLabel('Probe Thickness (um): ')
        self.thickness_input = IntLineEdit(0, str(self.probe_settings['probe_thickness']))
        self.thickness_input.sig_text_changed.connect(self.probe_thickness_changed)

        tip_length_label = QLabel('B Tip Length (um): ')
        self.tip_length_input = IntLineEdit(0, str(self.probe_settings['tip_length']))
        self.tip_length_input.sig_text_changed.connect(self.tip_length_changed)

        site_height_label = QLabel('Site Height (um): ')
        self.site_height_input = IntLineEdit(0, str(self.probe_settings['site_height']))
        self.site_height_input.sig_text_changed.connect(self.site_height_changed)

        site_width_label = QLabel('Site Width (um): ')
        self.site_width_input = IntLineEdit(0, str(self.probe_settings['site_width']))
        self.site_width_input.sig_text_changed.connect(self.site_width_changed)

        n_column_label = QLabel('Number of columns: ')
        self.n_column_spinbox = QSpinBox()
        self.n_column_spinbox.setRange(1, 10)
        self.n_column_spinbox.setValue(n_column)

        row_names = [QLabel('Number of Sites: '), QLabel('C Sites Distance (um): '),
                     QLabel('D X Bias (um): '), QLabel('E Y Bias (um): ')]

        self.sites_distance_wl = []
        self.per_max_sites_wl = []
        self.x_bias_wl = []
        self.y_bias_wl = []
        for i in range(n_column):
            self.sites_distance_wl.append(IntLineEdit(i, str(self.probe_settings['sites_distance'][i])))
            self.per_max_sites_wl.append(IntLineEdit(i, str(self.probe_settings['per_max_sites'][i])))
            self.x_bias_wl.append(IntLineEdit(i, str(self.probe_settings['x_bias'][i])))
            self.y_bias_wl.append(IntLineEdit(i, str(self.probe_settings['y_bias'][i])))
            self.sites_distance_wl[-1].sig_text_changed.connect(self.sites_distance_changed)
            self.per_max_sites_wl[-1].sig_text_changed.connect(self.per_max_sites_changed)
            self.x_bias_wl[-1].sig_text_changed.connect(self.x_bias_changed)
            self.y_bias_wl[-1].sig_text_changed.connect(self.y_bias_changed)

        # connect
        self.n_column_spinbox.valueChanged.connect(self.n_column_changed)

        self.right_layout.addWidget(probe_length_label, 0, 0, 1, 1)
        self.right_layout.addWidget(self.probe_length_input, 0, 1, 1, 1)
        self.right_layout.addWidget(thickness_label, 1, 0, 1, 1)
        self.right_layout.addWidget(self.thickness_input, 1, 1, 1, 1)
        self.right_layout.addWidget(tip_length_label, 2, 0, 1, 1)
        self.right_layout.addWidget(self.tip_length_input, 2, 1, 1, 1)
        self.right_layout.addWidget(site_height_label, 3, 0, 1, 1)
        self.right_layout.addWidget(self.site_height_input, 3, 1, 1, 1)
        self.right_layout.addWidget(site_width_label, 4, 0, 1, 1)
        self.right_layout.addWidget(self.site_width_input, 4, 1, 1, 1)

        self.right_layout.addWidget(n_column_label, 5, 0, 1, 1)
        self.right_layout.addWidget(self.n_column_spinbox, 5, 1, 1, 1)

        for i in range(len(row_names)):
            self.right_layout.addWidget(row_names[i], 6 + i, 0, 1, 1)

        for j in range(n_column):
            self.right_layout.addWidget(self.per_max_sites_wl[j], 6, j + 1, 1, 1)
            self.right_layout.addWidget(self.sites_distance_wl[j], 7, j + 1, 1, 1)
            self.right_layout.addWidget(self.x_bias_wl[j], 8, j + 1, 1, 1)
            self.right_layout.addWidget(self.y_bias_wl[j], 9, j + 1, 1, 1)

        out_frame = QFrame()
        out_layout = QHBoxLayout(out_frame)
        out_layout.addWidget(fig_label)
        out_layout.addWidget(right_frame)

        # add widget to layout
        layout = QVBoxLayout()
        layout.addWidget(out_frame)
        layout.addSpacing(10)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def n_column_changed(self):
        n_column = self.n_column_spinbox.value()
        exist_column = len(self.x_bias_wl)
        if n_column == exist_column:
            return

        if n_column < exist_column:
            del_index = np.arange(n_column, exist_column)[::-1]
            for da_ind in del_index:
                self.sites_distance_wl[da_ind].sig_text_changed.disconnect(self.sites_distance_changed)
                self.per_max_sites_wl[da_ind].sig_text_changed.disconnect(self.per_max_sites_changed)
                self.x_bias_wl[da_ind].sig_text_changed.disconnect(self.x_bias_changed)
                self.y_bias_wl[da_ind].sig_text_changed.disconnect(self.y_bias_changed)

                self.right_layout.removeWidget(self.sites_distance_wl[da_ind])
                self.right_layout.removeWidget(self.per_max_sites_wl[da_ind])
                self.right_layout.removeWidget(self.x_bias_wl[da_ind])
                self.right_layout.removeWidget(self.y_bias_wl[da_ind])
                self.sites_distance_wl[da_ind].deleteLater()
                self.per_max_sites_wl[da_ind].deleteLater()
                self.x_bias_wl[da_ind].deleteLater()
                self.y_bias_wl[da_ind].deleteLater()
                del self.sites_distance_wl[da_ind]
                del self.per_max_sites_wl[da_ind]
                del self.x_bias_wl[da_ind]
                del self.y_bias_wl[da_ind]

                del self.probe_settings['sites_distance'][da_ind]
                del self.probe_settings['per_max_sites'][da_ind]
                del self.probe_settings['x_bias'][da_ind]
                del self.probe_settings['y_bias'][da_ind]
        else:
            for da_ind in range(exist_column, n_column):
                self.sites_distance_wl.append(IntLineEdit(da_ind, str(0)))
                self.per_max_sites_wl.append(IntLineEdit(da_ind, str(0)))
                self.x_bias_wl.append(IntLineEdit(da_ind, str(0)))
                self.y_bias_wl.append(IntLineEdit(da_ind, str(0)))

                self.sites_distance_wl[-1].sig_text_changed.connect(self.sites_distance_changed)
                self.per_max_sites_wl[-1].sig_text_changed.connect(self.per_max_sites_changed)
                self.x_bias_wl[-1].sig_text_changed.connect(self.x_bias_changed)
                self.y_bias_wl[-1].sig_text_changed.connect(self.y_bias_changed)

                self.right_layout.addWidget(self.per_max_sites_wl[-1], 6, da_ind + 1, 1, 1)
                self.right_layout.addWidget(self.sites_distance_wl[-1], 7, da_ind + 1, 1, 1)
                self.right_layout.addWidget(self.x_bias_wl[-1], 8, da_ind + 1, 1, 1)
                self.right_layout.addWidget(self.y_bias_wl[-1], 9, da_ind + 1, 1, 1)

                self.probe_settings['sites_distance'].append(0)
                self.probe_settings['per_max_sites'].append(0)
                self.probe_settings['x_bias'].append(0)
                self.probe_settings['y_bias'].append(0)
        self._refresh_ok_button()

    FIELD_RULES = {
        'probe_length': lambda v, s: v > 0,
        'probe_thickness': lambda v, s: v >= 0,
        'tip_length': lambda v, s: 0 <= v <= s['probe_length'],
        'site_height': lambda v, s: v > 0,
        'site_width': lambda v, s: v > 0,
        'sites_distance': lambda v, s: v > 0,
        'per_max_sites': lambda v, s: v > 0,
        'x_bias': lambda v, s: True,
        'y_bias': lambda v, s: v >= 0,
    }

    def _field_widgets(self):
        return {
            'probe_length': [self.probe_length_input],
            'probe_thickness': [self.thickness_input],
            'tip_length': [self.tip_length_input],
            'site_height': [self.site_height_input],
            'site_width': [self.site_width_input],
            'sites_distance': self.sites_distance_wl,
            'per_max_sites': self.per_max_sites_wl,
            'x_bias': self.x_bias_wl,
            'y_bias': self.y_bias_wl,
        }

    def _set_field(self, key, obj):
        w_id, text_val = obj
        try:
            value = int(text_val)
        except ValueError:
            value = None
        if value is not None:
            if isinstance(self.probe_settings[key], list):
                self.probe_settings[key][w_id] = value
            else:
                self.probe_settings[key] = value
        self._refresh_ok_button()

    def _refresh_ok_button(self):
        """Enable OK only when every field holds a valid value."""
        valid = True
        for key, widgets in self._field_widgets().items():
            for widget in widgets:
                try:
                    value = int(widget.text())
                except ValueError:
                    valid = False
                    break
                if not self.FIELD_RULES[key](value, self.probe_settings):
                    valid = False
                    break
            if not valid:
                break
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def probe_length_changed(self, obj):
        self._set_field('probe_length', obj)

    def probe_thickness_changed(self, obj):
        self._set_field('probe_thickness', obj)

    def tip_length_changed(self, obj):
        self._set_field('tip_length', obj)

    def site_width_changed(self, obj):
        self._set_field('site_width', obj)

    def site_height_changed(self, obj):
        self._set_field('site_height', obj)

    def sites_distance_changed(self, obj):
        self._set_field('sites_distance', obj)

    def per_max_sites_changed(self, obj):
        self._set_field('per_max_sites', obj)

    def x_bias_changed(self, obj):
        self._set_field('x_bias', obj)

    def y_bias_changed(self, obj):
        self._set_field('y_bias', obj)


class MultiProbePlanningDialog(QDialog):
    def __init__(self, multi_settings):
        super().__init__()

        self.setWindowTitle('Multi-Probe Geometry Setting Window')
        self.setStyleSheet(dialog_style)

        btn_box = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.button_box = QDialogButtonBox(btn_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        fig_label = QLabel()
        pixmap = QPixmap(resource_path('icons/toolbar/multi_probe.png'))
        fig_label.setPixmap(pixmap)
        fig_label.setFixedHeight(300)

        # initial values
        if multi_settings is None:
            self.multi_settings = {}
            self.multi_settings['x_vals'] = [-300, 300, -100, -300, 300]
            self.multi_settings['y_vals'] = [-100, -100, 0, 100, 100]
            self.multi_settings['faces'] = [0, 0, 0, 0, 0]

        else:
            # Edit a private copy so Cancel leaves the caller's settings intact.
            self.multi_settings = copy.deepcopy(multi_settings)

        n_probe = len(self.multi_settings['x_vals'])

        # initial widgets
        n_probe_label = QLabel('Number of Probes (stk): ')
        self.n_probe_spinbox = QSpinBox()
        self.n_probe_spinbox.setMinimum(2)
        self.n_probe_spinbox.setValue(n_probe)

        row_names = [QLabel('X Coordinates (um): '), QLabel('Y Coordinates (um): '),
                     QLabel('Probe Faces: ')]

        self.x_val_wl = []
        self.y_val_wl = []
        self.faces_wl = []
        # self.types_wl = []
        for i in range(n_probe):
            self.x_val_wl.append(IntLineEdit(i, str(self.multi_settings['x_vals'][i])))
            self.y_val_wl.append(IntLineEdit(i, str(self.multi_settings['y_vals'][i])))
            self.faces_wl.append(FaceCombo(i))
            self.faces_wl[-1].addItems(['Out', 'In', 'Left', 'Right'])
            face_index = int(self.multi_settings['faces'][i])
            self.faces_wl[-1].setCurrentIndex(face_index if 0 <= face_index <= 3 else 0)
            self.x_val_wl[-1].sig_text_changed.connect(self.x_vals_changed)
            self.y_val_wl[-1].sig_text_changed.connect(self.y_vals_changed)
            self.faces_wl[-1].sig_text_changed.connect(self.faces_changed)

        # connect
        self.n_probe_spinbox.valueChanged.connect(self.n_probe_changed)

        # add widgets to layout
        right_frame = QFrame()
        self.right_layout = QGridLayout(right_frame)
        self.right_layout.addWidget(n_probe_label, 0, 0, 1, 1)
        self.right_layout.addWidget(self.n_probe_spinbox, 0, 1, 1, 1)

        for i in range(len(row_names)):
            self.right_layout.addWidget(row_names[i], 1 + i, 0, 1, 1)

        for j in range(n_probe):
            self.right_layout.addWidget(self.x_val_wl[j], 1, j + 1, 1, 1)
            self.right_layout.addWidget(self.y_val_wl[j], 2, j + 1, 1, 1)
            self.right_layout.addWidget(self.faces_wl[j], 3, j + 1, 1, 1)

        #
        out_frame = QFrame()
        out_layout = QHBoxLayout(out_frame)
        out_layout.addWidget(fig_label)
        out_layout.addWidget(right_frame)

        # add widget to layout
        layout = QVBoxLayout()
        layout.addWidget(out_frame)
        layout.addSpacing(10)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def n_probe_changed(self):
        n_probe = self.n_probe_spinbox.value()
        exist_probe = len(self.x_val_wl)
        if n_probe == exist_probe:
            return

        if n_probe < exist_probe:
            del_index = np.arange(n_probe, exist_probe)[::-1]
            for da_ind in del_index:
                self.x_val_wl[da_ind].sig_text_changed.disconnect(self.x_vals_changed)
                self.y_val_wl[da_ind].sig_text_changed.disconnect(self.y_vals_changed)
                self.faces_wl[da_ind].sig_text_changed.disconnect(self.faces_changed)

                self.right_layout.removeWidget(self.x_val_wl[da_ind])
                self.right_layout.removeWidget(self.y_val_wl[da_ind])
                self.right_layout.removeWidget(self.faces_wl[da_ind])
                self.x_val_wl[da_ind].deleteLater()
                self.y_val_wl[da_ind].deleteLater()
                self.faces_wl[da_ind].deleteLater()
                del self.x_val_wl[da_ind]
                del self.y_val_wl[da_ind]
                del self.faces_wl[da_ind]

                del self.multi_settings['x_vals'][da_ind]
                del self.multi_settings['y_vals'][da_ind]
                del self.multi_settings['faces'][da_ind]
        else:
            for da_ind in range(exist_probe, n_probe):
                self.x_val_wl.append(IntLineEdit(da_ind, str(0)))
                self.y_val_wl.append(IntLineEdit(da_ind, str(0)))
                self.faces_wl.append(FaceCombo(da_ind))
                self.faces_wl[-1].addItems(['Out', 'In', 'Left', 'Right'])

                self.x_val_wl[-1].sig_text_changed.connect(self.x_vals_changed)
                self.y_val_wl[-1].sig_text_changed.connect(self.y_vals_changed)
                self.faces_wl[-1].sig_text_changed.connect(self.faces_changed)

                self.right_layout.addWidget(self.x_val_wl[-1], 1, da_ind + 1, 1, 1)
                self.right_layout.addWidget(self.y_val_wl[-1], 2, da_ind + 1, 1, 1)
                self.right_layout.addWidget(self.faces_wl[-1], 3, da_ind + 1, 1, 1)

                self.multi_settings['x_vals'].append(0)
                self.multi_settings['y_vals'].append(0)
                self.multi_settings['faces'].append(0)

    #
    def _set_coordinate(self, key, obj):
        w_id, text_val = obj
        try:
            self.multi_settings[key][w_id] = int(text_val)
        except ValueError:
            pass
        valid = True
        for widget in self.x_val_wl + self.y_val_wl:
            try:
                int(widget.text())
            except ValueError:
                valid = False
                break
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def x_vals_changed(self, obj):
        self._set_coordinate('x_vals', obj)

    def y_vals_changed(self, obj):
        self._set_coordinate('y_vals', obj)

    def faces_changed(self, obj):
        w_id = obj[0]
        index_val = obj[1]
        self.multi_settings['faces'][w_id] = index_val



