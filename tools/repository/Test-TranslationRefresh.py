"""Check a translation candidate/package against the reviewed Steam tables."""
import argparse
import csv
import hashlib
from pathlib import Path

import rebase_translations as rebase
import ams2_bgui_editor as bgui
import ams2_korean_font_builder as fonts
import halo_help
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stock', required=True, type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--package', required=True, type=Path)
    args = parser.parse_args()
    checked = 0
    for original in sorted((args.baseline / 'payload/direct/text').glob('*.tdb')):
        stock = rebase.tdb.parse_tdb(args.stock / original.name)
        patch = rebase.tdb.parse_tdb(original)
        expected, _ = rebase.merge(stock, patch)
        actual = args.package / 'payload/direct/text' / original.name
        assert actual.read_bytes() == expected, ('Stale packaged translation', original.name)
        checked += 1
    assert checked == 9
    for table in ('direct-files.tsv', 'direct-files-24132163.tsv'):
        rows = list(csv.DictReader((args.package / 'manifest' / table).open(encoding='utf-8-sig'), delimiter='\t'))
        assert len(rows) == 465
        for row in rows:
            path = args.package / 'payload/direct' / row['relative_path']
            alternate = args.package / 'payload/24132163' / row['relative_path']
            if table == 'direct-files-24132163.tsv' and alternate.exists():
                path = alternate
            assert path.stat().st_size == int(row['bytes'])
            assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == row['sha256']
    required = {ord(c) for value in rebase.TRANSLATIONS.values() for c in value if '\uac00' <= c <= '\ud7a3'}
    document = rebase.tdb.parse_tdb(args.package / 'payload/direct/text/game.tdb')
    index = document.keys.index('Game_HelpText_ManufacturerEvents')
    halo_text = document.language('Korean').values[index]
    required.update(ord(c) for c in halo_text if '\uac00' <= c <= '\ud7a3')
    names = set()
    for folder in ('direct', '24132163'):
        for menu in (args.package / 'payload' / folder / 'gui').glob('menu_*.bgui'):
            names.update(r.font.replace('\\', '/').lower() for r in bgui.parse_text_records(menu.read_bytes()))
    for name in names:
        font = args.package / 'payload/direct' / name
        assert required <= set(fonts.parse_bfont(font.read_bytes(), name).codepoints), ('Missing new Hangul', name)
    for folder in ('direct', '24132163'):
        for relative in halo_help.MENUS:
            data = (args.package / 'payload' / folder / relative).read_bytes()
            help_record = halo_help.record(data)
            assert data[help_record.start + 57] == 3, ('Hidden halo help', folder, relative)
            assert struct.unpack_from('<I', data, help_record.flags_offset + 8)[0] == 0x552CADF8
            assert halo_help.patch(data) == (data, {})
    assert document.language('English').hashes[index] & 0xffffffff == 0x552CADF8
    assert halo_text == '운전석 시점에서 헤일로 중앙 기둥만 숨기고 나머지 헤일로 구조는 그대로 표시합니다.'
    stock = rebase.tdb.parse_tdb(args.stock / 'game.tdb')
    patch = rebase.tdb.parse_tdb(args.baseline / 'payload/direct/text/game.tdb')
    stock.keys[0] = 'Game_Unreviewed_New_Key'
    try:
        rebase.merge(stock, patch)
    except ValueError as error:
        assert 'Unreviewed' in str(error)
    else:
        raise AssertionError('Unreviewed key accepted')
    stock = rebase.tdb.parse_tdb(args.stock / 'game.tdb')
    patch.keys[1] = patch.keys[0]
    try:
        rebase.merge(stock, patch)
    except ValueError as error:
        assert 'Conflicting' in str(error)
    else:
        raise AssertionError('Conflicting duplicate accepted')
    print(f'PASS: {checked} tables; both 465-file manifests; {len(names)} menu fonts; halo help in both menus/builds; rejection guards')


if __name__ == '__main__':
    main()
