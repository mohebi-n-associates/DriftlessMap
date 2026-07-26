import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import nrrd
from PyQt6.QtWidgets import QApplication

from herbs.allen_downloader import AllenDownloader, _stream_unique_nrrd_values
from herbs.obj_items import render_small_volume


class AllenDownloaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resolution_changes_prefill_estimated_bregma_voxels(self):
        dialog = AllenDownloader()
        try:
            cases = (
                (dialog.vs_rabnt1, 10, [540, 44, 570]),
                (dialog.vs_rabnt2, 25, [216, 18, 228]),
                (dialog.vs_rabnt3, 50, [108, 9, 114]),
            )
            for radio_button, resolution, expected in cases:
                radio_button.setChecked(True)
                self.app.processEvents()

                self.assertEqual(dialog.voxel_size, resolution)
                self.assertEqual(dialog.bregma_coord, expected)
                self.assertEqual(
                    [
                        dialog.b_input1.text(),
                        dialog.b_input2.text(),
                        dialog.b_input3.text(),
                    ],
                    [str(value) for value in expected],
                )
        finally:
            dialog.deleteLater()

    def test_stream_unique_nrrd_values_reads_gzip_data_in_chunks(self):
        annotation = np.array(
            [
                [[0, 1, 1], [997, 997, 545]],
                [[614454277, 1, 0], [545, 997, 614454277]],
            ],
            dtype=np.uint32,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            annotation_path = Path(temporary_directory) / "annotation.nrrd"
            nrrd.write(
                str(annotation_path),
                annotation,
                header={"encoding": "gzip"},
            )
            progress = []

            result = _stream_unique_nrrd_values(
                str(annotation_path),
                progress=lambda current, total: progress.append((current, total)),
                chunk_size=7,
            )

        self.assertTrue(np.array_equal(result, np.unique(annotation)))
        self.assertEqual(progress[0], (0, annotation.size))
        self.assertEqual(progress[-1], (annotation.size, annotation.size))

    def test_fallback_mesh_reports_named_processing_phases(self):
        shape = (12, 12, 12)
        coordinates = np.indices(shape)
        structure_mask = (
            (coordinates[0] - 5.5) ** 2
            + (coordinates[1] - 5.5) ** 2
            + (coordinates[2] - 5.5) ** 2
        ) < 16
        atlas = np.zeros(shape, dtype=np.float32)
        atlas[structure_mask] = 1
        labels = np.zeros(shape, dtype=np.int32)
        labels[structure_mask] = 997
        progress = []

        with tempfile.TemporaryDirectory() as temporary_directory:
            render_small_volume(
                997,
                temporary_directory,
                atlas,
                labels,
                factor=2,
                level=0.1,
                progress=lambda fraction, phase: progress.append((fraction, phase)),
            )
            self.assertTrue(
                (Path(temporary_directory) / "997.pkl").is_file()
            )

        fractions = [fraction for fraction, _ in progress]
        phases = [phase for _, phase in progress]
        self.assertEqual(fractions, sorted(fractions))
        self.assertEqual(fractions[0], 0.0)
        self.assertEqual(fractions[-1], 1.0)
        self.assertIn("extracting the mesh surface", phases)
        self.assertIn("saving the generated mesh", phases)


if __name__ == "__main__":
    unittest.main()
