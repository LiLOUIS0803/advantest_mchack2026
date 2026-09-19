"""Create an explicit, auditable source upload archive for Gemini."""
import csv
import hashlib
import importlib.metadata
import io
import json
import platform
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = {}
    for directory in ('realtime', 'oneAPI_py3.10', 'SmarTest', 'tests', 'doc'):
        print('Collecting ' + directory, flush=True)
        for path in (ROOT / directory).rglob('*'):
            if not path.is_file() or any(p in ('__pycache__', '.git', '.abin', '.metadata', 'logs') for p in path.parts):
                continue
            if path.suffix in ('.pyc', '.log'):
                continue
            files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ('normal_model.npz', 'model_info.json', 'wafer_classifier/model.joblib', 'wafer_classifier/info.json'):
        path = ROOT / 'artifacts' / name
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    with (ROOT / 'data/splits/manifest.csv').open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = [r for r in reader if int(r['wafer']) != 2 and r['split'] != 'excluded']
    for row in rows:
        for key in ('csv', 'metadata'):
            if row[key]:
                path = ROOT / row[key]
                path.resolve().relative_to(ROOT.resolve())
                files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    print('Collected replay data', flush=True)
    manifest = io.StringIO(newline='')
    writer = csv.DictWriter(manifest, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    files['data/splits/manifest.csv'] = manifest.getvalue().encode('utf-8')
    files['data/TrainDataInfo.txt'] = (ROOT / 'data/TrainDataInfo.txt').read_bytes()
    files['deploy/GEMINI_UPLOAD.md'] = (ROOT / 'deploy/GEMINI_UPLOAD.md').read_bytes()
    files['reports/wafer_classifier/comparison.json'] = (ROOT / 'reports/wafer_classifier/comparison.json').read_bytes()
    versions = {'python': platform.python_version(), 'packages': {
        name: importlib.metadata.version(name)
        for name in ('numpy', 'scipy', 'scikit-learn', 'joblib', 'threadpoolctl')},
        'status': 'source package; ACS runtime compatibility and ONEAPI integration pending'}
    files['deploy/runtime-versions.json'] = json.dumps(versions, indent=2).encode()
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files['deploy/package-manifest.json'] = json.dumps(checksums, indent=2).encode()
    output = ROOT / 'dist/wafer-watch-gemini-source.zip'
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr('wafer-watch/' + name, data)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert not any('W02_' in name or 'notifications.sqlite' in name for name in archive.namelist())
        for name, checksum in checksums.items():
            assert hashlib.sha256(archive.read('wafer-watch/' + name)).hexdigest() == checksum
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest + '  ' + output.name + '\n', encoding='ascii')
    print(json.dumps({'archive': str(output), 'files': len(files), 'replay_wafers': len(rows),
                      'bytes': output.stat().st_size, 'sha256': digest}, indent=2))


if __name__ == '__main__':
    main()
