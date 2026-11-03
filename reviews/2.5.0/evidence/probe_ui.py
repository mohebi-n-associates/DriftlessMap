"""Diagnostic evidence for the 2.5.0 review, not an application change.
Run in a dedicated environment with DRIFTLESSMAP_REVIEW_SOURCE pointing at
an extracted copy of commit 5305b1d78efcf1077dc2333e87d04aceabac3e18.
Generated projects and source images use temporary folders. GUI checks run
offscreen, and settings are isolated. Observations are printed as JSON.
"""

import os, sys, tempfile, json
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.environ["DRIFTLESSMAP_REVIEW_SOURCE"])
import tests.settings_isolation  # noqa: F401 (isolate user settings)
import numpy as np, cv2
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from unittest.mock import patch
from driftlessmap.v2.shell import V2Window
from tests.atlas_fixture import make_processed_atlas
from driftlessmap import file_dialogs

app = QApplication([])
root = Path(tempfile.mkdtemp(prefix="dmap-review-ui-"))
s = V2Window(QSettings(str(root / "v2.ini"), QSettings.Format.IniFormat))
w = s.engine
assert w.load_volume_atlas(str(make_processed_atlas(root / "atlas")))
ids = []
for name in ["one", "two"]:
    path = root / (name + ".png")
    cv2.imwrite(str(path), np.full((32, 24, 3), 120, np.uint8))
    with patch.object(file_dialogs, "get_open_file_name", return_value=(str(path), "")):
        w.load_image()
    ids.append(w.section_id)
f = w.add_implant("fiber")
s.go_to("annotate")
card = s.panels["annotate"].implants
card.refresh(select=f.implant_id)
card.draw.setChecked(True)
card._mode("draw")
card.editor.vertices = [[5, 5], [15, 5], [15, 20], [5, 20]]
card.editor._show_preview()
s.go_to("project")
assert w.switch_section(ids[0])[0]
s.refresh()
s.go_to("annotate")
mode = card.editor.mode
verts = card.editor.vertices[:]
card.editor.finish()
print(
    "REVIEW_RESULT",
    json.dumps(
        {
            "outline_mode_after_switch": mode,
            "draft_after_switch": verts,
            "new_section_outline": w.implant_outline(f.implant_id),
            "new_section": w.section_id,
            "original_section": ids[1],
        }
    ),
    flush=True,
)
print("REVIEW_SCREENSHOT_FOLDER", str(root), flush=True)
s.resize(1280, 800)
s.show()
app.processEvents()
s.refresh()
app.processEvents()
for step in ["project", "section", "register", "annotate", "results"]:
    s.go_to(step)
    app.processEvents()
    s.grab().save(str(root / ("review-" + step + ".png")))
    print(
        "REVIEW_LAYOUT",
        json.dumps(
            {
                "step": step,
                "window_width": s.width(),
                "window_height": s.height(),
                "panel_width": s.stack.width(),
                "views_width": s.views.width(),
                "inspector_width": s.inspector_tabs.width(),
            }
        ),
        flush=True,
    )
s.apply_theme("light")
s.go_to("section")
app.processEvents()
s.grab().save(str(root / "review-light.png"))
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
