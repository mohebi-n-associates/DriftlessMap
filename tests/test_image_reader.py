import importlib.util
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
import tifffile


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "image_reader.py"
SPEC = importlib.util.spec_from_file_location("image_reader", MODULE_PATH)
image_reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(image_reader)


class TiffReaderTests(unittest.TestCase):
    def test_tiff_is_the_default_histology_dialog_filter(self):
        self.assertEqual(
            image_reader.HISTOLOGY_IMAGE_FILTERS[0],
            "TIFF (*.tif *.tiff)",
        )
        self.assertTrue(
            image_reader.HISTOLOGY_IMAGE_FILTER.startswith(
                "TIFF (*.tif *.tiff);;"
            )
        )

    def test_uint8_grayscale_is_one_channel_not_rgb(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "gray.tif"
            tifffile.imwrite(path, np.arange(20, dtype=np.uint8).reshape(4, 5))
            reader = image_reader.TIFFReader(path)

        self.assertEqual(reader.error_index, 0)
        self.assertFalse(reader.is_rgb)
        self.assertEqual(reader.pixel_type, "gray8")
        self.assertEqual(reader.n_channels, 1)
        self.assertEqual(reader.data["scene 0"].shape, (4, 5, 1))

    def test_rgb_and_page_stack_have_distinct_contracts(self):
        with tempfile.TemporaryDirectory() as folder:
            rgb_path = Path(folder) / "rgb.tif"
            stack_path = Path(folder) / "stack.tif"
            tifffile.imwrite(rgb_path, np.zeros((4, 5, 3), dtype=np.uint8))
            tifffile.imwrite(
                stack_path,
                np.zeros((6, 4, 5), dtype=np.uint16),
                metadata={"axes": "ZYX"},
            )

            rgb = image_reader.TIFFReader(rgb_path)
            stack = image_reader.TIFFReader(stack_path)

        self.assertTrue(rgb.is_rgb)
        self.assertEqual(rgb.n_channels, 3)
        self.assertEqual(rgb.n_pages, 1)
        self.assertFalse(stack.is_rgb)
        self.assertEqual(stack.n_channels, 1)
        self.assertEqual(stack.n_pages, 6)
        self.assertEqual(stack.data["scene 0"].shape, (6, 4, 5))

    def test_series_with_different_layouts_report_error_without_uninitialized_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "multi.tif"
            with tifffile.TiffWriter(path) as writer:
                writer.write(np.zeros((4, 5), dtype=np.uint8))
                writer.write(np.ones((6, 7), dtype=np.uint16))
            reader = image_reader.TIFFReader(path)

        self.assertEqual(reader.error_index, 1)
        self.assertEqual(reader.data, {})

    def test_six_channel_uint16_is_kept_natively(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "channels.tif"
            data = np.arange(6 * 5 * 4, dtype=np.uint16).reshape(6, 5, 4) * 500
            tifffile.imwrite(path, data, imagej=True, metadata={"axes": "CYX"})
            reader = image_reader.TIFFReader(path)

        self.assertEqual(reader.error_index, 0)
        self.assertEqual(reader.n_channels, 6)
        self.assertEqual(reader.data["scene 0"].dtype, np.uint16)
        np.testing.assert_array_equal(reader.data["scene 0"], np.moveaxis(data, 0, -1))
        self.assertEqual(len(reader.rgb_colors), 6)
        self.assertEqual(len(reader.channel_name), 6)

    def test_more_channels_than_the_limit_is_rejected_before_ui_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "channels.tif"
            tifffile.imwrite(
                path,
                np.zeros((image_reader.MAX_CHANNELS + 1, 4, 6), dtype=np.uint8),
                imagej=True,
                metadata={"axes": "CYX"},
            )
            reader = image_reader.TIFFReader(path)

        self.assertEqual(reader.error_index, 8)
        self.assertNotIn("scene 0", reader.data)


class FolderReaderTests(unittest.TestCase):
    def test_folder_reader_is_sorted_and_supplies_complete_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            cv2.imwrite(str(folder / "b.png"), np.zeros((3, 4, 3), dtype=np.uint8))
            cv2.imwrite(str(folder / "A.jpg"), np.ones((3, 4, 3), dtype=np.uint8))
            (folder / "ignored.pdf").write_bytes(b"not an image")

            reader = image_reader.ImagesReader(folder)

        self.assertEqual(reader.file_name_list, ["A", "b"])
        self.assertEqual(reader.n_scenes, 2)
        self.assertEqual(reader.n_pages, 1)
        self.assertEqual(reader.scale, {"scene 0": 1.0, "scene 1": 1.0})
        self.assertEqual(reader.data["scene 0"].shape, (3, 4, 3))


class EmbeddedReaderTests(unittest.TestCase):
    def test_embedded_reader_preserves_active_raster_contract(self):
        pixels = np.arange(24, dtype=np.uint16).reshape(3, 4, 2)
        reader = image_reader.EmbeddedImageReader(
            pixels,
            {
                "is_rgb": False,
                "pixel_type": "gray16",
                "level": 65535,
                "n_channels": 2,
                "data_type": "uint16",
                "rgb_colors": [(255, 0, 0), (0, 255, 0)],
                "channel_name": ["A", "B"],
            },
        )

        self.assertEqual(reader.n_scenes, 1)
        self.assertEqual(reader.n_pages, 1)
        self.assertEqual(reader.level, 65535)
        np.testing.assert_array_equal(reader.data["scene 0"], pixels)



class EmbeddedReaderScaleTests(unittest.TestCase):
    def test_embedded_raster_keeps_its_saved_scale(self):
        pixels = np.zeros((4, 5, 3), dtype=np.uint8)
        reader = image_reader.EmbeddedImageReader(pixels, {"image_scale": 0.1})
        self.assertEqual(reader.scale["scene 0"], 0.1)

    def test_invalid_or_missing_scale_falls_back_to_full_resolution(self):
        pixels = np.zeros((4, 5, 3), dtype=np.uint8)
        for metadata in (None, {}, {"image_scale": 0}, {"image_scale": "x"}):
            reader = image_reader.EmbeddedImageReader(pixels, metadata)
            self.assertEqual(reader.scale["scene 0"], 1.0)


class InputRobustnessTests(unittest.TestCase):
    def test_non_ascii_paths_decode(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / "Müller åß"
            directory.mkdir()
            path = directory / "slide.png"
            ok, encoded = cv2.imencode(".png", np.full((4, 5, 3), 90, dtype=np.uint8))
            self.assertTrue(ok)
            path.write_bytes(encoded.tobytes())
            reader = image_reader.ImageReader(path)
            self.assertEqual(reader.data["scene 0"].shape, (4, 5, 3))

    def test_tiff_folders_keep_their_bit_depth(self):
        with tempfile.TemporaryDirectory() as folder:
            for index in range(2):
                tifffile.imwrite(
                    Path(folder) / "section{}.tif".format(index),
                    np.full((6, 7), 4000 + index, dtype=np.uint16),
                )
            reader = image_reader.ImagesReader(folder)
            self.assertEqual(reader.n_scenes, 2)
            self.assertEqual(reader.data_type, "uint16")
            self.assertEqual(reader.level, 65535)
            self.assertEqual(reader.n_channels, 1)
            self.assertEqual(int(reader.data["scene 1"][0, 0, 0]), 4001)

    def test_tiff_folders_with_mixed_layouts_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            tifffile.imwrite(Path(folder) / "a.tif", np.zeros((6, 7), dtype=np.uint16))
            tifffile.imwrite(Path(folder) / "b.tif", np.zeros((6, 7), dtype=np.uint8))
            with self.assertRaisesRegex(ValueError, "different bit depth"):
                image_reader.ImagesReader(folder)

if __name__ == "__main__":
    unittest.main()


class TiffLayoutTests(unittest.TestCase):
    def write(self, folder, name, data, **kwargs):
        path = Path(folder) / name
        tifffile.imwrite(path, data, **kwargs)
        return path

    def test_imagej_hyperstack_pages_over_z_and_keeps_every_channel(self):
        data = np.arange(5 * 3 * 6 * 7, dtype=np.uint16).reshape(5, 3, 6, 7)
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "zcyx.tif", data, imagej=True, metadata={"axes": "ZCYX"})
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 0)
        self.assertEqual((reader.n_channels, reader.n_pages, reader.page_axis), (3, 5, "Z"))
        self.assertEqual(reader.data["scene 0"].shape, (5, 6, 7, 3))
        np.testing.assert_array_equal(reader.data["scene 0"][2], np.moveaxis(data[2], 0, -1))

    def test_time_is_fixed_when_z_is_browsed(self):
        data = np.zeros((2, 4, 3, 6, 7), dtype=np.uint16)
        data[0, 1, 2] = 9
        data[1] = 5
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "tzcyx.tif", data, imagej=True, metadata={"axes": "TZCYX"})
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 0)
        self.assertEqual(reader.fixed_axes, {"T": 0})
        self.assertTrue(any("T plane 1 of 2" in note for note in reader.notes))
        self.assertEqual(reader.data["scene 0"].shape, (4, 6, 7, 3))
        self.assertEqual(int(reader.data["scene 0"][1, ..., 2].max()), 9)

    def test_chosen_time_plane_is_read(self):
        data = np.zeros((3, 4, 2, 6, 7), dtype=np.uint16)
        for t in range(3):
            data[t] = t + 1
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "tzcyx.tif", data, imagej=True, metadata={"axes": "TZCYX"})
            reader = image_reader.TIFFReader(path, planes={"T": 2})
            beyond = image_reader.TIFFReader(path, planes={"T": 3})
        self.assertEqual(reader.error_index, 0)
        self.assertEqual((reader.fixed_axes, reader.fixed_axis_sizes), ({"T": 2}, {"T": 3}))
        self.assertTrue(np.all(reader.data["scene 0"] == 3))
        self.assertEqual(beyond.error_index, 9)
        self.assertIsNotNone(beyond.error_message)

    def test_plane_selection_is_validated(self):
        self.assertEqual(image_reader.plane_selection({"T": 2, "R": 0}), {"T": 2, "R": 0})
        for bad in (None, [], {"T": -1}, {"T": 1.5}, {"C": 0}, {"TT": 0}, {"T": True}):
            self.assertEqual(image_reader.plane_selection(bad), {}, bad)

    def test_pyramid_levels_are_read_on_request(self):
        data = np.random.default_rng(4).integers(0, 60000, (2, 64, 80), dtype=np.uint16)
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "pyramid.ome.tif")
            with tifffile.TiffWriter(path) as tiff:
                tiff.write(data, subifds=2, metadata={"axes": "CYX"}, tile=(16, 16))
                tiff.write(data[:, ::2, ::2], subfiletype=1, tile=(16, 16))
                tiff.write(data[:, ::4, ::4], subfiletype=1, tile=(16, 16))
            reader = image_reader.TIFFReader(path)
            self.assertEqual(reader.error_index, 0)
            self.assertTrue(reader.has_levels)
            self.assertEqual(reader.level_scales, [1.0, 0.5, 0.25])
            self.assertEqual(reader.data["scene 0"].shape, (64, 80, 2))
            reader.read_data(0.3, scene_index=0)
            self.assertEqual(reader.scale["scene 0"], 0.5)
            np.testing.assert_array_equal(reader.data["scene 0"],
                                          np.moveaxis(data[:, ::2, ::2], 0, -1))
            reader.read_data(0.25, scene_index=0)
            self.assertEqual(reader.data["scene 0"].shape, (16, 20, 2))
            reader.read_data(None, scene_index=0)
            self.assertEqual((reader.scale["scene 0"], reader.data["scene 0"].shape),
                             (1.0, (64, 80, 2)))

    def test_level_choice_keeps_at_least_the_requested_resolution(self):
        scales = [1.0, 0.5, 0.25]
        self.assertEqual(image_reader.choose_level(scales, None), 0)
        self.assertEqual(image_reader.choose_level(scales, 1.0), 0)
        self.assertEqual(image_reader.choose_level(scales, 0.6), 0)
        self.assertEqual(image_reader.choose_level(scales, 0.5), 1)
        self.assertEqual(image_reader.choose_level(scales, 0.01), 2)

    def test_ome_channel_names_and_colours(self):
        data = np.zeros((3, 6, 7), dtype=np.uint16)
        metadata = {"axes": "CYX", "Channel": {"Name": ["DAPI", "GFP", "Tracer"],
                                               "Color": [65535, 16711935, -16776961]}}
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "ome.ome.tif", data, ome=True, metadata=metadata)
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 0)
        self.assertEqual(reader.channel_name, ["DAPI", "GFP", "Tracer"])
        self.assertEqual(reader.rgb_colors[0], (0, 0, 255))
        self.assertEqual(reader.rgb_colors[1], (0, 255, 0))
        self.assertEqual(reader.rgb_colors[2], (255, 0, 0))

    def test_named_channels_without_colours_get_conventional_colours(self):
        data = np.zeros((4, 6, 7), dtype=np.uint16)
        metadata = {"axes": "CYX", "Channel": {"Name": ["GFP", "Hoechst 33342", "tdTomato",
                                                        "Tracer"]}}
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "named.ome.tif", data, ome=True, metadata=metadata)
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 0)
        self.assertEqual(reader.rgb_colors[:3], [(0, 255, 0), (0, 90, 255), (255, 0, 0)])
        # Unrecognised names keep the positional default.
        self.assertEqual(reader.rgb_colors[3], image_reader.CHANNEL_COLORS[3])

    def test_named_colours_are_used_once_and_unnamed_files_are_unchanged(self):
        self.assertEqual(image_reader.default_channel_colors(["GFP", "YFP"], 2),
                         [(0, 255, 0), image_reader.CHANNEL_COLORS[1]])
        self.assertEqual(image_reader.default_channel_colors(None, 3),
                         image_reader.CHANNEL_COLORS[:3])
        self.assertIsNone(image_reader.named_channel_color("Channel 2"))
        for name, rgb in (("EGFP", (0, 255, 0)), ("AF488", (0, 255, 0)),
                          ("Alexa Fluor 647", (255, 0, 255)), ("GCaMP6s", (0, 255, 0)),
                          ("mCherry", (255, 0, 0)), ("Far-red", (255, 0, 255))):
            self.assertEqual(image_reader.named_channel_color(name), rgb, name)
        for name in ("Indicator", "Synapsin", "Iba1", "Tracer"):
            self.assertIsNone(image_reader.named_channel_color(name), name)

    def test_rgba_alpha_is_reported_not_silently_dropped(self):
        data = np.zeros((6, 7, 4), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "rgba.tif", data, photometric="rgb", extrasamples=["unassalpha"])
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 0)
        self.assertTrue(reader.is_rgb)
        self.assertEqual(reader.data["scene 0"].shape, (6, 7, 3))
        self.assertTrue(any("alpha" in note for note in reader.notes))

    def test_several_series_become_scenes_read_on_demand(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "series.tif"
            with tifffile.TiffWriter(path) as writer:
                writer.write(np.full((4, 5), 1, dtype=np.uint8))
                writer.write(np.full((6, 7), 2, dtype=np.uint8))
            reader = image_reader.TIFFReader(path)
            self.assertEqual(reader.error_index, 0)
            self.assertEqual(reader.n_scenes, 2)
            self.assertNotIn("scene 1", reader.data)
            reader.read_data(1.0, scene_index=1)
        self.assertEqual(reader.data["scene 1"].shape, (6, 7, 1))
        self.assertEqual(int(reader.data["scene 1"].max()), 2)

    def test_errors_carry_a_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, "float.tif", np.zeros((4, 5), dtype=np.float32))
            reader = image_reader.TIFFReader(path)
        self.assertEqual(reader.error_index, 2)
        self.assertIn("16-bit", reader.error_message)
