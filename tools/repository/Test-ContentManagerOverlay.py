"""Exercise compiled CM launch repair against an isolated copy of captured game files."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--cli', type=Path)
    parser.add_argument('--fault-cli', type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    paths = json.loads((work / 'fixture-paths.json').read_text())
    game, root = Path(paths['game']).resolve(), Path(paths['root']).resolve()
    assert game.is_relative_to(work) and root.is_relative_to(game)
    edits = json.loads(gzip.decompress((work / 'data/cm-overlays.json.gz').read_bytes()))['files']
    cli = args.cli or work / 'build/next/installer/AMS2 Korean Patch TestCli.exe'
    fault_cli = args.fault_cli or cli.with_name('CM Fault Test.exe')
    checks = []

    def run(name, expected=0, fault=False):
        result = subprocess.run([str(fault_cli if fault else cli), '--repair-game-update', str(game)], capture_output=True)
        (work / (name + '.log')).write_bytes(result.stdout + result.stderr)
        assert result.returncode == expected, (name, result.returncode, result.stderr)
        checks.append(name)

    def reset():
        for relative in edits:
            shutil.copy2(args.capture / relative, game / relative)

    def snapshot():
        def times(path):
            stat = path.stat()
            return stat.st_mtime_ns, getattr(stat, 'st_birthtime_ns', stat.st_ctime_ns)
        return {relative: (digest(game / relative), *times(game / relative)) for relative in edits}

    protected = [game / (relative + '.orig') for relative in edits]
    protected += [game / 'Mods/state.json', game / 'Mods/cm-preservation-sentinel']
    before = {str(p): digest(p) for p in protected}
    reset()
    times = snapshot()
    run('cm-reapply')
    assert all(digest(game / p) == e['after'] for p, e in edits.items())
    assert all(snapshot()[p][1:] == times[p][1:] for p in edits)
    checks.append('all-13-patched-with-original-timestamps')
    stable = snapshot()
    backups = sorted(p.name for p in (root / 'cm-overlay').iterdir())
    run('unchanged-launch')
    assert snapshot() == stable
    assert sorted(p.name for p in (root / 'cm-overlay').iterdir()) == backups
    run('unchanged-launch-again')
    reset()
    run('cm-regenerated-between-launches')
    reset()
    target = game / next(iter(edits))
    marker = b'unknown mod edit preserved'
    target.write_bytes(target.read_bytes() + marker)
    times_before = snapshot()[next(iter(edits))][1:]
    run('unrelated-shared-mod-preserved')
    assert target.read_bytes().endswith(marker)
    assert snapshot()[next(iter(edits))][1:] == times_before
    run('unrelated-shared-mod-idempotent')
    assert target.read_bytes().endswith(marker)
    reset()
    native = snapshot()
    (game / '.compat_fail_after_write').touch()
    try:
        run('injected-write-failure', 1, True)
    finally:
        (game / '.compat_fail_after_write').unlink()
    assert snapshot() == native
    assert not (root / 'cm-overlay/pending.json').exists()
    (game / '.compat_interrupt_after_write').touch()
    try:
        run('interrupted-process', 73, True)
    finally:
        (game / '.compat_interrupt_after_write').unlink()
    assert 'status\tGAME_UPDATE_PENDING' in (root / 'install-state.tsv').read_text(encoding='utf-8')
    run('next-launch-recovers-interruption')
    assert 'status\tGAME_UPDATE_PENDING' not in (root / 'install-state.tsv').read_text(encoding='utf-8')
    assert all(digest(game / p) == e['after'] for p, e in edits.items())
    assert before == {str(p): digest(p) for p in protected}
    rows = list(csv.DictReader((root / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    assert all(not (game / row['relative_path']).exists() or digest(game / row['relative_path']) == row['after_sha256'] for row in rows)
    checks.append('cm-backups-state-and-unrelated-mod-preserved')
    # CM installed after Korean: disabling bootfiles restores its Korean .orig.
    for relative in edits:
        shutil.copy2(game / (relative + '.orig'), game / relative)
    (game / 'Mods/state.json').rename(game / 'Mods/state.disabled.json')
    run('cm-disabled-restores-existing-korean')
    (game / 'Mods/state.disabled.json').rename(game / 'Mods/state.json')
    (work / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': checks, 'production_cli_sha256': digest(cli), 'fault_cli_sha256': digest(fault_cli)}, indent=2))
    print('PASS:', len(checks), 'checks; isolated fixture only')


if __name__ == '__main__':
    main()
