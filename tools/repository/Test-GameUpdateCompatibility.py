"""Exercise update repair and 0.83 install/restore using copied assets and inert game executables."""
import argparse
import csv
import ctypes
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import uuid

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
STATE = 'Backup/AMS2-Korean/AMS2-KR-BETA-0.82-PRETENDARD'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def varint(n):
    result = bytearray()
    while n >= 128:
        result.append((n & 127) | 128); n >>= 7
    result.append(n)
    return bytes(result)


def message(field, value):
    if isinstance(value, int):
        return varint(field << 3) + varint(value)
    return varint((field << 3) | 2) + varint(len(value)) + value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', type=Path, required=True, help='read-only source game')
    p.add_argument('--compatibility', type=Path, required=True)
    p.add_argument('--failure-cli', type=Path)
    args = p.parse_args()
    source, compat = args.game.resolve(), args.compatibility.resolve()
    root = WORK / 'build/qa083' / uuid.uuid4().hex[:8]
    root.mkdir(parents=True)
    game = root / 'steamapps/common/Automobilista 2'
    game.mkdir(parents=True)
    package = compat / 'package/AMS2 한국어 패치 오픈베타 0.83'
    cli = compat / 'build/0.83/installer/AMS2 Korean Patch TestCli.exe'
    rules = json.loads((compat / 'data/rules.json').read_text(encoding='utf-8'))
    rows = list(csv.DictReader((source / STATE / 'files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    state_head = dict(line.split('\t', 1) for line in (source / STATE / 'install-state.tsv').read_text(encoding='utf-8').splitlines())
    state_head['game_dir'] = str(game)
    for row in rows:
        relative = row['relative_path'].replace('\\', '/')
        target = game / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)
    for relative in ('Languages/Languages.bml', 'Pakfiles/Dir/TEXT.bff'):
        (game / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, game / relative)
    for name in ('AMS2.exe', 'AMS2AVX.exe'):
        (game / name).write_text('INERT FIXTURE - NEVER EXECUTE', encoding='ascii')
    shutil.copytree(source / STATE, game / STATE, ignore=shutil.ignore_patterns('transaction', 'logs', 'shortcuts.tsv', 'game-updates'))
    (game / STATE / 'install-state.tsv').write_text(''.join(k + '\t' + v + '\n' for k, v in state_head.items()), encoding='utf-8')
    acf = root / 'steamapps/appmanifest_1066890.acf'

    def manifest(build='25271800', stock=None):
        acf.write_text('"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "' + build + '" "InstalledDepots" { "1066891" { "manifest" "1000000000001" } } }', encoding='utf-8')
        if stock:
            relative, content = stock
            entry = message(1, relative.encode()) + message(2, len(content)) + message(5, hashlib.sha1(content).digest())
            payload = message(1, entry)
            depot = root / 'steamapps/depotcache/1066891_1000000000001.manifest'
            depot.parent.mkdir(exist_ok=True)
            depot.write_bytes(struct.pack('<II', 0x71F617D0, len(payload)) + payload)

    def repair(label, success=True, tool=cli):
        result = subprocess.run([str(tool), '--repair-game-update', str(game)], capture_output=True, timeout=120)
        (root / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert (result.returncode == 0) == success, label + ': ' + (result.stdout + result.stderr).decode('utf-8', errors='replace')[-2000:]
        checks.append(label)

    def assets():
        return {str(p.relative_to(game)): sha(p) for p in game.rglob('*') if p.is_file() and 'game-updates' not in p.parts and p.name != 'events.log' and 'logs' not in p.parts}

    def steam_replace():
        for relative in list(rules['menus']) + list(rules['archives']):
            shutil.copy2(compat / 'original' / relative, game / relative)

    checks = []
    manifest()
    repair('old-082-after-steam-update')
    for relative in list(rules['menus']) + list(rules['archives']):
        assert sha(game / relative) == sha(compat / 'candidate' / relative), relative
        assert sha(game / STATE / 'original' / state_head['backup_id'] / relative) == sha(compat / 'original' / relative)
    before = assets()
    repair('idempotent-second-launch')
    assert assets() == before
    steam_replace(); manifest('25271801')
    repair('repeat-steam-overwrite')
    before = assets()
    repair('repeat-idempotence')
    assert assets() == before

    # A future verified Steam menu changes geometry: retain it while remapping fonts.
    relative = 'gui/menu_dialogbox_gamewide_1_6.bgui'
    content = bytearray((compat / 'original' / relative).read_bytes())
    marker = content.index(b'\x04Text\x52\x2B\x5D\x5F') - 4
    struct.pack_into('<f', content, marker + 17, struct.unpack_from('<f', content, marker + 17)[0] + 1)
    (game / relative).write_bytes(content); manifest('25271802', (relative, content))
    repair('future-verified-menu-font-only')
    assert struct.unpack_from('<f', (game / relative).read_bytes(), marker + 17)[0] == struct.unpack_from('<f', content, marker + 17)[0]

    # Unknown archive, missing font, and a malformed verified menu all stop before mutation.
    archive = game / 'Pakfiles/HUDDISPLAY.bff'; valid = archive.read_bytes()
    archive.write_bytes(valid[:-1] + bytes([valid[-1] ^ 1])); before = assets()
    repair('unknown-archive-zero-write', False); assert assets() == before
    archive.write_bytes(valid)
    font = game / 'gui/kr081_ers_value_60.bfont'; valid = font.read_bytes(); font.unlink(); before = assets()
    repair('missing-font-zero-write', False); assert assets() == before; font.write_bytes(valid)
    broken = bytearray(content); struct.pack_into('<I', broken, 4, 0xffffffff)
    valid = (game / relative).read_bytes(); (game / relative).write_bytes(broken)
    manifest('25271803', (relative, broken)); before = assets()
    repair('changed-structure-zero-write', False); assert assets() == before
    (game / relative).write_bytes(valid); manifest('25271802')

    unknown = bytes(content).replace(b'ams2_font_heading_bold.bfont', b'ams2_font_heading_xxxx.bfont', 1)
    assert unknown != bytes(content)
    (game / relative).write_bytes(unknown); manifest('25271803', (relative, unknown)); before = assets()
    repair('unknown-font-zero-write', False); assert assets() == before
    (game / relative).write_bytes(valid); manifest('25271802')
    table = game / STATE / 'files.tsv'; valid_table = table.read_bytes()
    table.write_bytes(valid_table.replace(rows[0]['relative_path'].encode(), b'../AMS2.exe', 1)); before = assets()
    repair('unsafe-state-path-zero-write', False); assert assets() == before; table.write_bytes(valid_table)
    index = game / 'Pakfiles/Dir/TEXT.bff'; valid_index = index.read_bytes(); index.write_bytes(valid_index + b'new-structure'); before = assets()
    repair('unknown-translation-index-zero-write', False); assert assets() == before; index.write_bytes(valid_index)

    steam_replace(); manifest('25271800')
    if args.failure_cli:
        flag = game / '.compat_fail_after_write'; flag.touch(); before = assets()
        repair('late-failure-restores-assets-backups-state', False, args.failure_cli)
        assert assets() == before; flag.unlink()
        flag = game / '.compat_interrupt_after_write'; flag.touch()
        repair('simulate-process-interruption', False, args.failure_cli); flag.unlink()
        assert 'status\tGAME_UPDATE_PENDING' in (game / STATE / 'install-state.tsv').read_text(encoding='utf-8')
        repair('recover-interruption-and-reapply')
        for relative_path in list(rules['menus']) + list(rules['archives']):
            assert sha(game / relative_path) == sha(compat / 'candidate' / relative_path)
        steam_replace(); manifest('25271800')
    before = assets()
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(game / relative), 0x80000000, 1, None, 3, 0, None)
    assert handle != ctypes.c_void_p(-1).value
    try:
        repair('locked-file-zero-write', False)
    finally:
        kernel.CloseHandle(handle)
    assert assets() == before
    readonly = game / relative
    assert kernel.SetFileAttributesW(ctypes.c_wchar_p(str(readonly)), 1)
    repair('readonly-repair-after-refusal')
    assert readonly.stat().st_file_attributes & 1
    assert kernel.SetFileAttributesW(ctypes.c_wchar_p(str(readonly)), 0x80)

    def operation(label, action, expected):
        result = subprocess.run([str(cli), '--game-dir', str(game), '--release-root', str(package), action, '--mock'], capture_output=True, timeout=180)
        (root / (label + '.log')).write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0 and ('STATUS=' + expected).encode() in result.stdout, label + ': ' + (result.stdout + result.stderr).decode('utf-8', errors='replace')[-1800:]
        checks.append(label)

    operation('upgrade-082-to-083', '--install', 'UPDATED_EXACT')
    operation('installed-check', '--check', 'INSTALLED_EXACT')
    repair('new-installed-launch-guard')
    installed_rows = list(csv.DictReader((game / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.83-PRETENDARD/files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    operation('uninstall-new-game-originals', '--uninstall', 'RESTORED_EXACT')
    for row in installed_rows:
        path = game / row['relative_path']
        if row['action'] == 'created':
            assert not path.exists(), row['relative_path']
        else:
            assert sha(path) == row['before_sha256'], row['relative_path']
    for cycle in (1, 2):
        operation('fresh-install-' + str(cycle), '--install', 'INSTALLED_EXACT')
        operation('fresh-remove-' + str(cycle), '--uninstall', 'RESTORED_EXACT')
    # 0.8/0.81 used the earlier 450-file installation contract (before the ERS additions).
    old_package = WORK / 'releases/0.81/AMS2 한국어 패치 오픈베타 0.81'
    old_manifest = list(csv.DictReader((old_package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    old_root = game / 'Backup/AMS2-Korean/AMS2-KR-BETA-0.81-PRETENDARD'
    shutil.copytree(game / STATE, old_root, ignore=shutil.ignore_patterns('game-updates', 'logs', 'transaction', 'shortcuts.tsv'))
    old_head = dict(state_head, status='INSTALLED', buildid='24132163')
    (old_root / 'install-state.tsv').write_text(''.join(k + '\t' + v + '\n' for k, v in old_head.items()), encoding='utf-8')
    original_rows = {r['relative_path'].replace('\\', '/').lower(): r for r in rows}
    legacy_rows = []
    for item in old_manifest:
        key = item['relative_path'].replace('\\', '/').lower()
        row = original_rows[key].copy()
        row['after_bytes'], row['after_sha256'] = item['bytes'], item['sha256']
        if row['action'] == 'modified':
            original = old_root / 'original' / old_head['backup_id'] / row['relative_path']
            row['before_sha256'], row['before_bytes'] = sha(original), str(original.stat().st_size)
        target = game / item['relative_path']; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_package / 'payload/direct' / item['relative_path'], target)
        legacy_rows.append(row)
    row = original_rows['pakfiles/igphasehud.bff'].copy()
    original = old_root / 'original' / old_head['backup_id'] / row['relative_path']
    row['before_sha256'], row['before_bytes'] = sha(original), str(original.stat().st_size)
    legacy_rows.append(row)
    assert len(legacy_rows) == 450
    with (old_root / 'files.tsv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(legacy_rows[0]), delimiter='\t', lineterminator='\n')
        writer.writeheader(); writer.writerows(legacy_rows)
    steam_replace(); manifest()
    operation('legacy-081-steam-update-upgrade', '--install', 'UPDATED_EXACT')
    operation('legacy-upgrade-remove', '--uninstall', 'RESTORED_EXACT')
    report = {'status': 'PASS', 'checks': checks, 'fixture': str(root), 'game_executed': False, 'cli_sha256': sha(cli)}
    (root / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
