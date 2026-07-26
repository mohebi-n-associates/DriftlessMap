from pathlib import Path
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib


REPOSITORY_ROOT = Path(__file__).parents[1]


def project_metadata():
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


class PackagingMetadataTests(unittest.TestCase):
    def test_modern_runtime_and_dependency_baseline(self):
        metadata = project_metadata()

        self.assertEqual(metadata["requires-python"], ">=3.10")
        self.assertIn("PyQt6>=6.8,<7", metadata["dependencies"])
        self.assertIn("pyqtgraph>=0.14,<0.15", metadata["dependencies"])
        self.assertIn("superqt>=0.8,<0.9", metadata["dependencies"])
        self.assertIn("numpy>=2.0,<3", metadata["dependencies"])
        self.assertIn("opencv-python>=4.10,<6", metadata["dependencies"])
        self.assertFalse(
            any(
                requirement.startswith(("PyQt5", "h5py", "tables"))
                for requirement in metadata["dependencies"]
            )
        )
        for version in ("3.10", "3.11", "3.12", "3.13", "3.14"):
            self.assertIn(
                "Programming Language :: Python :: {}".format(version),
                metadata["classifiers"],
            )

    def test_czi_support_is_optional_on_supported_upstream_runtimes(self):
        metadata = project_metadata()

        self.assertFalse(
            any(
                requirement.startswith("aicspylibczi")
                for requirement in metadata["dependencies"]
            )
        )
        self.assertEqual(
            metadata["optional-dependencies"]["czi"],
            ["aicspylibczi>=3.3.1; python_version < '3.14'"],
        )

    def test_project_links_and_entry_point_use_the_current_repository(self):
        metadata = project_metadata()

        self.assertEqual(
            metadata["urls"]["Homepage"],
            "https://github.com/mohebi-n-associates/HERBS",
        )
        self.assertEqual(
            metadata["urls"]["Bug Tracker"],
            "https://github.com/mohebi-n-associates/HERBS/issues",
        )
        self.assertEqual(metadata["scripts"]["herbs"], "herbs.run_herbs:run")

    def test_release_history_is_kept_in_one_cumulative_file(self):
        history_path = REPOSITORY_ROOT / "WhatsNew.md"
        history = history_path.read_text(encoding="utf-8")

        self.assertEqual(
            sorted(path.name for path in REPOSITORY_ROOT.glob("WhatsNew*.md")),
            ["WhatsNew.md"],
        )
        for version in ("1.0.3", "1.0.2", "1.0.1", "1.0.0", "0.2.8.1"):
            self.assertIn("## HERBS {}".format(version), history)
        self.assertIn(
            "[What’s New in HERBS](WhatsNew.md)",
            (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
