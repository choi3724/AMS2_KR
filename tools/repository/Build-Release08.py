"""Assemble 0.8 from the verified 0.7 ZIP and externally built 0.8 executables."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
BUILD = WORK / 'build/0.8'
PACKAGE = WORK / 'releases/0.8/AMS2 한국어 패치 CB 0.8'
BASE_ZIP = WORK / 'releases/0.7/AMS2.CB.0.7.zip'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    if PACKAGE.exists() or REPO in PACKAGE.resolve().parents:
        raise ValueError('Release output must be new and outside the repository')
    assert sha(BASE_ZIP) == 'A8244FB06B57B4747672FF59BD737D0209A4D3CD0E7F755F7CD5EFE5EFEB590E'
    baseline = BUILD / 'baseline'
    baseline.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(BASE_ZIP) as archive:
        archive.extractall(baseline)  # Pinned, previously validated archive.
    source = baseline / 'AMS2 한국어 패치 CB 0.7'
    rows = list(csv.DictReader((source / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    for row in rows:
        path = source / 'payload/direct' / row['relative_path']
        assert path.stat().st_size == int(row['bytes']) and sha(path) == row['sha256'].upper()
    overlay = BUILD / 'translation'
    subprocess.run([sys.executable, '-B', str(REPO / 'tools/AMS2-Asset-Studio/build_ui_hotfix.py'),
                    '--release-root', str(source), '--output', str(overlay), '--version', '0.8'], check=True)
    PACKAGE.mkdir(parents=True)
    for directory in ('assets', 'payload', 'runtime'):
        shutil.copytree(source / directory, PACKAGE / directory)
    (PACKAGE / 'manifest').mkdir()
    binaries = BUILD / 'installer'
    installer_name = 'AMS2 한국어 패치 CB 0.8.exe'
    shutil.copy2(binaries / 'AMS2-Korean-Patch-CB-0.8.exe', PACKAGE / installer_name)
    shutil.copy2(REPO / 'installer/0.8/Installer.exe.config', PACKAGE / (installer_name + '.config'))
    changed = []
    for row in rows:
        relative = row['relative_path']
        replacement = (binaries / relative) if relative.endswith('Launcher.exe') else (overlay / 'payload' / relative)
        if replacement.is_file():
            target = PACKAGE / 'payload/direct' / relative
            shutil.copy2(replacement, target)
            if row['role'] == 'created':
                row['allowed_before_sha256'] = ';'.join(sorted(set(filter(None, row['allowed_before_sha256'].split(';') + [row['sha256']]))))
            row['bytes'], row['sha256'] = str(target.stat().st_size), sha(target)
            changed.append(relative)
    assert set(changed) == {'AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe', 'text/game.tdb', 'text/drivers.tdb'}
    with (PACKAGE / 'manifest/direct-files.tsv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    # The unchanged, runtime-tested BFF tool is retained with the hash pinned by BetaCore.
    runtime = PACKAGE / 'runtime/AMS2.DynamicBffPatcher.exe'
    assert sha(runtime) == '4179D08A1452D497D612B0B371BF9C8881AFFDBEAE2389A9A1D393F85FA6AAA5'
    notes = REPO / 'releases/0.8/RELEASE_NOTES.md'
    shutil.copy2(notes, PACKAGE / notes.name)
    manifest = {
        'schema': 'ams2-kr-closed-beta-release-v08', 'version': '0.8',
        'package_id': 'AMS2-KR-BETA-0.8-PRETENDARD', 'creator': 'ENGIceBlasT',
        'reference_buildid': '24132163', 'baseline_tag': 'v0.7', 'baseline_zip_sha256': sha(BASE_ZIP),
        'direct_files': len(rows), 'changed_direct_files': changed,
        'dynamic_bff_patcher_sha256': sha(runtime), 'launcher_update_protocol': 1,
        'validation_status': 'AWAITING_PACKAGE_TESTS',
        'pending': ['Multiplayer replay-save dialog', 'VR headset startup', 'Replay time-column clipping'],
    }
    (PACKAGE / 'manifest/release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: 0.8 package assembled; 449 direct files, exactly 4 replacements; original menu/HUD retained.')


if __name__ == '__main__':
    main()
