import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QDialogButtonBox

from driftlessmap.probe_utiles import linear_silicon_settings_error
from driftlessmap.wtiles import LinearSiliconInfoDialog, MultiProbePlanningDialog


def linear_settings():
    return {
        "probe_length": 5000,
        "probe_thickness": 20,
        "tip_length": 175,
        "site_height": 12,
        "site_width": 12,
        "per_max_sites": [32],
        "sites_distance": [20],
        "x_bias": [0],
        "y_bias": [0],
    }


class LinearSiliconDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def ok_button(self, dialog):
        return dialog.button_box.button(QDialogButtonBox.StandardButton.Ok)

    def test_editing_does_not_touch_the_callers_settings(self):
        original = linear_settings()
        snapshot = copy.deepcopy(original)
        dialog = LinearSiliconInfoDialog(original)
        dialog.n_column_spinbox.setValue(3)
        dialog.probe_length_input.setText("900")
        dialog.sites_distance_wl[0].setText("40")
        dialog.reject()
        self.assertEqual(original, snapshot)
        self.assertEqual(dialog.probe_settings["probe_length"], 900)
        self.assertEqual(len(dialog.probe_settings["x_bias"]), 3)

    def test_added_columns_use_the_same_rows_as_initial_columns(self):
        dialog = LinearSiliconInfoDialog(linear_settings())
        dialog.n_column_spinbox.setValue(2)
        layout = dialog.right_layout
        for column in (1, 2):
            index = column - 1
            self.assertIs(
                layout.itemAtPosition(6, column).widget(),
                dialog.per_max_sites_wl[index],
            )
            self.assertIs(
                layout.itemAtPosition(7, column).widget(),
                dialog.sites_distance_wl[index],
            )

    def test_ok_tracks_every_field_and_buttons_stay_visible(self):
        dialog = LinearSiliconInfoDialog(linear_settings())
        dialog.site_height_input.setText("")
        self.assertFalse(dialog.button_box.isHidden())
        self.assertFalse(self.ok_button(dialog).isEnabled())

        # A valid edit elsewhere must not re-enable OK while a field is empty.
        dialog.site_width_input.setText("14")
        self.assertFalse(self.ok_button(dialog).isEnabled())

        dialog.site_height_input.setText("12")
        self.assertTrue(self.ok_button(dialog).isEnabled())


class MultiProbeDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_saved_faces_are_shown_and_cancel_keeps_settings(self):
        original = {"x_vals": [-100, 100], "y_vals": [0, 0], "faces": [2, 1]}
        snapshot = copy.deepcopy(original)
        dialog = MultiProbePlanningDialog(original)
        self.assertEqual(
            [combo.currentIndex() for combo in dialog.faces_wl], [2, 1]
        )
        dialog.n_probe_spinbox.setValue(4)
        dialog.x_val_wl[0].setText("-250")
        dialog.reject()
        self.assertEqual(original, snapshot)


class LinearSiliconValidationTests(unittest.TestCase):
    def test_valid_geometry_has_no_error(self):
        self.assertIsNone(linear_silicon_settings_error(linear_settings()))

    def test_column_starting_beyond_the_shank_is_rejected(self):
        settings = linear_settings()
        settings["y_bias"] = [5000]
        self.assertIn("Column 1", linear_silicon_settings_error(settings))

    def test_tip_as_long_as_the_probe_is_rejected(self):
        settings = linear_settings()
        settings["tip_length"] = settings["probe_length"]
        self.assertIn("tip length", linear_silicon_settings_error(settings))

    def test_zero_site_dimensions_are_rejected(self):
        for key in ("site_height", "site_width"):
            settings = linear_settings()
            settings[key] = 0
            self.assertIsNotNone(linear_silicon_settings_error(settings))


if __name__ == "__main__":
    unittest.main()
