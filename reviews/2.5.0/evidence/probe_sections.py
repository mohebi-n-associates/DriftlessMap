"""Diagnostic evidence for the 2.5.0 review, not an application change.
Run in a dedicated environment with DRIFTLESSMAP_REVIEW_SOURCE pointing at
an extracted copy of commit 5305b1d78efcf1077dc2333e87d04aceabac3e18.
Generated projects and source images use temporary folders. GUI checks run
offscreen, and settings are isolated. Observations are printed as JSON.
"""

import os, sys, tempfile, json
import numpy as np
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DRIFTLESSMAP_SECTIONS_TEST_CHILD"] = "1"
sys.path.insert(0, os.environ["DRIFTLESSMAP_REVIEW_SOURCE"])
import tests.settings_isolation  # noqa: F401 (isolate user settings)
from tests.test_sections import SectionPersistenceTests
from tests.atlas_fixture import make_processed_atlas
from driftlessmap.persistence import load_driftlessmap_file
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
t = SectionPersistenceTests()
t.setUp()
root = Path(tempfile.mkdtemp(prefix="dmap-review-case-"))
w, f, a, r = t.two_section_project(root)
b = w.section_id
case = sys.argv[1]


def out(**data):
    print("REVIEW_RESULT " + json.dumps(data, default=str), flush=True)


if case == "tiff":
    import tifffile

    path = root / "stack.tif"
    tifffile.imwrite(
        path,
        np.stack([np.full((32, 24), 40, np.uint8), np.full((32, 24), 180, np.uint8)]),
        metadata={"axes": "ZYX"},
        photometric="minisblack",
    )
    t.load_section(w, path)
    w.atlas_tri_inside_data[:] = [[5.0, 5.0], [15.0, 5.0], [10.0, 20.0]]
    w.histo_tri_inside_data[:] = [[5.0, 5.0], [15.0, 5.0], [10.0, 20.0]]
    reviewed = w.mark_registration_reviewed()
    t.map_fiber(w, f)
    rec = w.mapping_ledger.get(w.section_id, "fiber", f.implant_id)
    reviewed = w.mark_registration_reviewed()
    before = {
        "page": w.image_view.display_img_index,
        "mean": float(w.image_view.current_img.mean()),
        "review": w.registration_review_state(),
        "fingerprint": w.current_registration_fingerprint(),
        "sid": w.section_id,
    }
    w.image_view.page_ctrl.page_slider.setValue(1 - w.image_view.display_img_index)
    after = {
        "page": w.image_view.display_img_index,
        "mean": float(w.image_view.current_img.mean()),
        "review": w.registration_review_state(),
        "fingerprint": w.current_registration_fingerprint(),
        "sid": w.section_id,
        "mapping": w.mapping_status(rec),
    }
    out(reviewed=reviewed, before=before, after=after)
elif case == "stale":
    assert w.build_implant(f.implant_id)[0]
    ix = w.implant_objects(f.implant_id, built=True)[0]
    before = w.object_mapping_status(ix)
    w.atlas_view.cpage_ctrl.set_val(21)
    changed = w.object_mapping_status(ix)
    switched = w.switch_section(a)
    after = w.object_mapping_status(ix)
    paths, notes = w.export_all_results(str(root / "export"))
    out(before=before, changed=changed, switched=switched, after=after, notes=notes)
elif case == "remove":
    assert w.build_implant(f.implant_id)[0]
    before = list(w.object_ctrl.obj_type)
    before_units = len(w.mapping_ledger.records())
    removed = w.remove_section(a, delete_results=True)
    after = list(w.object_ctrl.obj_type)
    rebuilt = w.build_implant(f.implant_id)
    out(
        before=before,
        before_units=before_units,
        removed=removed,
        after=after,
        remaining_records=len(w.mapping_ledger.records()),
        rebuilt=rebuilt,
    )
elif case == "portable":
    t.write_section(root / "pfc-1.png", 50)
    result = w.save_project_called(portable=True, path=str(root / "portable.dmap"))
    payload, error = load_driftlessmap_file(
        str(root / "portable.dmap"), expected_kind="project"
    )
    out(
        saved=result,
        error=error,
        portable_sources=list((payload.get("portable_sources") or {}).keys()),
        stored_packed=list(
            (payload.get("portable_sources") or {}).get("sections", {}).keys()
        ),
        changed=payload["sections"]["stored"][0]["state"]["histology_provenance"][
            "source_changed_since_load"
        ],
        message=w.statusbar.currentMessage(),
    )
elif case == "atlas":
    assert w.build_implant(f.implant_id)[0]
    old_report = w.implant_report(f.implant_id)
    loaded = w.load_volume_atlas(
        str(make_processed_atlas(root / "different-atlas", voxel_size=50))
    )
    switched = w.switch_section(a)
    ix = w.implant_objects(f.implant_id, built=True)[0]
    out(
        loaded=loaded,
        switched=switched,
        objects=w.object_ctrl.obj_type,
        status=w.object_mapping_status(ix),
        atlas_voxel=w.atlas_view.vox_size_um,
        old_report_voxel=old_report.get("voxel_um"),
        provenance=w.get_object_export_provenance()["atlas"],
    )
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
