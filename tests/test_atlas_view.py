import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from herbs.atlas_view import AtlasView, PageController
from herbs.slice_stacks import SliceStacks, image_position_in_bounds


class PageControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_programmatic_page_changes_render_immediately(self):
        controller = PageController()
        pages = []
        controller.sig_page_changed.connect(pages.append)
        controller.set_max(20)

        controller.set_val(7)

        self.assertEqual(pages, [7])
        self.assertEqual(controller.page_label.text(), "7")

    def test_dragging_coalesces_intermediate_pages_and_keeps_latest(self):
        controller = PageController()
        pages = []
        controller.sig_page_changed.connect(pages.append)
        controller.set_max(20)
        controller.page_slider.setSliderDown(True)

        controller.page_slider.setValue(2)
        controller.page_slider.setValue(6)
        controller.page_slider.setValue(11)

        self.assertEqual(pages, [])
        self.assertEqual(controller.page_label.text(), "11")

        controller._flush_pending_page()

        self.assertEqual(pages, [11])

    def test_arrow_keys_advance_a_focused_atlas_plane(self):
        image = SliceStacks()
        controller = PageController()
        image.sig_page_step_requested.connect(controller.step_by)
        controller.set_max(10)
        controller.set_val(5)

        image.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self.assertEqual(controller.page_slider.value(), 6)
        image.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self.assertEqual(controller.page_slider.value(), 5)

        controller.set_val(0)
        image.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Left,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self.assertEqual(controller.page_slider.value(), 0)
        controller.set_val(10)
        image.keyPressEvent(
            QKeyEvent(
                QKeyEvent.Type.KeyPress,
                Qt.Key.Key_Right,
                Qt.KeyboardModifier.NoModifier,
            )
        )
        self.assertEqual(controller.page_slider.value(), 10)


class AtlasViewPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_sparse_labels_and_boundaries_render_without_dense_volumes(self):
        view = AtlasView()
        shape = (4, 5, 6)
        atlas = np.linspace(
            0, 1, np.prod(shape), dtype=np.float32
        ).reshape(shape)
        labels = np.zeros(shape, dtype=np.int32)
        labels[1:3, 1:4, 1:5] = 614454277
        atlas_info = [
            {"name": "anterior"},
            {"name": "dorsal"},
            {"name": "right"},
            {"vxsize": 10, "Bregma": [2, 2, 3]},
        ]
        label_info = {
            "index": np.array([1, 614454277]),
            "parent": np.array([0, 1]),
            "color": np.array([[10, 20, 30], [40, 50, 60]]),
            "label": np.array(["Root", "Region"]),
            "abbrev": np.array(["R", "X"]),
        }

        view.set_data(atlas, labels, atlas_info, label_info, None)

        self.assertEqual(view.label_tree.current_lut.shape, (3, 4))
        self.assertEqual(view.cimg.label_data.dtype, np.int32)
        self.assertEqual(view.cimg.label_img.image.dtype, np.uint16)
        self.assertIsNone(view.atlas_boundary)

        view.set_boundary_visible(True)

        self.assertEqual(
            view.cimg.boundary.image.shape, view.cimg.label_data.shape
        )

    def test_image_edge_hover_coordinates_are_rejected(self):
        image = np.zeros((3, 4), dtype=np.uint8)

        self.assertTrue(image_position_in_bounds(QPointF(3.999, 2.999), image))
        self.assertFalse(image_position_in_bounds(QPointF(4, 2), image))
        self.assertFalse(image_position_in_bounds(QPointF(3, 3), image))
        self.assertFalse(image_position_in_bounds(QPointF(-0.01, 1), image))


if __name__ == "__main__":
    unittest.main()
