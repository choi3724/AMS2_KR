"""Assemble 0.83.1 with shared assets and four alternate menus for build 24132163."""
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compatibility', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.compatibility.resolve(), args.output.resolve()
    if output.exists() or output == REPO or REPO in output.parents:
        raise ValueError('Use a new output outside Git')
    baseline = WORK / 'releases/0.83/AMS2 한국어 패치 오픈베타 0.83'
    assert sha(baseline.parent / 'AMS2.0.83.zip') == 'E34DFFA3401BFB0AD30F891078DF31142CE291E92D6F57FF85DC481EF63E44A0'
    rows = list(csv.DictReader((baseline / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    assert len(rows) == 465
    for row in rows:
        assert sha(baseline / 'payload/direct' / row['relative_path']) == row['sha256']
    output.mkdir(parents=True)
    for folder in ('assets', 'runtime', 'payload'):
        shutil.copytree(baseline / folder, output / folder)
    (output / 'manifest').mkdir()
    binaries = source / 'build/0.83.1/installer'
    for row in rows:
        name = row['relative_path']
        if name in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe'):
            row['allowed_before_sha256'] = ';'.join(sorted(set(filter(None, row['allowed_before_sha256'].split(';'))) | {row['sha256']}))
            shutil.copy2(binaries / name, output / 'payload/direct' / name)
            row['sha256'], row['bytes'] = sha(binaries / name), str((binaries / name).stat().st_size)
    def table(name, entries):
        with (output / 'manifest' / name).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
            writer.writeheader(); writer.writerows(entries)
    table('direct-files.tsv', rows)
    legacy = json.loads((source / 'data/rules.json').read_text(encoding='utf-8'))['legacy']
    old_rows = [dict(row) for row in rows]
    for row in old_rows:
        relative = row['relative_path'].replace('\\', '/').lower()
        if relative in legacy['menus']:
            original = source / 'candidate-24132163' / relative
            target = output / 'payload/24132163' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            row['sha256'], row['bytes'] = sha(target), str(target.stat().st_size)
            # Never accept a newer-build menu as a stock backup on the older build.
            row['allowed_before_sha256'] = legacy['menus'][relative]['stock']
    table('direct-files-24132163.tsv', old_rows)
    shutil.copy2(source / 'data/HUDDISPLAY.24132163.xor.gz', output / 'payload/HUDDISPLAY.24132163.xor.gz')
    name = 'AMS2 한국어 패치 오픈베타 0.83.1.exe'
    shutil.copy2(binaries / 'AMS2-Korean-Patch-OB-0.83.1.exe', output / name)
    shutil.copy2(REPO / 'installer/0.83.1/Installer.exe.config', output / (name + '.config'))
    shutil.copy2(REPO / 'releases/0.83.1/RELEASE_NOTES.md', output / 'RELEASE_NOTES.md')
    metadata = {'version': '0.83.1', 'supported_builds': ['24132163', '25271800'], 'direct_files_per_build': 465,
                'compatibility_rules_sha256': sha(source / 'data/rules.json'), 'status': 'AWAITING_TESTS'}
    (output / 'manifest/release-manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print('PASS:', output)


if __name__ == '__main__':
    main()
