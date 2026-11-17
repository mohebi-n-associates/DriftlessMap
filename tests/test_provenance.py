from pathlib import Path
import pickle
import tempfile
import unittest

import numpy as np

from driftlessmap.provenance import (
    describe_atlas_path,
    describe_path,
    pack_path,
    references_match,
    resolve_reference,
    unpack_path,
    verify_reference,
)


def write_atlas(folder, protocol=5, voxel=7, caches=b"caches"):
    """The content files of a small atlas, pickled as one computer would."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    labels = np.zeros((6, 5, 4), dtype=np.int32)
    labels[2:4, 1:3, 1:3] = voxel
    files = {
        "atlas_axis_info.pkl": {"to_HERBS": (2, 0, 1), "direction_change": (True, False, False),
                                "size": (6, 5, 4)},
        "atlas_labels.pkl": {"index": np.array([1, 7]), "label": np.array(["root", "area"]),
                             "level_indicator": [1, 2]},
        "atlas_pre_made.pkl": {"data": np.linspace(0, 1, 120, dtype=np.float32).reshape(6, 5, 4),
                               "info": [{"name": "anterior", "units": "um"}, {"vxsize": 25}]},
        "segment_pre_made.pkl": {"data": labels, "unique_label": np.array([0, voxel], np.uint32)},
    }
    for name, value in files.items():
        with (folder / name).open("wb") as stream:
            pickle.dump(value, stream, protocol=protocol)
    # Display caches: every computer writes its own.
    (folder / "atlas_small_meshdata.pkl").write_bytes(caches)
    (folder / "coronal_contour_pre_made.pkl").write_bytes(caches)
    return folder


def without_content_digests(reference):
    """The reference as DriftlessMap before 2.9.4 saved it."""
    older = dict(reference)
    older["files"] = [
        {key: value for key, value in record.items() if key != "content_sha256"}
        for record in reference["files"]
    ]
    return older


class AtlasAcrossComputersTests(unittest.TestCase):
    """The same atlas processed on another computer is the same atlas."""

    def test_content_digest_ignores_encoding_and_follows_the_data(self):
        from driftlessmap.provenance import content_digest

        value = {"data": np.arange(24, dtype=np.int32).reshape(2, 3, 4), "info": [1, 2.5, "um"],
                 "ok": True, "none": None}
        same = [
            pickle.loads(pickle.dumps(value, protocol=protocol)) for protocol in (2, 3, 4, 5)
        ] + [
            {"none": None, "ok": True, "info": (1, 2.5, "um"),
             "data": value["data"].astype(">i4")},
            dict(value, data=np.asfortranarray(value["data"])),
        ]
        expected = content_digest(value)
        self.assertEqual(len(expected), 64)
        for other in same:
            self.assertEqual(content_digest(other), expected)
        different = [
            dict(value, data=value["data"].astype(np.int64)),
            dict(value, data=value["data"].reshape(4, 3, 2)),
            dict(value, data=value["data"] + (np.arange(24).reshape(2, 3, 4) == 23)),
            dict(value, info=[1, 2.5, "mm"]),
            dict(value, info=[2.5, 1, "um"]),
            dict(value, ok=1),
            dict(value, extra=0),
        ]
        for other in different:
            self.assertNotEqual(content_digest(other), expected)
        with self.assertRaises(TypeError):
            content_digest({"unsupported": object()})

    def test_text_arrays_count_by_their_values(self):
        from driftlessmap.provenance import content_digest

        names = np.array(["root", "area"])
        self.assertEqual(content_digest(names), content_digest(names.astype("U40")))
        self.assertEqual(content_digest(names), content_digest(names.astype(object)))
        self.assertNotEqual(content_digest(names), content_digest(np.array(["root", "areas"])))

    def test_one_pass_checksum_equals_the_plain_one(self):
        from driftlessmap.provenance import hash_file_and_content, sha256_file

        with tempfile.TemporaryDirectory() as folder:
            atlas = write_atlas(Path(folder) / "atlas")
            for protocol in (3, 4, 5):
                target = atlas / "segment_pre_made.pkl"
                value = pickle.loads(target.read_bytes())
                target.write_bytes(pickle.dumps(value, protocol=protocol) + b"trailing bytes")
                checksum, content = hash_file_and_content(target)
                self.assertEqual(checksum, sha256_file(target))
                self.assertEqual(len(content), 64)
            # Not a pickle DriftlessMap reads: the checksum alone.
            target.write_bytes(b"not a pickle")
            self.assertEqual(hash_file_and_content(target), (sha256_file(target), None))
            target.write_bytes(pickle.dumps(Path("unsafe")))
            self.assertEqual(hash_file_and_content(target), (sha256_file(target), None))

    def test_new_references_record_content_for_the_atlas_files_only(self):
        from driftlessmap.provenance import ATLAS_CONTENT_FILES

        with tempfile.TemporaryDirectory() as folder:
            reference = describe_atlas_path(write_atlas(Path(folder) / "atlas"))
            for record in reference["files"]:
                self.assertEqual("content_sha256" in record, record["path"] in ATLAS_CONTENT_FILES)
            # An ordinary folder never gets them.
            plain = describe_path(Path(folder) / "atlas")
            self.assertFalse(any("content_sha256" in record for record in plain["files"]))

    def test_atlas_processed_elsewhere_is_verified_by_its_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for saved_with, found_with in ((4, 5), (5, 4), (2, 5), (5, 3)):
                saved = write_atlas(root / "saved-{}-{}".format(saved_with, found_with),
                                    protocol=saved_with, caches=b"this computer")
                found = write_atlas(root / "found-{}-{}".format(saved_with, found_with),
                                    protocol=found_with, caches=b"another computer's")
                reference = describe_atlas_path(saved)
                self.assertFalse(references_match(reference, describe_atlas_path(found)))
                # Saved by 2.9.4 (content digests) and by earlier versions (bytes only).
                for saved_reference in (reference, without_content_digests(reference)):
                    self.assertEqual(verify_reference(found, saved_reference), (True, None))
                    self.assertEqual(verify_reference(saved, saved_reference), (True, None))

    def test_different_atlas_data_is_refused_whatever_the_encoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            reference = describe_atlas_path(write_atlas(root / "saved", protocol=4))
            for protocol in (4, 5):
                other = write_atlas(root / "other-{}".format(protocol), protocol=protocol, voxel=8)
                for saved_reference in (reference, without_content_digests(reference)):
                    matches, reason = verify_reference(other, saved_reference)
                    self.assertFalse(matches)
                    self.assertIn("segment_pre_made.pkl", reason)
            # A missing content file, and one that is far from the saved size.
            incomplete = write_atlas(root / "incomplete", protocol=5)
            (incomplete / "atlas_labels.pkl").unlink()
            self.assertEqual(verify_reference(incomplete, reference),
                             (False, "missing atlas_labels.pkl"))
            larger = write_atlas(root / "larger", protocol=5)
            (larger / "atlas_pre_made.pkl").write_bytes(b"x" * 200000)
            self.assertEqual(verify_reference(larger, reference),
                             (False, "size differs for atlas_pre_made.pkl"))

    def test_display_caches_do_not_decide_but_content_files_do(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            atlas = write_atlas(root / "atlas")
            reference = describe_atlas_path(atlas)
            (atlas / "atlas_small_meshdata.pkl").write_bytes(b"meshed again")
            (atlas / "coronal_contour_pre_made.pkl").unlink()
            (atlas / "atlas_meshdata.pkl").write_bytes(b"a cache made later")
            self.assertEqual(verify_reference(atlas, reference), (True, None))

            partial = write_atlas(root / "partial")
            (partial / "atlas_axis_info.pkl").unlink()
            reference = describe_atlas_path(partial)
            write_atlas(partial)
            self.assertEqual(verify_reference(partial, reference),
                             (False, "unexpected atlas_axis_info.pkl"))

    def test_other_places_are_tried_after_the_saved_ones(self):
        from driftlessmap.provenance import candidate_paths

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            saved = write_atlas(root / "pc" / "atlas", protocol=4)
            project = root / "pc" / "study.dmap"
            reference = describe_atlas_path(saved, project_path=project)
            here = write_atlas(root / "mac" / "my-atlas", protocol=5)
            other = write_atlas(root / "mac" / "other-atlas", voxel=9)
            self.assertEqual(resolve_reference(reference, project_path=project)[0],
                             str(saved.resolve()))
            saved.rename(root / "pc" / "gone")
            self.assertIsNone(resolve_reference(reference, project_path=project)[0])
            self.assertIsNone(resolve_reference(reference, project_path=project,
                                                extra=(None, str(other)))[0])
            found, error = resolve_reference(reference, project_path=project,
                                             extra=(None, str(other), str(here)))
            self.assertEqual((found, error), (str(here.resolve()), None))
            self.assertEqual(candidate_paths(reference, project, extra=(str(here), str(here)))[-1],
                             here.resolve())

    def test_atlas_caches_are_written_with_one_fixed_protocol(self):
        from driftlessmap.persistence import CACHE_PICKLE_PROTOCOL, write_cache_pickle

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "atlas_axis_info.pkl"
            write_cache_pickle(target, {"size": (1, 2, 3)})
            self.assertEqual(CACHE_PICKLE_PROTOCOL, 5)
            self.assertEqual(target.read_bytes()[:2], b"\x80\x05")


class ProvenanceTests(unittest.TestCase):
    def test_file_reference_relocates_relative_to_project_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "study" / "result.dmap"
            source = root / "study" / "inputs" / "slice.tif"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"exact histology bytes")

            reference = describe_path(source, project_path=project)
            resolved, error = resolve_reference(reference, project_path=project)

            self.assertIsNone(error)
            self.assertEqual(Path(resolved), source.resolve())
            self.assertEqual(reference["relative_path"], "inputs/slice.tif")

            source.write_bytes(b"modified histology")
            matches, reason = verify_reference(source, reference)
            self.assertFalse(matches)
            self.assertIn("differs", reason)

    def test_atlas_identity_uses_recognized_processed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            atlas = Path(folder) / "allen_25um"
            atlas.mkdir()
            (atlas / "atlas_axis_info.pkl").write_bytes(b"axes")
            (atlas / "segment_pre_made.pkl").write_bytes(b"labels")
            (atlas / "unrelated.tmp").write_bytes(b"ignored")

            first = describe_atlas_path(atlas)
            copied = Path(folder) / "copy"
            copied.mkdir()
            (copied / "atlas_axis_info.pkl").write_bytes(b"axes")
            (copied / "segment_pre_made.pkl").write_bytes(b"labels")
            second = describe_atlas_path(copied)

            self.assertTrue(references_match(first, second))
            self.assertEqual(
                [record["path"] for record in first["files"]],
                ["atlas_axis_info.pkl", "segment_pre_made.pkl"],
            )

    def test_portable_payload_round_trip_is_inert_and_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.czi"
            source.write_bytes(bytes(range(255)))
            reference = describe_path(source)
            payload = pack_path(source, reference=reference)
            self.assertTrue(hasattr(payload["files"][0]["data"], "extract_to"))

            extracted = unpack_path(payload, Path(folder) / "unpacked")
            self.assertEqual(Path(extracted).read_bytes(), source.read_bytes())
            matches, error = verify_reference(extracted, reference)
            self.assertTrue(matches, error)

    def test_portable_payload_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "safe"
            with self.assertRaises(ValueError):
                unpack_path(
                    {"kind": "directory", "name": "../escape", "files": []},
                    destination,
                )
            self.assertFalse((Path(folder) / "escape").exists())

    def test_directory_reference_rejects_unsafe_record_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "atlas"
            root.mkdir()
            reference = {
                "kind": "directory",
                "files": [
                    {"path": "../secret", "size_bytes": 1, "sha256": "x"}
                ],
            }
            matches, reason = verify_reference(root, reference)
            self.assertFalse(matches)
            self.assertIn("unsafe", reason)



class ProvenanceIntegrityTests(unittest.TestCase):
    def test_packing_refuses_a_source_that_changed_after_fingerprinting(self):
        from driftlessmap import provenance
        from driftlessmap.persistence import save_driftlessmap_file

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "slide.tif"
            source.write_bytes(b"original pixels")
            reference = provenance.describe_path(source)
            source.write_bytes(b"edited pixels!!")
            payload = provenance.pack_path(source, reference=reference)
            success, error = save_driftlessmap_file(
                Path(folder) / "portable.dmap", {"portable": payload}, "test"
            )
            self.assertFalse(success)
            self.assertIn("changed after it was fingerprinted", error)

    def test_atlas_verification_rejects_content_files_added_later(self):
        from driftlessmap import provenance

        with tempfile.TemporaryDirectory() as folder:
            atlas = Path(folder) / "atlas"
            atlas.mkdir()
            (atlas / "atlas_pre_made.pkl").write_bytes(b"volume")
            (atlas / "segment_pre_made.pkl").write_bytes(b"labels")
            reference = provenance.describe_atlas_path(atlas)
            self.assertEqual(provenance.verify_reference(atlas, reference), (True, None))
            # A display cache made later (2.9.4) does not change the atlas...
            (atlas / "atlas_meshdata.pkl").write_bytes(b"new mesh")
            self.assertEqual(provenance.verify_reference(atlas, reference), (True, None))
            # ...its regions do.
            (atlas / "atlas_labels.pkl").write_bytes(b"new regions")
            matches, reason = provenance.verify_reference(atlas, reference)
            self.assertFalse(matches)
            self.assertIn("atlas_labels.pkl", reason)

    def test_tampered_file_list_is_rejected(self):
        from driftlessmap import provenance

        with tempfile.TemporaryDirectory() as folder:
            atlas = Path(folder) / "atlas"
            atlas.mkdir()
            (atlas / "atlas_pre_made.pkl").write_bytes(b"volume")
            (atlas / "segment_pre_made.pkl").write_bytes(b"labels")
            reference = provenance.describe_atlas_path(atlas)
            reference["files"] = reference["files"][:1]
            matches, reason = provenance.verify_reference(atlas, reference)
            self.assertFalse(matches)

    def test_single_file_payload_extracts_to_its_record_path(self):
        from driftlessmap import provenance
        from driftlessmap.persistence import ArchiveAttachment

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "real.tif"
            source.write_bytes(b"pixels")
            payload = {
                "kind": "file",
                "name": "renamed.tif",
                "files": [{"path": "real.tif",
                           "data": ArchiveAttachment(source_path=source)}],
            }
            extracted = provenance.unpack_path(payload, Path(folder) / "out")
            self.assertTrue(Path(extracted).is_file())
            self.assertEqual(Path(extracted).read_bytes(), b"pixels")

if __name__ == "__main__":
    unittest.main()
