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
    def test_desktop_build_assets_and_native_workflow_exist(self):
        metadata = project_metadata()
        desktop_dependencies = metadata["optional-dependencies"]["desktop-build"]

        self.assertTrue(any(item.startswith("pyinstaller") for item in desktop_dependencies))
        for relative_path in (
            "driftlessmap/icons/app/driftlessmap.png",
            "driftlessmap/icons/app/driftlessmap.ico",
            "driftlessmap/icons/app/driftlessmap.icns",
            "packaging/DriftlessMap.spec",
            "packaging/build_windows.ps1",
            "packaging/build_macos.sh",
            ".github/workflows/desktop-builds.yml",
        ):
            self.assertTrue((REPOSITORY_ROOT / relative_path).is_file(), relative_path)

        workflow = (REPOSITORY_ROOT / ".github/workflows/desktop-builds.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("windows-latest", workflow)
        self.assertIn("macos-14", workflow)
        self.assertIn("release upload", workflow)

    def test_modern_runtime_and_dependency_baseline(self):
        metadata = project_metadata()

        self.assertEqual(metadata["requires-python"], ">=3.10")
        self.assertIn("PyQt6>=6.8,<7", metadata["dependencies"])
        self.assertIn("pyqtgraph>=0.14,<0.15", metadata["dependencies"])
        self.assertIn("superqt>=0.8,<0.9", metadata["dependencies"])
        self.assertIn("numpy>=2.0,<3", metadata["dependencies"])
        self.assertIn("opencv-python-headless>=4.10,<6", metadata["dependencies"])
        self.assertFalse(
            any(
                requirement.startswith("opencv-python>=")
                for requirement in metadata["dependencies"]
            )
        )
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

        self.assertEqual(metadata["name"], "driftlessmap")
        self.assertEqual(
            metadata["urls"]["Homepage"],
            "https://github.com/mohebi-n-associates/DriftlessMap",
        )
        self.assertEqual(
            metadata["urls"]["Bug Tracker"],
            "https://github.com/mohebi-n-associates/DriftlessMap/issues",
        )
        self.assertEqual(
            metadata["scripts"]["driftlessmap"], "driftlessmap:run"
        )
        self.assertNotIn("herbs", metadata["scripts"])
        self.assertFalse((REPOSITORY_ROOT / "herbs").exists())
        author_names = {author["name"] for author in metadata["authors"]}
        self.assertTrue(
            {
                "Jingyi Guo Fuglstad",
                "Pearl Saldanha",
                "Jacopo Paglia",
                "Jonathan R. Whitlock",
                "Mohebi & Associates",
                "Ali Mohebi",
            }.issubset(author_names)
        )
        self.assertEqual(
            metadata["urls"]["Maintaining Organization"],
            "https://www.mohebi-associates.org/",
        )
        self.assertEqual(
            metadata["urls"]["Lead Maintainer"],
            "https://www.mohebial.com/",
        )

    def test_license_and_origin_attribution_are_preserved(self):
        license_text = (REPOSITORY_ROOT / "LICENSE.txt").read_text(
            encoding="utf-8"
        )
        origins = (REPOSITORY_ROOT / "ORIGINS.md").read_text(encoding="utf-8")

        self.assertIn("Copyright (c) 2022 HERBS Developers.", license_text)
        self.assertIn(
            "Copyright (c) 2026 Ali Mohebi and DriftlessMap contributors.",
            license_text,
        )
        self.assertIn("https://github.com/Whitlock-Group/HERBS", origins)
        self.assertIn("10.7554/eLife.83496", origins)
        self.assertIn("not affiliated with or endorsed", origins)
        self.assertIn("https://www.mohebi-associates.org/", origins)
        self.assertIn("https://www.mohebial.com/", origins)

    def test_release_history_is_kept_in_one_cumulative_file(self):
        history_path = REPOSITORY_ROOT / "WhatsNew.md"
        history = history_path.read_text(encoding="utf-8")

        self.assertEqual(
            sorted(path.name for path in REPOSITORY_ROOT.glob("WhatsNew*.md")),
            ["WhatsNew.md"],
        )
        self.assertIn("## DriftlessMap 1.2.0", history)
        self.assertIn("## DriftlessMap 1.1.0", history)
        for version in (
            "1.0.5",
            "1.0.4",
            "1.0.3",
            "1.0.2",
            "1.0.1",
            "1.0.0",
            "0.2.8.1",
        ):
            self.assertIn("## HERBS {}".format(version), history)
        self.assertIn(
            "[What’s New in DriftlessMap](WhatsNew.md)",
            (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
