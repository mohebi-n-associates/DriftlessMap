"""Diagnostics for the DriftlessMap 2.8.3 review, commit e7f8563.
Set DMAP_REVIEW_ROOT to an isolated archive of the reviewed commit. Run one
case per process (see README.md). Input data/settings are disposable fixtures.
These are observations, not tests whose successful exit means behavior is correct.
"""

import os, sys, tempfile, json
from pathlib import Path

sys.path.insert(0, os.environ["DMAP_REVIEW_ROOT"])
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DRIFTLESSMAP_V2_TEST_CHILD"] = "1"
import tests.settings_isolation  # noqa: F401
import numpy as np
from driftlessmap.probe_plans import (
    ProbePlan,
    ProposalRequest,
    propose_plans,
    plan_readout,
    shank_lines,
    target_coverage,
    Craniotomy,
    _LineScorer,
)
from driftlessmap.probe_utiles import Probe


def report(**kw):
    print("REVIEW_RESULT " + json.dumps(kw), flush=True)


case = sys.argv[1]
if case in ("multi", "gap", "hierarchy", "conflict"):
    from tests.test_probe_plans import make_target_atlas

    atlas, labels = make_target_atlas()
    plan = ProbePlan("P", [600, 100, -1200], probe_settings=Probe().get_settings())
    if case == "multi":
        hardware = Probe()
        hardware.set_np2()
        plan = plan.copy(probe_settings=hardware.get_settings())
        # Central target is narrower than the space between four physical shanks.
        # Put an avoided region on one outer shank, away from the centre line.
        labels[58:64, 40:44, 55:64] = 42
        plan = plan.copy(
            shank_offsets_um=[-375, -125, 125, 375], targets=[40], avoid=[42]
        )
        hole = Craniotomy("hole", "small", [600, 100], 200)
        request = ProposalRequest(
            [40], avoid=[42], max_ap_tilt_deg=0, max_ml_tilt_deg=0, craniotomy=hole
        )
        props, reasons = propose_plans(atlas, request, plan)
        # Existing X sits above A; remove it only on the central footprint.
        if not props:
            labels[50:54, 40:44, 58:62] = 10
            props, reasons = propose_plans(atlas, request, plan)
        best = props[0]
        p = best["plan"]
        readout = plan_readout(p, atlas)
        actual = []
        for line in shank_lines(p, readout, atlas):
            pts = np.linspace(line[0], line[-1], 500) + atlas.bregma
            ids, _ = atlas.labels_at(pts)
            actual.append(
                {
                    "hits_target": bool(np.any(ids == 40)),
                    "hits_avoid": bool(np.any(ids == 42)),
                    "entry_hole_distance_um": hole.distance_um(line[0] * atlas.vox_um),
                }
            )
        report(
            case=case,
            proposals=len(props),
            reported_reached=best["reached"],
            coverage=best["coverage"],
            reasons=reasons,
            actual_shanks=actual,
            hole_radius_um=100,
        )
    elif case == "gap":
        labels[10:70, 10:70, 44:50] = 0
        props, reasons = propose_plans(
            atlas, ProposalRequest([40], max_ap_tilt_deg=0, max_ml_tilt_deg=0), plan
        )
        best = props[0]
        r = plan_readout(best["plan"], atlas)
        report(
            case=case,
            proposals=len(props),
            reasons=reasons,
            tip_region=r["tip_region"][0],
            warnings=r["warnings"],
            coverage=best["coverage"],
        )
    elif case == "hierarchy":
        for targets in ([10, 40], [40, 10]):
            request = ProposalRequest(targets, max_ap_tilt_deg=0, max_ml_tilt_deg=0)
            result = _LineScorer(atlas, request, plan).evaluate(
                plan.direction, [600, 100, -1000]
            )
            p = plan.copy(tip_um=result["tip_um"], targets=targets)
            report(
                case=case,
                targets=targets,
                reached=result["reached"],
                coverage=result["coverage_um"],
                readout=target_coverage(p, plan_readout(p, atlas), atlas),
            )
    else:
        request = ProposalRequest(
            [40], avoid=[40], max_ap_tilt_deg=0, max_ml_tilt_deg=0
        )
        props, reasons = propose_plans(atlas, request, plan)
        report(
            case=case,
            requested_avoid=[40],
            effective_avoid=request.avoid,
            proposals=len(props),
            reasons=reasons,
        )
else:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from tests.test_v2_shell import V2ShellTests
    from tests.atlas_fixture import make_processed_atlas
    from driftlessmap.persistence import load_driftlessmap_file

    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        test = V2ShellTests()
        w = test.make_window(folder)
        e = w.engine
        assert e.load_volume_atlas(
            str(
                make_processed_atlas(root / "atlas", shape=(80, 64, 64), axis_info=True)
            )
        )
        w.run("probe.plan")
        w.refresh()
        editor = w.panels["annotate"].implants.probe_card.plan_editor
        before = e.probe_plan("Probe 1").copy()
        if case in ("pending_save", "pending_new", "pending_undo"):
            path = root / "base.dmap"
            assert e.save_project_called(path=str(path))
            w.mark_saved()
            editor.steer_key(Qt.Key.Key_W)
            wanted = editor.current().tip_um[:]
            report(
                case=case,
                stage="pending",
                old=before.tip_um,
                shown=wanted,
                dirty=w.is_dirty(),
                pending=editor._pending is not None,
            )
            if case == "pending_save":
                w.save_project()
                data, error = load_driftlessmap_file(str(path), expected_kind="project")
                assert error is None
                report(
                    case=case,
                    stage="saved",
                    disk=data["probe_plans"][0]["tip_um"],
                    shown=editor.current().tip_um,
                    dirty=w.is_dirty(),
                )
                QTest.qWait(650)
                report(
                    case=case,
                    stage="settled",
                    stored=e.probe_plan("Probe 1").tip_um,
                    dirty=w.is_dirty(),
                )
            elif case == "pending_new":
                test.answer_new_project(w, "Keep the atlas")
                w.run("project.new")
                QTest.qWait(650)
                report(
                    case=case,
                    stage="new_document",
                    plans=e.probe_plans.to_list(),
                    editor_pending=editor._pending is not None,
                    objects=e.object_ctrl.obj_name,
                )
            else:
                e.undo_mapping_step()
                w.refresh()
                QTest.qWait(650)
                report(
                    case=case,
                    stage="after_undo",
                    plans=e.probe_plans.to_list(),
                    redo=e.undo_history.redo_label(),
                )
        elif case == "steering":
            w.show()
            w.activateWindow()
            app.processEvents()
            editor._set_steering(True)
            w.go_to("project")
            w.setFocus()
            app.processEvents()
            QTest.keyClick(w, Qt.Key.Key_W)
            QTest.qWait(650)
            report(
                case=case,
                editor_visible=editor.isVisible(),
                steering_checked=editor.steer_button.isChecked(),
                before=before.tip_um,
                after=e.probe_plan("Probe 1").tip_um,
            )
        elif case == "dialog_stale":
            from driftlessmap.v2.proposal_dialog import ProposalDialog

            dialog = ProposalDialog(editor)
            dialog._add(dialog.targets, 20)
            dialog.max_ap.setValue(0)
            dialog.max_ml.setValue(0)
            dialog.midline.setValue(0)
            dialog.find()
            original_side = dialog.request().side
            dialog.side.setCurrentIndex(2 if original_side == 1 else 1)
            dialog.use()
            report(
                case=case,
                requested_side=dialog.request().side,
                chosen_tip_ml=dialog.chosen.tip_um[0],
                use_enabled=dialog.use_button.isEnabled(),
            )
        elif case == "lambda":
            e.atlas_view.atlas_lambda = e.atlas_view.origin_3d + np.array(
                [0.0, 20.0, 0.0]
            )
            e.set_surgery_settings(bregma_lambda_um=450)
            before_lambda = e.atlas_bregma_lambda_um()
            before_scale = e.surgery_scale()
            payload = e.project_payload()
            payload["img_ctrl_data"] = {"current_img": np.zeros((0, 0, 3), np.uint8)}
            loaded = e.load_project(payload)
            report(
                case=case,
                invalid_project_loaded=loaded,
                before_um=before_lambda,
                after_um=e.atlas_bregma_lambda_um(),
                before_scale=before_scale,
                after_scale=e.surgery_scale(),
            )
        elif case == "ui":
            from driftlessmap.v2.proposal_dialog import ProposalDialog

            out = Path(os.environ["DMAP_REVIEW_SCREENSHOTS"])
            out.mkdir(parents=True, exist_ok=True)
            w.resize(1280, 800)
            w.show()
            app.processEvents()
            w.refresh()
            app.processEvents()
            panel = w.panels["annotate"]
            panel.ensureWidgetVisible(editor.start_button)
            app.processEvents()
            w.grab().save(str(out / "plan-1280.png"))
            panel.ensureWidgetVisible(editor.readout)
            app.processEvents()
            w.grab().save(str(out / "plan-readout-1280.png"))
            dialog = ProposalDialog(editor)
            dialog._add(dialog.targets, 20)
            dialog.max_ap.setValue(0)
            dialog.max_ml.setValue(0)
            dialog.midline.setValue(0)
            dialog.find()
            dialog.show()
            app.processEvents()
            dialog.grab().save(str(out / "proposal.png"))
            report(
                case=case,
                window_size=[w.width(), w.height()],
                panel_width=panel.viewport().width(),
                panel_minimum=panel.widget().minimumSizeHint().width(),
                dialog_size=[dialog.width(), dialog.height()],
            )
sys.stdout.flush()
os._exit(0)
