"""Prepare the September 2026 compatibility candidate without writing game files."""
import argparse
import collections
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
sys.path.insert(0, str(REPO / 'tools/AMS2-Asset-Studio'))
sys.path.insert(0, str(REPO / 'tools/AMS2-Asset-Studio/vendor'))
import ams2_bgui_editor as bgui
from build_ers_hotfix import ROUTES, patch_layout
from steam_manifest import parse_manifest
from rebase_translations import build as rebase_translations
import halo_help

MENUS = ['gui/menu_' + name + '_1_6.bgui' for name in
         ('dialogbox_frontendonly', 'dialogbox_gamewide', 'ingamemenu', 'mainmenu')]
STOCK = {
    'Pakfiles/IGPHASEHUD.bff': '0F4EC40436B7AD92988C959996A66FBE05C45421C6EEA18D6B4843D2D8004DFB',
    'Pakfiles/HUDDISPLAY.bff': '401A819D78DC45E9555888AB96F7885B0737F2831C9B02EF0654746AB9F93E97',
}
FONT = re.compile(rb'(?i)gui\\[a-z0-9_]+\.bfont')


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def run(args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, encoding='utf-8').stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', type=Path, required=True)
    p.add_argument('--previous-originals', type=Path, required=True, help='Verified build 24132163 menu originals')
    p.add_argument('--current-originals', type=Path, required=True, help='Verified build 25271800 menu/archive originals')
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    game, out = args.game.resolve(), args.output.resolve()
    if out.exists() or out == REPO or REPO in out.parents or game == out or game in out.parents:
        raise ValueError('Use a new output directory outside the repository and game')
    package = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
    old = args.previous_originals.resolve()
    current_root = args.current_originals.resolve()
    depot = Path(r'C:\Program Files (x86)\Steam\depotcache\1066891_98964879310403435.manifest')
    official = {r['filename'].replace('\\', '/').lower(): r for r in parse_manifest(depot)}
    rows = list(csv.DictReader((package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    out.mkdir(parents=True)
    data = out / 'data'
    data.mkdir()
    (out / 'original').mkdir()
    rules = {'build': '25271800', 'menus': {}, 'archives': {}, 'files': {}}
    for row in rows:
        relative = row['relative_path'].replace('\\', '/')
        content = (package / 'payload/direct' / relative).read_bytes()
        assert sha(content) == row['sha256'].upper()
        rules['files'][relative.lower()] = {'sha256': sha(content), 'role': row['role']}
    pairs, all_pairs, global_map = {}, {}, collections.defaultdict(collections.Counter)
    for relative in MENUS:
        before = bgui.parse_text_records((old / relative).read_bytes())
        after = bgui.parse_text_records((package / 'payload/direct' / relative).read_bytes())
        assert len(before) == len(after)
        pairs[relative] = list(zip(before, after))
        for a, b in pairs[relative]:
            assert a.object_id == b.object_id
        old_fonts = list(FONT.finditer((old / relative).read_bytes()))
        patched_fonts = list(FONT.finditer((package / 'payload/direct' / relative).read_bytes()))
        assert len(old_fonts) == len(patched_fonts)
        all_pairs[relative] = list(zip(old_fonts, patched_fonts))
        for a, b in all_pairs[relative]:
            global_map[a.group().decode().lower()][b.group().decode().lower()] += 1
    for relative in MENUS:
        source = (current_root / relative).read_bytes()
        assert hashlib.sha1(source).hexdigest().upper() == official[relative]['sha1_content']
        source_records = bgui.parse_text_records(source)
        bgui.parse_resource_header(source)
        mapping = collections.defaultdict(collections.Counter)
        for a, b in all_pairs[relative]:
            mapping[a.group().decode().lower()][b.group().decode().lower()] += 1
        default = {font: values.most_common(1)[0][0] for font, values in global_map.items()}
        default.update({font: values.most_common(1)[0][0] for font, values in mapping.items()})
        overrides = {}
        for a, b in pairs[relative]:
            if b.font.lower() == default[a.font.lower()]:
                continue
            # The new main menu renumbered objects without moving these reviewed records.
            # Establish their new identities once; runtime requires the exact new record fingerprint.
            current = source_records[a.ordinal]
            previous_semantic, current_semantic = a.semantic(), current.semantic()
            for key in ('object_id', 'font'):
                previous_semantic.pop(key); current_semantic.pop(key)
            assert previous_semantic == current_semantic, ('review changed special record', relative, a.ordinal)
            overrides[str(current.object_id)] = [current.font.lower(), b.font.lower(), sha(source[current.start:current.font_length_offset])]
        edits, fonts = [], []
        text_by_font = {record.font_bytes_offset: record for record in source_records}
        for field in FONT.finditer(source):
            assert source[field.start() - 1] == len(field.group())
            native = field.group().decode().lower()
            target = default[native]
            record = text_by_font.get(field.start())
            if record and str(record.object_id) in overrides:
                expected, target, fingerprint = overrides[str(record.object_id)]
                assert native == expected
                assert sha(source[record.start:record.font_length_offset]) == fingerprint
            assert target == native or target.replace('\\', '/') in rules['files']
            fonts.append(target)
            edits.append((field.start() - 1, field.end(), target))
        result = bytearray(source)
        for start, end, font in reversed(edits):
            encoded = font.encode()
            result[start:end] = bytes([len(encoded)]) + encoded
        result = bytes(result)
        final = bgui.parse_text_records(result)
        assert len(final) == len(source_records)
        for before, after in zip(source_records, final):
            a, b = before.semantic(), after.semantic()
            a.pop('font'); b.pop('font')
            assert a == b
        restored = bytearray(result)
        for before, after in reversed(list(zip(FONT.finditer(source), FONT.finditer(result)))):
            value = before.group()
            restored[after.start() - 1:after.end()] = bytes([len(value)]) + value
        assert bytes(restored) == source
        help_overrides = {}
        if relative in halo_help.MENUS:
            result, help_overrides = halo_help.patch(result)
        rules['menus'][relative] = {'stock': sha(source), 'patched': sha(result), 'count': len(edits), 'texts': len(final),
                                    'map': default, 'overrides': overrides, 'helpOverrides': help_overrides}
        rules['files'][relative]['sha256'] = sha(result)
        for folder, content in [('original', source), ('candidate', result)]:
            path = out / folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        print(relative, len(edits), 'font fields;', len(final), 'Text records; font reversal PASS; halo help', len(help_overrides))
    inspect = WORK / 'build/repo-tools/BffEntryInspect/bin/Release/netcoreapp3.1/BffEntryInspect.exe'
    patcher = package / 'runtime/AMS2.DynamicBffPatcher.exe'
    for relative, expected in STOCK.items():
        source = (current_root / relative).read_bytes()
        assert sha(source) == expected
        assert hashlib.sha1(source).hexdigest().upper() == official[relative.lower()]['sha1_content']
        original = out / 'original' / relative
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(source)
        candidate = out / 'candidate' / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        if 'IGPHASEHUD' in relative:
            run([patcher, 'patch', game, original, candidate, out / 'igphase-report.json'])
        else:
            extracted = out / 'hud-before'
            listing = run([inspect, game, original, '.bgui', extracted])
            (out / 'hud-inventory.txt').write_text(listing)
            entries = {path.replace('\\', '/').lower(): int(index) for index, path in
                       re.findall(r'^\[(\d+)\] Path=(.+?) DataPos=', listing, re.M)}
            previous = original
            ranges = []
            for n, path in enumerate(ROUTES):
                replacement = out / 'hud-patched' / path
                replacement.parent.mkdir(parents=True, exist_ok=True)
                replacement.write_bytes(patch_layout((extracted / path).read_bytes(), path, archive=True))
                next_path = out / ('steps/%02d/HUDDISPLAY.bff' % n)
                report = next_path.with_suffix('.json')
                run([inspect, '--pack-entry', game, previous, entries[path.lower()], replacement, next_path, report])
                details = json.loads(report.read_text(encoding='utf-8-sig'))
                assert details['status'] == 'PASS' and details['validation_extract_sha256'] == sha(replacement.read_bytes())
                start = 0x130 + entries[path.lower()] * 42
                pos = int(details['data_position'], 16)
                ranges += [(start + 16, start + 24), (start + 34, start + 38), (pos, pos + details['allocation_bytes'])]
                previous = next_path
            shutil.copy2(previous, candidate)
            after = candidate.read_bytes()
            cursor = 0
            for start, end in sorted(ranges):
                assert cursor <= start < end <= len(source) and source[cursor:start] == after[cursor:start]
                cursor = end
            assert source[cursor:] == after[cursor:]
            final_extract = out / 'hud-after'
            run([inspect, game, candidate, '.bgui', final_extract])
            for path in extracted.rglob('*.bgui'):
                rel = path.relative_to(extracted)
                expected_path = out / 'hud-patched' / rel
                assert (final_extract / rel).read_bytes() == (expected_path if expected_path.exists() else path).read_bytes()
            print('HUDDISPLAY:', len(entries), 'layouts;', len(ROUTES), 'ERS layouts changed; all other bytes preserved')
        after = candidate.read_bytes()
        assert len(after) == len(source)
        delta = gzip.compress(bytes(a ^ b for a, b in zip(source, after)), mtime=0)
        key = Path(relative).stem
        (data / (key + '.xor.gz')).write_bytes(delta)
        rules['archives'][relative.lower()] = {'stock': sha(source), 'patched': sha(after), 'bytes': len(source), 'resource': key}
        rules['files'][relative.lower()] = {'sha256': sha(after), 'role': 'modified'}
    # Most text tables live in BOOTFLOW, not Dir/TEXT. Review actual native keys too.
    bootflow = game / 'Pakfiles/BOOTFLOW.bff'
    assert hashlib.sha1(bootflow.read_bytes()).hexdigest().upper() == official['pakfiles/bootflow.bff']['sha1_content']
    extracted_text = out / 'stock-text'
    run([inspect, game, bootflow, '.tdb', extracted_text])
    reviews = rebase_translations(extracted_text / 'text', package / 'payload/direct/text', out / 'candidate/text')
    for review in reviews:
        rules['files']['text/' + review['file']]['sha256'] = review['after_sha256'].upper()
    # TEXT contains additional tables; a changed index still requires review.
    text_index = (current_root / 'Pakfiles/Dir/TEXT.bff').read_bytes()
    assert hashlib.sha1(text_index).hexdigest().upper() == official['pakfiles/dir/text.bff']['sha1_content']
    rules['textIndex'] = sha(text_index)
    for relative in ('Languages/Languages.bml', 'Pakfiles/Dir/TEXT.bff'):
        original = current_root / relative
        assert hashlib.sha1(original.read_bytes()).hexdigest().upper() == official[relative.lower()]['sha1_content']
        target = out / 'original' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    (data / 'rules.json').write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: compatibility data', data)


if __name__ == '__main__':
    main()
