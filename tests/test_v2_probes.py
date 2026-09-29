import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from driftlessmap.v2.probes import ProbeBook, group_of, probe_of


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _Row:
    def __init__(self):
        self.text_btn = _Label()
        self.colour = None

    def set_icon_style(self, colour):
        self.colour = colour


class _Signal:
    def __init__(self):
        self.emitted = []

    def emit(self, value):
        self.emitted.append(value)


class FakeObjects:
    def __init__(self):
        self.obj_name, self.obj_type, self.obj_list, self.obj_data = [], [], [], []
        self.current_obj_index = None
        self.sig_color_changed = _Signal()

    def add(self, name, kind, data=None):
        self.obj_name.append(name)
        self.obj_type.append(kind)
        self.obj_data.append(data)
        self.obj_list.append(_Row())

    def delete_objects(self, indexes):
        for index in sorted(indexes, reverse=True):
            for column in (self.obj_name, self.obj_type, self.obj_list, self.obj_data):
                del column[index]

    def unmerge_objects(self):
        index = self.current_obj_index
        pieces = self.obj_data[index]
        self.delete_objects([index])
        for name in pieces:
            self.add(name, "probe piece")


class _ColourButton:
    def __init__(self):
        self.colour = None

    def setColor(self, colour):
        self.colour = colour


class _Tools:
    def __init__(self):
        self.probe_color_btn = _ColourButton()


class FakeEngine:
    """The part of the engine the probe book uses."""

    def __init__(self, section_image=True):
        self.object_ctrl = FakeObjects()
        self.working_img_data = {"img-probe": []}
        self.working_atlas_data = {"atlas-probe": []}
        self.h2a_transferred = False
        self.tool_box = _Tools()
        self.shanks = 1
        self.merges = []
        self.image_view = type("V", (), {"image_file": object() if section_image else None})()

    def transfer_to_atlas_clicked(self):
        self.h2a_transferred = not self.h2a_transferred

    def transform_accept(self):
        self.working_atlas_data["atlas-probe"] = list(self.working_img_data["img-probe"])
        self.working_img_data["img-probe"] = []

    def make_probe_piece(self):
        if not self.working_atlas_data["atlas-probe"]:
            return
        for shank in range(self.shanks):
            name = "probe {} - piece".format(shank) if self.shanks > 1 else "probe - piece"
            self.object_ctrl.add(name, "probe piece")
        self.working_atlas_data["atlas-probe"] = []

    def merge_probes(self, only=None):
        o = self.object_ctrl
        self.merges.append(sorted(only))
        for group in sorted(only):
            parts = [i for i, n in enumerate(o.obj_name)
                     if o.obj_type[i] == "probe piece" and group_of(n) == group]
            names = [o.obj_name[i] for i in parts]
            o.delete_objects(parts)
            o.add(group, "merged probe", names)


class ProbeBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def mark(self, engine, count=2):
        engine.working_img_data["img-probe"] = [[float(i), float(i)] for i in range(count)]

    def test_sections_are_filed_under_the_active_probe(self):
        engine = FakeEngine()
        book = ProbeBook(engine)
        first = book.new()
        self.assertEqual(book.names(), ["Probe 1"])
        self.assertFalse(book.add_section(first)[0])       # nothing marked yet
        self.mark(engine, 1)
        self.assertFalse(book.add_section(first)[0])       # one point is not a track
        self.mark(engine)
        ok, _message = book.add_section(first)
        self.assertTrue(ok)
        self.assertTrue(engine.h2a_transferred)           # warped automatically
        engine.h2a_transferred = False
        self.mark(engine)
        book.add_section(first)
        second = book.new()
        self.mark(engine)
        book.add_section(second)
        self.assertEqual(book.names(), ["Probe 1", "Probe 2"])
        self.assertEqual(book.summary("Probe 1"), "2 sections · not built")
        self.assertEqual(engine.object_ctrl.obj_name,
                         ["Probe 1 - piece", "Probe 1 - piece", "Probe 2 - piece"])

    def test_build_only_the_chosen_probe_and_rebuild_after_new_sections(self):
        engine = FakeEngine()
        book = ProbeBook(engine)
        for probe in (book.new(), book.new()):
            self.mark(engine)
            book.add_section(probe)
        ok, _ = book.build("Probe 1")
        self.assertTrue(ok)
        self.assertEqual(engine.merges, [["Probe 1"]])
        self.assertEqual(book.summary("Probe 1"), "built")
        self.assertEqual(book.summary("Probe 2"), "1 section · not built")
        built = book.built("Probe 1")[0]
        self.assertIsNotNone(engine.object_ctrl.obj_list[built].colour)
        # A new section after building: the next build uses every section.
        self.mark(engine)
        engine.h2a_transferred = False
        book.add_section("Probe 1")
        self.assertIn("new section", book.summary("Probe 1"))
        book.build("Probe 1")
        rebuilt = engine.object_ctrl.obj_data[book.built("Probe 1")[0]]
        self.assertEqual(len(rebuilt), 2)
        self.assertEqual(len(book.built("Probe 1")), 1)

    def test_multi_shank_parts_and_rename(self):
        engine = FakeEngine(section_image=False)
        engine.shanks = 2
        book = ProbeBook(engine)
        probe = book.new()
        engine.working_atlas_data["atlas-probe"] = [[0, 0], [1, 1]]   # pre-plan on the atlas
        self.assertTrue(book.add_section(probe)[0])
        self.assertEqual(engine.object_ctrl.obj_name,
                         ["Probe 1 shank 1 - piece", "Probe 1 shank 2 - piece"])
        self.assertEqual(book.names(), ["Probe 1"])
        book.build(probe)
        self.assertEqual(engine.merges, [["Probe 1 shank 1", "Probe 1 shank 2"]])
        self.assertEqual(book.rename("Probe 1", "  Planned   V1 "), "Planned V1")
        self.assertEqual(sorted(engine.object_ctrl.obj_name),
                         ["Planned V1 shank 1", "Planned V1 shank 2"])
        self.assertEqual(probe_of("Planned V1 shank 2"), "Planned V1")

    def test_invalid_names(self):
        book = ProbeBook(FakeEngine())
        book.new()
        book.new()
        for name in ("", "left-probe", "Probe 3 shank 2"):
            with self.subTest(name):
                with self.assertRaises(ValueError):
                    book.rename("Probe 1", name)
        with self.assertRaises(ValueError):
            book.rename("Probe 1", "Probe 2")


if __name__ == "__main__":
    unittest.main()
