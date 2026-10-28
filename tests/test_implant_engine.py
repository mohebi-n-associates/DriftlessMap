"""Implants in the engine: outlines, mapping, undo, building and projects."""

import tests.settings_isolation  # noqa: F401  (before the app reads settings)
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from functools import wraps
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
CHILD = os.environ.get("DRIFTLESSMAP_IMPLANT_TEST_CHILD") == "1"

import cv2
import numpy as np

from driftlessmap.persistence import load_driftlessmap_file, save_driftlessmap_file

if CHILD:
    from PyQt6.QtWidgets import QApplication, QFileDialog

    from driftlessmap.app import DriftlessMap

# A vertical slot in the 24 x 32 section: the fiber track.
SLOT = [[10.0, 4.0], [14.0, 4.0], [14.0, 20.0], [10.0, 20.0]]


def isolated_gui_test(test):
    """Run each OpenGL integration case in its own Qt process."""

    @wraps(test)
    def wrapper(self):
        if CHILD:
            return test(self)
        environment = os.environ.copy()
        environment["DRIFTLESSMAP_IMPLANT_TEST_CHILD"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "unittest",
             "tests.test_implant_engine.{}".format(test.__qualname__)],
            check=False, capture_output=True, text=True, env=environment)
        self.assertEqual(result.returncode, 0, "{}\n{}".format(result.stdout, result.stderr))

    return wrapper


class ImplantEngineTests(unittest.TestCase):
    @isolated_gui_test
    def test_specs_invalidate_build_through_save_reopen_export_and_rebuild(self):
        from driftlessmap.mapping_records import BUILD_CHANGED

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_section(root)
            fiber = window.add_implant("fiber", specs={"diameter_um": 100})
            window.set_implant_outline(fiber.implant_id, SLOT)
            self.assertTrue(window.map_implant(fiber.implant_id)[0])
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            window.set_implant_specs(fiber.implant_id, {"diameter_um": 400})
            built = window.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(window.object_mapping_status(built), BUILD_CHANGED)
            self.assertIn(built, window.out_of_date_objects())
            project = str(root / "changed.dmap")
            self.assertTrue(window.save_project_called(path=project))
            payload, error = load_driftlessmap_file(project, expected_kind="project")
            self.assertIsNone(error)
            restored = self.window_with_section(root)
            prepared = restored.prepare_project_sources(payload, project)
            self.assertTrue(restored.load_project(prepared))
            built = restored.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(restored.object_mapping_status(built), BUILD_CHANGED)
            table = root / "implants.csv"
            restored.export_implant_table(table)
            with table.open() as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["status"], BUILD_CHANGED)
            self.assertIn("100", row["specs"])
            self.assertTrue(restored.build_implant(fiber.implant_id)[0])
            built = restored.implant_objects(fiber.implant_id, built=True)[0]
            self.assertIsNone(restored.implant_build_status(built))
            self.assertEqual(restored.implant_report(fiber.implant_id)["specs"]["diameter_um"], 400)
            self.assertTrue(restored.undo_mapping_step())
            self.assertEqual(restored.implant_report(fiber.implant_id)["specs"]["diameter_um"], 100)
            built = restored.implant_objects(fiber.implant_id, built=True)[0]
            self.assertEqual(restored.object_mapping_status(built), BUILD_CHANGED)
            self.assertTrue(restored.redo_mapping_step())
            self.assertEqual(restored.implant_report(fiber.implant_id)["specs"]["diameter_um"], 400)

    @isolated_gui_test
    def test_unrecordable_mutation_clears_both_history_directions(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.window_with_section(Path(folder))
            fiber = window.add_implant("fiber")
            window.set_implant_outline(fiber.implant_id, SLOT)
            self.assertTrue(window.map_implant(fiber.implant_id)[0])
            self.assertTrue(window.undo_mapping_step())
            self.assertIsNotNone(window.undo_history.redo_label())
            window.undo_history.budget_bytes = 1
            self.assertTrue(window.map_implant(fiber.implant_id)[0])
            self.assertIsNone(window.undo_history.undo_label())
            self.assertIsNone(window.undo_history.redo_label())

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

    def window_with_section(self, root):
        from tests.atlas_fixture import make_processed_atlas

        window = DriftlessMap()
        self.windows.append(window)
        self.assertTrue(window.load_volume_atlas(str(make_processed_atlas(root / "atlas"))))
        source = root / "section.png"
        image = np.zeros((32, 24, 3), dtype=np.uint8)
        image[4:28, 4:20] = 200
        cv2.imwrite(str(source), image)
        self.assertTrue(window.load_single_image_file(str(source), ".png"))
        window.current_img_path = str(source)
        return window

    @isolated_gui_test
    def test_map_undo_edit_update_and_build_a_fiber(self):
        with tempfile.TemporaryDirectory() as folder:
            window = self.window_with_section(Path(folder))
            fiber = window.add_implant("fiber", specs={"diameter_um": 100})
            self.assertEqual(fiber.name, "Fiber 1")
            ok, message = window.map_implant(fiber.implant_id)
            self.assertFalse(ok)
            self.assertIn("Draw the outline", message)

            window.set_implant_outline(fiber.implant_id, SLOT)
            window.set_implant_point(fiber.implant_id, [12.0, 20.0])
            ok, message = window.map_implant(fiber.implant_id)
            self.assertTrue(ok, message)
            self.assertTrue(window.h2a_transferred)
            o = window.object_ctrl
            self.assertEqual(o.obj_type, ["fiber piece"])
            self.assertEqual(o.obj_name, ["Fiber 1 - piece"])
            record = window.mapping_ledger.get(window.section_id, "fiber", fiber.implant_id)
            self.assertEqual(o.obj_derivation, [[[record.unit_id, 1]]])
            part = o.obj_data[0]
            self.assertEqual(part["implant_id"], fiber.implant_id)
            self.assertEqual(np.asarray(part["outline"]).shape[1], 3)
            self.assertEqual(len(part["point"]), 3)
            self.assertEqual(window.implant_outlines, {})
            xs, _ys = window._kept_outlines_item.getData()
            self.assertGreater(len(xs), 4)
            self.assertEqual(window.undo_history.undo_label(), "Map Fiber 1")

            # Undo brings the outline back and removes the part and record.
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, [])
            self.assertEqual(len(window.mapping_ledger), 0)
            np.testing.assert_allclose(window.implant_outline(fiber.implant_id)["points"], SLOT)
            self.assertTrue(window.redo_mapping_step())
            self.assertEqual(o.obj_type, ["fiber piece"])

            # Edit marks returns the outline; mapping it again replaces the part.
            self.assertTrue(window.edit_mapped_marks(record.unit_id))
            np.testing.assert_allclose(window.implant_outline(fiber.implant_id)["points"], SLOT)
            window.set_implant_outline(fiber.implant_id,
                                       [[10.0, 4.0], [14.0, 4.0], [14.0, 22.0], [10.0, 22.0]])
            self.assertTrue(window.map_implant(fiber.implant_id)[0])
            self.assertEqual(o.obj_type, ["fiber piece"])
            again = window.mapping_ledger.by_unit(record.unit_id)
            self.assertEqual(again.revision, 2)
            updated = window.update_mapping(record.unit_id)
            self.assertEqual(updated.revision, 3)
            self.assertEqual(o.obj_derivation, [[[record.unit_id, 3]]])

            ok, message = window.build_implant(fiber.implant_id)
            self.assertTrue(ok, message)
            self.assertEqual(o.obj_type, ["merged fiber"])
            report = window.implant_report(fiber.implant_id)
            self.assertEqual(report["tip_source"], "marked tip")
            self.assertIn(report["tip"]["region"], ("child", "grandchild"))
            self.assertEqual(o.obj_derivation, [[[record.unit_id, 3]]])
            self.assertEqual(window.object_mapping_status(0), "current")
            self.assertIsNotNone(window.object_3d_list[0])

            # Building again rebuilds from the same part and, changing nothing,
            # is not a separate undo step; undo restores the part.
            self.assertTrue(window.build_implant(fiber.implant_id)[0])
            self.assertEqual(o.obj_type, ["merged fiber"])
            self.assertEqual(window.undo_history.undo_label(), "Build Fiber 1")
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, ["fiber piece"])
            self.assertEqual(window.undo_history.undo_label(), "Update mapping of Fiber 1")

    @isolated_gui_test
    def test_rename_delete_projects_tables_and_object_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            window = self.window_with_section(root)
            prism = window.add_implant("prism", specs={"width_um": 300, "depth_um": 300,
                                                       "face": "medial"})
            fiber = window.add_implant("fiber", name="Fiber left")
            window.set_implant_outline(prism.implant_id,
                                       [[6.0, 6.0], [18.0, 6.0], [18.0, 24.0], [6.0, 24.0]])
            self.assertTrue(window.map_implant(prism.implant_id)[0])
            self.assertTrue(window.build_implant(prism.implant_id)[0])
            window.set_implant_outline(fiber.implant_id, SLOT)
            o = window.object_ctrl
            self.assertEqual(o.obj_type, ["merged prism"])
            report = window.implant_report(prism.implant_id)
            self.assertEqual(report["face"], "medial")

            window.rename_implant(prism.implant_id, "Prism A")
            self.assertEqual(o.obj_name, ["Prism A"])
            with self.assertRaises(ValueError):
                window.rename_implant(fiber.implant_id, "Prism A")

            table = root / "implants.csv"
            self.assertEqual(window.export_implant_table(str(table)), 1)
            with table.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["name"], "Prism A")
            self.assertEqual(rows[0]["face"], "medial")

            # The project keeps implants, unmapped outlines, records and objects.
            project = root / "implants.dmap"
            with patch.object(QFileDialog, "getSaveFileName",
                              return_value=(str(project), "DriftlessMap Project (*.dmap)")):
                window.save_project_called(portable=False)
            payload, error = load_driftlessmap_file(project, "project")
            self.assertIsNone(error)
            self.assertEqual([i["name"] for i in payload["implants"]], ["Prism A", "Fiber left"])
            restored = DriftlessMap()
            self.windows.append(restored)
            self.assertTrue(restored.load_volume_atlas(window.volume_atlas_path))
            restored.load_project(restored.prepare_project_sources(payload, str(project)))
            self.assertEqual([i.name for i in restored.implants.implants()],
                             ["Prism A", "Fiber left"])
            np.testing.assert_allclose(
                restored.implant_outline(fiber.implant_id)["points"], SLOT)
            self.assertEqual(restored.object_ctrl.obj_type, ["merged prism"])
            self.assertEqual(restored.implant_report(prism.implant_id)["face"], "medial")
            self.assertEqual(len(restored.mapping_ledger), 1)

            # Projects without implants (2.0.0a12 and earlier) still open.
            older = dict(payload)
            older.pop("implants")
            older.pop("implant_outlines")
            old_window = DriftlessMap()
            self.windows.append(old_window)
            old_window.load_project(old_window.prepare_project_sources(older, str(project)))
            self.assertEqual(len(old_window.implants), 0)

            # An exported prism imports into another project as an implant.
            exported = root / "prism.dmapobj"
            save_driftlessmap_file(exported, {"type": "merged prism", "name": "Prism A",
                                              "data": o.obj_data[0]}, "object")
            other = self.window_with_section(root / "other")
            with patch.object(QFileDialog, "getOpenFileNames",
                              return_value=([str(exported)], "")):
                other.load_objects()
            self.assertEqual(other.object_ctrl.obj_type, ["merged prism"])
            adopted = other.implants.implants()
            self.assertEqual([i.name for i in adopted], ["Prism A"])
            self.assertIsNotNone(other.implant_report(adopted[0].implant_id))

            # Export all results: a project copy, objects and the implant table in one
            # folder, without changing the project being worked on.
            window.current_project_path = str(project)
            out = root / "results"
            paths, notes = window.export_all_results(str(out))
            names = sorted(str(Path(p).relative_to(out)) for p in paths)
            layers = [n for n in names if n.startswith("layers")]
            # Each layer as .dmaplayer (image layers add a .jpg preview).
            self.assertEqual(len([n for n in layers if n.endswith(".dmaplayer")]),
                             len(window.layer_ctrl.layer_link))
            self.assertEqual([n for n in names if n not in layers],
                             ["implants.csv", "implants.dmap",
                              str(Path("objects") / "Prism A.dmapobj")])
            self.assertEqual(notes, [])
            self.assertEqual(window.current_project_path, str(project))
            copy, error = load_driftlessmap_file(out / "implants.dmap", "project")
            self.assertIsNone(error)
            self.assertEqual([i["name"] for i in copy["implants"]], ["Prism A", "Fiber left"])
            exported_object, error = load_driftlessmap_file(
                out / "objects" / "Prism A.dmapobj", "object")
            self.assertIsNone(error)
            self.assertEqual(exported_object["type"], "merged prism")

            # Deleting an implant removes its objects and records; undo restores them.
            self.assertTrue(window.delete_implant(prism.implant_id))
            self.assertEqual(o.obj_type, [])
            self.assertEqual(len(window.mapping_ledger), 0)
            self.assertIsNone(window.implants.get(prism.implant_id))
            self.assertTrue(window.undo_mapping_step())
            self.assertEqual(o.obj_type, ["merged prism"])
            self.assertEqual(window.implants.get(prism.implant_id).name, "Prism A")


if __name__ == "__main__":
    unittest.main()
