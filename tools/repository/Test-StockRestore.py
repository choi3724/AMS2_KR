"""Exercise the complete standalone recovery payload on disposable game directories."""
import csv
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import zipfile

WORK = Path(__file__).resolve().parents[3]
BUILD = WORK / 'build/full-uninstall'
TOOL = BUILD / 'StockRestoreCheck.exe'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    output = BUILD / 'tests' / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    with zipfile.ZipFile(BUILD / 'stock.zip') as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read('stock-files.tsv').decode('utf-8')), delimiter='\t'))
    checks = []

    def shortcut_folder(game):
        return game.parent.parent.parent / 'shortcuts'

    def shortcut_snapshot(game):
        return {str(p): sha(p) for p in shortcut_folder(game).glob('*.lnk')}

    def fixture(name, missing=False, base=output):
        game = base / name / 'steamapps/common/Automobilista 2'
        game.mkdir(parents=True)
        (game.parent.parent / 'appmanifest_1066890.acf').write_text('"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "24132163" }', encoding='ascii')
        for rel in ['AMS2.exe', 'AMS2AVX.exe', 'Vehicles/preserve.bin', 'Replays/preserve.rpl', 'gui/unrelated-mod.bgui', 'Backup/old-original/preserve.bin']:
            p = game / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'UNRELATED DATA MUST NOT CHANGE: ' + rel.encode())
        p = game / 'Languages/Languages.bml'
        p.parent.mkdir(parents=True)
        shutil.copy2(WORK / 'build/0.7/fixture/steamapps/common/Automobilista 2/Languages/Languages.bml', p)
        if not missing:
            for row in rows:
                p = game / row['relative_path']
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b'UNKNOWN MIXED/DAMAGED PATCH DATA: ' + row['relative_path'].encode())
            for version in ['0.7', '0.82']:
                p = game / f'Backup/AMS2-Korean/AMS2-KR-BETA-{version}-PRETENDARD/install-state.tsv'
                p.parent.mkdir(parents=True)
                p.write_bytes(b'CORRUPTED UNREADABLE INSTALLATION STATE')
                (p.parent / 'files.tsv').write_bytes(b'ORIGINAL BACKUP INDEX TO PRESERVE')
            os.chmod(game / rows[0]['relative_path'], 0o444)
            links = shortcut_folder(game)
            links.mkdir()
            definitions = [('renamed-normal.lnk', game / 'AMS2 Korean Launcher.exe'),
                           ('vr.lnk', game / 'AMS2 Korean VR Launcher.exe'),
                           ('unrelated.lnk', game / 'AMS2.exe')]
            script = "$shell = New-Object -ComObject WScript.Shell\n"
            for name, target in definitions:
                script += "$link = $shell.CreateShortcut('" + str(links / name).replace("'", "''") + "')\n$link.TargetPath = '" + str(target).replace("'", "''") + "'\n$link.Save()\n"
            subprocess.run(['powershell', '-NoProfile', '-Command', script], check=True, capture_output=True)
            # Even a correctly hashed record cannot authorize deleting an unrelated shortcut.
            (p.parent / 'shortcuts.tsv').write_text('kind\tpath\tsha256\nDESKTOP\t' + str(links / 'unrelated.lnk') + '\t' + sha(links / 'unrelated.lnk') + '\nBROKEN\tX:\\bad\0path.lnk\tINVALID\n', encoding='utf-8')
        return game

    def snapshot(game):
        return {str(p.relative_to(game)): (sha(p), p.stat().st_file_attributes) for p in game.rglob('*')
                if p.is_file() and 'AMS2-Korean-StockRestore' not in p.parts}

    def recover(game, label, success=True, fail_after=None, tool=TOOL):
        env = dict(os.environ)
        env['AMS2_STOCK_TEST_SHORTCUTS'] = str(shortcut_folder(game))
        if fail_after is not None:
            env['AMS2_STOCK_TEST_FAIL_AFTER'] = str(fail_after)
        result = subprocess.run([str(tool), '--restore', str(game)], capture_output=True, env=env, timeout=180)
        (output / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert (result.returncode == 0) == success, (label, result.stdout.decode('utf-8-sig', errors='replace'), result.stderr.decode('utf-8-sig', errors='replace'))
        checks.append(label)
        print('PASS:', label, flush=True)
        return result

    def verify(game):
        for row in rows:
            p = game / row['relative_path']
            if row['action'] == 'restore':
                assert p.stat().st_size == int(row['bytes']) and sha(p) == row['sha256'], row
            else:
                assert not p.exists(), row
        assert not list((game / 'Backup/AMS2-Korean').glob('AMS2-KR-BETA-*/install-state.tsv'))
        assert not list((game / 'Backup/AMS2-Korean').glob('AMS2-KR-BETA-*/shortcuts.tsv'))
        for name in ['renamed-normal.lnk', 'vr.lnk']:
            assert not (shortcut_folder(game) / name).exists()

    fonts = fixture('font-diagnostic', missing=True)
    baseline = list(csv.DictReader((BUILD / 'font-baseline.tsv').open(encoding='utf-8'), delimiter='\t'))
    intact = next(row for row in baseline if row['relative_path'].endswith('.bfont'))
    changed = next(row for row in baseline if row['relative_path'].endswith('.bfont') and row != intact)
    original_game = Path('E:/SteamLibrary/steamapps/common/Automobilista 2')
    for row in [intact, changed]:
        target = fonts / row['relative_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original_game / row['relative_path'], target)
    (fonts / changed['relative_path']).write_bytes(b'CHANGED FONT DESCRIPTOR')
    (fonts / 'gui/font_phoenix_body_regular.dds').write_bytes(b'EXTRA FONT TEXTURE FOR DIAGNOSIS')
    before = snapshot(fonts)
    diagnostic = output / 'font-diagnostic.zip'
    result = subprocess.run([str(TOOL), '--font-audit', str(fonts), str(diagnostic)], capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(fonts) == before
    with zipfile.ZipFile(diagnostic) as z:
        report = {r['relative_path']: r for r in csv.DictReader(io.StringIO(z.read('default-fonts.tsv').decode('utf-8')), delimiter='\t')}
        assert report[intact['relative_path']]['status'] == 'STOCK'
        assert report[changed['relative_path']]['status'] == 'DIFFERENT'
        textures = list(csv.DictReader(io.StringIO(z.read('loose-font-textures.tsv').decode('utf-8')), delimiter='\t'))
        assert textures[0]['relative_path'] == 'gui/font_phoenix_body_regular.dds'
        assert textures[0]['sha256'] == sha(fonts / 'gui/font_phoenix_body_regular.dds')
        assert 'read_only=true' in z.read('summary.txt').decode('utf-8')
        assert sum(r['status'] == 'MISSING' for r in report.values()) == len(baseline) - 2
    result = subprocess.run([str(TOOL), '--font-audit', str(fonts), str(fonts / 'must-not-write.zip')], capture_output=True, timeout=60)
    assert result.returncode != 0 and snapshot(fonts) == before
    checks.append('font-diagnostic-stock-texture-change-missing-and-zero-game-writes')
    print('PASS:', checks[-1], flush=True)

    if '--font-audit-only' in sys.argv:
        report = {'status': 'PASS', 'checks': checks, 'game_files_unchanged': True, 'diagnostic_exe_sha256': sha(BUILD / 'AMS2 기본 폰트 진단.exe')}
        (output / 'font-audit-result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        (BUILD / 'font-audit-result-path.txt').write_text(str(output / 'font-audit-result.json'), encoding='utf-8')
        print('PASS: font audit only; evidence:', output, flush=True)
        return

    game = fixture('mixed')
    before = snapshot(game)
    links_before = shortcut_snapshot(game)
    result = recover(game, 'unknown-files-and-corrupted-records')
    verify(game)
    backup = Path(next(l[7:] for l in result.stdout.decode('utf-8-sig').splitlines() if l.startswith('BACKUP=')))
    table = list(csv.DictReader((backup / 'before.tsv').open(encoding='utf-8'), delimiter='\t'))
    assert len(table) == len(rows) + 7
    expected = {str(game / rel).lower(): info[0] for rel, info in before.items()}
    expected.update({p.lower(): value for p, value in links_before.items()})
    for row in table:
        p = backup / row['backup_file']
        assert sha(p) == expected[row['target_path'].lower()] == row['before_sha256']
    managed = {str(Path(r['relative_path'])).lower() for r in table}
    assert all(snapshot(game)[rel][0] == value[0] for rel, value in before.items() if rel.lower() not in managed)
    assert shortcut_snapshot(game) == {str(shortcut_folder(game) / 'unrelated.lnk'): links_before[str(shortcut_folder(game) / 'unrelated.lnk')]}
    recover(game, 'repeat-recovery')
    verify(game)

    missing = fixture('missing', missing=True)
    recover(missing, 'all-patch-targets-and-records-missing')
    verify(missing)

    rollback = fixture('rollback')
    before = snapshot(rollback)
    links_before = shortcut_snapshot(rollback)
    recover(rollback, 'failure-after-files-records-and-shortcuts-rolls-back', success=False, fail_after=len(rows) + 5)
    assert snapshot(rollback) == before, 'Rollback must preserve every byte and attribute, including installation records'
    assert shortcut_snapshot(rollback) == links_before, 'Rollback must also restore the removed shortcuts'

    locked = fixture('locked')
    before = snapshot(locked)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(str(locked / 'gui/display_porsche_963_IMSA.bgui'), 0x80000000, 1, None, 3, 0, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        recover(locked, 'locked-target-refuses-before-mutation', success=False)
    finally:
        kernel.CloseHandle(handle)
    assert snapshot(locked) == before

    corrupt = output / 'CorruptPayload.exe'
    exe, payload = TOOL.read_bytes(), (BUILD / 'stock.zip').read_bytes()
    offset = exe.index(payload)
    damaged = bytearray(exe)
    damaged[offset + 40] ^= 1
    corrupt.write_bytes(damaged)
    before = snapshot(locked)
    recover(locked, 'corrupt-embedded-stock-refused', success=False, tool=corrupt)
    assert snapshot(locked) == before

    other_build = fixture('different-build', missing=True)
    acf = other_build.parent.parent / 'appmanifest_1066890.acf'
    acf.write_text(acf.read_text().replace('24132163', '99999999'))
    before = snapshot(other_build)
    recover(other_build, 'different-game-build-refused', success=False)
    assert snapshot(other_build) == before

    linked = fixture('linked-directory', missing=True)
    outside = output / 'outside-game'
    outside.mkdir()
    sentinel = outside / 'HUDDISPLAY.bff'
    sentinel.write_bytes(b'FILE OUTSIDE SELECTED GAME MUST NOT CHANGE')
    link = linked / 'Pakfiles'
    assert link.resolve().is_relative_to(WORK) and outside.resolve().is_relative_to(WORK)
    ps = "New-Item -ItemType Junction -Path '" + str(link).replace("'", "''") + "' -Target '" + str(outside).replace("'", "''") + "' -ErrorAction Stop | Out-Null"
    subprocess.run(['powershell', '-NoProfile', '-Command', ps], check=True, capture_output=True)
    before = sha(sentinel)
    recover(linked, 'directory-junction-refused', success=False)
    assert sha(sentinel) == before

    # Use the actual shipped installer code/payload, then recover independently of its state.
    # Their legacy path limit requires a shorter fixture root than the new tool's stress cases.
    published = fixture('', missing=True, base=WORK / 'build' / ('sr-' + output.name))
    recover(published, 'stock-before-published-installers')
    for version, folder in [('0.8', 'AMS2 한국어 패치 CB 0.8'), ('0.81', 'AMS2 한국어 패치 오픈베타 0.81'), ('0.82', 'AMS2 한국어 패치 오픈베타 0.82')]:
        package = WORK / 'releases' / version / folder
        cli = WORK / 'build' / version / 'installer/AMS2 Korean Patch TestCli.exe'
        result = subprocess.run([str(cli), '--game-dir', str(published), '--release-root', str(package), '--install', '--mock'], capture_output=True, timeout=180)
        label = 'published-' + version + '-install-after-stock-or-upgrade'
        (output / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, label
        manifest = list(csv.DictReader((package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
        for row in manifest:
            assert sha(published / row['relative_path']) == row['sha256'], row['relative_path']
        checks.append(label)
        print('PASS:', label, flush=True)
    recover(published, 'recover-real-082-installation')
    verify(published)
    result = subprocess.run([str(cli), '--game-dir', str(published), '--release-root', str(package), '--install', '--mock'], capture_output=True, timeout=180)
    (output / 'reinstall-after-complete-removal.log').write_bytes(result.stdout + result.stderr)
    assert result.returncode == 0, 'Reinstall after complete removal failed'
    for row in manifest:
        assert sha(published / row['relative_path']) == row['sha256'], row['relative_path']
    checks.append('reinstall-after-complete-removal')
    recover(published, 'complete-removal-after-reinstall')
    verify(published)
    (output / 'result.json').write_text(json.dumps({'status': 'PASS', 'checks': checks, 'restore_count': sum(r['action'] == 'restore' for r in rows), 'remove_count': sum(r['action'] == 'remove' for r in rows), 'live_game_modified': False, 'published_fixture': str(published), 'exe_sha256': sha(BUILD / 'AMS2 한국어 패치 완전 제거.exe')}, indent=2) + '\n', encoding='utf-8')
    (BUILD / 'test-result-path.txt').write_text(str(output / 'result.json'), encoding='utf-8')
    print('PASS: all checks; evidence:', output, flush=True)


if __name__ == '__main__':
    main()
