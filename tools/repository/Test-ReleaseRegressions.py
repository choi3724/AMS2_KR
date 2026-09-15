"""Prove the release gate rejects historical regressions in disposable fixtures."""
import argparse
import csv
import json
from pathlib import Path
import shutil
import struct
import sys

import release_regressions as gate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AMS2-Asset-Studio/vendor'))
import halo_help
import hud_beta_help


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--compatibility', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    repo = Path(__file__).resolve().parents[2]
    if root.exists() or repo == root or repo in root.parents:
        raise ValueError('Use a new test folder outside Git')
    root.mkdir(parents=True)
    package = root / 'package'
    compatibility = root / 'compatibility'
    shutil.copytree(args.package, package)
    shutil.copytree(args.compatibility / 'data', compatibility / 'data')
    for folder in ('original', 'original-24132163', 'candidate', 'candidate-24132163'):
        for path in (args.compatibility / folder / 'gui').glob('menu_*.bgui'):
            target = compatibility / folder / 'gui' / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    passed = []
    gate.verify(package, compatibility, '0.83.3', root / 'intact.json')
    passed.append('intact release')

    def rejected(name, path, content, expected_path=None):
        before = path.read_bytes()
        if content is None:
            path.unlink()
        else:
            path.write_bytes(content)
        try:
            try:
                gate.verify(package, compatibility, '0.83.3', root / (name + '.json'))
            except ValueError:
                result = json.loads((root / (name + '.json')).read_text(encoding='utf-8'))
                if expected_path:
                    assert any(issue['path'] == expected_path for issue in result['issues']), result
                else:
                    assert 'Unexpected release version' in result['error'], result
            else:
                raise AssertionError('Regression accepted: ' + name)
        finally:
            path.write_bytes(before)
        passed.append(name)
        print('PASS:', name, flush=True)

    main_menu = package / 'payload/direct' / hud_beta_help.MENU
    original = main_menu.read_bytes()
    assert original.count(hud_beta_help.field(hud_beta_help.KOREAN)) == 1
    rejected('hud-beta-English-restored', main_menu,
             original.replace(hud_beta_help.field(hud_beta_help.KOREAN), hud_beta_help.field(hud_beta_help.ENGLISH)),
             'payload/direct/' + hud_beta_help.MENU)
    halo = halo_help.record(original)
    hidden = bytearray(original)
    hidden[halo.start + 57] = 19
    struct.pack_into('<I', hidden, halo.flags_offset + 8, 0xE0B842FA)
    rejected('halo-help-hidden-again', main_menu, hidden, 'payload/direct/' + hud_beta_help.MENU)
    rejected('native-menu-fonts-restored', main_menu,
             (compatibility / 'original' / hud_beta_help.MENU).read_bytes(), 'payload/direct/' + hud_beta_help.MENU)
    for label, relative in (
        ('translation-table-missing', 'payload/direct/text/game.tdb'),
        ('ers-layout-missing', 'payload/direct/gui/display_formula_hybrid_gen1.bgui'),
        ('ers-archive-delta-missing', 'payload/HUDDISPLAY.24132163.xor.gz'),
    ):
        rejected(label, package / relative, None, relative)
    font = next((package / 'payload/direct/gui').glob('*.bfont'))
    rejected('font-file-missing', font, None, font.relative_to(package).as_posix())
    rules_path = compatibility / 'data/rules.json'
    rules = json.loads(rules_path.read_text(encoding='utf-8'))
    rules['menus'][hud_beta_help.MENU].pop('literalText')
    rejected('runtime-literal-rule-missing', rules_path,
             json.dumps(rules).encode('utf-8'), 'data/rules.json')
    table = package / 'manifest/direct-files.tsv'
    lines = table.read_bytes().splitlines(keepends=True)
    rejected('manifest-row-missing', table, b''.join(lines[:-1]), 'direct-files.tsv')
    # A self-consistent manifest cannot bless a stale launcher version.
    launcher = package / 'payload/direct/AMS2 Korean Launcher.exe'
    before_table = table.read_bytes()
    stale = args.package.parents[1] / '0.83.2/AMS2 한국어 패치 오픈베타 0.83.2/payload/direct/AMS2 Korean Launcher.exe'
    old_table = package / 'manifest/direct-files-24132163.tsv'
    before_old = old_table.read_bytes()
    try:
        for path in (table, old_table):
            entries = list(csv.DictReader(path.open(encoding='utf-8'), delimiter='\t'))
            for row in entries:
                if row['relative_path'] == launcher.name:
                    row['sha256'], row['bytes'] = gate.sha(stale), str(stale.stat().st_size)
            with path.open('w',encoding='utf-8',newline='') as stream:
                writer = csv.DictWriter(stream,fieldnames=list(entries[0]),delimiter='\t')
                writer.writeheader(); writer.writerows(entries)
        rejected('stale-launcher-with-matching-manifest', launcher, stale.read_bytes())
    finally:
        table.write_bytes(before_table); old_table.write_bytes(before_old)
    baseline = json.loads(gate.BASELINE.read_text(encoding='utf-8'))
    minimal = {'files': {'package': {'file':'A' * 64}}, 'reviewed_changes': []}
    assert gate.compare({'file':'B' * 64}, minimal, 'package')
    minimal['reviewed_changes'] = [{'scope':'package','path':'file','before':'A' * 64,'after':'B' * 64,
                                   'reason':'Intentional test change','validation':'Test evidence'}]
    assert not gate.compare({'file':'B' * 64}, minimal, 'package')
    assert gate.compare({'file':'C' * 64}, minimal, 'package')
    passed.append('reviewed-change-exact-hash-only')
    (root / 'result.json').write_text(json.dumps({'status':'PASS','checks':passed,'baseline':baseline['baseline_version'],
                                                'game_executed':False},indent=2),encoding='utf-8')
    print('PASS:', len(passed), 'checks;', root)


if __name__ == '__main__':
    main()
