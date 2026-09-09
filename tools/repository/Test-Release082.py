"""Verify 0.82 install, upgrade, ERS test adoption, refusal and rollback in an isolated fixture."""
import csv
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
BUILD = WORK / 'build/0.82'
PACKAGE = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
ERS = WORK / 'build/0.81-ers-test2'
HUD = 'Pakfiles/HUDDISPLAY.bff'
IG = 'Pakfiles/IGPHASEHUD.bff'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    fixture = BUILD / 'tests' / ('install-' + uuid.uuid4().hex[:8])
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
    assert len(rows) == 465
    originals = {}
    preserved = next(row['relative_path'] for row in rows if row['role'] == 'created' and row['relative_path'].lower().endswith('.bfont'))
    for row in rows:
        relative = row['relative_path']
        payload = PACKAGE / 'payload/direct' / relative
        assert payload.stat().st_size == int(row['bytes']) and sha(payload) == row['sha256']
        if row['role'] == 'modified' or relative == preserved:
            target = game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative.startswith('gui/display_formula_') and (ERS / 'backup' / relative).is_file():
                shutil.copy2(ERS / 'backup' / relative, target)
            else:
                target.write_text('0.82 fixture original: ' + relative, encoding='utf-8')
            originals[relative] = sha(target)
    old_backups = WORK / 'build/0.7/fixture/steamapps/common/Automobilista 2/Backup/AMS2-Korean/AMS2-KR-BETA-0.7-PRETENDARD/original'
    stock_ig = next(path for path in old_backups.rglob('IGPHASEHUD.bff') if sha(path) == 'F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA')
    (game / 'Pakfiles').mkdir()
    for relative, source in ((IG, stock_ig), (HUD, ERS / 'backup' / HUD)):
        shutil.copy2(source, game / relative)
        originals[relative] = sha(source)
    cli = BUILD / 'installer/AMS2 Korean Patch TestCli.exe'
    old_package = WORK / 'releases/0.81' / PACKAGE.name.replace('0.82', '0.81')
    old_cli = WORK / 'build/0.81/installer/AMS2 Korean Patch TestCli.exe'

    def operation(label, action, package=PACKAGE, tool=cli, expected='INSTALLED_EXACT', success=True):
        result = subprocess.run([str(tool), '--game-dir', str(game), '--release-root', str(package), action, '--mock'], capture_output=True, timeout=180)
        (fixture / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert (result.returncode == 0) == success, label + ' failed: inspect fixture log'
        assert ('STATUS=' + expected).encode() in result.stdout, label + ' unexpected status'
        print('PASS:', label, flush=True)

    def restored():
        for relative, before in originals.items():
            assert sha(game / relative) == before, 'restore differs: ' + relative
        for row in rows:
            if row['role'] == 'created' and row['relative_path'] not in originals:
                assert not (game / row['relative_path']).exists(), 'created file remains: ' + row['relative_path']

    def installed():
        for row in rows:
            assert sha(game / row['relative_path']) == row['sha256']
        assert sha(game / HUD) == 'F8A840F569D256DB4E1A67D73C5B2BB9CC4927E18109178B67356479BDCE81E5'

    for cycle in (1, 2):
        operation(str(cycle) + '-install', '--install')
        installed()
        operation(str(cycle) + '-repeat-install', '--install')
        operation(str(cycle) + '-check', '--check')
        operation(str(cycle) + '-remove', '--uninstall', expected='RESTORED_EXACT')
        restored()
    operation('upgrade-prepare-081', '--install', old_package, old_cli)
    operation('upgrade-081', '--install', expected='UPDATED_EXACT')
    installed()
    operation('upgrade-remove', '--uninstall', expected='RESTORED_EXACT')
    restored()
    operation('test-adoption-prepare-081', '--install', old_package, old_cli)
    for entry in json.loads((ERS / 'manifest.json').read_text(encoding='utf-8'))['files']:
        target = game / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ERS / 'payload' / entry['path'], target)
    operation('test-adoption-install', '--install')
    installed()
    operation('test-adoption-remove', '--uninstall', expected='RESTORED_EXACT')
    restored()

    # Unknown/missing game archives and malformed package deltas must fail before any game asset changes.
    original_hud = (game / HUD).read_bytes()
    changed = bytearray(original_hud)
    changed[-1] ^= 1
    (game / HUD).write_bytes(changed)
    operation('unknown-archive-refused', '--install', expected='INSTALL_FAILED', success=False)
    assert (game / HUD).read_bytes() == changed
    (game / HUD).write_bytes(original_hud)
    restored()
    (game / HUD).unlink()
    operation('missing-archive-refused', '--install', expected='INSTALL_FAILED', success=False)
    assert not (game / HUD).exists()
    (game / HUD).write_bytes(original_hud)
    restored()
    bad_package = fixture / 'damaged-package'
    shutil.copytree(PACKAGE, bad_package)
    for label, damage in (('corrupt-delta', b'not gzip'), ('truncated-delta', (PACKAGE / 'payload/HUDDISPLAY.xor.gz').read_bytes()[:100])):
        (bad_package / 'payload/HUDDISPLAY.xor.gz').write_bytes(damage)
        operation(label + '-refused', '--install', package=bad_package, expected='INSTALL_FAILED', success=False)
        restored()

    # Hold the final archive against replacement: all earlier writes must roll back exactly.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(game / HUD), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        operation('locked-final-archive-rollback', '--install', expected='INSTALL_FAILED', success=False)
    finally:
        kernel.CloseHandle(handle)
    restored()
    state = game / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.82-PRETENDARD/install-state.tsv'
    assert 'status\tROLLED_BACK' in state.read_text(encoding='utf-8')
    operation('after-rollback-install', '--install')
    installed()
    # Removal must preserve a changed, user-owned file instead of deleting it.
    font = game / 'gui/kr081_ers_value_60.bfont'
    font_bytes = font.read_bytes()
    font.write_bytes(font_bytes + b'user-change')
    operation('modified-font-removal-refused', '--uninstall', expected='RESTORE_FAILED', success=False)
    assert font.read_bytes() == font_bytes + b'user-change'
    font.write_bytes(font_bytes)
    operation('final-remove', '--uninstall', expected='RESTORED_EXACT')
    restored()
    report = dict(status='PASS', install_restore_cycles=2, upgrade_081_to_082='PASS', ers_test_adoption='PASS',
                  malformed_input_refused=True, automatic_rollback='PASS', manual_font_change_preserved=True,
                  restored_files=len(originals), removed_created_files=sum(row['role'] == 'created' and row['relative_path'] not in originals for row in rows),
                  game_executed=False)
    (fixture / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (BUILD / 'tests/install-result.json').write_text(json.dumps(dict(report, fixture=str(fixture)), indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
