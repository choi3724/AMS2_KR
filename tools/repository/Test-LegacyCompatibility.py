"""Check both build lifecycles; the unavailable old TEXT index uses a declared fixture fingerprint."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compatibility', type=Path, required=True)
    parser.add_argument('--package', type=Path)
    parser.add_argument('--version', choices=('0.83.1', '0.83.2', '0.83.3', '0.84', '0.85'), default='0.83.1')
    args = parser.parse_args()
    compat = args.compatibility.resolve()
    root = WORK / 'build' / ('qa' + args.version.replace('.', '')) / uuid.uuid4().hex[:8]
    root.mkdir(parents=True)
    package = args.package.resolve() if args.package else compat / 'package' / ('AMS2 한국어 패치 오픈베타 ' + args.version)
    production = compat / 'build' / args.version / 'installer/AMS2 Korean Patch TestCli.exe'
    rules = json.loads((compat / 'data/rules.json').read_text(encoding='utf-8'))
    assert rules['legacy']['textIndexSha1'] == 'E69F8BCC367FCE781C5F4F09CB5537D85F3C4A86'
    assert rules['legacy']['textIndexBytes'] == 53149
    old_index = b'OLD TEXT INDEX FIXTURE'.ljust(53149, b'\0')
    test_rules = json.loads(json.dumps(rules))
    test_rules['legacy']['textIndexSha1'] = hashlib.sha1(old_index).hexdigest().upper()
    (root / 'fixture-rules.json').write_text(json.dumps(test_rules), encoding='utf-8')
    cli = root / 'fixture-cli.exe'
    source = REPO / 'installer' / args.version
    command = [r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe', '/nologo', '/target:exe', '/platform:anycpu',
               '/main:Ams2KoreanBeta.TestCliProgram', '/out:' + str(cli), '/define:COMPATIBILITY_TEST']
    command += ['/reference:' + name + '.dll' for name in ('System', 'System.Core', 'System.Drawing', 'System.Windows.Forms', 'System.IO.Compression', 'System.IO.Compression.FileSystem', 'System.Web.Extensions')]
    command += ['/resource:' + str(root / 'fixture-rules.json') + ',Ams2KoreanBeta.Compatibility.rules.json']
    command += ['/resource:' + str(p) + ',Ams2KoreanBeta.Compatibility.' + p.name for p in (compat / 'data').glob('*.gz')]
    command += [str(source / (name + '.cs')) for name in ('AssemblyInfo', 'BetaCore', 'ErsArchivePatch', 'GameLauncher', 'GithubUpdater', 'GameUpdateCompatibility', 'TestCliProgram')]
    if (source / "ContentManagerOverlay.cs").exists(): command.append(str(source / "ContentManagerOverlay.cs"))
    compiled = subprocess.run(command, capture_output=True)
    (root / 'compile.log').write_bytes(compiled.stdout + compiled.stderr)
    assert compiled.returncode == 0, 'fixture compilation failed'
    checks = []

    def create(name, build):
        game = root / name / 'steamapps/common/Automobilista 2'
        game.mkdir(parents=True)
        with zipfile.ZipFile(WORK / 'build/full-uninstall/stock.zip') as stock:
            for entry in stock.namelist():
                if not entry.startswith('original/') or entry.endswith('/'): continue
                relative = Path(entry[len('original/'):])
                assert not relative.is_absolute() and '..' not in relative.parts
                target = game / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stock.read(entry))
        for name in ('AMS2.exe', 'AMS2AVX.exe'): (game / name).write_text('INERT FIXTURE: NEVER EXECUTE')
        for path in ('Languages/Languages.bml', 'Pakfiles/Dir/TEXT.bff'):
            target = game / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(compat / 'original' / path, target)
        set_build(game, build)
        if build == '24132163': (game / 'Pakfiles/Dir/TEXT.bff').write_bytes(old_index)
        else: steam_update(game)
        return game

    def set_build(game, build):
        (game.parents[1] / 'appmanifest_1066890.acf').write_text('"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "' + build + '" }')

    def steam_update(game):
        for relative in list(rules['menus']) + list(rules['archives']) + ['Pakfiles/Dir/TEXT.bff']:
            shutil.copy2(compat / 'original' / relative, game / relative)
        set_build(game, '25271800')

    def snapshot(game):
        return {p.relative_to(game).as_posix().lower(): sha(p) for p in game.rglob('*') if p.is_file() and 'Backup' not in p.relative_to(game).parts}

    def run(label, game, action, expected, tool=cli, release=package):
        params = ['--repair-game-update', str(game)] if action == 'repair' else ['--game-dir', str(game), '--release-root', str(release), action]
        result = subprocess.run([str(tool), *params], capture_output=True, timeout=180)
        output = result.stdout + result.stderr
        (root / (label + '.log')).write_bytes(output)
        assert expected.encode('utf-8') in output, label + ': ' + output.decode('utf-8', errors='replace')[-1300:]
        assert (result.returncode == 0) == (expected in ('INSTALLED_EXACT','UPDATED_EXACT','RESTORED_EXACT','COMPATIBILITY=PASS')), label
        checks.append(label)
        print('PASS:', label, flush=True)

    def installed(game, build):
        name = 'direct-files-24132163.tsv' if build == '24132163' else 'direct-files.tsv'
        for row in csv.DictReader((package / 'manifest' / name).open(encoding='utf-8'), delimiter='\t'):
            assert sha(game / row['relative_path']) == row['sha256'], row['relative_path']
        profile = rules['legacy'] if build == '24132163' else rules
        for path, rule in profile['archives'].items(): assert sha(game / path) == rule['patched'], path

    for build in ('24132163','25271800'):
        game = create(build, build)
        before = snapshot(game)
        tool = cli if build == '24132163' else production
        for cycle in (1,2):
            run(build + '-install-' + str(cycle), game, '--install', 'INSTALLED_EXACT', tool)
            installed(game, build)
            run(build + '-check-' + str(cycle), game, '--check', 'INSTALLED_EXACT', tool)
            run(build + '-repeat-' + str(cycle), game, '--install', 'INSTALLED_EXACT', tool)
            run(build + '-launch-guard-' + str(cycle), game, 'repair', 'COMPATIBILITY=PASS', tool)
            run(build + '-remove-' + str(cycle), game, '--uninstall', 'RESTORED_EXACT', tool)
            assert snapshot(game) == before
    if args.version in ('0.83.2', '0.83.3', '0.84', '0.85'):
        previous_version = '0.84' if args.version == '0.85' else '0.83.3' if args.version == '0.84' else '0.83.2' if args.version == '0.83.3' else '0.83.1'
        previous = WORK / ('build/release084' if previous_version == '0.84' else 'build/hud-beta-help-legacy-20260914-v2' if previous_version == '0.83.3' else 'build/translation-halo-legacy-20260913-v1' if previous_version == '0.83.2' else 'build/compat-legacy-20260913-v3')
        previous_rules = json.loads((previous / 'data/rules.json').read_text(encoding='utf-8'))
        previous_rules['legacy']['textIndexSha1'] = test_rules['legacy']['textIndexSha1']
        previous_rules_file = root / 'previous-fixture-rules.json'
        previous_rules_file.write_text(json.dumps(previous_rules), encoding='utf-8')
        previous_cli = root / 'previous-fixture-cli.exe'
        previous_command = [item.replace(str(source), str(REPO / 'installer' / previous_version)).replace('/out:' + str(cli), '/out:' + str(previous_cli))
                            for item in command if not item.startswith('/resource:') and not item.endswith('ContentManagerOverlay.cs')]
        if (REPO / 'installer' / previous_version / 'ContentManagerOverlay.cs').exists(): previous_command.append(str(REPO / 'installer' / previous_version / 'ContentManagerOverlay.cs'))
        previous_command += ['/resource:' + str(previous_rules_file) + ',Ams2KoreanBeta.Compatibility.rules.json']
        previous_command += ['/resource:' + str(p) + ',Ams2KoreanBeta.Compatibility.' + p.name for p in (previous / 'data').glob('*.gz')]
        compiled = subprocess.run(previous_command, capture_output=True)
        (root / 'previous-compile.log').write_bytes(compiled.stdout + compiled.stderr)
        assert compiled.returncode == 0
        previous_package = WORK / 'releases' / previous_version / ('AMS2 한국어 패치 오픈베타 ' + previous_version)
        for build in ('24132163', '25271800'):
            game = create(previous_version + '-upgrade-' + build, build)
            before = snapshot(game)
            old_tool = previous_cli if build == '24132163' else previous / 'build' / previous_version / 'installer/AMS2 Korean Patch TestCli.exe'
            new_tool = cli if build == '24132163' else production
            run(build + '-' + previous_version + '-install', game, '--install', 'INSTALLED_EXACT', old_tool, previous_package)
            run(build + '-' + args.version + '-upgrade', game, '--install', 'UPDATED_EXACT', new_tool)
            installed(game, build)
            run(build + '-' + args.version + '-upgrade-remove', game, '--uninstall', 'RESTORED_EXACT', new_tool)
            assert snapshot(game) == before
    game = create('legacy-upgrade', '24132163')
    before = snapshot(game)
    # Locate the frozen package by its manifest, independent of its historical folder spelling.
    old_package = next((WORK / 'releases/0.7').glob('*/manifest/direct-files.tsv')).parents[1]
    old_cli = WORK / 'build/0.7/installer/AMS2 Korean Patch TestCli.exe'
    run('old-07-install', game, '--install', 'INSTALLED_EXACT', old_cli, old_package)
    run('old-07-upgrade-on-old-game', game, '--install', 'UPDATED_EXACT')
    installed(game, '24132163')
    run('old-game-launch-guard', game, 'repair', 'COMPATIBILITY=PASS')
    for relative in ('gui/menu_mainmenu_1_6.bgui', 'Pakfiles/HUDDISPLAY.bff'):
        path = game / relative; content = path.read_bytes()
        path.write_bytes(content[:-1] + bytes([content[-1] ^ 1])); changed = snapshot(game)
        run('old-manual-change-' + path.stem, game, 'repair', '지원되는 게임 빌드이지만')
        assert snapshot(game) == changed
        path.write_bytes(content)
    steam_update(game)
    (game / '.compat_interrupt_after_write').write_text('fault injection')
    run('interrupted-game-update', game, 'repair', '게임 업데이트 감지')
    (game / '.compat_interrupt_after_write').unlink()
    run('recover-and-repair-new-game', game, 'repair', 'COMPATIBILITY=PASS')
    installed(game, '25271800')
    run('new-game-after-old-install-check', game, '--check', 'INSTALLED_EXACT', production)
    run('new-game-after-old-install-remove', game, '--uninstall', 'RESTORED_EXACT', production)
    for relative in list(rules['menus']) + list(rules['archives']) + ['Pakfiles/Dir/TEXT.bff']:
        before[relative.lower()] = sha(compat / 'original' / relative)
    assert snapshot(game) == before
    game = create('errors', '24132163')
    before = snapshot(game)
    # The production fingerprint must reject fixture bytes, not silently accept a legacy build ID.
    run('production-rejects-fake-old-index', game, '--install', '지원되는 게임 빌드이지만', production)
    assert snapshot(game) == before
    (game / 'Pakfiles/Dir/TEXT.bff').write_bytes(b'unknown index')
    run('old-game-wrong-index', game, '--install', '지원되는 게임 빌드이지만')
    set_build(game, '99999999'); before = snapshot(game)
    run('unknown-game-message', game, '--install', '아직 지원 여부가 확인되지 않은')
    assert snapshot(game) == before
    result = {'status':'PASS', 'checks':checks, 'production_cli_sha256':sha(production), 'fixture_cli_sha256':sha(cli),
              'game_executed':False, 'old_index_fixture_only':True,
              'old_index_provenance':'Production uses exact size/SHA1 from Steam depot 3757163003589186571; old index content unavailable locally.'}
    (root / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS:', root)


if __name__ == '__main__':
    main()
