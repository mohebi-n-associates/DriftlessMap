import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

import numpy as np


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication


PACKAGE_PATH = Path(__file__).parents[1] / "herbs"
PACKAGE_NAME = "_herbs_label_tree_test"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault(PACKAGE_NAME, package)
SPEC = importlib.util.spec_from_file_location(
    "{}.label_tree".format(PACKAGE_NAME), PACKAGE_PATH / "label_tree.py"
)
label_tree = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = label_tree
SPEC.loader.exec_module(label_tree)


class LabelTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_reset_restores_qcolor_without_type_error(self):
        tree = label_tree.LabelTree()
        tree.set_labels(
            {
                "index": np.array([1]),
                "parent": np.array([-1]),
                "color": np.array([[10, 20, 30]]),
                "label": np.array(["Region"]),
                "abbrev": np.array(["R"]),
            }
        )
        tree.set_label_color(1, QColor(200, 100, 50), recursive=False)
        tree.reset_colors()

        self.assertEqual(tree.labels_by_id[1]["btn"].color().getRgb()[:3], (10, 20, 30))
        np.testing.assert_array_equal(tree.current_lut[1, :3], (10, 20, 30))

    def test_sparse_allen_ids_use_a_compact_display_lut(self):
        tree = label_tree.LabelTree()
        tree.set_labels(
            {
                "index": np.array([1, 614454277]),
                "parent": np.array([-1, 1]),
                "color": np.array([[10, 20, 30], [40, 50, 60]]),
                "label": np.array(["Root", "Sparse"]),
                "abbrev": np.array(["R", "S"]),
            }
        )

        mapped = tree.map_labels(
            np.array([[0, 1, 614454277, 999]], dtype=np.int32)
        )

        self.assertEqual(tree.current_lut.shape, (3, 4))
        self.assertEqual(mapped.dtype, np.uint16)
        np.testing.assert_array_equal(mapped, [[0, 1, 2, 0]])
        np.testing.assert_array_equal(
            tree.color_for_label(614454277), [40, 50, 60, 255]
        )


if __name__ == "__main__":
    unittest.main()
