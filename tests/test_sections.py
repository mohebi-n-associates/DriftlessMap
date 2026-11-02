"""Multi-section projects: the section book, the spill cache and switching."""

import tests.settings_isolation  # noqa: F401  (before the app reads settings)
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from functools import wraps
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CHILD = os.environ.get("DRIFTLESSMAP_SECTIONS_TEST_CHILD") == "1"

import cv2
import numpy as np

from driftlessmap.sections import SectionBook, SpillCache, section_fields

if CHILD:
    from PyQt6.QtWidgets import QApplication

    from driftlessmap.app import DriftlessMap

SLOT = [[10.0, 4.0], [14.0, 4.0], [14.0, 20.0], [10.0, 20.0]]


def isolated_gui_test(test):
    """Run each OpenGL integration case in its own Qt process."""

    @wraps(test)
    def wrapper(self):
        if CHILD:
            return test(self)
        environment = os.environ.copy()
        environment["DRIFTLESSMAP_SECTIONS_TEST_CHILD"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "tests.test_sections.{}".format(test.__qualname__)],
            check=False, capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, "{}\n{}".format(result.stdout, result.stderr))

    return wrapper


class SectionBookTests(unittest.TestCase):
    def test_sections_are_added_after_the_open_one_and_stay_named_uniquely(self):
        book = SectionBook("a", "pfc.tif")
        with self.assertRaises(ValueError):
            book.add("b", "pfc.tif")         # the open section must be put away first
        book.put_away({"img_path": "a"}, {}, {"pairs": 3})
        book.add("b", "pfc.tif")
        self.assertEqual(book.names(), ["pfc.tif", "pfc.tif (2)"])
        self.assertEqual(book.active_id, "b")
        self.assertTrue(book.entry("a").stored)
        self.assertEqual(book.entry("a").summary, {"pairs": 3})
        with self.assertRaises(ValueError):
            book.remove("b")                 # the open section cannot be removed
        book.move("b", -1)
        self.assertEqual([e.section_id for e in book.entries()], ["b", "a"])
        self.assertEqual(book.rename("a", "pfc.tif (2)"), "pfc.tif (2) (2)")

    def test_a_section_read_again_keeps_its_place_and_name(self):
        book = SectionBook("a")
        book.follow_active("a", "first.tif")
        book.put_away({}, {})
        book.add("b", "second.tif")
        book.follow_active("c", "second.tif")   # the open image was read again
        self.assertEqual([e.section_id for e in book.entries()], ["a", "c"])
        self.assertEqual(book.names(), ["first.tif", "second.tif"])

    def test_opening_needs_the_open_section_put_away(self):
        book = SectionBook("a", "one")
        book.put_away({"x": 1}, {})
        book.add("b", "two")
        with self.assertRaises(ValueError):
            book.activate("a")
        book.put_away({"x": 2}, {})
        self.assertEqual(book.activate("a").state, {"x": 1})
        book.opened("a")
        self.assertFalse(book.entry("a").stored)

    def test_section_fields_keep_a_slice_atlas_with_the_document(self):
        volume = {"current_atlas": "volume", "atlas_control": {}, "img_path": "x",
                  "object_data": None}
        self.assertEqual(section_fields(volume), ["img_path", "atlas_control"])
        self.assertEqual(section_fields(dict(volume, current_atlas="slice")), ["img_path"])


class SpillCacheTests(unittest.TestCase):
    def test_large_arrays_become_shared_copy_on_write_files(self):
        cache = SpillCache(min_bytes=1000)
        big = np.arange(4000, dtype=np.uint16).reshape(40, 100)
        small = np.arange(10)
        spilled = cache.spill({"img": big, "layers": [big.copy(), small], "n": 3})
        self.assertIsInstance(spilled["img"], np.memmap)
        np.testing.assert_array_equal(spilled["img"], big)
        self.assertNotIsInstance(spilled["layers"][1], np.memmap)
        # Identical contents share one file.
        self.assertEqual(len(os.listdir(cache.folder)), 1)
        self.assertEqual(spilled["img"].filename, spilled["layers"][0].filename)
        # Changes stay in memory; the file and the other array keep the data.
        spilled["img"][0, 0] = 999
        np.testing.assert_array_equal(spilled["layers"][0], big)
        np.testing.assert_array_equal(np.load(spilled["img"].filename), big)
        big[0, 0] = 7                     # the source is not referenced
        self.assertEqual(spilled["layers"][0][0, 0], 0)
        folder = cache.folder
        del spilled
        cache.close()
        self.assertFalse(os.path.exists(folder))


class SectionEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = (QApplication.instance() or QApplication([])) if CHILD else None

    def setUp(self):
        self.windows = []

    def tearDown(self):
        for window in reversed(self.windows):
            window.close()
            window.deleteLater()
        if self.application is not None:
            self.application.processEvents()

    def window_with_atlas(self, root):
        from tests.atlas_fixture import make_processed_atlas

        window = DriftlessMap()
        self.windows.append(window)
        self.assertTrue(window.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
        # Exercise the memory-mapped path with these small test images.
        window._section_cache.min_bytes = 0
        return window

    def load_section(self, window, path):
        from driftlessmap import file_dialogs

        with patch.object(file_dialogs, "get_open_file_name", return_value=(str(path), "")):
            window.load_image()
        self.assertEqual(window.current_img_path, str(path))

    @staticmethod
    def write_section(path, value):
        image = np.zeros((32, 24, 3), dtype=np.uint8)
        image[4:28, 4:20] = value
        image[6, 6] = value // 2     # makes each image's bytes distinct
        cv2.imwrite(str(path), image)

    def map_fiber(self, window, fiber):
        window.set_implant_outline(fiber.implant_id, SLOT)
        ok, message = window.map_implant(fiber.implant_id)
        self.assertTrue(ok, message)

    @isolated_gui_test
    def test_each_section_keeps_its_image_placement_marks_and_mapping(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            view = window.atlas_view
            first, second = root / "pfc-1.png", root / "pfc-2.png"
            self.write_section(first, 200)
            self.write_section(second, 120)

            self.load_section(window, first)
            self.assertEqual(len(window.sections), 1)
            fiber = window.add_implant("fiber", specs={"diameter_um": 100})
            view.cpage_ctrl.set_val(12)
            window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            window.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
            self.map_fiber(window, fiber)
            first_id = window.section_id
            first_raster = np.array(window.image_view.current_img)

            # Loading another image adds a section; the first is kept.
            self.load_section(window, second)
            self.assertEqual(len(window.sections), 2)
            self.assertNotEqual(window.section_id, first_id)
            self.assertEqual(window.sections.names(), ["pfc-1.png", "pfc-2.png"])
            second_id = window.section_id
            view.cpage_ctrl.set_val(20)
            window.atlas_tri_inside_data[:] = [[2.0, 2.0], [7.0, 2.0]]
            window.histo_tri_inside_data[:] = [[3.0, 3.0], [8.0, 3.0]]
            self.map_fiber(window, fiber)
            second_raster = np.array(window.image_view.current_img)
            stored = window.sections.entry(first_id).state
            self.assertIsInstance(stored["img_ctrl_data"]["current_img"], np.memmap)
            self.assertEqual(len(window.implant_objects(fiber.implant_id)), 2)

            # Opening the first brings back exactly what it had.
            ok, message = window.switch_section(first_id)
            self.assertTrue(ok, message)
            self.assertEqual(window.section_id, first_id)
            np.testing.assert_array_equal(window.image_view.current_img, first_raster)
            self.assertEqual(view.current_coronal_index, 12)
            self.assertEqual(window.atlas_tri_inside_data, [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]])
            self.assertEqual(window.histo_tri_inside_data, [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]])
            self.assertEqual(window.current_img_path, str(first))
            first_record = window.mapping_ledger.get(first_id, "fiber", fiber.implant_id)
            self.assertEqual(first_record.status(window.section_id,
                                                 window.current_registration_fingerprint()),
                             "current")
            self.assertEqual([r.unit_id for r in window.section_mappings(first_id)],
                             [first_record.unit_id])
            # Mapping it again replaces this section's part, not the other's.
            self.map_fiber(window, fiber)
            self.assertEqual(len(window.implant_objects(fiber.implant_id)), 2)
            self.assertEqual(window.mapping_ledger.by_unit(first_record.unit_id).revision, 2)
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            self.assertEqual(window.implant_report(fiber.implant_id)["sections"], 2)

            ok, message = window.switch_section(second_id)
            self.assertTrue(ok, message)
            np.testing.assert_array_equal(window.image_view.current_img, second_raster)
            self.assertEqual(view.current_coronal_index, 20)
            self.assertEqual(window.atlas_tri_inside_data, [[2.0, 2.0], [7.0, 2.0]])
            # Built objects are the document's: still there in every section.
            self.assertEqual(len(window.implant_objects(fiber.implant_id, built=True)), 1)

    @isolated_gui_test
    def test_a_failed_switch_restores_the_open_section(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            first, second = root / "a.png", root / "b.png"
            self.write_section(first, 200)
            self.write_section(second, 120)
            self.load_section(window, first)
            first_id = window.section_id
            self.load_section(window, second)
            second_id = window.section_id
            raster = np.array(window.image_view.current_img)
            window.atlas_tri_inside_data[:] = [[2.0, 2.0], [7.0, 2.0]]

            original = DriftlessMap.set_setting_data
            calls = []

            def fail_once(engine, data):
                # Opening the first section fails; restoring the second works.
                calls.append(1)
                if len(calls) == 1:
                    raise RuntimeError("broken widget")
                return original(engine, data)

            with patch.object(DriftlessMap, "set_setting_data", fail_once):
                ok, message = window.switch_section(first_id)
            self.assertFalse(ok)
            self.assertIn("broken widget", message)
            self.assertEqual(window.section_id, second_id)
            self.assertEqual(window.sections.active_id, second_id)
            np.testing.assert_array_equal(window.image_view.current_img, raster)
            self.assertEqual(window.atlas_tri_inside_data, [[2.0, 2.0], [7.0, 2.0]])
            self.assertTrue(window.sections.entry(first_id).stored)
            self.assertTrue(window.switch_section(first_id)[0])

    @isolated_gui_test
    def test_a_changed_source_opens_the_saved_image_and_sections_can_be_removed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            first, second = root / "a.png", root / "b.png"
            self.write_section(first, 200)
            self.write_section(second, 120)
            self.load_section(window, first)
            fiber = window.add_implant("fiber")
            self.map_fiber(window, fiber)
            first_id = window.section_id
            raster = np.array(window.image_view.current_img)
            self.load_section(window, second)

            time.sleep(0.01)
            self.write_section(first, 50)             # the file changed on disk
            ok, message = window.switch_section(first_id)
            self.assertTrue(ok, message)
            self.assertIn("saved image", message)
            np.testing.assert_array_equal(window.image_view.current_img, raster)
            self.assertIsNone(window.current_img_path)

            second_id = next(e.section_id for e in window.sections.entries()
                             if e.section_id != first_id)
            self.assertFalse(window.remove_section(first_id)[0])   # open: refused
            self.assertTrue(window.switch_section(second_id)[0])
            self.assertEqual(len(window.implant_objects(fiber.implant_id)), 1)
            ok, _message = window.remove_section(first_id, delete_results=True)
            self.assertTrue(ok)
            self.assertEqual(len(window.sections), 1)
            self.assertEqual(window.implant_objects(fiber.implant_id), [])
            self.assertEqual(window.section_mappings(first_id), [])


if __name__ == "__main__":
    unittest.main()
