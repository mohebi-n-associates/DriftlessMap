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
