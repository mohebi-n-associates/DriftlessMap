import unittest

import numpy as np

from driftlessmap.implants import (
    FIBER,
    PRISM,
    AtlasFrame,
    ImplantBook,
    csv_row,
    probe_csv_row,
    fill_outline,
    fit_fiber,
    fit_prism,
    model_segments,
    points_in_polygon,
    report_lines,
    resample_closed,
    validated_outline,
    validated_specs,
)
from driftlessmap.mapping_records import MappingLedger, new_identifier
from driftlessmap.probe_reconstruction import build_probe_reconstruction

SHAPE = (240, 240, 240)
BREGMA = np.array([120.0, 120.0, 160.0])  # brain surface at relative DV 0


def frame(voxel_um=10.0):
    labels = np.zeros(SHAPE, dtype=np.int32)
    labels[:, :, :160] = 1      # cortex below the surface (relative DV < 0)
    labels[:, :, :100] = 2      # a deeper region (relative DV < -60)
    info = {"index": [1, 2], "label": ["Cortex", "Deep"], "abbrev": ["CTX", "DP"]}
    return AtlasFrame(labels, info, BREGMA, voxel_um)


def coronal_rectangle(ap, ml_low, ml_high, dv_low, dv_high, step=1.0):
    """A closed rectangle in the coronal plane AP = ``ap`` (ML, AP, DV)."""
    corners = np.array([[ml_low, dv_low], [ml_high, dv_low], [ml_high, dv_high],
                        [ml_low, dv_high]])
    flat = resample_closed(corners, spacing=step)
    return np.stack([flat[:, 0], np.full(len(flat), ap), flat[:, 1]], axis=1)


def sagittal_rectangle(ml, ap_low, ap_high, dv_low, dv_high, step=1.0):
    corners = np.array([[ap_low, dv_low], [ap_high, dv_low], [ap_high, dv_high],
                        [ap_low, dv_high]])
    flat = resample_closed(corners, spacing=step)
    return np.stack([np.full(len(flat), ml), flat[:, 0], flat[:, 1]], axis=1)


def fiber_section(plane, offset, centre_ml, centre_ap, radius, tip_dv, top_dv=0.0):
    """Outline a vertical fiber of ``radius`` leaves in a coronal or sagittal section."""
    half = np.sqrt(max(radius ** 2 - offset ** 2, 0.25))
    if plane == "coronal":
        return coronal_rectangle(centre_ap + offset, centre_ml - half, centre_ml + half,
                                 tip_dv, top_dv)
    return sagittal_rectangle(centre_ml + offset, centre_ap - half, centre_ap + half,
                              tip_dv, top_dv)


class DefinitionTests(unittest.TestCase):
    def test_specs_are_completed_and_checked(self):
        self.assertEqual(validated_specs(FIBER, {}), {"diameter_um": 200.0, "na": 0.39})
        self.assertEqual(validated_specs(PRISM, {"width_um": 1000})["depth_um"], 1500.0)
        for kind, bad in ((FIBER, {"diameter_um": -1}), (FIBER, {"na": "x"}),
                          (FIBER, {"colour": 1}), (PRISM, {"face": "up"}),
                          ("probe", {})):
            with self.assertRaises(ValueError, msg=bad):
                validated_specs(kind, bad)

    def test_book_names_round_trip_and_damage(self):
        book = ImplantBook()
        fiber = book.add(FIBER)
        prism = book.add(PRISM, specs={"face": "medial"})
        self.assertEqual((fiber.name, prism.name), ("Fiber 1", "Prism 1"))
        self.assertEqual(book.add(FIBER, taken={"Fiber 2"}).name, "Fiber 3")
        with self.assertRaises(ValueError):
            book.add(FIBER, name="Fiber 1")
        with self.assertRaises(ValueError):
            book.rename(fiber.implant_id, "has-dash")
        book.rename(fiber.implant_id, "Fiber left")
        restored, problems = ImplantBook.from_list(book.to_list())
        self.assertEqual(problems, [])
        self.assertEqual([i.to_dict() for i in restored.implants()], book.to_list())
        saved = book.to_list()
        saved[0]["specs"] = {"diameter_um": 0}
        saved[1]["implant_id"] = "bad"
        restored, problems = ImplantBook.from_list(saved + [{"x": 1}])
        self.assertEqual(len(problems), 3)
        self.assertEqual(ImplantBook.from_list("x")[1], ["The saved implants are not a list."])

    def test_outlines(self):
        with self.assertRaises(ValueError):
            validated_outline([[0, 0], [1, 1]])
        with self.assertRaises(ValueError):
            validated_outline([[0, 0], [1, 1], [2, 2]])
        square = validated_outline([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]])
        self.assertEqual(len(square), 4)
        dense = resample_closed(square, spacing=2.0)
        self.assertEqual(len(dense), 20)
        self.assertLessEqual(np.max(np.linalg.norm(np.diff(np.vstack([dense, dense[:1]]),
                                                           axis=0), axis=1)), 2.0)
        inside = points_in_polygon(np.array([[5, 5], [11, 5], [0.5, 9.5]]), square)
        self.assertEqual(inside.tolist(), [True, False, True])
        samples = fill_outline(coronal_rectangle(3.0, 0, 10, -20, 0))
        np.testing.assert_allclose(samples[:, 1], 3.0)
        self.assertTrue(np.all((samples[:, 0] >= 0) & (samples[:, 0] <= 10)))

    def test_mapping_records_accept_implant_outlines(self):
        ledger = MappingLedger()
        section, implant = new_identifier(), new_identifier()
        source = {"points": [[0, 0], [5, 0], [5, 9]], "point": [[2.0, 8.0]]}
        record = ledger.record(section, "fiber", source, "a" * 64, "reviewed", "t",
                               probe=implant)
        restored, problems = MappingLedger.from_list(ledger.to_list())
        self.assertEqual(problems, [])
        np.testing.assert_array_equal(restored.by_unit(record.unit_id).source["point"],
                                      [[2.0, 8.0]])
        with self.assertRaises(ValueError):
            ledger.record(section, "prism", source, "a" * 64, "r", "t", probe="Prism 1")
        with self.assertRaises(ValueError):
            ledger.record(section, "fiber", {"points": [[0, 0], [1, 1]]}, "a" * 64, "r", "t",
                          probe=implant)


class FiberFitTests(unittest.TestCase):
    def check_tip(self, report, expected, tolerance=0.5):
        tip = np.asarray(report["tip"]["bregma_relative_vox"])
        self.assertLess(np.linalg.norm(tip - expected), tolerance, tip)

    def test_vertical_fiber_cut_coronally_and_sagittally(self):
        for plane in ("coronal", "sagittal"):
            pieces = [{"outline": fiber_section(plane, offset, 20.0, 0.0, 10.0, -50.0)}
                      for offset in (-6.0, 0.0, 6.0)]
            report = fit_fiber(pieces, {"diameter_um": 200}, frame())
            self.check_tip(report, [20.0, 0.0, -50.0])
            self.assertEqual(report["tip"]["region"], "Cortex")
            self.assertAlmostEqual(report["tip"]["dv_um"], 500.0, delta=5)
            self.assertAlmostEqual(report["depth_below_surface_um"], 500.0, delta=15)
            self.assertLess(report["angles"]["ml_angle_deg"], 1.0)
            self.assertEqual(report["warnings"], [], plane)
            self.assertEqual(report["section_planes"], [plane])

    def test_angled_fiber_tip_is_on_its_axis(self):
        angle = np.deg2rad(15)
        axis = np.array([np.sin(angle), 0.0, -np.cos(angle)])
        across = np.array([np.cos(angle), 0.0, np.sin(angle)])
        entry = np.array([10.0, 0.0, 0.0])
        tip = entry + 70.0 * axis
        pieces = []
        for ap in (-5.0, 0.0, 5.0):
            half = np.sqrt(100.0 - ap ** 2)
            corners = [entry - half * across, tip - half * across, tip + half * across,
                       entry + half * across]
            flat = resample_closed(np.array(corners)[:, [0, 2]], spacing=1.0)
            pieces.append({"outline": np.stack([flat[:, 0], np.full(len(flat), ap),
                                                flat[:, 1]], axis=1)})
        report = fit_fiber(pieces, {"diameter_um": 200}, frame())
        self.check_tip(report, tip, tolerance=1.0)
        self.assertAlmostEqual(report["angles"]["ml_angle_deg"], 15.0, delta=1.0)
        self.assertEqual(report["angles"]["ml_tilt"], "lateral")

    def test_marked_tip_one_section_and_width_warnings(self):
        piece = {"outline": fiber_section("coronal", 0.0, 20.0, 0.0, 10.0, -60.0),
                 "point": [20.0, 0.0, -58.0]}
        report = fit_fiber([piece], {"diameter_um": 200}, frame())
        self.check_tip(report, [20.0, 0.0, -58.0])
        self.assertEqual(report["tip_source"], "marked tip")
        self.assertAlmostEqual(report["tip_offset_from_fit_um"], 20.0, delta=1)
        self.assertTrue(any("Only one section" in w for w in report["warnings"]))

        wide = {"outline": fiber_section("coronal", 0.0, 20.0, 0.0, 20.0, -60.0)}
        report = fit_fiber([wide], {"diameter_um": 200}, frame())
        self.assertTrue(any("tissue damage" in w for w in report["warnings"]))
        narrow = {"outline": fiber_section("coronal", 9.9, 20.0, 0.0, 10.0, -60.0)}
        report = fit_fiber([narrow, narrow], {"diameter_um": 200}, frame())
        self.assertTrue(any("no section passed near" in w for w in report["warnings"]))

    def test_report_text_csv_and_model(self):
        pieces = [{"outline": fiber_section("coronal", o, 20.0, 0.0, 10.0, -60.0)}
                  for o in (-3.0, 3.0)]
        report = fit_fiber(pieces, {}, frame())
        lines = report_lines(report)
        self.assertIn("Tip", lines[0])
        self.assertIn("Cortex", lines[0])
        row = csv_row("Fiber 1", report)
        self.assertEqual(row["type"], "Optical fiber")
        self.assertEqual(row["region_acronym"], "CTX")
        self.assertEqual(model_segments(report["model"]).shape[1], 3)
        self.assertEqual(len(model_segments(report["model"])) % 2, 0)

    def test_parts_must_be_valid(self):
        with self.assertRaises(ValueError):
            fit_fiber([], {}, frame())
        with self.assertRaises(ValueError):
            fit_fiber([{"outline": [[0, 0, 0], [1, 1, 1]]}], {}, frame())


class ProbeRowTests(unittest.TestCase):
    def test_a_built_probe_gets_a_tip_summary_row(self):
        tip, entry = np.array([0.0, 0.0, -80.0]), np.array([0.0, 0.0, 0.0])
        index = lambda point: (point + BREGMA).astype(int)
        recon = build_probe_reconstruction(
            insertion_bregma_vox=entry, terminus_bregma_vox=tip,
            insertion_vox_index=index(entry), terminus_vox_index=index(tip),
            contact_bregma_vox=[np.array([[0.0, 0.0, -70.0]])],
            contact_vox_index=[index(np.array([[0.0, 0.0, -70.0]]))],
            contact_structure_ids=[np.array([2])],
            contact_local_from_tip_base_um=[np.array([[100.0, 0.0, 0.0]])],
            probe_length_um=800, probe_settings={"probe_type_name": "NP1.0"},
            site_face="Front", voxel_size_um=10, bregma_herbs_vox=BREGMA,
            herbs_atlas_shape=SHAPE,
            label_info={"index": np.array([1, 2]), "label": np.array(["Cortex", "Deep"]),
                        "abbrev": np.array(["CTX", "DP"]), "parent": np.array([0, 0]),
                        "color": np.array([[1, 2, 3], [4, 5, 6]])})
        row = probe_csv_row("Probe 1", recon, frame(), 2)
        self.assertEqual((row["type"], row["specs"], row["point"]), ("Probe", "NP1.0", "tip"))
        self.assertEqual((row["dv_um"], row["region_acronym"], row["sections"]), (800.0, "DP", 2))
        self.assertEqual(row["depth_below_surface_um"], 800.0)
        self.assertEqual(row["ap_tilt_deg"], 0.0)
        self.assertEqual(row["face"], "")


class PrismFitTests(unittest.TestCase):
    SPECS = {"width_um": 1500, "depth_um": 1500, "face": "lateral"}

    def test_coronal_sections_give_bottom_and_ml_edges(self):
        pieces = [{"outline": coronal_rectangle(ap, 40.0, 100.0, -80.0, 0.0)}
                  for ap in (-20.0, 0.0, 20.0)]
        report = fit_prism(pieces, self.SPECS, frame(voxel_um=25.0))
        self.assertAlmostEqual(report["bottom"]["dv_um"], 2000.0, delta=30)
        self.assertAlmostEqual(report["ml_medial_edge_um"], 1000.0, delta=1)
        self.assertAlmostEqual(report["ml_lateral_edge_um"], 2500.0, delta=1)
        self.assertAlmostEqual(report["ml_centre_um"], 1750.0, delta=1)
        self.assertAlmostEqual(report["face_um"], 2500.0, delta=1)
        self.assertEqual(report["ap_range_um"], [-500.0, 500.0])
        self.assertEqual(report["bottom"]["region"], "Deep")
        self.assertTrue(any("AP extent" in w for w in report["warnings"]))
        self.assertFalse(any("ML edges" in w for w in report["warnings"]))
        self.assertFalse(any("specified" in w for w in report["warnings"]))
        self.assertTrue(report["face_regions"])
        self.assertAlmostEqual(report["depth_below_surface_um"], 2000.0, delta=40)

    def test_left_hemisphere_and_medial_face(self):
        pieces = [{"outline": coronal_rectangle(0.0, -100.0, -40.0, -80.0, 0.0)}]
        report = fit_prism(pieces, dict(self.SPECS, face="medial"), frame(voxel_um=25.0))
        self.assertAlmostEqual(report["ml_medial_edge_um"], -1000.0, delta=1)
        self.assertAlmostEqual(report["ml_lateral_edge_um"], -2500.0, delta=1)
        self.assertAlmostEqual(report["face_um"], -1000.0, delta=1)
        self.assertTrue(any("Only one section" in w for w in report["warnings"]))

    def test_sagittal_sections_limit_ml_and_check_size(self):
        pieces = [{"outline": sagittal_rectangle(ml, -30.0, 30.0, -80.0, 0.0)}
                  for ml in (50.0, 70.0, 90.0)]
        report = fit_prism(pieces, self.SPECS, frame(voxel_um=25.0))
        self.assertAlmostEqual(report["ml_medial_edge_um"], 1250.0, delta=1)
        self.assertAlmostEqual(report["ml_lateral_edge_um"], 2250.0, delta=1)
        self.assertTrue(any("ML edges" in w for w in report["warnings"]))
        self.assertAlmostEqual(report["bottom"]["dv_um"], 2000.0, delta=30)

        small = [{"outline": coronal_rectangle(0.0, 40.0, 70.0, -80.0, 0.0)}]
        report = fit_prism(small, self.SPECS, frame(voxel_um=25.0))
        self.assertTrue(any("specified" in w for w in report["warnings"]))

    def test_marked_bottom_csv_and_block(self):
        pieces = [{"outline": coronal_rectangle(0.0, 40.0, 100.0, -80.0, 0.0),
                   "point": [70.0, 0.0, -78.0]}]
        report = fit_prism(pieces, self.SPECS, frame(voxel_um=25.0))
        self.assertEqual(report["bottom_source"], "marked bottom edge")
        self.assertAlmostEqual(report["bottom"]["dv_um"], 1950.0, delta=1)
        row = csv_row("Prism 1", report)
        self.assertEqual(row["face"], "lateral")
        self.assertEqual(row["point"], "bottom centre")
        self.assertEqual(len(model_segments(report["model"])), 24)
        self.assertTrue(any("Imaging face" in line for line in report_lines(report)))


if __name__ == "__main__":
    unittest.main()
