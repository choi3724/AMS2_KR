"""Include ERS routes in HUDDISPLAY.bff, retaining all other archive entries."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

from build_ers_hotfix import ROUTES, patch_layout, sha

ARCHIVE = 'Pakfiles/HUDDISPLAY.bff'
STOCK_HASH = '0673E7D678E1B4B2486867072BCEA0F1F11B1D571807A582AC85B91F2C9E37A2'
ENTRY = re.compile(r'^\[(\d+)\] Path=(.+?) DataPos=0x([0-9A-F]+) Packed=(\d+) Original=(\d+) Compression=(\w+) CRC=0x([0-9A-F]+)$', re.M)


def inspect(tool, game, archive, output):
    result = subprocess.run([str(tool), str(game), str(archive), '.bgui', str(output)],
                            check=True, capture_output=True, encoding='utf-8')
    rows = {}
    for index, path, offset, packed, original, compression, crc in ENTRY.findall(result.stdout):
        key = path.replace('\\', '/').lower()
        assert key not in rows
        rows[key] = dict(index=int(index), path=path.replace('\\', '/'), offset=int(offset, 16),
                         packed=int(packed), original=int(original), compression=compression, crc=crc)
    assert len(rows) == 327, 'Unexpected HUDDISPLAY layout inventory'
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game-dir', type=Path, required=True)
    p.add_argument('--direct-candidate', type=Path, required=True)
    p.add_argument('--bff-tool', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    game, direct, tool, out = (x.resolve() for x in (args.game_dir, args.direct_candidate, args.bff_tool, args.output))
    if out.exists() or game == out or game in out.parents or direct == out or direct in out.parents:
        raise ValueError('Output must be new and outside the game/direct candidate')
    stock = (game / ARCHIVE).read_bytes()
    assert sha(stock) == STOCK_HASH, 'Unreviewed archive; no game files changed'
    manifest = json.loads((direct / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['scope'] == 'ERS_COCKPIT_TEST'
    allowed = set(ROUTES) | {'gui/kr081_ers_value_%d%s' % (n, ext) for n in (20, 40, 52, 60) for ext in ('.bfont', '_00.dds', '_01.dds')}
    assert len(manifest['files']) == 20 and {r['path'] for r in manifest['files']} == allowed
    for row in manifest['files']:
        assert sha((direct / 'payload' / row['path']).read_bytes()) == row['after_sha256']
    out.mkdir(parents=True)
    extracted = out / 'archive-before'
    entries = inspect(tool, game, game / ARCHIVE, extracted)
    source = game / ARCHIVE
    reports, ranges, expected_layouts = [], [], {}
    for number, relative in enumerate(ROUTES):
        entry = entries[relative.lower()]
        original = (extracted / relative).read_bytes()
        patched = patch_layout(original, relative, archive=True)
        replacement = out / 'archive-patched' / relative
        replacement.parent.mkdir(parents=True, exist_ok=True)
        replacement.write_bytes(patched)
        expected_layouts[relative.lower()] = patched
        destination = out / ('steps/%02d/HUDDISPLAY.bff' % number)
        report_path = destination.with_suffix('.json')
        subprocess.run([str(tool), '--pack-entry', str(game), str(source), str(entry['index']),
                        str(replacement), str(destination), str(report_path)],
                       check=True, capture_output=True, encoding='utf-8')
        report = json.loads(report_path.read_text(encoding='utf-8-sig'))
        assert report['status'] == 'PASS' and report['validation_extract_sha256'] == sha(patched)
        assert report['source_original_bytes'] == report['candidate_original_bytes'] == len(original)
        assert report['candidate_packed_bytes'] <= report['allocation_bytes']
        assert int(report['data_position'], 16) == entry['offset']
        start = 0x130 + entry['index'] * 42
        ranges.extend(((start + 16, start + 24), (start + 34, start + 38),
                       (entry['offset'], entry['offset'] + report['allocation_bytes'])))
        reports.append(report)
        source = destination
    candidate = source.read_bytes()
    assert len(stock) == len(candidate)
    # Check every byte outside the eight compressed allocations and their size/CRC fields.
    cursor = 0
    for start, end in sorted(ranges):
        assert cursor <= start < end <= len(stock)
        assert stock[cursor:start] == candidate[cursor:start], 'Unrelated archive bytes changed'
        cursor = end
    assert stock[cursor:] == candidate[cursor:]
    final_entries = inspect(tool, game, source, out / 'archive-after')
    assert set(final_entries) == set(entries)
    for key, entry in entries.items():
        actual = (out / 'archive-after' / entry['path']).read_bytes()
        before = (extracted / entry['path']).read_bytes()
        assert actual == expected_layouts.get(key, before), key
        if key not in expected_layouts:
            assert final_entries[key] == entry, key
    for row in manifest['files']:
        target = out / 'payload' / row['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(direct / 'payload' / row['path'], target)
    target = out / 'payload' / ARCHIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(candidate)
    manifest.update(version='0.81-ers-test2', scope='ERS_COCKPIT_ARCHIVE_TEST', status='AWAITING_GAME_TEST')
    manifest['files'].append(dict(path=ARCHIVE, before_sha256=STOCK_HASH, after_sha256=sha(candidate)))
    manifest['validation'].update(archive_layouts_changed=8, archive_ers_routes=13,
                                  other_319_layouts_unchanged=True, other_archive_bytes_unchanged=True,
                                  archive_size_unchanged=True, game_test_passed=False)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (out / 'archive-validation.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    assert (game / ARCHIVE).read_bytes() == stock
    print('PASS: archived ERS routes patched; 319 other layouts and all unrelated archive bytes unchanged')


if __name__ == '__main__':
    main()
