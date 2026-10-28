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
    def test_the_2_0_interface_is_the_default(self):
        self.assertEqual(requested_interface(["driftlessmap"], {}), "preview")
        self.assertEqual(requested_interface(["driftlessmap", "file.dmap"], {}), "preview")

    def test_flag_or_environment_selects_an_interface(self):
        self.assertEqual(requested_interface(["DriftlessMap", "--classic"], {}), "classic")
        self.assertEqual(requested_interface(["x"], {"DRIFTLESSMAP_INTERFACE": " Classic "}),
                         "classic")
        self.assertEqual(requested_interface(["DriftlessMap", "--v2"], {}), "preview")
        self.assertEqual(requested_interface(["DriftlessMap", "--preview"], {}), "preview")
        self.assertEqual(requested_interface(["x"], {"DRIFTLESSMAP_INTERFACE": " V2 "}), "preview")
        # A flag wins over the environment.
        self.assertEqual(requested_interface(["x", "--v2"], {"DRIFTLESSMAP_INTERFACE": "classic"}),
                         "preview")
        self.assertEqual(requested_interface(["x", "--classic"], {"DRIFTLESSMAP_INTERFACE": "v2"}),
                         "classic")
        # The program name itself is never read as a flag.
        self.assertEqual(requested_interface(["--classic"], {}), "preview")
        self.assertEqual(without_interface_flags(["app", "--v2", "--classic", "-V"]),
                         ["app", "-V"])

    def test_bundles_restart_themselves_and_installs_run_the_package(self):
        self.assertEqual(interface_command("preview", True, "/Apps/DriftlessMap"),
                         ("/Apps/DriftlessMap", ["--v2"]))
        self.assertEqual(interface_command("classic", True, "/Apps/DriftlessMap"),
                         ("/Apps/DriftlessMap", ["--classic"]))
        self.assertEqual(interface_command("preview", False, "/usr/bin/python3"),
                         ("/usr/bin/python3", ["-m", "driftlessmap.v2"]))
        self.assertEqual(interface_command("classic", False, "/usr/bin/python3"),
                         ("/usr/bin/python3", ["-m", "driftlessmap", "--classic"]))
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

    def test_launching_without_a_flag_starts_the_2_0_interface(self):
        from unittest import mock

        from driftlessmap.run_driftlessmap import run

        with mock.patch.object(sys, "argv", ["driftlessmap", "file.dmap"]), \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch("driftlessmap.v2.main", return_value=5) as preview:
            os.environ.pop("DRIFTLESSMAP_INTERFACE", None)
            self.assertEqual(run(), 5)
        preview.assert_called_once_with(["driftlessmap", "file.dmap"])


if __name__ == "__main__":
    unittest.main()
