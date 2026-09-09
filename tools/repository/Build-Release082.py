"""Assemble 0.82 from the pinned 0.81 ZIP and runtime-reviewed ERS candidate."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
BUILD = WORK / 'build/0.82'
PACKAGE = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
BASE_ZIP = WORK / 'releases/0.81/AMS2 한국어 패치 오픈베타 0.81.zip'
STOCK_SHA = '0673E7D678E1B4B2486867072BCEA0F1F11B1D571807A582AC85B91F2C9E37A2'
PATCHED_SHA = 'F8A840F569D256DB4E1A67D73C5B2BB9CC4927E18109178B67356479BDCE81E5'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=WORK / 'build/0.81-ers-test2')
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    if PACKAGE.exists() or REPO in PACKAGE.resolve().parents:
        raise ValueError('Release output must be new and outside the repository')
    assert sha(BASE_ZIP) == '4219812330063E4E156763AFCFF7D82EB1E5DC02CB30410D6BE25380FD7CBA30'
    baseline = BUILD / 'baseline'
    if not baseline.exists():
        baseline.mkdir(parents=True)
        with zipfile.ZipFile(BASE_ZIP) as archive:
            archive.extractall(baseline)  # Pinned, previously verified release; every payload is rechecked below.
    source = baseline / 'AMS2 한국어 패치 오픈베타 0.81'
    rows = list(csv.DictReader((source / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    assert len(rows) == 449
    table = {r['relative_path']: r for r in rows}
    for row in rows:
        payload = source / 'payload/direct' / row['relative_path']
        assert payload.stat().st_size == int(row['bytes']) and sha(payload) == row['sha256'].upper()
    ers = json.loads((candidate / 'manifest.json').read_text(encoding='utf-8'))
    assert ers['scope'] == 'ERS_COCKPIT_ARCHIVE_TEST' and ers['status'] == 'GAME_TEST_PASSED'
    assert ers['validation']['game_test_scope'] == 'Formula Ultimate Hybrid Gen1 normal cockpit ERS Balanced label only'
    assert len(ers['files']) == 21 and ers['validation']['bgui_font_routes'] == 13
    for row in ers['files']:
        assert sha(candidate / 'payload' / row['path']) == row['after_sha256']
    original = candidate / 'backup/Pakfiles/HUDDISPLAY.bff'
    patched = candidate / 'payload/Pakfiles/HUDDISPLAY.bff'
    assert sha(original) == STOCK_SHA and sha(patched) == PATCHED_SHA
    assert original.stat().st_size == patched.stat().st_size == 23701335

    PACKAGE.mkdir(parents=True)
    for directory in ('assets', 'payload', 'runtime'):
        shutil.copytree(source / directory, PACKAGE / directory)
    (PACKAGE / 'manifest').mkdir()
    binaries = BUILD / 'installer'
    name = 'AMS2 한국어 패치 오픈베타 0.82.exe'
    shutil.copy2(binaries / 'AMS2-Korean-Patch-OB-0.82.exe', PACKAGE / name)
    shutil.copy2(REPO / 'installer/0.82/Installer.exe.config', PACKAGE / (name + '.config'))
    overlays = [(r['path'], candidate / 'payload' / r['path'], r['before_sha256'])
                for r in ers['files'] if r['path'] != 'Pakfiles/HUDDISPLAY.bff']
    overlays += [(name, binaries / name, None) for name in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe')]
    changed, added = [], []
    for relative, payload, before in overlays:
        target = PACKAGE / 'payload/direct' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative in table:
            row = table[relative]
            if before is not None:
                assert row['sha256'] == before
            # Includes the 0.81 payload for verified original-backup adoption after the ERS test.
            row['allowed_before_sha256'] = ';'.join(sorted(set(filter(None, row['allowed_before_sha256'].split(';') + [row['sha256']]))))
            changed.append(relative)
        else:
            assert before is not None
            row = dict(relative_path=relative, bytes='', sha256='', role='created' if before == 'MISSING' else 'modified',
                       allowed_before_sha256='' if before == 'MISSING' else before)
            rows.append(row)
            table[relative] = row
            added.append(relative)
        shutil.copy2(payload, target)
        row['bytes'], row['sha256'] = str(target.stat().st_size), sha(target)
    assert len(rows) == 465 and len(changed) == 6 and len(added) == 16
    with (PACKAGE / 'manifest/direct-files.tsv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    # Native gzip plus XOR stores only the reviewed difference, not a full game archive.
    before, after = original.read_bytes(), patched.read_bytes()
    delta = bytes(a ^ b for a, b in zip(before, after))
    compressed = gzip.compress(delta, mtime=0)
    assert bytes(a ^ b for a, b in zip(before, gzip.decompress(compressed))) == after
    assert bytes(a ^ b for a, b in zip(after, gzip.decompress(compressed))) == before
    (PACKAGE / 'payload/HUDDISPLAY.xor.gz').write_bytes(compressed)
    runtime = PACKAGE / 'runtime/AMS2.DynamicBffPatcher.exe'
    assert sha(runtime) == '4179D08A1452D497D612B0B371BF9C8881AFFDBEAE2389A9A1D393F85FA6AAA5'
    shutil.copy2(REPO / 'releases/0.82/RELEASE_NOTES.md', PACKAGE / 'RELEASE_NOTES.md')
    manifest = dict(schema='ams2-kr-open-beta-release-v082', version='0.82', package_id='AMS2-KR-BETA-0.82-PRETENDARD',
                    creator='ENGIceBlasT', reference_buildid='24132163', baseline_tag='v0.81', baseline_zip_sha256=sha(BASE_ZIP),
                    direct_files=len(rows), changed_direct_files=changed, added_direct_files=added,
                    ers_archive_before_sha256=STOCK_SHA, ers_archive_after_sha256=PATCHED_SHA,
                    ers_delta_sha256=sha(PACKAGE / 'payload/HUDDISPLAY.xor.gz'),
                    dynamic_bff_patcher_sha256=sha(runtime), launcher_update_protocol=1,
                    validation_status='AWAITING_PACKAGE_TESTS', game_test_scope=ers['validation']['game_test_scope'],
                    pending=['Other ERS modes, notifications and vehicles', 'Multiplayer replay-save dialog',
                             'VR headset startup', 'Full automatic update and game relaunch', 'Replay time-column clipping'])
    (PACKAGE / 'manifest/release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: 0.82 assembled; 465 direct files; 13 ERS routes; %d-byte archive delta' % len(compressed))


if __name__ == '__main__':
    main()
