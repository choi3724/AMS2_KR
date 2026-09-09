"""Exercise 0.8 install/restore and 0.7 upgrade in a new isolated game fixture."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
BUILD = WORK / 'build/0.8'
PACKAGE = WORK / 'releases/0.8/AMS2 한국어 패치 CB 0.8'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    fixture = BUILD / 'tests/install'
    fixture.mkdir(parents=True, exist_ok=False)
    game = fixture / 'steamapps/common/Automobilista 2'
    game.mkdir(parents=True)
    (fixture / 'steamapps/appmanifest_1066890.acf').write_text(
        '"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "24132163" }', encoding='utf-8')
    for name in ('AMS2.exe', 'AMS2AVX.exe'):
        (game / name).write_text('FIXTURE ONLY - NEVER EXECUTED', encoding='ascii')
    (game / 'Languages').mkdir()
    shutil.copy2(WORK / 'build/0.7/fixture/steamapps/common/Automobilista 2/Languages/Languages.bml', game / 'Languages/Languages.bml')
    rows = list(csv.DictReader((PACKAGE / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    originals = {}
    preserved_created = next(row['relative_path'] for row in rows if row['role'] == 'created' and row['relative_path'].lower().endswith('.bfont'))
    for row in rows:
        relative = row['relative_path']
        payload = PACKAGE / 'payload/direct' / relative
        assert payload.stat().st_size == int(row['bytes']) and sha(payload) == row['sha256']
        if row['role'] == 'modified' or relative == preserved_created:
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('0.8 fixture original: ' + relative, encoding='utf-8')
            originals[relative] = sha(target)
    old_backups = WORK / 'build/0.7/fixture/steamapps/common/Automobilista 2/Backup/AMS2-Korean/AMS2-KR-BETA-0.7-PRETENDARD/original'
    stock = next(path for path in old_backups.rglob('IGPHASEHUD.bff') if sha(path) == 'F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA')
    relative = 'Pakfiles/IGPHASEHUD.bff'
    (game / relative).parent.mkdir(parents=True)
    shutil.copy2(stock, game / relative)
    originals[relative] = sha(stock)
    cli = BUILD / 'installer/AMS2 Korean Patch TestCli.exe'

    def operation(label, action, package=PACKAGE, tool=cli, expected=None):
        result = subprocess.run([str(tool), '--game-dir', str(game), '--release-root', str(package), action, '--mock'], capture_output=True)
        (fixture / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, label + ' failed: inspect fixture log'
        assert ('STATUS=' + expected).encode() in result.stdout, label + ' unexpected status'

    def restored():
        for relative, before in originals.items():
            assert sha(game / relative) == before, 'restore differs: ' + relative
        for row in rows:
            if row['role'] == 'created' and row['relative_path'] not in originals:
                assert not (game / row['relative_path']).exists(), 'created file remains: ' + row['relative_path']

    for cycle in (1, 2):
        operation(str(cycle) + '-install', '--install', expected='INSTALLED_EXACT')
        operation(str(cycle) + '-check', '--check', expected='INSTALLED_EXACT')
        operation(str(cycle) + '-remove', '--uninstall', expected='RESTORED_EXACT')
        restored()
    operation('upgrade-prepare-07', '--install', BUILD / 'baseline/AMS2 한국어 패치 CB 0.7',
              WORK / 'build/0.7/installer/AMS2 Korean Patch TestCli.exe', 'INSTALLED_EXACT')
    operation('upgrade-08', '--install', expected='UPDATED_EXACT')
    operation('upgrade-check', '--check', expected='INSTALLED_EXACT')
    operation('upgrade-remove', '--uninstall', expected='RESTORED_EXACT')
    restored()
    report = {'status': 'PASS', 'install_restore_cycles': 2, 'upgrade_07_to_08': 'PASS',
              'restored_files': len(originals), 'removed_created_files': sum(row['role'] == 'created' and row['relative_path'] not in originals for row in rows),
              'game_executed': False}
    (fixture / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('PASS: install/check/restore twice, 0.7 to 0.8 upgrade, 96 originals exact, 354 created files removed. No game executed.')


if __name__ == '__main__':
    main()
