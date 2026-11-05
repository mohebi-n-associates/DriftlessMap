import os,sys,time,json,tempfile,cProfile,pstats,io
from pathlib import Path
sys.path.insert(0,os.environ['DMAP_REVIEW_ROOT'])
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['DRIFTLESSMAP_V2_TEST_CHILD']='1'
import tests.settings_isolation  # noqa: F401
import numpy as np
from driftlessmap.probe_plans import ProbePlan,plan_readout,clearances,space_plans,planned_model
from tests.test_probe_plans import make_atlas
from tests.test_plan_spacing import fiber
from driftlessmap.probe_utiles import Probe
def report(**kw):print('REVIEW_RESULT '+json.dumps(kw),flush=True)
case=sys.argv[1]; atlas,labels,info=make_atlas()
if case=='containment':
    prism=ProbePlan('Prism',[500,-500,-1400],kind='prism',implant_id='a'*32,roll_deg=90,
                    specs={'width_um':1000,'depth_um':1000,'length_um':3000,'bevel_deg':90})
    f=ProbePlan('Fiber',[0,0,-500],kind='fiber',implant_id='b'*32,
                specs={'diameter_um':100,'fiber_length_um':10000})
    reads=[(p,plan_readout(p,atlas)) for p in (prism,f)]
    report(case=case,clearances=clearances(reads),model=planned_model(prism,reads[0][1],atlas.vox_um))
elif case=='fixed':
    plans=[fiber('Fiber 1',[-800,0,-1200]),fiber('Fiber 2',[-600,0,-1200]),fiber('Fiber 3',[900,900,-1200])]
    spaced,result=space_plans(atlas,plans,['Fiber 3'],max_ml_deg=0,max_ap_deg=0)
    report(case=case,report=result,actual=clearances([(p,plan_readout(p,atlas)) for p in spaced]))
elif case=='overlap':
    plans=[fiber('Fiber 1',[0,0,-1200]),fiber('Fiber 2',[0,0,-1200])]
    spaced,result=space_plans(atlas,plans,[p.probe for p in plans])
    report(case=case,report=result,angles=[p.ml_tilt_deg for p in spaced],actual=clearances([(p,plan_readout(p,atlas)) for p in spaced]))
elif case=='pure_perf':
    examples=[ProbePlan('Probe',[0,0,-1200],probe_settings=Probe().get_settings()),
              fiber('Fiber 1',[0,0,-1200]),
              ProbePlan('Prism',[-500,500,-1400],kind='prism',implant_id='a'*32,roll_deg=180,
                        specs={'width_um':1000,'depth_um':1000,'length_um':3000,'bevel_deg':45})]
    for p in examples:
        times=[]
        for _ in range(5):
            t=time.perf_counter();plan_readout(p,atlas);times.append(time.perf_counter()-t)
        report(case=case,operation='plan_readout',kind=p.kind,median_seconds=float(np.median(times)))
    plans=[fiber('Fiber 1',[300,0,-1200]),fiber('Fiber 2',[500,200,-1300])]
    profile=cProfile.Profile();t=time.perf_counter();profile.enable()
    spaced,result=space_plans(atlas,plans,[p.probe for p in plans]);profile.disable()
    report(case=case,operation='space_plans_2_fibers',seconds=time.perf_counter()-t,report=result)
    s=io.StringIO();pstats.Stats(profile,stream=s).strip_dirs().sort_stats('cumulative').print_stats(18);print(s.getvalue(),flush=True)
elif case=='gui_perf':
    from PyQt6.QtWidgets import QApplication
    from tests.test_v2_shell import V2ShellTests
    from tests.atlas_fixture import make_processed_atlas
    app=QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as folder:
        w=V2ShellTests().make_window(folder);e=w.engine
        assert e.load_volume_atlas(str(make_processed_atlas(Path(folder)/'atlas',shape=(80,64,64),axis_info=True)))
        w.start_probe_plan('prism');w.refresh()
        profile=cProfile.Profile(); times=[]
        profile.enable()
        for _ in range(3):
            t=time.perf_counter();w.refresh();times.append(time.perf_counter()-t)
        profile.disable();report(case=case,operation='unchanged_shell_refresh_prism',seconds=times)
        s=io.StringIO();pstats.Stats(profile,stream=s).strip_dirs().sort_stats('cumulative').print_stats(25);print(s.getvalue(),flush=True)
        times=[]
        for _ in range(3):
            t=time.perf_counter();e.plan_overlay.refresh();times.append(time.perf_counter()-t)
        report(case=case,operation='unchanged_overlay_refresh_prism',seconds=times)
        if os.environ.get('DMAP_REVIEW_SCREENSHOTS'):
            out=Path(os.environ['DMAP_REVIEW_SCREENSHOTS']);out.mkdir(exist_ok=True,parents=True)
            w.resize(1280,800);w.show();app.processEvents()
            w.grab().save(str(out/'prism-1280.png'))
sys.stdout.flush();os._exit(0)
