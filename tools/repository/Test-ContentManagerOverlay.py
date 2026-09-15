"""Exercise compiled CM launch repair against an isolated copy of captured game files."""
import argparse
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
        return {relative: (digest(game / relative), (game / relative).stat().st_mtime_ns,
                           (game / relative).stat().st_birthtime_ns) for relative in edits}

    protected = [game / (relative + '.orig') for relative in edits]
    protected += [game / 'Mods/state.json', game / 'Mods/cm-preservation-sentinel', root / 'files.tsv', root / 'install-state.tsv']
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
    target.write_bytes(target.read_bytes() + b'unknown mod edit')
    corrupt = snapshot()
    run('unknown-shared-mod-rejected', 1)
    assert snapshot() == corrupt
    reset()
    native = snapshot()
    (game / '.cm_fail_after_write').touch()
    try:
        run('injected-write-failure', 1, True)
    finally:
        (game / '.cm_fail_after_write').unlink()
    assert snapshot() == native
    assert not (root / 'cm-overlay/pending.json').exists()
    (game / '.cm_interrupt_after_write').touch()
    try:
        run('interrupted-process', 74, True)
    finally:
        (game / '.cm_interrupt_after_write').unlink()
    assert (root / 'cm-overlay/pending.json').exists()
    run('next-launch-recovers-interruption')
    assert not (root / 'cm-overlay/pending.json').exists()
    assert all(digest(game / p) == e['after'] for p, e in edits.items())
    assert before == {str(p): digest(p) for p in protected}
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
