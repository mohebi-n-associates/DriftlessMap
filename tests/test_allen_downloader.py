from pathlib import Path
import tempfile
import unittest

import numpy as np
import nrrd

from herbs.allen_downloader import _stream_unique_nrrd_values


class AllenDownloaderTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
