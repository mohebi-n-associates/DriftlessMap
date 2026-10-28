"""Keep tests from touching the user's real DriftlessMap settings.

File dialogs remember the last folder in the user settings file; tests that
fake dialogs would otherwise write to it. Import this module first.
"""

import atexit
import os
import shutil
import tempfile

if not os.environ.get("DRIFTLESSMAP_CONFIG_DIR"):
    _folder = tempfile.mkdtemp(prefix="driftlessmap-test-settings-")
    os.environ["DRIFTLESSMAP_CONFIG_DIR"] = _folder
    atexit.register(shutil.rmtree, _folder, True)
