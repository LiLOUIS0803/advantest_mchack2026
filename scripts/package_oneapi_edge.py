"""Populate the single upload folder and create the ACS Edge archive."""
from pathlib import Path
import ast
import hashlib
import json
import runpy
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    runpy.run_path(str(ROOT/'scripts/build_temperature_flow.py'),run_name='__main__')
    runpy.run_path(str(ROOT/'scripts/restore_scene2_ui.py'),run_name='__main__')
    target=ROOT/'oneAPI_py3.10'
    runtime=('__init__.py','data.py','metrics.py','engine.py','classifier_features.py',
             'portable_model.py','classifier_engine.py','replay.py','notifications.py',
             'server.py','frontend.py','oneapi_adapter.py','scene2_runtime.py','combined_bridge.py','hc_push.py')
    for name in runtime:
        src=ROOT/'realtime'/name;dest=target/'bin/realtime'/name
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    webnames=('index.html','dashboard.css','api.js','app.js','visuals.js','outcomes.js','hierarchy.js','theme.js','notifications.js',
              'scene2-style.css','task-nav.js','tasks.html','temperature.html','temperature.css','temperature.js')
    for name in webnames:
        dest=target/'bin/realtime/web'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'realtime/web'/name,dest)
    for name in ('normal_model.npz','model_info.json','wafer_classifier/model.npz',
                 'wafer_classifier/info.json','wafer_classifier/portable_validation.json','wafer_classifier/portable_cases.npz',
                 'scene2/temp_models.json','scene2/evaluation.json','scene2/uncertainty.json','scene2/test_flow.json'):
        dest=target/'bin/artifacts'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/'artifacts'/name,dest)
    for name in ('__init__.py','temp_predictor.py'):
        dest=target/'bin/scene2'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'scene2'/name,dest)
    for name in ('__init__.py','hc_server.py'):
        dest=target/'hc/realtime'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'realtime'/name,dest)
    for name in webnames:
        dest=target/'hc/realtime/web'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'realtime/web'/name,dest)
    shutil.copyfile(ROOT/'deploy/setup_hc.py',target/'hc/setup.py')
    shutil.copyfile(ROOT/'deploy/start_hc.py',target/'hc/start.py')
    descriptor=json.loads((ROOT/'SmarTest/app_descriptor.json').read_text())
    container=descriptor['edge']['containers'][0]
    container['image']='grp4/py-app:tasks-v7'
    container['environment'].pop('ACTIONS_FILE_PATH',None)
    container['environment']['REPORT_DIR']='/var/lib/wafer-watch'
    (target/'app_descriptor.json').write_text(json.dumps(descriptor,indent=2)+'\n',encoding='utf-8')
    paths=[p for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts
           and p.suffix not in ('.pyc','.log','.sqlite3') and p.name not in ('package-manifest.json','hc-token.txt','app_descriptor.hc.json')]
    for p in paths:
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'),feature_version=(3,10))
    hashes={p.relative_to(target).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest=target/'package-manifest.json';manifest.write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    paths.append(manifest)
    archive=ROOT/'dist/oneAPI_py3.10-edge.zip';archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:z.write(p,'oneAPI_py3.10/'+p.relative_to(target).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(n.startswith('oneAPI_py3.10/') for n in z.namelist())
        for name,digest in hashes.items():assert hashlib.sha256(z.read('oneAPI_py3.10/'+name)).hexdigest()==digest
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'archive':str(archive),'files':len(paths),'bytes':archive.stat().st_size,'sha256':digest}))


if __name__=='__main__':main()
