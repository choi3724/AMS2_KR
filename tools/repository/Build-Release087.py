"""Assemble the Open Beta 0.87 package from the verified 0.86 assets and adaptive runtime."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import release_regressions

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def write_table(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binaries', type=Path, required=True)
    parser.add_argument('--compatibility', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    binaries = args.binaries.resolve()
    compatibility = args.compatibility.resolve()
    output = args.output.resolve()
    if output.exists() or output == REPO or REPO in output.parents:
        raise ValueError('Use a new output outside Git')

    baseline = WORK / 'releases/0.86/AMS2 한국어 패치 오픈베타 0.86'
    package = output / 'AMS2 한국어 패치 오픈베타 0.87'
    shutil.copytree(baseline, package)

    for name in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe'):
        shutil.copy2(binaries / name, package / 'payload/direct' / name)
    shutil.copy2(binaries / 'runtime/AMS2.DynamicBffPatcher.exe', package / 'runtime/AMS2.DynamicBffPatcher.exe')
    old_installer = package / 'AMS2 한국어 패치 오픈베타 0.86.exe'
    old_config = package / 'AMS2 한국어 패치 오픈베타 0.86.exe.config'
    old_installer.unlink()
    old_config.unlink()
    installer = package / 'AMS2 한국어 패치 오픈베타 0.87.exe'
    shutil.copy2(binaries / 'AMS2-Korean-Patch-OB-0.87.exe', installer)
    shutil.copy2(binaries / 'AMS2-Korean-Patch-OB-0.87.exe.config', package / (installer.name + '.config'))
    shutil.copy2(REPO / 'releases/0.87/RELEASE_NOTES.md', package / 'RELEASE_NOTES.md')
    shutil.copy2(REPO / 'installer/0.87/README.md', package / 'README.md')
    shutil.copy2(REPO / 'installer/0.87/ownership-coverage.json', package / 'manifest/ownership-coverage.json')

    for table_name in ('direct-files.tsv', 'direct-files-24132163.tsv'):
        path = package / 'manifest' / table_name
        rows = list(csv.DictReader(path.open(encoding='utf-8-sig'), delimiter='\t'))
        for row in rows:
            if row['relative_path'] not in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe'):
                continue
            payload = package / 'payload/direct' / row['relative_path']
            previous = row['sha256'].upper()
            allowed = set(filter(None, row['allowed_before_sha256'].split(';')))
            allowed.add(previous)
            row['allowed_before_sha256'] = ';'.join(sorted(allowed))
            row['bytes'] = str(payload.stat().st_size)
            row['sha256'] = sha(payload)
        write_table(path, rows)

    rules = compatibility / 'data/rules.json'
    metadata = {
        'version': '0.87',
        'known_builds': ['24132163', '25271800'],
        'build_policy': 'advisory; actual file structure decides installation and launch',
        'direct_files_per_build': 465,
        'compatibility_rules_sha256': sha(rules),
        'ownership_catalog_sha256': sha(REPO / 'installer/0.87/ownership.tsv'),
        'status': 'AWAITING_TESTS',
    }
    manifest = package / 'manifest/release-manifest.json'
    manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    try:
        regression = release_regressions.verify(package, compatibility, '0.87', package / 'manifest/regression-report.json')
    except Exception:
        metadata['status'] = 'BLOCKED_REGRESSION'
        manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        raise
    metadata['status'] = 'REGRESSION_PASS_AWAITING_LIFECYCLE'
    metadata['regression_runtime_checks'] = len(regression['runtime'])
    manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS:', package)


if __name__ == '__main__':
    main()
