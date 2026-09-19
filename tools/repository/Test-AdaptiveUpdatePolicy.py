"""Exercise the 0.86 build-advisory repair policy in isolated game copies."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True, help='read-only installed game source')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--cli', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', default='0.86')
    args = parser.parse_args()
    source, package, cli, output = map(Path.resolve, (args.game, args.package, args.cli, args.output))
    repo = Path(__file__).resolve().parents[2]
    if output.exists() or output == repo or repo in output.parents:
        raise ValueError('Use a new output outside Git')
    output.mkdir(parents=True)
    active = source / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.85-PRETENDARD'
    head = dict(line.split('\t', 1) for line in (active / 'install-state.tsv').read_text(encoding='utf-8').splitlines())
    rows = list(csv.DictReader((active / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    backup = active / 'original' / head['backup_id']
    checks = []

    def manifest(root, build):
        acf = root / 'steamapps/appmanifest_1066890.acf'
        acf.parent.mkdir(parents=True, exist_ok=True)
        acf.write_text('"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "' + build + '" }', encoding='utf-8')

    def inert(game):
        for name in ('AMS2.exe', 'AMS2AVX.exe'):
            (game / name).write_text('INERT TEST FIXTURE - NEVER EXECUTE', encoding='ascii')
        for relative in ('Languages/Languages.bml', 'Pakfiles/Dir/TEXT.bff'):
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)

    def run(label, game, extra, success=True):
        result = subprocess.run([str(cli), *extra], capture_output=True, timeout=420)
        (output / (label + '.log')).write_bytes(result.stdout + result.stderr)
        if (result.returncode == 0) != success:
            raise AssertionError(label + ': ' + (result.stdout + result.stderr).decode('utf-8', errors='replace')[-4000:])
        checks.append(label)
        return (result.stdout + result.stderr).decode('utf-8', errors='replace')

    # Existing 0.85 install after Steam replaced many files.
    root = output / 'existing'
    game = root / 'steamapps/common/Automobilista 2'
    game.mkdir(parents=True)
    for row in rows:
        src, target = source / row['relative_path'], game / row['relative_path']
        if row['relative_path'] in ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe') and sha(src) != row['after_sha256']:
            src = repo.parent / 'releases/0.85/AMS2 한국어 패치 오픈베타 0.85/payload/direct' / row['relative_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    inert(game)
    shutil.copytree(active, game / active.relative_to(source), ignore=shutil.ignore_patterns('game-updates', 'logs', 'events.log'))
    state = game / active.relative_to(source)
    # The source may have been superseded by a later real-PC validation.  The
    # fixture intentionally exercises it as the active predecessor state.
    state_head = dict(head, status='INSTALLED', game_dir=str(game))
    (state / 'install-state.tsv').write_text(''.join(k + '\t' + v + '\n' for k, v in state_head.items()), encoding='utf-8')
    manifest(root, '25391793')
    run('updated-existing-reapply', game, ['--repair-game-update', str(game)])
    repaired_rows = list(csv.DictReader((state / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    assert all((game / row['relative_path']).is_file() and sha(game / row['relative_path']) == row['after_sha256'] for row in repaired_rows)
    checks.append('all-managed-files-match-state')
    before = {row['relative_path']: sha(game / row['relative_path']) for row in repaired_rows}
    run('idempotent-second-check', game, ['--repair-game-update', str(game)])
    assert before == {row['relative_path']: sha(game / row['relative_path']) for row in repaired_rows}

    manifest(root, '99999999')
    run('build-number-only-and-no-depot', game, ['--repair-game-update', str(game)])
    assert before == {row['relative_path']: sha(game / row['relative_path']) for row in repaired_rows}

    menus = [row for row in repaired_rows if row['relative_path'].lower().endswith('.bgui') and row['action'] == 'modified'][:2]
    for row in menus:
        shutil.copy2(state / 'original' / state_head['backup_id'] / row['relative_path'], game / row['relative_path'])
    run('multiple-files-mixed-state', game, ['--repair-game-update', str(game)])
    assert all(sha(game / row['relative_path']) == next(x['after_sha256'] for x in csv.DictReader((state / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t') if x['relative_path'] == row['relative_path']) for row in menus)

    optional = game / 'Pakfiles/HUDDISPLAY.bff'
    optional.write_bytes(b'unsupported optional archive')
    text = run('optional-failure-allows-core', game, ['--repair-game-update', str(game)])
    assert 'COMPATIBILITY=PASS' in text
    assert next(r for r in csv.DictReader((state / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t') if r['relative_path'].lower() == 'pakfiles\\huddisplay.bff')['after_sha256'] == sha(optional)

    for row in menus:
        (game / row['relative_path']).write_bytes(b'broken required bgui ' + row['relative_path'].encode())
    snapshot = {p.relative_to(game).as_posix(): sha(p) for p in game.rglob('*') if p.is_file() and 'game-updates' not in p.parts}
    text = run('aggregate-required-failures-zero-write', game, ['--repair-game-update', str(game)], False)
    assert all(row['relative_path'].replace('\\', '/').lower() in text.lower() for row in menus)
    assert snapshot == {p.relative_to(game).as_posix(): sha(p) for p in game.rglob('*') if p.is_file() and 'game-updates' not in p.parts}

    # Unknown-build first install: stock modified files, no Korean-created files.
    fresh_root = output / 'fresh'
    fresh = fresh_root / 'steamapps/common/Automobilista 2'
    fresh.mkdir(parents=True)
    manifest_rows = list(csv.DictReader((package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    for row in manifest_rows:
        if row['role'] != 'modified':
            continue
        src = backup / row['relative_path']
        target = fresh / row['relative_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    for relative in ('Pakfiles/IGPHASEHUD.bff', 'Pakfiles/HUDDISPLAY.bff'):
        target = fresh / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    inert(fresh)
    manifest(fresh_root, '99999998')
    text = run('unknown-build-first-install', fresh, ['--game-dir', str(fresh), '--release-root', str(package), '--install', '--mock'])
    assert 'STATUS=INSTALLED_' in text
    run('unknown-build-installed-check', fresh, ['--game-dir', str(fresh), '--release-root', str(package), '--check', '--mock'])
    run('unknown-build-uninstall', fresh, ['--game-dir', str(fresh), '--release-root', str(package), '--uninstall', '--mock'])

    report = {'status': 'PASS', 'checks': checks, 'game_executed': False, 'source_game_modified': False,
              'fixture': str(output), 'cli_sha256': sha(cli), 'package_installer_sha256': sha(package / ('AMS2 한국어 패치 오픈베타 '+args.version+'.exe'))}
    (output / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
