"""Release gate: retain reviewed assets and exercise the shipped menu repair code."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile

HERE = Path(__file__).resolve().parent
BASELINE = HERE / 'regressions/baseline-0.83.3.json'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def resolve(root, relative):
    path = (root / relative).resolve()
    if path == root.resolve() or root.resolve() not in path.parents:
        raise ValueError('Path outside package: ' + relative)
    return path


def inventory(root, scope, versioned):
    folders = ('payload', 'runtime') if scope == 'package' else ('data',)
    return {p.relative_to(root).as_posix(): sha(p) for folder in folders
            for p in (root / folder).rglob('*') if p.is_file()
            and p.relative_to(root).as_posix() not in versioned}


def compare(actual, baseline, scope):
    expected = dict(baseline['files'][scope])
    for change in baseline['reviewed_changes']:
        if change['scope'] != scope:
            continue
        path = change['path']
        if not change.get('reason', '').strip() or not change.get('validation', '').strip():
            raise ValueError('Change needs reason and validation: ' + path)
        if expected.get(path) != change['before']:
            raise ValueError('Reviewed change does not match baseline: ' + path)
        after = change['after']
        if not isinstance(after, str) or len(after) != 64 or any(c not in '0123456789ABCDEF' for c in after):
            raise ValueError('Reviewed change needs an exact SHA256: ' + path)
        expected[path] = after
    return [{'scope': scope, 'path': path, 'expected': expected.get(path), 'actual': actual.get(path)}
            for path in sorted(set(expected) | set(actual)) if expected.get(path) != actual.get(path)]


def check_manifests(package, baseline):
    errors = []
    tables = {'25271800': 'direct-files.tsv', '24132163': 'direct-files-24132163.tsv'}
    direct = {p.removeprefix('payload/direct/') for p in baseline['files']['package'] if p.startswith('payload/direct/')}
    direct.update(p.removeprefix('payload/direct/') for p in baseline['versioned_files'])
    for change in baseline['reviewed_changes']:
        if change['scope'] == 'package' and change['path'].startswith('payload/direct/'):
            direct.add(change['path'].removeprefix('payload/direct/'))
    for build in baseline['builds']:
        rows = list(csv.DictReader((package / 'manifest' / tables[build]).open(encoding='utf-8-sig'), delimiter='\t'))
        names = [row['relative_path'].replace('\\', '/') for row in rows]
        if len(set(name.lower() for name in names)) != len(names) or set(names) != direct:
            errors.append({'scope': build, 'path': tables[build], 'error': 'manifest membership/duplicate mismatch'})
        for name, row in zip(names, rows):
            path = resolve(package, 'payload/direct/' + name)
            alternate = resolve(package, 'payload/' + build + '/' + name)
            if alternate.exists():
                path = alternate
            if not path.is_file() or path.stat().st_size != int(row['bytes']) or sha(path) != row['sha256'].upper():
                errors.append({'scope': build, 'path': name, 'error': 'manifest bytes/hash mismatch'})
    return errors


def check_help(package, baseline):
    # Independent invariants still apply when a menu hash change is intentionally reviewed.
    sys.path.insert(0, str(HERE.parent / 'AMS2-Asset-Studio/vendor'))
    import halo_help
    import hud_beta_help
    errors = []
    for build in baseline['builds']:
        for name in halo_help.MENUS:
            path = package / 'payload' / build / name
            if not path.exists():
                path = package / 'payload/direct' / name
            data = path.read_bytes()
            record = halo_help.record(data)
            if data[record.start + 57] != 3 or struct.unpack_from('<I', data, record.flags_offset + 8)[0] != 0x552CADF8:
                errors.append({'scope': build, 'path': name, 'error': 'halo help visibility/reference regression'})
            if name == hud_beta_help.MENU and (data.count(hud_beta_help.field(hud_beta_help.KOREAN)) != 1 or
                                              hud_beta_help.field(hud_beta_help.ENGLISH) in data):
                errors.append({'scope': build, 'path': name, 'error': 'HUD beta help translation regression'})
    return errors


def menu_reapplication(package, compatibility, version):
    """Invoke the actual shipped installer and both launchers without starting them."""
    executables = [package / ('AMS2 한국어 패치 오픈베타 ' + version + '.exe')]
    executables += [package / 'payload/direct' / name for name in
                    ('AMS2 Korean Launcher.exe', 'AMS2 Korean VR Launcher.exe')]
    with tempfile.TemporaryDirectory(prefix='ams2-menu-regression-') as temporary:
        harness = Path(temporary) / 'VerifyMenus.exe'
        command = [r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe', '/nologo',
                   '/reference:System.Core.dll', '/out:' + str(harness), str(HERE / 'Verify-MenuReapplication.cs')]
        compiled = subprocess.run(command, capture_output=True, timeout=60)
        if compiled.returncode:
            raise ValueError('Menu verifier compilation failed: ' + (compiled.stdout + compiled.stderr).decode(errors='replace'))
        results = []
        for executable in executables:
            result = subprocess.run([str(harness), str(executable), str(compatibility), version], capture_output=True, timeout=90)
            output = (result.stdout + result.stderr).decode('utf-8', errors='replace').strip()
            if result.returncode:
                raise ValueError(executable.name + ': ' + output)
            results.append(output)
        return results


def verify(package, compatibility, version, report):
    baseline = json.loads(BASELINE.read_text(encoding='utf-8'))
    baseline['reviewed_changes'] = [c for c in baseline['reviewed_changes'] if not c.get('versions') or version in c['versions']]
    result = {'status': 'FAIL', 'baseline': baseline['baseline_version'], 'baseline_sha256': sha(BASELINE),
              'version': version, 'issues': [], 'runtime': [], 'game_executed': False}
    try:
        if baseline['schema'] != 1:
            raise ValueError('Unsupported regression baseline schema')
        for scope, root in (('package', package), ('compatibility', compatibility)):
            actual = inventory(root, scope, baseline['versioned_files'])
            result['issues'] += compare(actual, baseline, scope)
        result['issues'] += check_manifests(package, baseline)
        result['issues'] += check_help(package, baseline)
        if result['issues']:
            raise ValueError('Previous fixes may be missing; review ' + str(len(result['issues'])) + ' asset differences')
        result['runtime'] = menu_reapplication(package, compatibility, version)
        result['status'] = 'PASS'
    except Exception as error:
        result['error'] = str(error)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if result['status'] != 'PASS':
        raise ValueError(result['error'] + '; report: ' + str(report))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--compatibility', type=Path, required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.package.resolve(), args.compatibility.resolve(), args.version, args.report.resolve())
    print('PASS: previous assets, both manifests, shipped installer/desktop/VR menu reapplication')
