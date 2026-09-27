from pathlib import Path
import tempfile
import unittest

from driftlessmap.provenance import (
    describe_atlas_path,
    describe_path,
    pack_path,
    references_match,
    resolve_reference,
    unpack_path,
    verify_reference,
)


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

    def test_atlas_verification_rejects_identity_files_added_later(self):
        from driftlessmap import provenance

        with tempfile.TemporaryDirectory() as folder:
            atlas = Path(folder) / "atlas"
            atlas.mkdir()
            (atlas / "atlas_pre_made.pkl").write_bytes(b"volume")
            (atlas / "segment_pre_made.pkl").write_bytes(b"labels")
            reference = provenance.describe_atlas_path(atlas)
            self.assertEqual(provenance.verify_reference(atlas, reference), (True, None))
            (atlas / "atlas_meshdata.pkl").write_bytes(b"new mesh")
            matches, reason = provenance.verify_reference(atlas, reference)
            self.assertFalse(matches)
            self.assertIn("atlas_meshdata.pkl", reason)

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
