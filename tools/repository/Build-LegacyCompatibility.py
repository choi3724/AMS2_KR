"""Add the verified 24132163 profile to an external 25271800 compatibility build."""
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import zipfile

spec = importlib.util.spec_from_file_location('compat', Path(__file__).with_name('Build-GameUpdateCompatibility.py'))
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    current, out = args.current.resolve(), args.output.resolve()
    if out.exists() or out == compat.REPO or compat.REPO in out.parents:
        raise ValueError('Use a new external output directory')
    old_package = compat.WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
    archive = old_package.parent / (old_package.name + '.zip')
    assert compat.sha(archive.read_bytes()) == 'AF00158ECF5D1AF3BE6BA8E2800402330FC6B0EA8206BF23B676613A86EA900D'
    with zipfile.ZipFile(archive) as released:
        for relative in ['payload/direct/' + name for name in compat.MENUS] + ['payload/HUDDISPLAY.xor.gz', 'runtime/AMS2.DynamicBffPatcher.exe']:
            assert (old_package / relative).read_bytes() == released.read(old_package.name + '/' + relative)
    out.mkdir(parents=True)
    for name in ('data', 'candidate', 'original'):
        shutil.copytree(current / name, out / name)
    rules = json.loads((out / 'data/rules.json').read_text(encoding='utf-8'))
    legacy = copy.deepcopy(rules)
    legacy['build'] = '24132163'
    legacy.pop('textIndex')
    legacy['menus'] = {}
    official = {r['filename'].replace('\\', '/').lower(): r for r in compat.parse_manifest(Path(r'C:\Program Files (x86)\Steam\depotcache\1066891_3757163003589186571.manifest'))}
    legacy['textIndexSha1'] = official['pakfiles/dir/text.bff']['sha1_content']
    legacy['textIndexBytes'] = official['pakfiles/dir/text.bff']['size']
    with zipfile.ZipFile(compat.WORK / 'build/full-uninstall/stock.zip') as stock:
        for relative in compat.MENUS + ['Pakfiles/IGPHASEHUD.bff', 'Pakfiles/HUDDISPLAY.bff']:
            content = stock.read('original/' + relative)
            assert hashlib.sha1(content).hexdigest().upper() == official[relative.lower()]['sha1_content']
            target = out / 'original-24132163' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    for relative in compat.MENUS:
        before = (out / 'original-24132163' / relative).read_bytes()
        after = (old_package / 'payload/direct' / relative).read_bytes()
        output = out / 'candidate-24132163' / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(after)
        resource = Path(relative).stem + '.24132163.bgui.gz'
        (out / 'data' / resource).write_bytes(gzip.compress(after, mtime=0))
        legacy['menus'][relative] = {'stock': compat.sha(before), 'patched': compat.sha(after), 'resource': resource}
        legacy['files'][relative]['sha256'] = compat.sha(after)
    for relative in ('Pakfiles/IGPHASEHUD.bff', 'Pakfiles/HUDDISPLAY.bff'):
        source = out / 'original-24132163' / relative
        output = out / 'candidate-24132163' / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if 'IGPHASE' in relative:
            compat.run([old_package / 'runtime/AMS2.DynamicBffPatcher.exe', 'patch', current / 'original', source, output, out / 'legacy-ig-report.json'])
        else:
            delta = gzip.decompress((old_package / 'payload/HUDDISPLAY.xor.gz').read_bytes())
            original = source.read_bytes()
            assert len(delta) == len(original)
            output.write_bytes(bytes(a ^ b for a, b in zip(original, delta)))
            assert compat.sha(output.read_bytes()) == 'F8A840F569D256DB4E1A67D73C5B2BB9CC4927E18109178B67356479BDCE81E5'
        before, after = source.read_bytes(), output.read_bytes()
        assert len(before) == len(after)
        resource = Path(relative).stem + '.24132163'
        (out / 'data' / (resource + '.xor.gz')).write_bytes(gzip.compress(bytes(a ^ b for a, b in zip(before, after)), mtime=0))
        legacy['archives'][relative.lower()] = {'stock': compat.sha(before), 'patched': compat.sha(after), 'bytes': len(before), 'resource': resource}
        legacy['files'][relative.lower()]['sha256'] = compat.sha(after)
    rules['legacy'] = legacy
    (out / 'data/rules.json').write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PASS: two game profiles; legacy menus and ERS match the reviewed 0.82 payload')


if __name__ == '__main__':
    main()
