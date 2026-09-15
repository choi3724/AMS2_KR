"""Reproduce the old-record CM guard error and verify CM-free launch checks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--old-cli', type=Path, required=True)
    parser.add_argument('--new-cli', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    assert not output.exists() and not output.is_relative_to(repo)
    game = output / 'steamapps/common/Automobilista 2'
    shutil.copytree(args.fixture, game)
    shutil.copy2(args.fixture.parent.parent / 'appmanifest_1066890.acf', game.parent.parent / 'appmanifest_1066890.acf')
    for p in (game / 'Backup/AMS2-Korean').glob('*/install-state.tsv'):
        p.write_text(p.read_text(encoding='utf-8').replace(str(args.fixture.resolve()), str(game)), encoding='utf-8')
    state = game / 'Mods/state.json'
    absent = game / 'Mods/disabled-state.json'
    if not state.exists():
        absent.rename(state)
    def snapshot():
        return {str(p.relative_to(game)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in game.rglob('*') if p.is_file()}
    checks = []
    def run(label, cli, expected):
        before = snapshot()
        result = subprocess.run([str(cli), '--repair-game-update', str(game)], capture_output=True)
        (output / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert result.returncode == expected, (label, result.stdout, result.stderr)
        assert snapshot() == before, label + ': unexpected file write'
        checks.append(label)
    run('084-reproduces-intact-old-record-error', args.old_cli, 1)
    run('085-accepts-intact-old-record-with-cm', args.new_cli, 0)
    state.rename(absent)
    run('085-no-cm-installation-record', args.new_cli, 0)
    run('084-no-cm-installation-record-control', args.old_cli, 0)
    absent.rename(state)
    driver = game / 'text/drivers.tdb'
    driver.write_bytes(driver.read_bytes() + b'unknown-mod-change')
    run('085-unknown-edits-still-rejected', args.new_cli, 1)
    (output / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': checks,
        'new_cli_sha256': hashlib.sha256(args.new_cli.read_bytes()).hexdigest(), 'game_executed': False}, indent=2))
    print('PASS:', len(checks), 'CM version guard checks')


if __name__ == '__main__':
    main()
