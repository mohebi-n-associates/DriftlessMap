"""Reproducible diagnostics for the 2.6.0 follow-up review.
Set DMAP_REVIEW_ROOT to an isolated archive of reviewed commit ce419db.
Run one case per process: atlas, legacy, checker, repair, multi_repair,
review, batch, or ui. UI also uses DMAP_REVIEW_SCREENSHOTS as output folder.
All input data and application settings are temporary. These probes observe
bugs; their exit success does not mean the reported behavior is correct.
"""

import os, sys, tempfile, json
from pathlib import Path
sys.path.insert(0, os.environ['DMAP_REVIEW_ROOT'])
os.environ['DRIFTLESSMAP_V2_TEST_CHILD'] = '1'
os.environ['DRIFTLESSMAP_SECTIONS_TEST_CHILD'] = '1'
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tests.settings_isolation  # noqa: F401
import numpy as np
import cv2
from PyQt6.QtWidgets import QApplication
from tests.test_sections import SectionPersistenceTests
from tests.test_v2_shell import V2ShellTests
from tests.atlas_fixture import make_processed_atlas
app = QApplication.instance() or QApplication([])
def report(**kw): print('REVIEW_RESULT '+json.dumps(kw), flush=True)
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    case = sys.argv[1]
    if case in ('atlas', 'legacy', 'multi_repair'):
        test = SectionPersistenceTests(); test.setUp()
        e, fiber, first, raster = test.two_section_project(root)
        assert e.build_implant(fiber.implant_id)[0]
        if case == 'atlas':
            before = e.atlas_view.vox_size_um
            make_processed_atlas(e.volume_atlas_path, voxel_size=50)
            result = e.load_volume_atlas(e.volume_atlas_path)
            report(case=case, load_accepted=result, before=before, after=e.atlas_view.vox_size_um,
                   objects=e.object_ctrl.obj_name, export_voxel_um=e.get_object_export_provenance()['atlas']['voxel_size_um'])
        elif case == 'legacy':
            e.atlas_view.cpage_ctrl.set_val(e.atlas_view.current_coronal_index+2)
            changed = e.section_id
            assert e.switch_section(first)[0]
            index = e.implant_objects(fiber.implant_id, built=True)[0]
            before = e.object_mapping_status(index)
            e.sections.entry(changed).summary.pop('registration', None)
            report(case=case, with_fingerprint=before, old_summary_without_fingerprint=e.object_mapping_status(index))
            path=root/'old-summary.dmap'
            assert e.save_project_called(path=str(path))
            reopened,_=test.open_project(root,path)
            index=reopened.implant_objects(fiber.implant_id,built=True)[0]
            status=reopened.object_mapping_status(index)
            assert reopened.switch_section(changed)[0]
            index=reopened.implant_objects(fiber.implant_id,built=True)[0]
            report(case='legacy_reopen',before_visiting_section=status,after_visiting_section=reopened.object_mapping_status(index))
        else:
            second=e.section_id
            e.atlas_view.cpage_ctrl.set_val(e.atlas_view.current_coronal_index+2)
            assert e.switch_section(first)[0]
            e.atlas_view.cpage_ctrl.set_val(e.atlas_view.current_coronal_index+2)
            index=e.implant_objects(fiber.implant_id,built=True)[0]
            affected=e.stale_contribution(index)
            outcome=e.update_mapping(affected.unit_id)
            index=e.implant_objects(fiber.implant_id,built=True)[0]
            report(case=case, update_succeeded=outcome is not None, first=first, second=second,
                   next_affected=e.stale_contribution(index).section_id,
                   contributions=[(r.section_id,s) for r,s in e.object_contributions(index)])
    else:
        test = V2ShellTests(); w = test.make_window(folder); e = w.engine
        assert e.load_volume_atlas(str(make_processed_atlas(root/'atlas')))
        cv2.imwrite(str(root/'s.png'), np.full((32,24,3),120,np.uint8))
        assert e.load_single_image_file(str(root/'s.png'), '.png')
        e.atlas_tri_inside_data[:] = [[1.,1.],[5.,1.],[3.,5.]]
        e.histo_tri_inside_data[:] = [[2.,2.],[6.,2.],[4.,6.]]
        w.go_to('register'); panel = w.panels['register']; panel.refresh()
        if case == 'batch':
            import tifffile
            from unittest.mock import patch
            path=root/'stack.tif'
            tifffile.imwrite(path,np.arange(4*32*24,dtype=np.uint16).reshape(4,32,24),metadata={'axes':'ZYX'},photometric='minisblack')
            calls=[]; original=tifffile.TiffPageSeries.asarray
            def read(series,*args,**kwargs):
                calls.append(list(series.shape)); return original(series,*args,**kwargs)
            with patch.object(tifffile.TiffPageSeries,'asarray',read):
                added=e.add_sections([str(path)],pages_as_sections=True)
            report(case=case,sections_added=added,full_series_reads=len(calls),shapes=calls)
        elif case == 'ui':
            out=Path(os.environ['DMAP_REVIEW_SCREENSHOTS']); out.mkdir(parents=True,exist_ok=True)
            w.resize(1280,800); w.show(); app.processEvents(); w.refresh(); app.processEvents()
            for step in ('project','section','match','register','annotate','results'):
                w.go_to(step); app.processEvents(); w.grab().save(str(out/(step+'-1280.png')))
                report(case='layout',step=step,width=w.width(),height=w.height(),panel=w.stack.width(),views=w.views.width(),inspector_visible=w.inspector_tabs.isVisible())
            w.apply_theme('light'); w.resize(1100,800); w.go_to('section'); app.processEvents()
            w.grab().save(str(out/'section-light-1100.png'))
        elif case == 'review':
            before=e.registration_review_state()
            reason=w.registry.run('register.review')
            report(case=case, checklist=[b.isChecked() for b in panel.checklist], before=before,
                   command_reason=reason, after=e.registration_review_state())
        elif case == 'checker':
            e.transfer_to_atlas_clicked(); panel.refresh()
            original=np.array(e.working_atlas_data['atlas-overlay'])
            panel.checker.setChecked(True); panel._toggle_checker()
            payload=e.project_payload(); data=payload['layer_data']
            idx=e.layer_ctrl.layer_link.index('atlas-overlay')
            saved=data['2d_data'][idx]
            report(case=case, saved_matches_original=bool(np.array_equal(original,saved)),
                   saved_matches_checker=bool(np.array_equal(panel._overlay_item().image,saved)),
                   changed_values=int(np.count_nonzero(original!=saved)))
            path=root/'checker.dmap'
            assert e.save_project_called(path=str(path))
            from driftlessmap.persistence import load_driftlessmap_file
            loaded,error=load_driftlessmap_file(str(path),expected_kind='project')
            assert error is None
            prepared=e.prepare_project_sources(loaded,str(path))
            assert e.load_project(prepared,project_path=str(path))
            report(case='checker_reopen', overlay_matches_original=bool(np.array_equal(original,panel._overlay_item().image)))
        elif case == 'repair':
            d=e.working_img_data
            d['img-cells']=[[8.,8.],[12.,20.]]; d['cell_size']=[5,5]; d['cell_symbol']=['o','o']
            d['cell_layer_index']=[0,0]; d['cell_count']=[2]+[0]*(len(d['cell_count'])-1)
            e.transfer_to_atlas_clicked(); e.transform_accept(); e.make_pieces_of('cells'); e.merge_cells()
            e.atlas_tri_inside_data[0]=[1.5,1.]
            e.object_ctrl.current_obj_index=0; w.go_to('results'); p=w.panels['results']; p.refresh()
            p.update_affected()
            i=e.object_ctrl.current_obj_index
            report(case=case, selected_type=e.object_ctrl.obj_type[i], recovery_hidden=p.recovery.isHidden(),
                   all_types=e.object_ctrl.obj_type, statuses=[e.object_mapping_status(j) for j in range(len(e.object_ctrl.obj_type))])
            p.rebuild_selected()
            report(case='repair_after_build', all_types=e.object_ctrl.obj_type, statuses=[e.object_mapping_status(j) for j in range(len(e.object_ctrl.obj_type))])
    sys.stdout.flush()
    os._exit(0)
