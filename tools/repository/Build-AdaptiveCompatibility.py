"""Build build-agnostic, structure-validated compatibility rules for every managed BGUI.

The tool reads only verified v0.85 originals and payloads.  It records semantic
font-route transforms rather than blessing a game build or copying a complete
old BGUI over a future one.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/AMS2-Asset-Studio/vendor'))
import ams2_bgui_editor as bgui

ERS_NODE = 'KERSDeploymentModeName'
ERS_ROUTES = {
    'gui/display_formula_hybrid_gen1.bgui',
    'gui/display_formula_ultimate_2019.bgui',
    'gui/display_formula_ultimate_2022.bgui',
    'gui/display_formula_ultimate_2024.bgui',
    'gui/display_lamborghini_sc63.bgui',
    'gui/display_lamborghini_sc63_IMSA.bgui',
    'gui/display_porsche_963.bgui',
    'gui/display_porsche_963_IMSA.bgui',
}

FONT = re.compile(rb'(?i)gui\\[a-z0-9_]+\.bfont')


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def build_rule(relative, source, patched, reviewed=None):
    source_fields = list(FONT.finditer(source))
    patched_fields = list(FONT.finditer(patched))
    if len(source_fields) != len(patched_fields) or not source_fields:
        raise ValueError(f'{relative}: font-field count changed')
    source_records = bgui.parse_text_records(source)
    patched_records = bgui.parse_text_records(patched)
    if len(source_records) != len(patched_records):
        raise ValueError(f'{relative}: Text record count changed')
    for before, after in zip(source_records, patched_records):
        if before.object_id != after.object_id:
            raise ValueError(f'{relative}: Text identity changed at {before.ordinal}')

    mapping = collections.defaultdict(collections.Counter)
    for before, after in zip(source_fields, patched_fields):
        mapping[before.group().decode('ascii').lower()][after.group().decode('ascii')] += 1
    defaults = {name: values.most_common(1)[0][0] for name, values in mapping.items()}
    # Patched routes are accepted as idempotent inputs.
    for target in (match.group().decode('ascii') for match in patched_fields):
        defaults.setdefault(target.lower(), target)

    by_offset = {record.font_bytes_offset: record for record in source_records}
    overrides = {}
    named_overrides = {}
    named_by_offset = {}
    if relative in ERS_ROUTES:
        for node in bgui._find_named_nodes(source, ERS_NODE):
            name_end = node.start + 5 + len(ERS_NODE)
            named_by_offset[name_end + 74] = f'{ERS_NODE}:{node.object_id}'
    unresolved = []
    for before, after in zip(source_fields, patched_fields):
        native = before.group().decode('ascii').lower()
        target = after.group().decode('ascii')
        if defaults[native] == target:
            continue
        record = by_offset.get(before.start())
        if record is None or record.object_id == 0:
            key = named_by_offset.get(before.start())
            if key is None:
                unresolved.append((before.start(), native, target))
            else:
                named_overrides[key] = [native, target]
            continue
        semantic = record.semantic()
        semantic.pop('font')
        patched_semantic = patched_records[record.ordinal].semantic()
        patched_semantic.pop('font')
        if semantic != patched_semantic:
            raise ValueError(f'{relative}: special Text semantics changed at {record.ordinal}')
        overrides[str(record.object_id)] = [native, target, sha(source[record.start:record.font_length_offset])]
    if unresolved:
        raise ValueError(f'{relative}: ambiguous non-Text font routes: {unresolved[:4]}')

    rule = {
        'stock': sha(source), 'patched': sha(patched), 'count': len(source_fields),
        'texts': len(source_records), 'map': defaults, 'overrides': overrides,
        'namedOverrides': named_overrides, 'helpOverrides': None, 'literalText': None,
    }
    if reviewed:
        # Preserve the two explicitly reviewed non-font corrections.  Their
        # structural fingerprints remain checked by the runtime patcher.
        rule['helpOverrides'] = reviewed.get('helpOverrides')
        rule['literalText'] = reviewed.get('literalText')
        rule['overrides'].update(reviewed.get('overrides') or {})
    return rule


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--originals', type=Path, required=True)
    parser.add_argument('--base-rules', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    originals = args.originals.resolve()
    output = args.output.resolve()
    if output.exists() or output == REPO or REPO in output.parents:
        raise ValueError('Use a new output directory outside Git')
    base = json.loads(args.base_rules.read_text(encoding='utf-8'))
    rows = list(csv.DictReader((package / 'manifest/direct-files.tsv').open(encoding='utf-8-sig'), delimiter='\t'))
    rules = json.loads(json.dumps(base))
    rules['policy'] = {
        'schema': 2,
        'buildIsAdvisory': True,
        'hashPurpose': 'state-identification-backup-and-result-verification',
        'requiredDirectFiles': True,
        'optionalArchives': ['pakfiles/igphasehud.bff', 'pakfiles/huddisplay.bff'],
    }
    rules['menus'] = {}
    for row in rows:
        relative = row['relative_path'].replace('\\', '/')
        if row['role'] != 'modified' or Path(relative).suffix.lower() != '.bgui':
            continue
        source_path = originals / relative
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        source = source_path.read_bytes()
        patched = (package / 'payload/direct' / relative).read_bytes()
        reviewed = base.get('menus', {}).get(relative.lower())
        rule = build_rule(relative, source, patched, reviewed)
        rules['menus'][relative.lower()] = rule
        rules['files'][relative.lower()]['sha256'] = rule['patched']
    expected = sum(1 for row in rows if row['role'] == 'modified' and Path(row['relative_path']).suffix.lower() == '.bgui')
    if len(rules['menus']) != expected:
        raise AssertionError((len(rules['menus']), expected))
    if rules.get('legacy'):
        legacy_specific = rules['legacy'].get('menus', {})
        rules['legacy']['menus'] = dict(rules['menus'])
        rules['legacy']['menus'].update(legacy_specific)
        rules['legacy']['policy'] = rules['policy']
    output.mkdir(parents=True)
    (output / 'rules.json').write_text(json.dumps(rules, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    report = {
        'status': 'PASS', 'schema': 2, 'managed_bgui_rules': len(rules['menus']),
        'verified_source_pair': 'v0.85 original-to-patched',
        'build_gate': False,
        'rules_sha256': sha((output / 'rules.json').read_bytes()),
    }
    (output / 'adaptive-rules-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
