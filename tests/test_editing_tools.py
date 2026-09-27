import os
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QLineEdit

from driftlessmap.toolbox import read_int_field
from driftlessmap.uuuuuu import tolerance_mask


class ToleranceMaskTests(unittest.TestCase):
    def test_band_is_two_sided(self):
        channel = np.array([[10, 45, 50, 55, 90]], dtype=np.uint8)
        mask = tolerance_mask(channel, 50, 5, 255)
        np.testing.assert_array_equal(mask, [[0, 255, 255, 255, 0]])

    def test_sixteen_bit_upper_bounds_do_not_wrap(self):
        channel = np.array([[250, 256, 300, 600]], dtype=np.uint16)
        # upper bound 512 would wrap to 0 if cast to uint8
        mask = tolerance_mask(channel, 300, 212, 65535)
        np.testing.assert_array_equal(mask, [[255, 255, 255, 0]])


class IntFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_incomplete_or_out_of_range_text_reads_as_none(self):
        field = QLineEdit()
        for text in ("", "-", "abc"):
            field.setText(text)
            self.assertIsNone(read_int_field(field))
        field.setText("0")
        self.assertIsNone(read_int_field(field, minimum=1))
        field.setText("7")
        self.assertEqual(read_int_field(field, minimum=1, maximum=9), 7)


if __name__ == "__main__":
    unittest.main()
