"""Assemble the update-aware 0.83 package from verified 0.82 and compatibility assets."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compatibility', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    compat, output = args.compatibility.resolve(), args.output.resolve()
    if output.exists() or output == REPO or REPO in output.parents:
        raise ValueError('Use a new output outside the repository')
    baseline = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
    assert sha(baseline.parent / (baseline.name + '.zip')) == 'AF00158ECF5D1AF3BE6BA8E2800402330FC6B0EA8206BF23B676613A86EA900D'
    rules = json.loads((compat / 'data/rules.json').read_text(encoding='utf-8'))
    rows = list(csv.DictReader((baseline / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    assert len(rows) == 465
    for row in rows:
        assert sha(baseline / 'payload/direct' / row['relative_path']) == row['sha256']
    output.mkdir(parents=True)
    for directory in ('assets', 'payload', 'runtime'):
        shutil.copytree(baseline / directory, output / directory)
    (output / 'manifest').mkdir()
    binaries = compat / 'build/0.83/installer'
    for row in rows:
        relative = row['relative_path'].replace('\\', '/')
        replacement = compat / 'candidate' / relative
        if relative in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe'):
            replacement = binaries / relative
        if replacement.exists():
            allowed = set(filter(None, row['allowed_before_sha256'].split(';')))
            allowed.add(row['sha256'])
            if relative.lower() in rules['menus']:
                allowed.add(rules['menus'][relative.lower()]['stock'])
            row['allowed_before_sha256'] = ';'.join(sorted(allowed))
            shutil.copy2(replacement, output / 'payload/direct' / relative)
            row['sha256'] = sha(replacement)
            row['bytes'] = str(replacement.stat().st_size)
    with (output / 'manifest/direct-files.tsv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)
    shutil.copy2(compat / 'data/HUDDISPLAY.xor.gz', output / 'payload/HUDDISPLAY.xor.gz')
    name = 'AMS2 한국어 패치 오픈베타 0.83.exe'
    shutil.copy2(binaries / 'AMS2-Korean-Patch-OB-0.83.exe', output / name)
    shutil.copy2(REPO / 'installer/0.83/Installer.exe.config', output / (name + '.config'))
    shutil.copy2(REPO / 'releases/0.83/RELEASE_NOTES.md', output / 'RELEASE_NOTES.md')
    manifest = {'schema': 'ams2-kr-open-beta-release-v083', 'version': '0.83',
                'package_id': 'AMS2-KR-BETA-0.83-PRETENDARD', 'creator': 'ENGIceBlasT',
                'reference_buildid': '25271800', 'baseline_tag': 'v0.82', 'direct_files': len(rows),
                'game_update_repair': 'verified Steam originals; font-only menu transformation; unknown archive/text structures stop launch',
                'compatibility_rules_sha256': sha(compat / 'data/rules.json'),
                'launcher_update_protocol': 1, 'ers_archive': rules['archives']['pakfiles/huddisplay.bff'],
                'validation_status': 'AWAITING_PACKAGE_TESTS', 'game_executed': False}
    (output / 'manifest/release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS:', output)


if __name__ == '__main__':
    main()
