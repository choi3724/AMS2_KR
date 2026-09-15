"""Build reviewed CM overlays from captured originals; never write installed game files."""
import argparse
import base64
import csv
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'AMS2-Asset-Studio/vendor'))
import ams2_tdb_editor as tdb
import ams2_bgui_editor as bgui


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError('Use a new output file')
    rows = {r['relative_path']: r for r in csv.DictReader((a.package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t')}
    captured = json.loads((a.capture / 'comparison.json').read_text(encoding='utf-8'))
    if len(captured) != 13 or any(not r['verified_native'] for r in captured):
        raise ValueError('Expected the reviewed 13-file CM capture')
    rules = {}
    for r in captured:
        name = r['path']
        before = (a.capture / name).read_bytes()
        after = (a.package / 'payload/direct' / name).read_bytes()
        if sha(before) != r['actual'] or sha(after) != rows[name]['sha256'] or sha(after) != r['orig_hash']:
            raise ValueError('Capture/package hash mismatch: ' + name)
        if name.endswith('.tdb'):
            native, korean = tdb.parse_tdb_bytes(before), tdb.parse_tdb_bytes(after)
            if korean.keys[:len(native.keys)] != native.keys:
                raise ValueError('Native keys changed: ' + name)
            for language in native.languages:
                result = korean.language(language.name)
                if result.hashes[:len(native.keys)] != language.hashes:
                    raise ValueError('Native key references changed: ' + name)
                if language.name != 'Korean' and result.values[:len(native.keys)] != language.values:
                    raise ValueError('Non-Korean CM data changed: ' + name)
        else:
            original_records, final_records = bgui.parse_text_records(before), bgui.parse_text_records(after)
            if len(original_records) != len(final_records):
                raise ValueError('Menu record count changed: ' + name)
            for left, right in zip(original_records, final_records):
                x, y = left.semantic(), right.semantic()
                x.pop('font'); y.pop('font')
                if x != y:
                    raise ValueError('Non-font menu change needs review: ' + name)
        start = 0
        while start < min(len(before), len(after)) and before[start] == after[start]:
            start += 1
        end = 0
        while end < min(len(before), len(after)) - start and before[-end-1] == after[-end-1]:
            end += 1
        removed = before[start:len(before)-end if end else len(before)]
        inserted = after[start:len(after)-end if end else len(after)]
        candidate = before[:start] + inserted + (before[-end:] if end else b'')
        if candidate != after:
            raise ValueError('Overlay reversal failed: ' + name)
        rules[name.lower()] = {'before':sha(before),'after':sha(after),'offset':start,
                              'remove':base64.b64encode(removed).decode(), 'insert':base64.b64encode(inserted).decode()}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_bytes(gzip.compress(json.dumps({'build':'25271800','files':rules}).encode('utf-8'),mtime=0))
    print('PASS: 13 overlays; native TDB keys/references/non-Korean values and non-font menu records preserved')


if __name__ == '__main__':
    main()
