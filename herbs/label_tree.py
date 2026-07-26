import os
import sys
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
import pyqtgraph as pg
from .uuuuuu import read_qss_file


reset_button_style = '''
QPushButton{
    background: #656565;
    border-radius: 5px;
    color: white;
    border-style: outset;
    border-bottom: 1px solid rgb(30, 30, 30);
    min-height: 16px;
    margin: 0px;
}

QPushButton:hover{
    background-color: #323232;
    border: 1px solid #656565;
}

'''


class SignalBlock(object):
    """Class used to temporarily block a Qt signal connection::

        with SignalBlock(signal, slot):
            # do something that emits a signal; it will
            # not be delivered to slot
    """
    def __init__(self, signal, slot):
        self.signal = signal
        self.slot = slot

    def __enter__(self):
        self.signal.disconnect(self.slot)
        return self

    def __exit__(self, *args):
        self.signal.connect(self.slot)
        

class LabelTree(QWidget):

    class SignalProxy(QObject):
        labelColorChanged = pyqtSignal(object)
        labelsChanged = pyqtSignal()
        resetLabels = pyqtSignal()
    
    def __init__(self, parent=None):
        self._sigprox = LabelTree.SignalProxy()
        self.label_color_changed = self._sigprox.labelColorChanged
        self.labels_changed = self._sigprox.labelsChanged
        self.reset_labels = self._sigprox.resetLabels

        self._block_signals = False
        QWidget.__init__(self, parent)
        label_tree_style = read_qss_file('qss/label_tree.qss')
        self.setStyleSheet(label_tree_style)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.label_level = None
        self.current_lut = None
        self.display_label_ids = None
        self.display_index_by_id = {}
        self.root_item = []
        self.root_acronym = []
        
        self.tree = QTreeWidget(self)
        self.layout.addWidget(self.tree)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.headerItem().setText(0, "id")
        self.tree.headerItem().setText(1, "name")
        self.tree.headerItem().setText(2, "color")
        self.labels_by_id = {}
        self.labels_by_acronym = {}
        self.checked = set()
        self.tree.itemChanged.connect(self.item_change)

        self.layout.addSpacing(10)
        self.reset_btn = QPushButton('Reset colors')
        self.reset_btn.setStyleSheet(reset_button_style)
        self.layout.addWidget(self.reset_btn)
        self.reset_btn.clicked.connect(self.reset_colors)
    
    def set_labels(self, label_data):
        self._block_signals = True
        try:
            if self.current_lut is not None:
                self.clear_labels()

            n_labels = len(label_data['index'])
            if n_labels == 0:
                raise ValueError('Atlas label data is empty.')
            label_ids = np.asarray(label_data['index'], dtype=np.int64)
            self.display_label_ids = np.unique(
                np.concatenate((np.array([0], dtype=np.int64), label_ids))
            )
            self.display_index_by_id = {
                int(label_id): display_index
                for display_index, label_id in enumerate(self.display_label_ids)
            }
            self.label_level = len(self.display_label_ids) - 1
            self.current_lut = np.zeros((self.label_level + 1, 4), dtype=np.ubyte)
            # Pass 1: create every item first so that parent lookups in pass 2
            # do not depend on the order labels appear in the atlas data.
            for i in range(n_labels):
                label_id = int(label_data['index'][i])
                parent = int(label_data['parent'][i])
                color = label_data['color'][i]
                display_index = self.display_index_by_id[label_id]
                self.current_lut[display_index] = np.array(
                    [color[0], color[1], color[2], 255]
                )
                da_color = QColor(color[0], color[1], color[2]).name(QColor.NameFormat.HexRgb)
                name = label_data['label'][i]
                acronym = label_data['abbrev'][i]
                if parent < 0:
                    parent = -1
                    self.root_acronym.append(acronym.encode())
                rec = (label_id, parent, name.encode(), acronym.encode(), da_color.encode())
                self.add_label(*rec)
            # Pass 2: attach each item to its parent (or to the tree root when the
            # parent is missing/negative), registering every top-level node as a
            # root so describe() can always terminate its upward walk.
            tree_root = self.tree.invisibleRootItem()
            for label_id, rec in self.labels_by_id.items():
                item = rec['item']
                parent = rec['parent']
                if parent in self.labels_by_id:
                    parent_item = self.labels_by_id[parent]['item']
                else:
                    parent_item = tree_root
                    self.root_item.append(item)
                parent_item.addChild(item)
                self.tree.setItemWidget(item, 2, rec['btn'])
                rec['btn'].sigColorChanged.connect(self.item_color_changed)
        finally:
            self._block_signals = False
        self.labels_changed.emit()

    def add_label(self, label_id, parent, name, acronym, color):
        item = QTreeWidgetItem([acronym.decode(), name.decode(), ''])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Unchecked)

        btn = pg.ColorButton(color=pg.mkColor(color.decode()))
        btn.defaultColor = QColor(btn.color())
        btn.id = label_id

        # Item creation and tree attachment are split into two passes (see
        # set_labels), so only register the item here; attachment happens later.
        self.labels_by_id[label_id] = {'item': item, 'btn': btn, 'parent': parent}
        item.id = label_id
        self.labels_by_acronym[acronym] = self.labels_by_id[label_id]

    def clear_labels(self):
        root = self.tree.invisibleRootItem()
        for label_id in list(self.labels_by_id.keys()):
            da_item = self.labels_by_id[label_id]['item']
            (da_item.parent() or root).removeChild(da_item)
        # Reset all bookkeeping so a subsequent set_labels() starts clean and
        # does not re-attach or treat stale entries as roots.
        self.labels_by_id = {}
        self.labels_by_acronym = {}
        self.root_item = []
        self.root_acronym = []
        self.checked = set()
        self.display_label_ids = None
        self.display_index_by_id = {}

    def item_change(self, item, col):
        checked = item.checkState(0) == Qt.CheckState.Checked
        with SignalBlock(self.tree.itemChanged, self.item_change):
            self.check_recursive(item, checked)
    
        if not self._block_signals:
            self.labels_changed.emit()

    def check_recursive(self, item, checked):
        if checked:
            self.checked.add(item.id)
            item.setCheckState(0, Qt.CheckState.Checked)
        else:
            if item.id in self.checked:
                self.checked.remove(item.id)
            item.setCheckState(0, Qt.CheckState.Unchecked)
    
        for i in range(item.childCount()):
            self.check_recursive(item.child(i), checked)

    def item_color_changed(self, btn):
        color = btn.color()
        self.set_label_color(btn.id, color)

    def set_label_color(self, label_id, color, recursive=True, emit=True):
        item = self.labels_by_id[label_id]['item']
        btn = self.labels_by_id[label_id]['btn']
        rgb_color = (color.red(), color.green(), color.blue(), color.alpha())
        display_index = self.display_index_by_id[int(label_id)]
        self.current_lut[display_index] = np.array(
            [rgb_color[0], rgb_color[1], rgb_color[2], rgb_color[3]]
        )
        with SignalBlock(btn.sigColorChanged, self.item_color_changed):
            btn.setColor(color)
        if recursive:
            for i in range(item.childCount()):
                ch = item.child(i)
                self.set_label_color(ch.id, color, recursive=recursive, emit=False)
        if emit:
            self.label_color_changed.emit((label_id, self.current_lut[label_id]))
    
    def lookup_table(self):
        lut = np.zeros((self.label_level + 1, 4), dtype=np.ubyte)
        for layer_id in self.checked:
            display_index = self.display_index_by_id.get(int(layer_id))
            if display_index is None:
                continue
            lut[display_index] = self.labels_by_id[layer_id]['btn'].color(mode='byte')
        return lut

    def map_labels(self, label_data):
        """Map sparse atlas structure IDs to compact display-LUT indexes."""
        label_data = np.asarray(label_data)
        if self.display_label_ids is None:
            return label_data

        flat_labels = label_data.reshape(-1)
        mapped_indexes = np.searchsorted(self.display_label_ids, flat_labels)
        valid = mapped_indexes < len(self.display_label_ids)
        clipped_indexes = np.minimum(mapped_indexes, len(self.display_label_ids) - 1)
        valid &= self.display_label_ids[clipped_indexes] == flat_labels

        dtype = np.uint16 if self.label_level <= np.iinfo(np.uint16).max else np.uint32
        mapped = np.zeros(flat_labels.shape, dtype=dtype)
        mapped[valid] = mapped_indexes[valid]
        return mapped.reshape(label_data.shape)

    def color_for_label(self, label_id):
        """Return the configured RGBA color for an original structure ID."""
        display_index = self.display_index_by_id.get(int(label_id))
        if display_index is None:
            return np.zeros(4, dtype=np.ubyte)
        return self.current_lut[display_index]

    def reset_colors(self):
        try:
            self.blockSignals(True)
            for k, v in self.labels_by_id.items():
                self.set_label_color(k, v['btn'].defaultColor, recursive=False, emit=False)
        finally:
            self.blockSignals(False)
            self.reset_labels.emit()
    
    def describe(self, label_id):
        if label_id == 0:
            return ''
        else:
            if label_id not in self.labels_by_id:
                return "Unknown label: %d" % label_id
        descr = []
        item = self.labels_by_id[label_id]['item']
        name = str(item.text(1))
        while item is not None and item not in self.root_item:
            # self.labels_by_acronym[b'Brain']['item'], self.labels_by_acronym[b'SpC']['item'], self.labels_by_acronym[b'IE']['item']
            descr.insert(0, str(item.text(0)))
            item = item.parent()
        return '[%d]' % label_id + ' > '.join(descr) + "  :  " + name
