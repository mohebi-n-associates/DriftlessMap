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

    def test_multi_series_tiff_reports_error_without_uninitialized_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "multi.tif"
            with tifffile.TiffWriter(path) as writer:
                writer.write(np.zeros((4, 5), dtype=np.uint8))
                writer.write(np.ones((6, 7), dtype=np.uint8))
            reader = image_reader.TIFFReader(path)

        self.assertEqual(reader.error_index, 1)
        self.assertIsNone(reader.pixel_type)
        self.assertEqual(reader.data, {})

    def test_more_than_four_channels_is_rejected_before_ui_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "channels.tif"
            tifffile.imwrite(
                path,
                np.zeros((5, 4, 6), dtype=np.uint8),
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


if __name__ == "__main__":
    unittest.main()
