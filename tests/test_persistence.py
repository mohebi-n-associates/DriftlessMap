import base64
import importlib.util
import os
from pathlib import Path
import pickle
import tempfile
import unittest

import numpy as np
import pandas as pd


MODULE_PATH = Path(__file__).parents[1] / "driftlessmap" / "persistence.py"
SPEC = importlib.util.spec_from_file_location("persistence", MODULE_PATH)
persistence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(persistence)


class LegacyPickleTests(unittest.TestCase):
    def test_success_and_failure_return_the_same_shape(self):
        with tempfile.TemporaryDirectory() as folder:
            valid_path = Path(folder) / "valid.pkl"
            invalid_path = Path(folder) / "invalid.pkl"
            with valid_path.open("wb") as stream:
                pickle.dump({"answer": 42}, stream)
            invalid_path.write_bytes(b"not a pickle")

            data, error = persistence.load_legacy_pickle(valid_path)
            self.assertEqual(data, {"answer": 42})
            self.assertIsNone(error)

            data, error = persistence.load_legacy_pickle(invalid_path)
            self.assertIsNone(data)
            self.assertIsInstance(error, str)

    def test_missing_file_returns_an_error_tuple(self):
        data, error = persistence.load_legacy_pickle("does-not-exist.pkl")
        self.assertIsNone(data)
        self.assertIn("Unable to read file", error)

    def test_legacy_reader_rejects_executable_globals(self):
        class Malicious:
            def __reduce__(self):
                return os.system, ("touch {}".format(marker),)

        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "executed"
            payload = Path(folder) / "malicious.pkl"
            with payload.open("wb") as stream:
                pickle.dump(Malicious(), stream)

            data, error = persistence.load_legacy_pickle(payload)
            self.assertIsNone(data)
            self.assertIn("unsupported type", error)
            self.assertFalse(marker.exists())

    def test_legacy_reader_accepts_highest_protocol_numpy_arrays(self):
        payload = {
            "index": np.arange(8, dtype=np.int64),
            "label": np.asarray(["region-a", "region-b"]),
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "numpy-arrays.pkl"
            with path.open("wb") as stream:
                pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)

            loaded, error = persistence.load_legacy_pickle(path)

        self.assertIsNone(error)
        np.testing.assert_array_equal(loaded["index"], payload["index"])
        np.testing.assert_array_equal(loaded["label"], payload["label"])

    def test_legacy_reader_normalizes_pandas_string_arrays_without_importing_globals(self):
        payload = {
            "label": pd.array(["Brain", "Cortex"], dtype="string"),
            "abbrev": pd.array(["Brain", "CTX"], dtype="string"),
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pandas-string-arrays.pkl"
            with path.open("wb") as stream:
                pickle.dump(payload, stream, protocol=pickle.HIGHEST_PROTOCOL)

            loaded, error = persistence.load_legacy_pickle(path)

        self.assertIsNone(error)
        self.assertIsInstance(loaded["label"], np.ndarray)
        self.assertIsInstance(loaded["abbrev"], np.ndarray)
        np.testing.assert_array_equal(loaded["label"], ["Brain", "Cortex"])
        np.testing.assert_array_equal(loaded["abbrev"], ["Brain", "CTX"])

    def test_numpy_2_pickle_loads_with_both_numpy_module_layouts(self):
        numpy_2_pickle = base64.b64decode(
            "gAWVlwAAAAAAAAB9lIwFaW5kZXiUjBNudW1weS5fY29yZS5udW1lcmljlIwL"
            "X2Zyb21idWZmZXKUk5QolhgAAAAAAAAA5QMAAAAAAAAIAAAAAAAAADcCAAAAAAAA"
            "lIwFbnVtcHmUjAVkdHlwZZSTlIwCaTiUiYiHlFKUKEsDjAE8lE5OTkr/////"
            "Sv////9LAHSUYksDhZSMAUOUdJRSlHMu"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "numpy-2-array.pkl"
            path.write_bytes(numpy_2_pickle)

            loaded, error = persistence.load_legacy_pickle(path)

        self.assertIsNone(error)
        np.testing.assert_array_equal(loaded["index"], [997, 8, 567])
        self.assertIn(
            ("numpy.core.numeric", "_frombuffer"),
            persistence.RestrictedUnpickler.SAFE_GLOBALS,
        )
        self.assertIn(
            ("numpy._core.numeric", "_frombuffer"),
            persistence.RestrictedUnpickler.SAFE_GLOBALS,
        )


class SafeArchiveTests(unittest.TestCase):
    def test_round_trip_preserves_nested_arrays_and_types(self):
        data = {
            "array": np.arange(12, dtype=np.uint16).reshape(3, 4),
            "tuple": ("a", 2),
            "nested": [True, None, np.float32(1.5)],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.herbs"
            success, error = persistence.save_herbs_file(path, data, "test")
            self.assertTrue(success, error)
            self.assertTrue(persistence.zipfile.is_zipfile(path))
            with persistence.zipfile.ZipFile(path) as archive:
                manifest = persistence.json.loads(
                    archive.read(persistence.MANIFEST_NAME)
                )
            self.assertEqual(manifest["format"], "DriftlessMap")

            loaded, error = persistence.load_herbs_file(path, "test")
            self.assertIsNone(error)
            np.testing.assert_array_equal(loaded["array"], data["array"])
            self.assertEqual(loaded["tuple"], ("a", 2))
            self.assertEqual(loaded["nested"], [True, None, 1.5])

    def test_archive_kind_is_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "layer.herbslayer"
            success, error = persistence.save_herbs_file(
                path,
                {
                    "layer_link": "img-mask",
                    "data": [1],
                    "color": [255, 0, 0],
                    "thumbnail": [1],
                },
                "layer",
            )
            self.assertTrue(success, error)

            loaded, error = persistence.load_herbs_file(path, "project")
            self.assertIsNone(loaded)
            self.assertIn("Expected a project file", error)

    def test_legacy_herbs_manifest_remains_readable(self):
        data = {"answer": 42}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.herbs"
            success, error = persistence.save_driftlessmap_file(
                path, data, "test"
            )
            self.assertTrue(success, error)
            with persistence.zipfile.ZipFile(path, "r") as source:
                entries = {
                    name: source.read(name) for name in source.namelist()
                }
            manifest = persistence.json.loads(
                entries[persistence.MANIFEST_NAME]
            )
            manifest["format"] = "HERBS"
            entries[persistence.MANIFEST_NAME] = persistence.json.dumps(
                manifest, separators=(",", ":")
            ).encode("utf-8")
            with persistence.zipfile.ZipFile(
                path, "w", compression=persistence.zipfile.ZIP_DEFLATED
            ) as archive:
                for name, payload in entries.items():
                    archive.writestr(name, payload)

            loaded, error = persistence.load_driftlessmap_file(path, "test")

        self.assertIsNone(error)
        self.assertEqual(loaded, data)


if __name__ == "__main__":
    unittest.main()
