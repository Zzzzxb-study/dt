"""Build a credential-free source release from an explicit file allowlist."""
import hashlib
import json
import tarfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'output'
FILES = ['manage.py', 'requirements.txt', 'README.md', '启动练习.cmd', 'Dockerfile', 'compose.yaml', 'compose.existing-caddy.yaml', '.env.example', '.gitignore', '.dockerignore']
DIRECTORIES = ['config', 'practice', 'templates', 'static', 'data', 'deploy', 'docs', 'tools']


def package():
    selected = [ROOT / file for file in FILES]
    for directory in DIRECTORIES:
        selected.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo'))
    selected.extend(ROOT.rglob('*.pdf'))
    selected.extend((OUT / 'ui').glob('*.png'))
    selected.append(OUT / '验收报告.md')
    selected = sorted(set(selected), key=lambda p: p.relative_to(ROOT).as_posix())
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in selected}
    (OUT / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    selected.append(OUT / 'release-manifest.json')
    archive = OUT / '长江学堂在线练习应用-源码部署包.zip'
    with ZipFile(archive, 'w', compression=ZIP_DEFLATED, compresslevel=9) as zip_file:
        for path in selected:
            zip_file.write(path, '长江学堂在线练习应用/' + path.relative_to(ROOT).as_posix())
    with ZipFile(archive) as zip_file:
        assert zip_file.testzip() is None
        names = zip_file.namelist()
        assert not any('/tmp/' in n or '/.deps/' in n or n.endswith(('.sqlite3', '/.env')) for n in names)
        for path, digest in manifest.items():
            assert hashlib.sha256(zip_file.read('长江学堂在线练习应用/' + path)).hexdigest() == digest
    linux_archive = OUT / 'cjpractice15-deploy.tar.gz'
    with tarfile.open(linux_archive, 'w:gz') as tar:
        for path in selected:
            tar.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    with tarfile.open(linux_archive, 'r:gz') as tar:
        for path, digest in manifest.items():
            assert hashlib.sha256(tar.extractfile(path).read()).hexdigest() == digest
        assert all(not name.startswith('/') and '..' not in Path(name).parts and name != '.env' for name in tar.getnames())
    print(json.dumps({'archive': str(archive), 'files': len(selected), 'bytes': archive.stat().st_size, 'integrity': 'OK', 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}, ensure_ascii=False, indent=2))
    print(json.dumps({'linux_archive': str(linux_archive), 'bytes': linux_archive.stat().st_size, 'integrity': 'OK'}, ensure_ascii=False))


if __name__ == '__main__':
    package()
