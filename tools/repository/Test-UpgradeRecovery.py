"""Reproduce the interrupted 0.7 upgrade recovery report without touching an installed game."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile

WORK = Path(__file__).resolve().parents[3]
PACKAGE = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
PREVIOUS = WORK / 'releases/0.81/AMS2 한국어 패치 오픈베타 0.81'
ERS = WORK / 'build/0.81-ers-test2'
LAYOUTS = ['gui/display_lamborghini_sc63.bgui', 'gui/display_lamborghini_sc63_IMSA.bgui',
           'gui/display_porsche_963.bgui', 'gui/display_porsche_963_IMSA.bgui']
LAUNCHERS = ['AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe']
IG, HUD = 'Pakfiles/IGPHASEHUD.bff', 'Pakfiles/HUDDISPLAY.bff'
PATHS = LAUNCHERS + LAYOUTS + [IG, HUD]


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest().upper()


def read_table(data):
    return list(csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter='\t'))


def write_table(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostic', type=Path, required=True)
    p.add_argument('--tool', type=Path, required=True)
    args = p.parse_args()
    output = WORK / 'build/upgrade-recovery/tests' / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    with zipfile.ZipFile(args.diagnostic) as z:
        source = {r['relative_path'].replace('\\', '/'): r for r in read_table(z.read('files.tsv'))}
        invariants = z.read('invariants.tsv')
    assert set(PATHS) <= set(source)
    manifest = {r['relative_path']: r for r in read_table((PACKAGE / 'manifest/direct-files.tsv').read_bytes())}
    stock_ig = next(p for p in (WORK / 'build/0.7/fixture').rglob('IGPHASEHUD.bff')
                    if sha(p) == source[IG]['before_sha256'])

    def fixture(name, status='PREPARED', installed=False, recorded_only=False):
        root = output / name
        game = root / 'steamapps/common/Automobilista 2'
        game.mkdir(parents=True)
        (root / 'steamapps/appmanifest_1066890.acf').write_text(
            '"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "24132163" }', encoding='ascii')
        for n in ('AMS2.exe', 'AMS2AVX.exe'):
            (game / n).write_text('FIXTURE ONLY - NOT EXECUTED', encoding='ascii')
        package = root / 'package'
        direct = [dict(manifest[path]) for path in LAUNCHERS + LAYOUTS]
        if recorded_only:
            for row in direct:
                row['allowed_before_sha256'] = source[row['relative_path']]['before_sha256'] if row['role'] == 'modified' else ''
        write_table(package / 'manifest/direct-files.tsv', direct)
        state = game / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.82-PRETENDARD'
        entries = [dict(source[path]) for path in PATHS]
        write_table(state / 'files.tsv', entries)
        (state / 'install-state.tsv').write_text('status\t' + status + '\ninstalled_utc\t2026-09-09T13:04:43Z\ngame_dir\t' +
            str(game) + '\nbuildid\t24132163\nbackup_id\tfixture\npredecessor_package_id\tAMS2-KR-BETA-0.7-PRETENDARD\n', encoding='utf-8')
        (state / 'invariants.tsv').write_bytes(invariants)
        for relative in PATHS:
            live = game / relative
            live.parent.mkdir(parents=True, exist_ok=True)
            if relative in LAUNCHERS + LAYOUTS:
                origin = PACKAGE if installed or (recorded_only and relative in LAUNCHERS) else PREVIOUS
                shutil.copy2(origin / 'payload/direct' / relative, live)
            else:
                shutil.copy2(stock_ig if relative == IG else ERS / 'backup' / HUD, live)
            if source[relative]['action'] == 'modified':
                original = stock_ig if relative == IG else ERS / 'backup' / HUD if relative == HUD else ERS / 'archive-before' / relative
                backup = state / 'original/fixture' / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, backup)
                assert sha(backup) == source[relative]['before_sha256']
        return root, game, package

    def run(case, tool, success):
        root, game, package = case
        before = {path: sha(game / path) if (game / path).exists() else 'ABSENT' for path in PATHS}
        r = subprocess.run([str(tool), '--game-dir', str(game), '--release-root', str(package), '--uninstall', '--mock'], capture_output=True, timeout=30)
        (root / 'result.log').write_bytes(r.stdout + r.stderr)
        assert (r.returncode == 0) == success, str(root / 'result.log')
        for path in PATHS:
            actual = sha(game / path) if (game / path).exists() else 'ABSENT'
            assert actual == (source[path]['before_sha256'] if success else before[path]), path
        if not success and tool == args.tool:
            assert (game / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.82-PRETENDARD/events.log').exists()
        print('PASS:', root.name, flush=True)

    # Both BFFs are already stock, as in the report, so the shipped binary fails without modifying them.
    baseline = fixture('published-082-reproduction')
    run(baseline, WORK / 'build/0.82/installer/AMS2 Korean Patch TestCli.exe', False)
    assert b'display_porsche_963_IMSA.bgui' in (baseline[0] / 'result.log').read_bytes()
    run(fixture('prepared-previous-release-files'), args.tool, True)
    run(fixture('prepared-recorded-before-files', recorded_only=True), args.tool, True)
    partial = fixture('interrupted-removal', status='INSTALLED', installed=True)
    (partial[1] / LAUNCHERS[0]).unlink()
    shutil.copy2(ERS / 'archive-before' / LAYOUTS[-1], partial[1] / LAYOUTS[-1])
    run(partial, args.tool, True)
    for name, status, installed in [('prepared-manual-change', 'PREPARED', False), ('installed-manual-change', 'INSTALLED', True)]:
        bad = fixture(name, status=status, installed=installed)
        (bad[1] / LAUNCHERS[0]).write_bytes(b'USER FILE MUST BE PRESERVED')
        shutil.copy2(ERS / 'payload' / HUD, bad[1] / HUD)
        run(bad, args.tool, False)
    report = dict(status='PASS', fixture=str(output), published_failure_reproduced=True, recovery_cases=3,
                  manual_change_zero_writes_cases=2, game_executed=False)
    (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
