"""Build an offline stock restore EXE from hash-verified original localization assets."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

REPO = Path(__file__).resolve().parents[2]
WORK = REPO.parent
OUT = WORK / 'build/full-uninstall'
PACKAGE = WORK / 'releases/0.82/AMS2 한국어 패치 오픈베타 0.82'
# Explicit font overlays, absent from the official loose-file depot. Removing these
# makes the restored stock font archives authoritative; never glob-delete GUI mods.
FONT_OVERLAYS = '''aries_frontend000 aries_frontend001 aries_frontend2000 aries_frontend2001
aries_frontend3000 aries_frontend3001 aries_frontend3002 aries_frontend3003
aries_frontend4000 aries_frontend4001 aries_frontend4002
font_aries_large font_aries_large_black_italic font_aries_small font_aries_small_black
font_display_generic_arial font_display_generic_arial_big font_display_generic_arial_narrow
font_display_generic_eurostile font_display_generic_lcd1 font_display_generic_lcd10
font_display_generic_lcd2 font_display_generic_lcd3 font_display_generic_lcd4
font_display_generic_lcd9 font_display_generic_led5 font_electronic_highway_27_distance
font_phoenix_body_footnote font_phoenix_body_large font_phoenix_body_regular
font_phoenix_page_title font_phoenix_tab_title'''.split()
STOCK = {
    'gui/display_lamborghini_sc63.bgui': 'C2C92733422C084434AB95D6497621851E8E2314BE26E4B8FDF256E251085046',
    'gui/display_lamborghini_sc63_IMSA.bgui': '6FE563F71FBED10001382F641BB4CA993D4327A294EBF5252DA1E76C5E1DFB97',
    'gui/display_porsche_963.bgui': 'FB51BA831B5755890BDA541E7CB7458C5B81AC03A75920CBF111487C9CFC252E',
    'gui/display_porsche_963_IMSA.bgui': '3122657E3EFD1F83D4F8BA2F21E6BAD3D7449F282E8BF9E5BCA831DD9746D8D1',
    'Pakfiles/IGPHASEHUD.bff': 'F967D1A322EB75AAD742CF21888D75DB0CA4CB407ACDEC72F14D32BD5351E7DA',
    'Pakfiles/HUDDISPLAY.bff': '0673E7D678E1B4B2486867072BCEA0F1F11B1D571807A582AC85B91F2C9E37A2',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().upper()


def font_baseline():
    depot = Path('C:/Program Files (x86)/Steam/depotcache/1066891_3757163003589186571.manifest')
    assert sha(depot) == '80CE273EDC8514A082EF4DDD7F7D3726675897757D4B68B51DC03516635886F6'
    sys.path.insert(0, str(WORK / 'analysis/AMS2-KR-004/provenance_mods'))
    from parse_steam_manifest import parse_manifest
    official = {r['filename'].replace('\\', '/').lower(): r for r in parse_manifest(depot)}
    fonts = {p for p in official if p.startswith('gui/') and p.count('/') == 1 and p.endswith('.bfont')}
    paths = set(fonts)
    game = Path('E:/SteamLibrary/steamapps/common/Automobilista 2')
    paths.update(['pakfiles/bootflow.bff', 'pakfiles/fontkorean.bff'])
    for rel in paths:
        data = (game / rel).read_bytes()
        assert hashlib.sha1(data).hexdigest().upper() == official[rel]['sha1_content'], rel
    text = 'relative_path\tbytes\tstock_sha1\n'
    for rel in sorted(paths):
        row = official[rel]
        text += f"{rel}\t{row['size']}\t{row['sha1_content']}\n"
    (OUT / 'font-baseline.tsv').write_text(text, encoding='utf-8')
    print('Official font diagnostic baseline:', len(paths), 'files', flush=True)
    return official, {rel: game / rel for rel in paths}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    official, font_sources = font_baseline()
    rows = list(csv.DictReader(io.StringIO((PACKAGE / 'manifest/direct-files.tsv').read_text('utf-8-sig')), delimiter='\t'))
    wanted, remove = dict(STOCK), set()
    for row in rows:
        rel = row['relative_path']
        if row['role'] == 'created':
            remove.add(rel)
        else:
            allowed = row['allowed_before_sha256'].split(';')
            if rel in wanted:
                assert wanted[rel] in allowed
            else:
                assert len(allowed) == 1, (rel, allowed)
                wanted[rel] = allowed[0]
    assert len(wanted) == 100 and len(remove) == 367 and not (set(wanted) & remove)
    wanted.update({rel: sha(p) for rel, p in font_sources.items()})
    remove.update('gui/' + name + '.dds' for name in FONT_OVERLAYS)
    # Verify coverage against the actual preceding packages, not their installation records.
    for version, name in [('0.7', 'AMS2 한국어 패치 CB 0.7'), ('0.8', 'AMS2 한국어 패치 CB 0.8'), ('0.81', 'AMS2 한국어 패치 오픈베타 0.81')]:
        table = WORK / 'releases' / version / name / 'manifest/direct-files.tsv'
        assert table.is_file(), 'Previous release manifest missing: ' + str(table)
        if table.exists():
            old = list(csv.DictReader(io.StringIO(table.read_text('utf-8-sig')), delimiter='\t'))
            assert {r['relative_path'] for r in old} <= set(wanted) | remove
            assert {r['relative_path'] for r in old if r['role'] == 'created'} <= remove
    roots = [
        WORK / 'build/0.81-ers-test2/archive-before',
        WORK / 'build/0.81-ers-test2/backup',
        Path('E:/SteamLibrary/steamapps/common/Automobilista 2/Backup/AMS2-Korean/AMS2-KR-BETA-0.7-PRETENDARD/original'),
        WORK / 'build/0.7/fixture',
    ]
    sources = dict(font_sources)
    by_name = {Path(rel).name.lower(): rel for rel in wanted}
    for root in roots:
        for line in subprocess.check_output(['rg', '--files', str(root)], encoding='utf-8').splitlines():
            candidate = Path(line)
            rel = by_name.get(candidate.name.lower())
            if rel and rel not in sources and sha(candidate) == wanted[rel]:
                sources[rel] = candidate
        if len(sources) == len(wanted):
            break
    assert set(sources) == set(wanted), 'Verified originals missing: ' + str(set(wanted) - set(sources))
    for rel, source in sources.items():
        record = official[rel.lower()]
        assert source.stat().st_size == record['size'], rel
        assert hashlib.sha1(source.read_bytes()).hexdigest().upper() == record['sha1_content'], rel
    assert not (set(rel.lower() for rel in remove) & set(official)), 'Cannot delete official files'
    assert len({rel.lower() for rel in wanted} | {rel.lower() for rel in remove}) == len(wanted) + len(remove)
    table = 'relative_path\taction\tbytes\tsha256\n'
    for rel in sorted(wanted):
        table += f'{rel}\trestore\t{sources[rel].stat().st_size}\t{wanted[rel]}\n'
    for rel in sorted(remove):
        table += f'{rel}\tremove\t0\tABSENT\n'
    archive = OUT / 'stock.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr('stock-files.tsv', table.encode('utf-8'))
        for rel, source in sorted(sources.items()):
            z.write(source, 'original/' + rel)
    source_audit = {rel: {'sha256': wanted[rel], 'bytes': p.stat().st_size, 'source': str(p)} for rel, p in sorted(sources.items())}
    (OUT / 'original-sources.json').write_text(json.dumps(source_audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (OUT / 'StockPayload.cs').write_text('namespace Ams2KoreanBeta { internal static class StockPayload { internal const string Sha256 = "' + sha(archive) + '"; internal const int RestoreCount = ' + str(len(wanted)) + '; internal const int RemoveCount = ' + str(len(remove)) + '; } }\n', encoding='utf-8')
    source = REPO / 'installer/0.82'
    manifest = (source / 'app.manifest').read_text('utf-8').replace('</windowsSettings>', '<longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware></windowsSettings>')
    (OUT / 'restore.manifest').write_text(manifest.replace('level="asInvoker"', 'level="requireAdministrator"'), encoding='utf-8')
    (OUT / 'test.manifest').write_text(manifest, encoding='utf-8')
    compiler = Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    common = ['/nologo', '/platform:anycpu', '/main:Ams2KoreanBeta.StockRestoreProgram',
              '/reference:System.dll', '/reference:System.Core.dll', '/reference:System.Drawing.dll',
              '/reference:System.Windows.Forms.dll', '/reference:System.IO.Compression.dll',
              '/reference:System.IO.Compression.FileSystem.dll',
              '/resource:' + str(archive) + ',Ams2KoreanBeta.Stock',
              '/resource:' + str(OUT / 'font-baseline.tsv') + ',Ams2KoreanBeta.FontBaseline',
              '/win32icon:' + str(source / 'ams2-korean.ico')]
    files = [source / n for n in ['StockRestore.cs', 'BetaCore.cs', 'ErsArchivePatch.cs', 'GameLauncher.cs']]
    files.append(OUT / 'StockPayload.cs')
    for filename, target, extra in [
        ('AMS2 한국어 패치 완전 제거.exe', 'winexe', ['/win32manifest:' + str(OUT / 'restore.manifest')]),
        ('StockRestoreCheck.exe', 'exe', ['/define:STOCK_RESTORE_TEST', '/win32manifest:' + str(OUT / 'test.manifest')]),
    ]:
        subprocess.run([str(compiler), '/target:' + target, '/out:' + str(OUT / filename), *common, *extra, *map(str, files)], check=True)
    # Reuse the same form and read-only audit; the small diagnostic EXE contains no restoration payload.
    diagnostic_args = [arg for arg in common if not arg.endswith(',Ams2KoreanBeta.Stock')]
    subprocess.run([str(compiler), '/target:winexe', '/out:' + str(OUT / 'AMS2 기본 폰트 진단.exe'),
                    '/define:FONT_AUDIT_ONLY', '/win32manifest:' + str(OUT / 'test.manifest'), *diagnostic_args, *map(str, files)], check=True)
    print(json.dumps({'status': 'PASS', 'restore': len(wanted), 'remove': len(remove), 'exe': str(OUT / 'AMS2 한국어 패치 완전 제거.exe'), 'payload_bytes': archive.stat().st_size}, ensure_ascii=False))


if __name__ == '__main__':
    main()
