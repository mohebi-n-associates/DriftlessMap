import os
import subprocess
import sys
import unittest
from pathlib import Path

from driftlessmap.interfaces import (
    interface_command,
    requested_interface,
    without_interface_flags,
)

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class InterfaceChoiceTests(unittest.TestCase):
    def test_classic_is_the_default(self):
        self.assertEqual(requested_interface(["driftlessmap"], {}), "classic")
        self.assertEqual(requested_interface(["driftlessmap", "file.dmap"], {}), "classic")

    def test_flag_or_environment_selects_the_preview(self):
        self.assertEqual(requested_interface(["DriftlessMap", "--v2"], {}), "preview")
        self.assertEqual(requested_interface(["DriftlessMap", "--preview"], {}), "preview")
        self.assertEqual(requested_interface(["x"], {"DRIFTLESSMAP_INTERFACE": " V2 "}), "preview")
        self.assertEqual(requested_interface(["x"], {"DRIFTLESSMAP_INTERFACE": "classic"}),
                         "classic")
        # The program name itself is never read as a flag.
        self.assertEqual(requested_interface(["--v2"], {}), "classic")
        self.assertEqual(without_interface_flags(["app", "--v2", "-V"]), ["app", "-V"])

    def test_bundles_restart_themselves_and_installs_run_the_package(self):
        self.assertEqual(interface_command("preview", True, "/Apps/DriftlessMap"),
                         ("/Apps/DriftlessMap", ["--v2"]))
        self.assertEqual(interface_command("classic", True, "/Apps/DriftlessMap"),
                         ("/Apps/DriftlessMap", []))
        self.assertEqual(interface_command("preview", False, "/usr/bin/python3"),
                         ("/usr/bin/python3", ["-m", "driftlessmap.v2"]))
        self.assertEqual(interface_command("classic", False, "/usr/bin/python3"),
                         ("/usr/bin/python3", ["-m", "driftlessmap"]))
        with self.assertRaises(ValueError):
            interface_command("other", False, "python")

    def test_the_bundle_launcher_routes_the_preview_flag(self):
        environment = dict(os.environ, PYTHONPATH=str(REPOSITORY_ROOT))
        result = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / "packaging" / "launcher.py"), "--v2", "-V"],
            check=False, capture_output=True, text=True, env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2.0 preview", result.stdout)


if __name__ == "__main__":
    unittest.main()
