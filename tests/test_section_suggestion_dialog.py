import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtWidgets import QApplication

from driftlessmap.atlas_matching import Orientation
from driftlessmap.section_suggestion_dialog import SectionSuggestionDialog


def report(plane, orientation, index, midline=None):
    suggestion = SimpleNamespace(index=index, tilt_degrees=(0.0, 0.0), score=1.0,
                                 orientation=orientation)
    candidate = SimpleNamespace(plane=plane, orientation=orientation, silhouette=0.9)
    return SimpleNamespace(plane_candidates=[candidate], plane_margin=0.1,
                           suggestions=[suggestion], midline=midline)


class HemisphereWordingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def dialog(self, plane, orientation, index, midline=None):
        volume = np.random.default_rng(0).random((20, 30, 40)).astype(np.float32)
        histology = np.random.default_rng(1).random((24, 32)).astype(np.float32)
        dialog = SectionSuggestionDialog(report(plane, orientation, index, midline),
                                         histology, volume, (10, 15, 20), 25.0)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def choices(self, dialog):
        return [dialog.hemisphere_group.button(i).text() for i in range(2)]

    def test_coronal_choices_name_the_animals_right_on_the_section(self):
        dialog = self.dialog("coronal", Orientation(0, False), 12)
        self.assertEqual(self.choices(dialog), ["toward the right of your section",
                                                "toward the left of your section"])
        dialog.hemisphere_group.button(1).setChecked(True)
        _plane, _index, orientation, _tilt, _rotate = dialog.choice()
        self.assertEqual(orientation, Orientation(0, True))

    def test_sagittal_choices_name_the_hemisphere(self):
        dialog = self.dialog("sagittal", Orientation(0, False), 20, midline=15)
        self.assertEqual(self.choices(dialog), ["Right hemisphere", "Left hemisphere"])
        dialog.hemisphere_group.button(1).setChecked(True)
        self.assertEqual(dialog.choice()[1], 10)


if __name__ == "__main__":
    unittest.main()
