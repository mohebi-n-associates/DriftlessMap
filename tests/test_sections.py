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
    def test_a_stored_section_keeps_only_a_valid_registration_fingerprint(self):
        from driftlessmap.sections import _valid_summary

        good = {"page": 3, "registration": "c" * 64}
        self.assertEqual(_valid_summary(good), good)
        for bad in ("short", "C" * 64, 5, None):
            summary = _valid_summary({"page": 3, "registration": bad})
            self.assertEqual(summary, {"page": 3} if bad is not None else
                             {"page": 3, "registration": None}, bad)
        self.assertEqual(_valid_summary("not a dict"), {})

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

            # Loading another image adds a section; the first is kept. The new
            # one starts without the first one's landmarks or warp preview.
            self.load_section(window, second)
            self.assertEqual(len(window.sections), 2)
            self.assertEqual(window.atlas_tri_inside_data, [])
            self.assertEqual(window.histo_tri_inside_data, [])
            self.assertFalse(window.h2a_transferred)
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
    def test_out_of_date_objects_name_the_section_and_the_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            first, second = root / "pfc-1.png", root / "pfc-2.png"
            self.write_section(first, 200)
            self.write_section(second, 120)
            fiber = None
            for path in (first, second):
                self.load_section(window, path)
                fiber = fiber or window.add_implant("fiber", specs={"diameter_um": 100})
                window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                window.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                self.map_fiber(window, fiber)
            first_id = window.sections.entries()[0].section_id
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            built = window.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(window.out_of_date_reason(built))

            # Moving a landmark of the open section names that section.
            window.atlas_tri_inside_data[0] = [1.5, 1.0]
            reason = window.out_of_date_reason(built)
            self.assertIn("pfc-2.png", reason)
            self.assertIn("landmarks, page or tilt", reason)
            self.assertIn("build it again", reason)
            exported, notes = window.export_all_results(str(root / "results"))
            self.assertTrue(exported)
            self.assertTrue(any("Fiber 1: the landmarks, page or tilt of pfc-2.png" in note
                                for note in notes), notes)
            window.atlas_tri_inside_data[0] = [1.0, 1.0]
            self.assertIsNone(window.out_of_date_reason(built))

            # Mapping the other section again names that one.
            self.assertTrue(window.switch_section(first_id)[0])
            self.map_fiber(window, fiber)
            self.assertIn("pfc-1.png was mapped again", window.out_of_date_reason(built))
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            built = window.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(window.out_of_date_reason(built))
            window.set_implant_specs(fiber.implant_id, {"diameter_um": 400})
            self.assertIn("implant settings changed", window.out_of_date_reason(built))

    @isolated_gui_test
    def test_clearing_a_mapped_outline_removes_it_from_parts_and_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            first, second = root / "pfc-1.png", root / "pfc-2.png"
            self.write_section(first, 200)
            self.write_section(second, 120)
            fiber = None
            for path in (first, second):
                self.load_section(window, path)
                fiber = fiber or window.add_implant("fiber", specs={"diameter_um": 100})
                window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                window.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                self.map_fiber(window, fiber)
            first_id = window.sections.entries()[0].section_id
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            o = window.object_ctrl
            self.assertEqual(o.obj_type, ["merged fiber"])

            # Edit the open section's outline, delete it and map: that mapping
            # goes, the build is taken apart and the other section's part stays.
            record = window.mapping_ledger.get(window.section_id, "fiber", fiber.implant_id)
            self.assertTrue(window.edit_mapped_marks(record.unit_id))
            self.assertIsNone(window.cleared_edit("fiber", fiber.implant_id))
            window.set_implant_outline(fiber.implant_id, [])
            self.assertEqual(window.cleared_edit("fiber", fiber.implant_id), record)
            ok, message = window.map_implant(fiber.implant_id)
            self.assertTrue(ok, message)
            self.assertIn("Took apart Fiber 1", message)
            self.assertIsNone(window.mapping_ledger.by_unit(record.unit_id))
            self.assertEqual(o.obj_type, ["fiber piece"])
            kept = window.mapping_ledger.get(first_id, "fiber", fiber.implant_id)
            self.assertEqual(o.obj_derivation, [[[kept.unit_id, 1]]])
            self.assertEqual(o.obj_data[0]["section_id"], first_id)
            self.assertEqual(window.object_mapping_status(0), "current")
            # Building again uses only what is left.
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            self.assertEqual(window.implant_report(fiber.implant_id)["sections"], 1)

            # Undo of both steps brings back the two-section build.
            self.assertTrue(window.undo_mapping_step())
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, ["merged fiber"])
            self.assertEqual(window.implant_report(fiber.implant_id)["sections"], 2)
            self.assertIsNotNone(window.mapping_ledger.by_unit(record.unit_id))

            # Remove mapping does the same for the other section, from its own
            # section only.
            self.assertIsNone(window.remove_mapping(kept.unit_id))
            self.assertTrue(window.switch_section(first_id)[0])
            removed, message = window.remove_mapping(kept.unit_id)
            self.assertEqual(removed.unit_id, kept.unit_id)
            self.assertEqual(o.obj_type, ["fiber piece"])
            self.assertNotEqual(o.obj_data[0]["section_id"], first_id)
            self.assertEqual(window.section_mappings(first_id), [])

    @isolated_gui_test
    def test_removing_a_section_keeps_the_other_sections_parts_of_a_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            fiber = None
            for name, value in (("a.png", 200), ("b.png", 120), ("c.png", 90)):
                self.write_section(root / name, value)
                self.load_section(window, root / name)
                fiber = fiber or window.add_implant("fiber", specs={"diameter_um": 100})
                window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
                window.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
                self.map_fiber(window, fiber)
            first_id = window.sections.entries()[0].section_id
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            o = window.object_ctrl
            self.assertEqual(o.obj_type, ["merged fiber"])

            ok, message = window.remove_section(first_id, delete_results=True)
            self.assertTrue(ok, message)
            self.assertIn("Took apart Fiber 1", message)
            self.assertEqual(o.obj_type, ["fiber piece", "fiber piece"])
            self.assertNotIn(first_id, [data["section_id"] for data in o.obj_data])
            self.assertIsNone(window.undo_history.undo_label())
            # The other two sections build again without being mapped again.
            ok, message = window.build_implant(fiber.implant_id)
            self.assertTrue(ok, message)
            self.assertEqual(window.implant_report(fiber.implant_id)["sections"], 2)

    @isolated_gui_test
    def test_several_files_and_tiff_pages_are_added_in_name_order(self):
        # Review U8: one step adds many sections; pages can be sections.
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            paths = []
            for name, value in (("s10.png", 90), ("s2.png", 120), ("s1.png", 200)):
                self.write_section(root / name, value)
                paths.append(str(root / name))
            stack = root / "stack.tif"
            tifffile.imwrite(stack, np.stack([np.full((32, 24), 40, np.uint8),
                                              np.full((32, 24), 180, np.uint8)]),
                             metadata={"axes": "ZYX"}, photometric="minisblack")
            self.assertEqual(window.add_sections(paths + [str(stack)], pages_as_sections=True),
                             5)
            self.assertEqual(window.sections.names(), [
                "s1.png", "s2.png", "s10.png", "stack.tif · page 1", "stack.tif · page 2"])
            entries = window.sections.entries()
            self.assertEqual(window.image_view.display_img_index, 1)      # page 2 is open
            self.assertTrue(window.switch_section(entries[3].section_id)[0])
            self.assertEqual(window.image_view.display_img_index, 0)
            self.assertEqual(float(window.image_view.current_img.mean()), 40.0)

            # Without the option a multi-page file is one section (added after
            # the open one, as every new section is).
            self.assertEqual(window.add_sections([str(stack)]), 1)
            self.assertEqual(window.sections.names()[4], "stack.tif")
            self.assertEqual(len(window.sections), 6)

    @isolated_gui_test
    def test_the_frame_follows_landmarks_as_they_are_placed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            section = root / "pfc-1.png"
            self.write_section(section, 200)
            self.load_section(window, section)
            height, width = window.image_view.img_size
            atlas_frame = [list(p) for p in window.atlas_tri_onside_data]
            pairs = [((2.0, 3.0), (10.0, 12.0)), ((20.0, 4.0), (19.0, 12.5)),
                     ((10.0, 28.0), (15.0, 24.0))]
            for (sx, sy), (ax, ay) in pairs[:2]:
                window._image_click_triang(None, sx, sy)
                window._atlas_click_triang(None, ax, ay)
            # Two pairs cannot fix the frame: it stays at the image corners.
            self.assertEqual(window.atlas_tri_onside_data, atlas_frame)
            (sx, sy), (ax, ay) = pairs[2]
            window._image_click_triang(None, sx, sy)
            window._atlas_click_triang(None, ax, ay)
            # The third pair moves the frame to where the landmarks put the
            # section's corners, kept inside both images.
            from driftlessmap.landmarks import fit_frame
            from driftlessmap.utils import get_corner_line_from_rect

            atlas_rect, section_rect = fit_frame(
                window.atlas_tri_inside_data, window.histo_tri_inside_data,
                window.atlas_view.slice_size, (height, width))
            self.assertEqual(window.atlas_tri_onside_data[:4],
                             get_corner_line_from_rect(atlas_rect)[0])
            self.assertEqual(window.histo_tri_onside_data[:4],
                             get_corner_line_from_rect(section_rect)[0])
            self.assertNotEqual(window.atlas_tri_onside_data, atlas_frame)
            # About atlas = section / 2 + (9, 10): the top-left corner is near (9, 10).
            np.testing.assert_allclose(atlas_rect[:2], (9.0, 10.0), atol=0.5)
            self.assertEqual(len(window.atlas_tri_data), len(window.histo_tri_data))

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



class SectionPersistenceTests(SectionEngineTests):
    """Saving and opening projects with several sections (project schema 4)."""

    def open_project(self, root, path):
        from driftlessmap.persistence import load_driftlessmap_file

        payload, error = load_driftlessmap_file(str(path), expected_kind="project")
        self.assertIsNone(error)
        window = DriftlessMap()
        self.windows.append(window)
        prepared = window.prepare_project_sources(payload, str(path))
        self.assertIsNotNone(prepared)
        self.assertTrue(window.load_project(prepared, project_path=str(path)))
        return window, payload

    @isolated_gui_test
    def test_tiff_pages_are_decoded_once_and_reopen_exactly(self):
        # Review F7 of 2.6.0: every page section decoded the whole stack again.
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            pages = 12
            stack = (np.arange(pages * 32 * 24, dtype=np.uint16).reshape(pages, 32, 24)
                     * 7) % 4096
            path = root / "stack.tif"
            tifffile.imwrite(path, stack, metadata={"axes": "ZYX"}, photometric="minisblack")
            decodes, original = [], tifffile.TiffPageSeries.asarray

            def counted(series, *args, **kwargs):
                decodes.append(tuple(series.shape))
                return original(series, *args, **kwargs)

            seen = []
            with patch.object(tifffile.TiffPageSeries, "asarray", counted):
                added = window.add_sections(
                    [str(path)], pages_as_sections=True,
                    progress=lambda done, total, name: seen.append((done, total, name)))
            self.assertEqual(added, pages)
            self.assertEqual(decodes, [(pages, 32, 24)])           # one decode
            self.assertEqual(seen[0], (0, 1, "stack.tif"))
            self.assertEqual(seen[-1], (pages - 1, pages, "stack.tif · page {}".format(pages)))
            names = ["stack.tif · page {}".format(n + 1) for n in range(pages)]
            self.assertEqual(window.sections.names(), names)
            # Sections share the decoded stack read-only; each has its own page.
            self.assertFalse(window.image_view.volume_img.flags.writeable)
            ids = [e.section_id for e in window.sections.entries()]
            for page, section_id in enumerate(ids):
                self.assertTrue(window.switch_section(section_id)[0])
                np.testing.assert_array_equal(window.image_view.current_img[..., 0],
                                              stack[page])
            # Flipping one section leaves the others as they were.
            window.image_view.image_vertical_flip()
            np.testing.assert_array_equal(window.image_view.current_img[..., 0],
                                          stack[-1][::-1])
            self.assertTrue(window.switch_section(ids[0])[0])
            np.testing.assert_array_equal(window.image_view.current_img[..., 0], stack[0])

            project = root / "pages.dmap"
            self.assertTrue(window.save_project_called(path=str(project)))
            for source_present in (True, False):
                if not source_present:
                    path.unlink()          # the embedded rasters then open
                # Declining to locate a missing source, as the user can.
                with patch.object(DriftlessMap, "_ask_for_verified_input",
                                  return_value=None):
                    reopened, _payload = self.open_project(root, project)
                self.assertEqual(reopened.sections.names(), names)
                for page, section_id in enumerate(ids):
                    self.assertTrue(reopened.switch_section(section_id)[0])
                    expected = stack[page][::-1] if page == pages - 1 else stack[page]
                    np.testing.assert_array_equal(
                        reopened.image_view.current_img[..., 0], expected,
                        "page {} (source present: {})".format(page + 1, source_present))

    @isolated_gui_test
    def test_adding_tiff_pages_stops_safely(self):
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_atlas(root)
            path = root / "stack.tif"
            stack = np.stack([np.full((32, 24), 10 * (n + 1), np.uint8) for n in range(6)])
            tifffile.imwrite(path, stack, metadata={"axes": "ZYX"}, photometric="minisblack")
            # Stop asked for while the fourth section is next.
            added = window.add_sections([str(path)], pages_as_sections=True,
                                        progress=lambda done, total, name: done < 3)
            self.assertEqual(added, 3)
            self.assertEqual(len(window.sections), 3)
            self.assertEqual(float(window.image_view.current_img.mean()), 30.0)

            # The file changing in the middle stops before the next page.
            def rewrite(done, total, name):
                if name.endswith("page 3"):
                    tifffile.imwrite(path, stack[::-1], metadata={"axes": "ZYX"},
                                     photometric="minisblack")
                return True

            before = len(window.sections)
            added = window.add_sections([str(path)], pages_as_sections=True, progress=rewrite)
            self.assertEqual(added, 2)
            self.assertEqual(len(window.sections), before + 2)

    def two_section_project(self, root):
        window = self.window_with_atlas(root)
        first, second = root / "pfc-1.png", root / "pfc-2.png"
        self.write_section(first, 200)
        self.write_section(second, 120)
        self.load_section(window, first)
        fiber = window.add_implant("fiber", specs={"diameter_um": 100})
        window.atlas_view.cpage_ctrl.set_val(12)
        window.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
        window.histo_tri_inside_data[:] = [[2.0, 2.0], [6.0, 2.0], [4.0, 6.0]]
        self.map_fiber(window, fiber)
        first_id = window.section_id
        raster = np.array(window.image_view.current_img)
        self.load_section(window, second)
        window.atlas_view.cpage_ctrl.set_val(20)
        self.map_fiber(window, fiber)
        window.rename_section(first_id, "rostral")
        return window, fiber, first_id, raster

    @isolated_gui_test
    def test_a_changed_stored_section_keeps_its_results_out_of_date(self):
        # Review B1: switching away from a changed section made its results current.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, fiber, first_id, _raster = self.two_section_project(root)
            second_id = window.section_id
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            built = window.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(window.out_of_date_reason(built))

            window.atlas_view.cpage_ctrl.set_val(22)        # pfc-2 changes after mapping
            self.assertIn("pfc-2.png", window.out_of_date_reason(built))
            self.assertTrue(window.switch_section(first_id)[0])
            built = window.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(window.object_mapping_status(built), "registration changed")
            reason = window.out_of_date_reason(built)
            self.assertIn("pfc-2.png", reason)
            self.assertIn("open pfc-2.png", reason)
            exported, notes = window.export_all_results(str(root / "results"))
            self.assertTrue(exported)
            self.assertTrue(any("pfc-2.png" in note for note in notes), notes)

            # Saved and opened with the other section open: still out of date.
            path = root / "stale.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))
            reopened, _payload = self.open_project(root, path)
            built = reopened.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIn("pfc-2.png", reopened.out_of_date_reason(built))

            # Opening it, updating the mapping and building again makes it current.
            self.assertTrue(reopened.switch_section(second_id)[0])
            record = reopened.mapping_ledger.get(second_id, "fiber", fiber.implant_id)
            self.assertIsNotNone(reopened.update_mapping(record.unit_id))
            self.assertTrue(reopened.build_implant(fiber.implant_id)[0])
            built = reopened.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(reopened.out_of_date_reason(built))
            self.assertTrue(reopened.switch_section(first_id)[0])
            built = reopened.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(reopened.out_of_date_reason(built))

    @isolated_gui_test
    def test_another_page_of_a_tiff_is_not_the_reviewed_registration(self):
        # Review B5: changing the TIFF page kept the review and the mapping current.
        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, fiber, _first_id, _raster = self.two_section_project(root)
            path = root / "stack.tif"
            tifffile.imwrite(path, np.stack([np.full((32, 24), 40, np.uint8),
                                             np.full((32, 24), 180, np.uint8)]),
                             metadata={"axes": "ZYX"}, photometric="minisblack")
            self.load_section(window, path)
            window.atlas_tri_inside_data[:] = [[5.0, 5.0], [15.0, 5.0], [10.0, 20.0]]
            window.histo_tri_inside_data[:] = [[5.0, 5.0], [15.0, 5.0], [10.0, 20.0]]
            self.map_fiber(window, fiber)
            window.mark_registration_reviewed()
            record = window.mapping_ledger.get(window.section_id, "fiber", fiber.implant_id)
            page = window.image_view.display_img_index
            self.assertEqual(window.registration_review_state(), "reviewed")
            self.assertEqual(window.mapping_status(record), "current")

            window.image_view.page_ctrl.page_slider.setValue(1 - page)
            self.assertEqual(window.registration_review_state(), "not reviewed")
            self.assertEqual(window.mapping_status(record), "registration changed")
            window.image_view.page_ctrl.page_slider.setValue(page)
            self.assertEqual(window.registration_review_state(), "reviewed")
            self.assertEqual(window.mapping_status(record), "current")

            # Opened from its embedded raster (original missing), it is still the
            # same page: the review and mapping stay current.
            project = root / "tiff.dmap"
            self.assertTrue(window.save_project_called(path=str(project)))
            path.unlink()
            with patch.object(DriftlessMap, "_ask_for_verified_input", return_value=None):
                reopened, _payload = self.open_project(root, project)
            self.assertEqual(reopened.registration_review_state(), "reviewed")
            self.assertEqual(reopened.mapping_status(
                reopened.mapping_ledger.by_unit(record.unit_id)), "current")

    @isolated_gui_test
    def test_another_atlas_cannot_replace_the_one_results_were_made_with(self):
        # Review B2: a different atlas of the same shape relabelled old results.
        import shutil

        from tests.atlas_fixture import make_processed_atlas

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, fiber, _first_id, _raster = self.two_section_project(root)
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            original = window.volume_atlas_path
            path = root / "two.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))
            other = make_processed_atlas(root / "other-atlas", voxel_size=50)

            self.assertFalse(window.load_volume_atlas(str(other)))
            self.assertIn("different atlas", window.statusbar.currentMessage())
            self.assertEqual(window.volume_atlas_path, original)
            self.assertEqual(window.atlas_view.vox_size_um, 25)
            self.assertEqual(window.get_object_export_provenance()["atlas"]["voxel_size_um"], 25.0)

            # The same atlas again, or an identical copy elsewhere, is fine.
            self.assertTrue(window.load_volume_atlas(original))
            copy = root / "atlas-copy"
            shutil.copytree(original, copy)
            self.assertTrue(window.load_volume_atlas(str(copy)))

            # 2.6.0 review F1: the loaded folder's files changed in place, or a
            # copy of the changed files, or the folder is gone: refused.
            changed_copy = root / "changed-copy"
            time.sleep(0.01)
            make_processed_atlas(copy, voxel_size=50)
            shutil.copytree(copy, changed_copy)
            for candidate in (copy, changed_copy):
                self.assertFalse(window.load_volume_atlas(str(candidate)), candidate)
                self.assertIn("changed (or went missing)", window.statusbar.currentMessage())
                self.assertEqual(window.atlas_view.vox_size_um, 25)
                self.assertEqual(window.object_ctrl.obj_type, ["merged fiber"])
                # Exports do not describe the results with the changed files either.
                with self.assertRaisesRegex(ValueError, "changed after they were loaded"):
                    window.get_object_export_provenance()
            shutil.rmtree(copy)
            self.assertFalse(window.load_volume_atlas(original))
            self.assertEqual(window.atlas_view.vox_size_um, 25)

            # Opening a project replaces the document, whatever its atlas.
            fresh = self.window_with_atlas(root / "fresh")
            self.write_section(root / "x.png", 90)
            self.load_section(fresh, root / "x.png")
            fresh.atlas_tri_inside_data[:] = [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]]
            self.assertIsNotNone(fresh.atlas_replacement_problem(str(other)))
            payload_window, _payload = self.open_project(root, path)
            self.assertEqual(len(payload_window.mapping_ledger), 2)

    @isolated_gui_test
    def test_a_portable_copy_treats_every_changed_original_alike(self):
        # Review B8: a changed stored section's original was silently left out.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, _fiber, _first_id, _raster = self.two_section_project(root)
            time.sleep(0.01)
            self.write_section(root / "pfc-1.png", 60)     # stored section's file changes
            portable = root / "portable.dmap"
            self.assertFalse(window.save_project_called(portable=True, path=str(portable)))
            message = window.statusbar.currentMessage()
            self.assertIn("rostral", message)
            self.assertIn("cannot be packed", message)
            self.assertFalse(portable.exists())

            # A normal save keeps the saved image and says so in its final message.
            normal = root / "normal.dmap"
            self.assertTrue(window.save_project_called(path=str(normal)))
            message = window.statusbar.currentMessage()
            self.assertIn("Project saved successfully", message)
            self.assertIn("rostral: its source changed after loading", message)

            # An original that is gone: the portable copy keeps the saved image
            # and the final message names the omission.
            (root / "pfc-1.png").unlink()
            self.assertTrue(window.save_project_called(portable=True, path=str(portable)))
            self.assertIn("rostral: its original source is unavailable",
                          window.statusbar.currentMessage())

    @isolated_gui_test
    def test_sections_without_a_recorded_registration_are_not_called_current(self):
        # 2.6.0 review F2: an older stored section's results looked current.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, fiber, first_id, _raster = self.two_section_project(root)
            second_id = window.section_id
            self.assertTrue(window.build_implant(fiber.implant_id)[0])

            def status():
                built = window.implant_objects(fiber.implant_id, built=True)[0]
                return window.object_mapping_status(built), built

            self.assertEqual(status()[0], "current")
            # As saved by 2.5.2 or earlier: the stored summary has no fingerprint.
            window.sections.entry(first_id).summary.pop("registration")
            state, built = status()
            self.assertEqual(state, "not verified")
            self.assertIn("rostral was saved without a record", window.unverified_reason(built))
            exported, notes = window.export_all_results(str(root / "results"))
            self.assertTrue(any("could not be verified" in note for note in notes), notes)
            # Opening it is the check; put away again, it is recorded.
            self.assertTrue(window.switch_section(first_id)[0])
            self.assertEqual(status()[0], "current")
            self.assertTrue(window.switch_section(second_id)[0])
            self.assertEqual(status()[0], "current")

            # Changed after mapping and unrecorded: not verified, then out of date.
            self.assertTrue(window.switch_section(first_id)[0])
            window.atlas_view.cpage_ctrl.set_val(window.atlas_view.current_coronal_index + 2)
            self.assertTrue(window.switch_section(second_id)[0])
            self.assertEqual(status()[0], "registration changed")
            window.sections.entry(first_id).summary.pop("registration")
            self.assertEqual(status()[0], "not verified")
            self.assertTrue(window.switch_section(first_id)[0])
            self.assertEqual(status()[0], "registration changed")
            window.atlas_view.cpage_ctrl.set_val(window.atlas_view.current_coronal_index - 2)
            self.assertTrue(window.switch_section(second_id)[0])

            # A damaged fingerprint is unknown after saving and opening.
            window.sections.entry(first_id).summary["registration"] = "not a fingerprint"
            path = root / "old.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))
            reopened, _payload = self.open_project(root, path)
            built = reopened.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(reopened.object_mapping_status(built), "not verified")

            # A section removed with its results kept cannot change: as mapped.
            ok, _message = reopened.remove_section(first_id)
            self.assertTrue(ok)
            built = reopened.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(reopened.object_mapping_status(built), "current")

    @isolated_gui_test
    def test_every_section_round_trips_through_a_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, fiber, first_id, raster = self.two_section_project(root)
            second_id = window.section_id
            path = root / "two.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))

            reopened, payload = self.open_project(root, path)
            self.assertEqual(payload["project_schema_version"], 4)
            self.assertEqual(len(payload["sections"]["stored"]), 1)
            self.assertEqual(payload["sections"]["active_section_id"], second_id)
            self.assertEqual(reopened.section_id, second_id)
            self.assertEqual(reopened.sections.names(), ["rostral", "pfc-2.png"])
            self.assertEqual(reopened.atlas_view.current_coronal_index, 20)

            ok, message = reopened.switch_section(first_id)
            self.assertTrue(ok, message)
            np.testing.assert_array_equal(reopened.image_view.current_img, raster)
            self.assertEqual(reopened.atlas_view.current_coronal_index, 12)
            self.assertEqual(reopened.atlas_tri_inside_data,
                             [[1.0, 1.0], [5.0, 1.0], [3.0, 5.0]])
            # Its source was found through its provenance and linked again.
            self.assertEqual(Path(reopened.current_img_path).resolve(),
                             (root / "pfc-1.png").resolve())
            record = reopened.mapping_ledger.get(first_id, "fiber", fiber.implant_id)
            self.assertEqual(record.status(reopened.section_id,
                                           reopened.current_registration_fingerprint()),
                             "current")
            self.map_fiber(reopened, fiber)
            self.assertEqual(len(reopened.implant_objects(fiber.implant_id)), 2)
            self.assertTrue(reopened.build_implant(fiber.implant_id)[0])

            # Saved again with the other section open, both survive.
            again = root / "again.dmap"
            self.assertTrue(reopened.save_project_called(path=str(again)))
            third, payload = self.open_project(root, again)
            self.assertEqual(third.section_id, first_id)
            self.assertEqual([e.section_id for e in third.sections.entries()],
                             [first_id, second_id])
            self.assertTrue(third.switch_section(second_id)[0])
            self.assertEqual(third.atlas_view.current_coronal_index, 20)

    @isolated_gui_test
    def test_moved_changed_and_missing_sources_of_stored_sections(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "study"
            root.mkdir()
            window, _fiber, first_id, raster = self.two_section_project(root)
            path = root / "two.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))

            # The study folder moved: found again next to the project.
            moved = Path(folder) / "moved"
            root.rename(moved)
            reopened, _payload = self.open_project(moved, moved / "two.dmap")
            self.assertTrue(reopened.switch_section(first_id)[0])
            self.assertEqual(Path(reopened.current_img_path).resolve(),
                             (moved / "pfc-1.png").resolve())

            # Changed bytes do not match the checksum: the saved image opens.
            self.write_section(moved / "pfc-1.png", 30)
            reopened, _payload = self.open_project(moved, moved / "two.dmap")
            ok, message = reopened.switch_section(first_id)
            self.assertTrue(ok, message)
            self.assertIn("saved image", message)
            self.assertIsNone(reopened.current_img_path)
            np.testing.assert_array_equal(reopened.image_view.current_img, raster)

            # Missing entirely: the same.
            (moved / "pfc-1.png").unlink()
            reopened, _payload = self.open_project(moved, moved / "two.dmap")
            self.assertTrue(reopened.switch_section(first_id)[0])
            np.testing.assert_array_equal(reopened.image_view.current_img, raster)

    @isolated_gui_test
    def test_a_portable_project_carries_every_section_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "study"
            root.mkdir()
            window, _fiber, first_id, raster = self.two_section_project(root)
            path = Path(folder) / "portable.dmap"
            self.assertTrue(window.save_project_called(portable=True, path=str(path)))
            for name in ("pfc-1.png", "pfc-2.png"):
                (root / name).unlink()
            reopened, payload = self.open_project(Path(folder), path)
            self.assertIn(first_id, payload["portable_sources"]["sections"])
            self.assertTrue(reopened.switch_section(first_id)[0])
            # The packed source was extracted and verified, not the fallback.
            self.assertIsNotNone(reopened.current_img_path)
            self.assertTrue(Path(reopened.current_img_path).is_file())
            np.testing.assert_array_equal(reopened.image_view.current_img, raster)

    @isolated_gui_test
    def test_older_projects_open_as_one_section_and_bad_entries_are_left_out(self):
        from driftlessmap.persistence import save_driftlessmap_file

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, _fiber, first_id, _raster = self.two_section_project(root)
            path = root / "two.dmap"
            self.assertTrue(window.save_project_called(path=str(path)))
            reopened, payload = self.open_project(root, path)

            # A schema 3 project: no sections block. Its earlier section's
            # mappings remain, listed as a section without a stored image.
            legacy = dict(payload, project_schema_version=3)
            legacy.pop("sections")
            legacy_path = root / "legacy.dmap"
            self.assertTrue(save_driftlessmap_file(str(legacy_path), legacy, "project")[0])
            old, _payload = self.open_project(root, legacy_path)
            self.assertEqual(len(old.sections), 1)
            self.assertEqual(old.sections_without_image(), [first_id])

            # A damaged stored section is left out; the project still opens.
            broken = dict(payload)
            block = dict(broken["sections"])
            item = dict(block["stored"][0])
            item["state"] = dict(item["state"], section_id="not-this-one")
            block["stored"] = [item]
            broken["sections"] = block
            broken_path = root / "broken.dmap"
            self.assertTrue(save_driftlessmap_file(str(broken_path), broken, "project")[0])
            damaged, _payload = self.open_project(root, broken_path)
            self.assertEqual(len(damaged.sections), 1)
            self.assertIn("do not belong", damaged.statusbar.currentMessage())

    @isolated_gui_test
    def test_export_all_results_writes_every_section_image_and_landmarks(self):
        import csv
        import json

        import tifffile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, _fiber, first_id, raster = self.two_section_project(root)
            second_raster = np.array(window.image_view.current_img)
            out = root / "results"
            paths, notes = window.export_all_results(str(out))
            sections = out / "sections"
            index = json.loads((sections / "sections.json").read_text())
            self.assertEqual([r["name"] for r in index], ["rostral", "pfc-2.png"])
            self.assertEqual(index[0]["section_id"], first_id)
            self.assertEqual(index[0]["atlas_plane"], "coronal")
            self.assertEqual(index[0]["atlas_page"], 12)
            self.assertTrue(index[1]["open"])
            for record, expected in zip(index, (raster, second_raster)):
                written = tifffile.imread(str(sections / record["image"]))
                np.testing.assert_array_equal(np.moveaxis(written, 0, -1), expected)
            with open(sections / index[0]["landmarks"]) as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 3)
            self.assertEqual(float(rows[0]["section_x"]), 2.0)
            self.assertIn(str(sections / "sections.json"), paths)

    @isolated_gui_test
    def test_the_classic_sections_dialog_lists_and_opens_sections(self):
        from driftlessmap.sections_dialog import SectionsDialog

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, _fiber, first_id, raster = self.two_section_project(root)
            self.assertIn(window.actionSections, window.menuFile.actions())
            dialog = SectionsDialog(window)
            self.assertEqual(dialog.list.count(), 2)
            self.assertIn("(open)", dialog.list.item(1).text())
            dialog.list.setCurrentRow(0)
            dialog.open_selected()
            self.assertEqual(window.section_id, first_id)
            np.testing.assert_array_equal(window.image_view.current_img, raster)
            self.assertIn("(open)", dialog.list.item(0).text())
            dialog.close()

    @isolated_gui_test
    def test_the_change_digest_covers_stored_sections_without_rereading_them(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window, _fiber, first_id, _raster = self.two_section_project(root)
            index = window.sections_index()
            self.assertIn(first_id, index["stored"])
            entry = window.sections.entry(first_id)
            with patch("driftlessmap.sections.state_digest") as digest:
                self.assertEqual(window.sections_index(), index)
                digest.assert_not_called()
            window.rename_section(first_id, "caudal")
            self.assertNotEqual(window.sections_index(), index)
            self.assertIsNotNone(entry._digest)


if __name__ == "__main__":
    unittest.main()
