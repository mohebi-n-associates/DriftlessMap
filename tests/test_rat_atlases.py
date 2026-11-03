"""Rat atlas downloads: region hierarchies, the SWC conversion and the dialogs."""

import tests.settings_isolation  # noqa: F401  (before the app reads settings)
import io
import json
import os
import tarfile
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from driftlessmap import rat_atlases
from driftlessmap.download_utils import _record_download, read_download_manifest
from driftlessmap.persistence import load_legacy_pickle
from driftlessmap.rat_atlases import (
    NO_PARENT,
    SWC_FEMALE_RAT,
    WAXHOLM,
    brainglobe_to_whs,
    label_info_from_brainglobe,
    label_info_from_ilf,
)

ILF = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<milf><meta><filename>test.ilf</filename></meta><structure>
<label abbreviation="Brain" color="#32a852" id="1000" name="Brain">
  <label abbreviation="wmt" color="#ffffff" id="1001" name="White matter">
    <label abbreviation="lot" id="180" name="lateral olfactory tract " color="#ff00dd"/>
  </label>
  <label abbreviation="Cx" color="#0a0b0c" id="10" name="Cortex"/>
</label>
<label abbreviation="vs" color="#000080" id="33" name="ventricular system"/>
</structure></milf>
"""

STRUCTURES = [
    {"id": 10000, "name": "Root", "acronym": "root", "structure_id_path": [10000],
     "rgb_triplet": [255, 255, 255]},
    {"id": 1000, "name": "Brain", "acronym": "Brain", "structure_id_path": [10000, 1000],
     "rgb_triplet": [50, 168, 82]},
    {"id": 1001, "name": "White matter", "acronym": "wmt",
     "structure_id_path": [10000, 1000, 1001], "rgb_triplet": [255, 255, 255]},
    {"id": 180, "name": "lateral olfactory tract", "acronym": "lot",
     "structure_id_path": [10000, 1000, 1001, 180], "rgb_triplet": [255, 0, 221]},
    {"id": 10, "name": "Cortex", "acronym": "Cx", "structure_id_path": [10000, 1000, 10],
     "rgb_triplet": [10, 11, 12]},
    {"id": 33, "name": "ventricular system", "acronym": "vs",
     "structure_id_path": [10000, 33], "rgb_triplet": [0, 0, 128]},
]


class RegionHierarchyTests(unittest.TestCase):
    def ilf(self, folder, text=ILF):
        path = os.path.join(folder, "labels.ilf")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
        return path

    def test_ilf_is_read_depth_first_with_parents_levels_and_colours(self):
        with tempfile.TemporaryDirectory() as folder:
            info = label_info_from_ilf(self.ilf(folder))
        self.assertEqual(info["index"].tolist(), [1000, 1001, 180, 10, 33])
        self.assertEqual(info["parent"].tolist(), [NO_PARENT, 1000, 1001, 1000, NO_PARENT])
        self.assertEqual(info["level_indicator"].tolist(), [0, 1, 2, 1, 0])
        self.assertEqual(info["color"][2].tolist(), [255, 0, 221])
        self.assertEqual(info["label"][2], "lateral olfactory tract")
        self.assertEqual(info["abbrev"].tolist(), ["Brain", "wmt", "lot", "Cx", "vs"])

    def test_brainglobe_structures_give_the_same_regions_without_their_root(self):
        with tempfile.TemporaryDirectory() as folder:
            expected = label_info_from_ilf(self.ilf(folder))
        info = label_info_from_brainglobe(STRUCTURES)
        for key in ("index", "color", "abbrev", "parent", "level_indicator"):
            np.testing.assert_array_equal(info[key], expected[key])
        self.assertEqual(info["label"], expected["label"])

    def test_repeated_regions_and_bad_colours_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                label_info_from_ilf(self.ilf(folder, ILF.replace('id="10"', 'id="180"')))
            with self.assertRaises(ValueError):
                label_info_from_ilf(self.ilf(folder, ILF.replace("#0a0b0c", "#0a0b")))


class PreparationTests(unittest.TestCase):
    def test_brainglobe_axes_become_whs_axes(self):
        # BrainGlobe asr (anterior->posterior, superior->inferior,
        # right->left) to WHS RAS order.
        x, y, z = 3, 5, 4
        volume = np.zeros((y, z, x), dtype=np.uint16)
        volume[0, 0, 2] = 7          # most anterior, most superior, third from the right
        whs = brainglobe_to_whs(volume, (x, y, z))
        self.assertEqual(whs.shape, (x, y, z))
        self.assertEqual(whs[2, y - 1, z - 1], 7)
        self.assertEqual(int(whs.sum()), 7)
        with self.assertRaises(ValueError):
            brainglobe_to_whs(volume, (x, z, y))

    def test_waxholm_archive_is_unpacked_and_its_hierarchy_written(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = os.path.join(folder, WAXHOLM.files[0].local)
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("MBAT/Data/WHS_SD_rat_atlas_v4.01.nii.gz", b"annotation")
                bundle.writestr("MBAT/Data/WHS_SD_rat_atlas_v4.01_labels.ilf", ILF)
                bundle.writestr("MBAT/readme.txt", b"ignored")
            rat_atlases.prepare_waxholm(folder)
            with open(os.path.join(folder, WAXHOLM.annotation), "rb") as stream:
                self.assertEqual(stream.read(), b"annotation")
            labels, error = load_legacy_pickle(os.path.join(folder, "atlas_labels.pkl"))
            self.assertIsNone(error)
            self.assertEqual(labels["index"].tolist(), [1000, 1001, 180, 10, 33])
            self.assertFalse(os.path.exists(os.path.join(folder, "readme.txt")))

    def test_an_archive_missing_a_file_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = os.path.join(folder, WAXHOLM.files[0].local)
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("Data/WHS_SD_rat_atlas_v4.01.nii.gz", b"annotation")
            with self.assertRaisesRegex(ValueError, "lacks"):
                rat_atlases.prepare_waxholm(folder)

    def test_swc_package_becomes_whs_nifti_files_and_labels(self):
        import nibabel as nib
        import tifffile

        x, y, z = 3, 5, 4
        reference = np.arange(y * z * x, dtype=np.uint16).reshape(y, z, x)
        annotation = np.zeros((y, z, x), dtype=np.uint32)
        annotation[1, 2, 0] = 180
        with tempfile.TemporaryDirectory() as folder:
            archive = os.path.join(folder, SWC_FEMALE_RAT.files[0].local)
            with tarfile.open(archive, "w:gz") as bundle:
                for name, data in (
                        ("reference.tiff", _tiff(tifffile, reference)),
                        ("annotation.tiff", _tiff(tifffile, annotation)),
                        ("structures.json", json.dumps(STRUCTURES).encode()),
                        ("metadata.json", json.dumps({"orientation": "asr",
                                                      "resolution": [39, 39, 39]}).encode())):
                    member = tarfile.TarInfo("pkg/" + name)
                    member.size = len(data)
                    bundle.addfile(member, io.BytesIO(data))
            with patch.object(rat_atlases, "WHS_SHAPE", (x, y, z)):
                rat_atlases.prepare_swc_female_rat(folder)
            template = np.asarray(nib.load(os.path.join(folder, SWC_FEMALE_RAT.template)).dataobj)
            labels = np.asarray(nib.load(os.path.join(folder, SWC_FEMALE_RAT.annotation)).dataobj)
            np.testing.assert_array_equal(template, brainglobe_to_whs(reference, (x, y, z)))
            self.assertEqual(labels[0, y - 2, z - 3], 180)
            info, error = load_legacy_pickle(os.path.join(folder, "atlas_labels.pkl"))
            self.assertIsNone(error)
            self.assertEqual(info["index"].tolist(), [1000, 1001, 180, 10, 33])


def _tiff(tifffile, array):
    stream = io.BytesIO()
    tifffile.imwrite(stream, array, photometric="minisblack")
    return stream.getvalue()


class ManifestTests(unittest.TestCase):
    def test_parallel_downloads_all_reach_the_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            threads = [threading.Thread(target=_record_download,
                                        args=(os.path.join(folder, "f{}".format(i)),
                                              "https://x/{}".format(i), "a" * 64, i))
                       for i in range(24)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(len(read_download_manifest(folder)), 24)


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_the_terms_must_be_accepted_before_downloading(self):
        from driftlessmap import file_dialogs
        from driftlessmap.atlas_downloader import AtlasDownloader
        from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog

        for dialog in (AtlasDownloader(), RatAtlasDownloadDialog(WAXHOLM)):
            with self.subTest(type(dialog).__name__), \
                    patch.object(file_dialogs, "get_existing_directory") as choose:
                dialog.download_start()
                choose.assert_not_called()
                self.assertIn("I agree", dialog.process_info.text())
                self.assertEqual(dialog.download_threads, {})
            dialog.deleteLater()
        swc = AtlasDownloader(atlas=SWC_FEMALE_RAT)
        self.assertTrue(swc.agree.isHidden())
        swc.deleteLater()

    def test_files_already_downloaded_are_recognised_by_their_bytes(self):
        import dataclasses
        import hashlib

        from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog

        mask = dataclasses.replace(WAXHOLM.files[2], sha256=hashlib.sha256(b"mask").hexdigest())
        atlas = dataclasses.replace(WAXHOLM, files=WAXHOLM.files[:2] + (mask,))
        dialog = RatAtlasDownloadDialog(atlas)
        with tempfile.TemporaryDirectory() as folder:
            template = atlas.files[1]
            for item, data in ((mask, b"mask"), (template, b"wrong nonempty bytes")):
                with open(os.path.join(folder, item.local), "wb") as stream:
                    stream.write(data)
                # The manifest claims both are the release; only bytes count.
                _record_download(os.path.join(folder, item.local), item.url, item.sha256,
                                 len(data))
            dialog.saving_folder = folder
            dialog._scan_folder()
            self.assertEqual(dialog.finish, [False, False, True])
            self.assertIn("Part of the atlas", dialog.folder_note.text())
            dialog.agree.setChecked(True)
            with patch.object(dialog, "start_download") as start:
                dialog.download_start()
            self.assertEqual([call.args[0] for call in start.call_args_list], [0, 1])
            dialog.process_start()
            self.assertIn("Download first", dialog.process_info.text())
            # A file changed after it was checked is checked again.
            with open(os.path.join(folder, mask.local), "wb") as stream:
                stream.write(b"MASK")
            self.assertNotIn(mask.local, dialog.matching_files(folder))
            dialog.finish = [True, True, True]
            dialog._refresh()
            self.assertIn("Everything is downloaded", dialog.folder_note.text())
        dialog.deleteLater()

    def test_the_classic_dialog_refuses_to_process_altered_files(self):
        from driftlessmap.atlas_downloader import AtlasDownloader

        dialog = AtlasDownloader(atlas=SWC_FEMALE_RAT)
        with tempfile.TemporaryDirectory() as folder:
            item = SWC_FEMALE_RAT.files[0]
            with open(os.path.join(folder, item.local), "wb") as stream:
                stream.write(b"not the archive")
            _record_download(os.path.join(folder, item.local), item.url, item.sha256, 15)
            dialog.saving_folder = folder
            with patch.object(dialog.thread, "start") as start:
                dialog.process_start()
            start.assert_not_called()
            self.assertIn("different from the published release", dialog.process_info.text())
        dialog.deleteLater()

    def test_download_rows_get_their_full_height(self):
        from driftlessmap.v2.allen_download_dialog import AllenDownloadDialog
        from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog

        for dialog in (RatAtlasDownloadDialog(WAXHOLM), AllenDownloadDialog()):
            with self.subTest(type(dialog).__name__):
                dialog.show()
                self.app.processEvents()
                for row in dialog._rows:
                    self.assertGreaterEqual(row.height(), row.sizeHint().height())
                dialog.hide()
            dialog.deleteLater()

    def test_rat_axis_info_is_what_the_atlas_processor_gives_for_ras(self):
        # Probe exports need atlas_axis_info.pkl; WHS volumes are stored RAS.
        from driftlessmap.atlas_processor import AtlasProcessor

        dialog = AtlasProcessor()
        for combo, axis, text in ((dialog.x_axis_combo, "x", "L.H. --> R.H."),
                                  (dialog.y_axis_combo, "y", "Post. --> Ant."),
                                  (dialog.z_axis_combo, "z", "Inf. --> Sup.")):
            combo.setCurrentText(text)
            dialog.dim_combo_changed(axis)
        expected = dict(dialog.axis_info, size=(512, 1024, 512))
        self.assertEqual(rat_atlases.waxholm_axis_info((512, 1024, 512)), expected)
        dialog.deleteLater()

    def test_escape_does_not_close_a_busy_download_dialog(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QMessageBox

        from driftlessmap.atlas_downloader import AtlasDownloader
        from driftlessmap.v2.allen_download_dialog import AllenDownloadDialog
        from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog

        for dialog in (AtlasDownloader(), RatAtlasDownloadDialog(SWC_FEMALE_RAT),
                       AllenDownloadDialog()):
            with self.subTest(type(dialog).__name__):
                dialog.show()
                with patch.object(dialog, "has_active_downloads", return_value=True), \
                        patch.object(QMessageBox, "information") as told:
                    QTest.keyClick(dialog, Qt.Key.Key_Escape)
                self.assertTrue(dialog.isVisible())
                self.assertTrue(dialog.continue_process)
                told.assert_called_once()
                QTest.keyClick(dialog, Qt.Key.Key_Escape)   # idle: Escape closes
                self.assertFalse(dialog.isVisible())
                self.assertFalse(dialog.continue_process)
            dialog.deleteLater()

    def test_failed_downloads_can_be_retried_and_stopped_processing_is_named(self):
        from driftlessmap.atlas_loader import begin_atlas_processing
        from driftlessmap.v2.rat_download_dialog import RatAtlasDownloadDialog

        dialog = RatAtlasDownloadDialog(SWC_FEMALE_RAT)
        with tempfile.TemporaryDirectory() as folder:
            dialog.saving_folder = folder
            dialog._scan_folder()
            self.assertNotIn("did not finish", dialog.folder_note.text())
            begin_atlas_processing(folder)          # a run that stopped part-way
            dialog._scan_folder()
            self.assertIn("did not finish last time", dialog.folder_note.text())
            dialog.download_failed(SWC_FEMALE_RAT.files[0].local, "Connection reset")
            dialog._refresh()
            self.assertEqual(dialog.download_btn.text(), "Retry failed downloads")
            self.assertTrue(dialog.download_btn.isEnabled())
            self.assertIn("Failed: Connection reset", dialog._rows[0].text())
        dialog.deleteLater()

    def test_processing_names_its_stages(self):
        from driftlessmap.atlas_downloader import WorkerProcessData

        worker = WorkerProcessData()
        stages = []
        worker.status.connect(stages.append)
        with tempfile.TemporaryDirectory() as folder:
            from driftlessmap.persistence import write_cache_pickle

            write_cache_pickle(os.path.join(folder, "atlas_labels.pkl"),
                               label_info_from_brainglobe(STRUCTURES))
            worker.set_data(folder, "t.nii.gz", "a.nii.gz", None, (1, 1, 1), (1, 1, 1), 39,
                            prepare=lambda _folder: None)
            worker.run()          # stops at the missing volumes, after naming the stages
        self.assertEqual(stages[0], "Preparing the downloaded files…")
        self.assertTrue(any("Reading the template" in stage for stage in stages))

    def test_a_failing_preparation_is_reported(self):
        from driftlessmap.atlas_downloader import WorkerProcessData

        def broken(_folder):
            raise ValueError("The archive lacks labels.ilf.")

        worker = WorkerProcessData()
        with tempfile.TemporaryDirectory() as folder:
            worker.set_data(folder, "t.nii.gz", "a.nii.gz", None, (1, 1, 1), (1, 1, 1), 39,
                            prepare=broken)
            worker.run()
        self.assertFalse(worker.success)
        self.assertIn("lacks labels.ilf", worker.message)


if __name__ == "__main__":
    unittest.main()
