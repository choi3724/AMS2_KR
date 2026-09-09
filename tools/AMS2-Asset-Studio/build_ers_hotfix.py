"""Build a reversible ERS-only font overlay from the reviewed 0.81 assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

sys.dont_write_bytecode = True
from asset_core import build_single_font

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'vendor'))
import ams2_bgui_editor as bgui
import ams2_korean_font_builder as fonts
import ams2_golden_font_appender as atlas
import ams2_tdb_editor as tdb
from PIL import Image, ImageDraw

NODE = 'KERSDeploymentModeName'
WORDS = ('자동', '꺼짐', '오프', '충전', '균형', '하이', '맥스')
ROUTES = {
    'gui/display_formula_hybrid_gen1.bgui': ('7335FB9F54EB44529ADF331A209DB3954AEAA2B7E3550279AE5D754F3B064E75', {200: 40, 211: 60}),
    'gui/display_formula_ultimate_2019.bgui': ('A1B11C01D31B537986885A956B1DF2F5290DA8A4D7FE2908EC982808ACAB7C70', {199: 40, 220: 60}),
    'gui/display_formula_ultimate_2022.bgui': ('0B5E71B82E5F9E54477EF5D9E52342DDB2BAB991FCDEFF0603E5978532EC5393', {212: 52}),
    'gui/display_formula_ultimate_2024.bgui': ('5B6CC2D8618420C3487523D1B3847A1D7336749C5519B622BE42345334199568', {228: 52, 304: 52}),
    'gui/display_lamborghini_sc63.bgui': ('79385806B72805304DB78AE959EF2D388165904269215C715AED5FF76FF5A041', {158: 52}),
    'gui/display_lamborghini_sc63_IMSA.bgui': ('1E996E48517BA1C4AD99D847D56ED5DC11186C063196B8C71FA442CD5C778215', {158: 52}),
    'gui/display_porsche_963.bgui': ('2DB6C971BAD551277B45841C94CA4A71E155F24A9B2CAE554ADBA17ED3E98F52', {473: 20, 839: 20}),
    'gui/display_porsche_963_IMSA.bgui': ('8C4EEC0B6D8D9BAD7FC487C0D60F356E68E7B73DA6D8346E38076EFB60843A0E', {473: 20, 839: 20}),
}
FONT_HASHES = {
    20: 'AF11B3871890855C680E46257304C8FD342CFBC1152C9199D12F2B7C1D5897E8',
    40: 'E863BF1C038CA32FACDD2E0FCE08FD43ED14EC822701FF4719206EB63E35D4EA',
    52: 'AF23B2C0D673A5574958DF8E5BF496FB74BA1E5072EC484DD894EF0690B03BAC',
    60: 'A549FE16F38D3DAEDDA2EC88CD1F9A9D4CBCC448E0B1E92CBE6D151DDE49A79F',
}
ARCHIVE_HASHES = {
    'gui/display_lamborghini_sc63.bgui': 'C2C92733422C084434AB95D6497621851E8E2314BE26E4B8FDF256E251085046',
    'gui/display_lamborghini_sc63_IMSA.bgui': '6FE563F71FBED10001382F641BB4CA993D4327A294EBF5252DA1E76C5E1DFB97',
    'gui/display_porsche_963.bgui': 'FB51BA831B5755890BDA541E7CB7458C5B81AC03A75920CBF111487C9CFC252E',
    'gui/display_porsche_963_IMSA.bgui': '3122657E3EFD1F83D4F8BA2F21E6BAD3D7449F282E8BF9E5BCA831DD9746D8D1',
}


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def patch_layout(data, relative, *, archive=False):
    expected, objects = ROUTES[relative]
    if archive:
        expected = ARCHIVE_HASHES.get(relative, expected)
    if sha(data) != expected:
        raise ValueError('Unsupported BGUI source: ' + relative)
    nodes = bgui._find_named_nodes(data, NODE)
    assert len(nodes) == len(objects) and {n.object_id for n in nodes} == set(objects)
    result = bytearray(data)
    changed = set()
    for node in nodes:
        size = objects[node.object_id]
        name_end = node.start + 5 + len(NODE)
        assert data[name_end + 64] == 0  # Empty localized-reference field.
        length_at = name_end + 73
        start, end = length_at + 1, length_at + 1 + data[length_at]
        old = ('GUI\\font_arial_bold_%d.bfont' % size).encode('ascii')
        new = ('GUI\\kr081_ers_value_%d.bfont' % size).encode('ascii')
        assert len(old) == len(new) == end - start and data[start:end] == old
        result[start:end] = new
        changed.update(i for i in range(start, end) if data[i] != result[i])
    result = bytes(result)
    assert len(data) == len(result)
    assert {i for i, (a, b) in enumerate(zip(data, result)) if a != b} == changed
    assert bgui._find_named_nodes(result, NODE) == nodes  # IDs, geometry, counts unchanged.
    assert bgui.parse_text_records(result) == bgui.parse_text_records(data)
    return result


def validate_font(gui, alias, original, preview, row):
    font = fonts.parse_bfont((gui / (alias + '.bfont')).read_bytes(), alias)
    assert font.name == alias and font.line_height == original.line_height
    assert set(original.codepoints) <= set(font.codepoints)
    assert set(map(ord, ''.join(WORDS))) <= set(font.codepoints)
    pages = [fonts.parse_dds((gui / (alias + '_%02d.dds' % i)).read_bytes(), alias) for i in range(font.atlas_count)]
    draw = ImageDraw.Draw(preview)
    draw.text((12, row + 12), alias[-2:], fill='white')
    for column, word in enumerate(WORDS):
        x = 70 + column * 150
        for char in word:
            index = font.codepoints.index(ord(char))
            page = pages[index // font.glyphs_per_atlas]
            rect = atlas.glyph_rect(font, index, page)
            width, height = rect[2] - rect[0], rect[3] - rect[1]
            raw = atlas.alpha_rect(page, rect)
            assert raw and max(raw) > 0, (alias, char)
            mask = Image.frombytes('L', (width, height), raw)
            assert mask.getbbox() and mask.getbbox()[1] > 0 and mask.getbbox()[3] < height
            left, _, advance = font.metrics[index]
            preview.paste('white', (x + left, row), mask)
            x += advance
    return {'alias': alias, 'glyph_count': font.glyph_count, 'line_height': font.line_height,
            'baseline': font.baseline, 'atlas_count': font.atlas_count, 'all_mode_glyphs_nonempty': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source_root.resolve(), args.output.resolve()
    repo = HERE.parents[1]
    if output.exists() or output == source or source in output.parents or output == repo or repo in output.parents:
        raise ValueError('Output must be new and outside the source/repository')
    inputs = {relative: (source / relative).read_bytes() for relative in ROUTES}
    patched = {relative: patch_layout(data, relative) for relative, data in inputs.items()}
    mode_rows = []
    for name in ('game.tdb', 'rac.tdb'):
        doc = tdb.parse_tdb(source / 'text' / name)
        for key, english, korean in zip(doc.keys, doc.language('English').values, doc.language('Korean').values):
            if '_ERSModes_' in key and not key.endswith(('ErsMode', 'ErsModeUpper')):
                mode_rows.append({'key': key, 'english': english, 'korean': korean})
    assert len(mode_rows) == 18 and {r['korean'] for r in mode_rows} == set(WORDS), 'ERS translations changed; review glyph coverage'
    source_font = HERE / 'assets/Pretendard-Medium.otf'
    assert sha(source_font.read_bytes()) == 'D39E50E4BB52B4993B6A4EEB821A171254745BD824446AF01E1F616B89FFACE0'
    template = source / 'gui/kr13_font_mono_16_00.dds'
    assert fonts.parse_dds(template.read_bytes(), str(template)).kind == 'L8'
    for size, expected in FONT_HASHES.items():
        path = source / ('gui/font_arial_bold_%d.bfont' % size)
        assert sha(path.read_bytes()) == expected, path
    gui = output / 'payload/gui'
    gui.mkdir(parents=True)
    reports = []
    preview = Image.new('RGB', (1140, 360), '#202020')
    for row, (size, pixels) in enumerate(((20, 21), (40, 42), (52, 55), (60, 63))):
        alias = 'kr081_ers_value_%d' % size
        base = source / ('gui/font_arial_bold_%d.bfont' % size)
        original = fonts.parse_bfont(base.read_bytes(), str(base))
        generated = output / 'font-build' / alias
        report = build_single_font(source_font, base, template, generated, alias, pixels,
                                   1.0, 1.0, 0, 0, original.line_height, -1, ''.join(WORDS),
                                   HERE / 'vendor/build_unified_ui_fonts.py', HERE / 'vendor/ams2_korean_font_builder.py')
        for path in sorted(generated.glob('*.dds')):
            data = path.read_bytes()
            parsed = fonts.parse_dds(data, str(path))
            # Reuse the established L8 transparent-floor correction. Keep the
            # 121..135 antialiasing samples; 120 is zero coverage, not gray ink.
            fixed = parsed.header + parsed.payload.replace(b'\x78', b'\x00')
            path.write_bytes(fixed)
            for item in report['dds']:
                if item['file'] == path.name:
                    item['sha256'] = sha(fixed)
            shutil.copy2(path, gui / path.name)
        shutil.copy2(generated / (alias + '.bfont'), gui / (alias + '.bfont'))
        report['checks']['l8_transparent_floor_normalized'] = True
        (generated / 'font-build-manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        reports.append(validate_font(gui, alias, original, preview, row * 88))
    preview.save(output / 'glyph-preview.png')
    for relative, data in patched.items():
        (output / 'payload' / relative).write_bytes(data)
    entries = [{'path': relative, 'before_sha256': sha(inputs[relative]), 'after_sha256': sha(data)} for relative, data in patched.items()]
    for path in sorted(gui.iterdir()):
        if path.suffix != '.bgui':
            relative = 'gui/' + path.name
            if (source / relative).exists():
                raise ValueError('New font alias already exists: ' + relative)
            entries.append({'path': relative, 'before_sha256': 'MISSING', 'after_sha256': sha(path.read_bytes())})
    assert len(entries) == 20 and sum(len(ids) for _, ids in ROUTES.values()) == 13
    assert all((source / relative).read_bytes() == data for relative, data in inputs.items())
    # Fail-closed regression check for unreviewed or already-patched layouts.
    rejected = False
    try:
        first = next(iter(patched))
        patch_layout(patched[first], first)
    except ValueError:
        rejected = True
    assert rejected
    manifest = dict(version='0.81-ers-test1', scope='ERS_COCKPIT_TEST', status='AWAITING_GAME_TEST',
                    files=entries, fonts=reports, mode_words=WORDS, mode_rows=mode_rows,
                    validation={'bgui_font_routes': 13, 'bgui_files': 8, 'same_length_font_edits_only': True,
                                'source_files_unchanged': True, 'reject_unreviewed_input': True,
                                'glyph_preview': 'glyph-preview.png', 'game_test_passed': False})
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: 13 ERS routes in 8 layouts; 4 dedicated fonts; 7 Korean mode names; game test required')


if __name__ == '__main__':
    main()
