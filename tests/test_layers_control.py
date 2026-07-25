import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest

import numpy as np


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication


PACKAGE_PATH = Path(__file__).parents[1] / "herbs"
PACKAGE_NAME = "_herbs_layers_control_test"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault(PACKAGE_NAME, package)
SPEC = importlib.util.spec_from_file_location(
    "{}.layers_control".format(PACKAGE_NAME), PACKAGE_PATH / "layers_control.py"
)
layers_control = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = layers_control
SPEC.loader.exec_module(layers_control)


def layer_state(selected_indexes):
    thumbnails = [np.zeros((4, 4), dtype=np.uint8) + index for index in range(3)]
    return {
        "layer_link": ["Image", "img-mask", "img-overlay"],
        "layer_color": [[255, 255, 255], [10, 20, 30], [40, 50, 60]],
        "layer_thumbnail": thumbnails,
        "layer_opacity": [100, 25, 70],
        "layer_blend_mode": ["Plus", "Multiply", "Overlay"],
        "current_layer_index": selected_indexes,
    }


class LayersControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_noncontiguous_selection_is_restored_exactly(self):
        control = layers_control.LayersControl()
        control.set_layer_data(layer_state([2, 0]))

        self.assertEqual(control.current_layer_index, [2, 0])
        self.assertEqual([layer.is_checked() for layer in control.layer_list], [True, False, True])

    def test_empty_layer_state_does_not_index_a_missing_widget(self):
        control = layers_control.LayersControl()
        data = layer_state([])
        for key in (
            "layer_link", "layer_color", "layer_thumbnail", "layer_opacity", "layer_blend_mode"
        ):
            data[key] = []

        control.set_layer_data(data)

        self.assertEqual(control.current_layer_index, [])
        self.assertEqual(control.layer_list, [])

    def test_delete_toolbar_removes_selected_layers_not_a_boolean_id(self):
        control = layers_control.LayersControl()
        control.set_layer_data(layer_state([2, 0]))
        deleted = []
        control.sig_layer_deleted.connect(deleted.append)

        control.delete_current_layers()

        self.assertEqual(deleted, ["img-overlay", "Image"])
        self.assertEqual(control.layer_link, ["img-mask"])
        self.assertEqual(control.current_layer_index, [])

    def test_inconsistent_saved_properties_are_rejected(self):
        control = layers_control.LayersControl()
        data = layer_state([0])
        data["layer_opacity"] = [100]

        with self.assertRaisesRegex(ValueError, "inconsistent lengths"):
            control.set_layer_data(data)


if __name__ == "__main__":
    unittest.main()
