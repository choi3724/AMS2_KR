"""Exercise direct upgrades using verified public payloads and isolated game copies."""
import argparse,csv,hashlib,io,json,pathlib,shutil,subprocess,zipfile

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def table(p): return list(csv.DictReader(p.open(encoding='utf-8-sig'),delimiter='\t'))
def write(p,rows):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('package','cli','game','catalog','output'): p.add_argument('--'+name,type=pathlib.Path,required=True)
    p.add_argument('--published-cli',type=pathlib.Path)
    p.add_argument('--published-package',type=pathlib.Path)
    p.add_argument('--version', default='0.87')
    p.add_argument('--only-tag', help='Run only this official release lifecycle, without the unrelated full fault suite')
    p.add_argument('--skip-scenarios', type=int, default=0, help='Resume after completed lifecycle scenarios; preserve earlier logs')
    p.add_argument('--cleanup-completed', action='store_true', help='Remove completed isolated fixtures, retaining logs')
    p.add_argument('--focus-old-menus',action='store_true',help='Focused rerun of original-menu migration and transaction/CM/parent cases')
    a=p.parse_args(); work=pathlib.Path(__file__).resolve().parents[3]
    if a.output.exists(): raise ValueError('fresh output required')
    a.output.mkdir(parents=True); checks=[]
    coverage=json.loads((a.catalog/'coverage.json').read_text())
    archives=list((work/'releases').rglob('*.zip'))+list((a.catalog/'official-archives').rglob('*.zip'))
    latest=table(a.package/'manifest/direct-files.tsv')
    current_root=a.game/'Backup/AMS2-Korean/AMS2-KR-BETA-0.86-PRETENDARD'
    current_head=dict(line.split('\t',1) for line in (current_root/'install-state.tsv').read_text(encoding='utf-8-sig').splitlines())
    current_rows=table(current_root/'files.tsv')
    current={r['relative_path'].replace('\\','/').lower():r for r in current_rows}
    stock=current_root/'original'/current_head['backup_id']
    def fixture(tag,label,mode='record',six=False):
        info=next(x for x in coverage if x['tag']==tag)
        archive=next(x for x in archives if x.name==info['asset'] and sha(x)==info['sha256'])
        game=a.output/label/'steamapps/common/Automobilista 2';game.mkdir(parents=True)
        state=game/'Backup/AMS2-Korean'/('renamed-old-install' if mode=='renamed' else 'AMS2-KR-BETA-'+tag[1:]+'-PRETENDARD')
        (game.parents[1]/'appmanifest_1066890.acf').write_text('"AppState" { "appid" "1066890" "installdir" "Automobilista 2" "buildid" "25391793" }')
        for name in ('AMS2.exe','AMS2AVX.exe'): (game/name).write_text('INERT TEST FIXTURE - NEVER EXECUTE')
        for row in latest:
            if row['role']=='modified':
                relative=row['relative_path'].replace('\\','/')
                target=game/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(a.game/relative,target)
        for name in ('Pakfiles/IGPHASEHUD.bff','Pakfiles/HUDDISPLAY.bff','Languages/Languages.bml','Pakfiles/Dir/TEXT.bff'):
            target=game/name;target.parent.mkdir(parents=True,exist_ok=True)
            original=stock/name
            shutil.copy2(original if original.exists() else a.game/name,target)
        with zipfile.ZipFile(archive) as z:
            names={n.replace('\\','/'):n for n in z.namelist()}
            manifest=next(n for n in names if n.endswith('/manifest/direct-files.tsv'))
            root=manifest.split('/manifest/')[0]
            old=list(csv.DictReader(io.StringIO(z.read(names[manifest]).decode('utf-8-sig')),delimiter='\t'))
            rows=[]
            for row in old:
                relative=row['relative_path'].replace('\\','/'); target=game/relative
                payload=next(n for n in names if n.lower()==(root+'/payload/direct/'+relative).lower())
                target.parent.mkdir(parents=True,exist_ok=True)
                # Simulate Steam's current menus alongside the predecessor's created assets.
                if row['role']=='created' or not target.exists() or mode=='old-menus': target.write_bytes(z.read(names[payload]))
                before='ABSENT';nbytes=0
                if row['role']=='modified':
                    original=stock/relative
                    if mode=='old-menus':
                        choices=[work/'build/release086-compat2/original-24132163'/relative, original]
                        allowed=set(row.get('allowed_before_sha256','').upper().split(';'))
                        original=next((v for v in choices if v.exists() and sha(v) in allowed),original)
                    if not original.exists(): original=target
                    backup=state/'original/fixture'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,backup)
                    before=sha(backup);nbytes=backup.stat().st_size
                r={'relative_path':relative,'action':row['role'],'before_bytes':str(nbytes),'before_sha256':before,'after_bytes':str(target.stat().st_size),'after_sha256':sha(target)}
                if not six: r.update(install_before_exists='1' if before!='ABSENT' else '0',install_before_bytes=str(nbytes),install_before_sha256=before)
                rows.append(r)
        if mode!='missing':
            state.mkdir(parents=True,exist_ok=True)
            (state/'install-state.tsv').write_text('status\tINSTALLED\ninstalled_utc\t2026-09-01T00:00:00Z\ngame_dir\t'+str(game)+'\nbuildid\t25391793\nbackup_id\tfixture\n')
            write(state/'files.tsv',rows)
            shutil.copy2(current_root/'invariants.tsv',state/'invariants.tsv')
            if mode=='broken': (state/'files.tsv').write_text('broken\ninvalid\n')
            if mode=='multiple': shutil.copytree(state,state.with_name('other-history'))
        else:
            # backup copying above may have created the folder; remove fixture-only records.
            shutil.rmtree(state,ignore_errors=True)
        return game,state,old
    def run(label,game,action='--install',success=True,cli=None,package=None):
        result=subprocess.run([str(cli or a.cli),'--game-dir',str(game),'--release-root',str(package or a.package),action,'--mock'],capture_output=True,timeout=300)
        raw=result.stdout+result.stderr
        try: text=raw.decode('utf-8')
        except UnicodeDecodeError: text=raw.decode('cp949',errors='replace')
        (a.output/(label+'.log')).write_text(text,encoding='utf-8')
        if (result.returncode==0)!=success: raise AssertionError(label+'\n'+text[-5000:])
        checks.append(label);return text
    def snapshot(game): return {p.relative_to(game).as_posix():sha(p) for p in game.rglob('*') if p.is_file() and 'Backup' not in p.relative_to(game).parts}
    def exact(game):
        state=game/('Backup/AMS2-Korean/AMS2-KR-BETA-'+a.version+'-PRETENDARD')
        rows=table(state/'files.tsv')
        assert all(sha(game/r['relative_path'].replace('\\','/'))==r['after_sha256'] for r in rows)
        assert 'schema_version\t2' in (state/'install-state.tsv').read_text()
    if a.published_cli and a.published_package:
        game,state,old=fixture('v0.84','published-086-reproduction')
        result=subprocess.run([str(a.published_cli),'--game-dir',str(game),'--release-root',str(a.published_package),'--install','--mock'],capture_output=True,timeout=300)
        raw=result.stdout+result.stderr
        (a.output/'published-086-reproduction.log').write_bytes(raw)
        assert result.returncode!=0 and b'AMS2 Korean Launcher.exe' in raw and b'AMS2 Korean VR Launcher.exe' in raw
        checks.append('published-086-old-launcher-collision-reproduced')
    scenarios=[('v0.6.2-hotfix','oldest-six','record',True),('v0.6.83','font-generation','record',True),('v0.7','skip-many','renamed',True),('v0.82','ers-transition','record',False),('v0.84','reported-084','record',False),('v0.85','previous-085','record',False),('v0.86','retry-086','record',False),('v0.84','multiple-history','multiple',True),('v0.84','no-record','missing',False),('v0.84','broken-record','broken',False),('v0.6.2-hotfix','oldest-original-menus','old-menus',True),('v0.84','old-original-menus','old-menus',False)]
    if a.version != '0.87': scenarios.append(('v0.87','previous-087','record',False))
    if a.only_tag:
        scenarios=[(a.only_tag,'targeted-upgrade','record',False)]
    if a.focus_old_menus: scenarios=[x for x in scenarios if x[2]=='old-menus']
    scenarios.sort(key=lambda x:x[2]!='old-menus')
    scenarios=scenarios[a.skip_scenarios:]
    for tag,label,mode,six in scenarios:
        game,state,old=fixture(tag,label,mode,six)
        prior=snapshot(game)
        run(label,game);exact(game)
        run(label+'-reinstall',game);exact(game)
        result=subprocess.run([str(a.cli),'--repair-game-update',str(game)],capture_output=True,timeout=300)
        assert result.returncode==0,(label,result.stdout,result.stderr);checks.append(label+'-launch-policy')
        run(label+'-uninstall',game,'--uninstall')
        restored_head=(game/('Backup/AMS2-Korean/AMS2-KR-BETA-'+a.version+'-PRETENDARD/install-state.tsv')).read_text()
        if 'restore_policy\tPRE_UPGRADE' in restored_head: assert snapshot(game)==prior
        else:
            assert not (game/'AMS2 Korean Launcher.exe').exists()
            assert not (game/'AMS2 Korean VR Launcher.exe').exists()
        if a.cleanup_completed:
            fixture_root=game.parents[2].resolve()
            assert fixture_root.parent==a.output.resolve()
            shutil.rmtree(fixture_root)
    if a.only_tag:
        report={'status':'PASS','checks':checks,'tag':a.only_tag,'version':a.version,'real_game_modified':False,'game_executed':False}
        (a.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report));return
    retired_package=a.output/'retirement-package';shutil.copytree(a.package,retired_package)
    retired_modified=next(r['relative_path'] for r in latest if r['role']=='modified')
    retired_created='AMS2 Korean VR Launcher.exe'
    for name in ('direct-files.tsv','direct-files-24132163.tsv'):
        path=retired_package/'manifest'/name
        write(path,[r for r in table(path) if r['relative_path'] not in (retired_created,retired_modified)])
    game,state,old=fixture('v0.84','retired-owned-files')
    original=sha(state/'original/fixture'/retired_modified.replace('\\','/'))
    run('retired-owned-files',game,package=retired_package)
    assert not (game/retired_created).exists() and sha(game/retired_modified.replace('\\','/'))==original
    run('retired-owned-files-uninstall',game,'--uninstall',package=retired_package)
    game,state,old=fixture('v0.84','retired-foreign-files')
    (game/retired_created).write_bytes(b'foreign replacement must remain')
    run('retired-foreign-files',game,package=retired_package)
    assert (game/retired_created).read_bytes()==b'foreign replacement must remain'
    game,state,old=fixture('v0.84','unknown-created')
    for rel in ('AMS2 Korean Launcher.exe','AMS2 Korean VR Launcher.exe','text/game.tdb'):
        (game/rel).write_bytes(b'unknown foreign file')
    before=snapshot(game);text=run('unknown-created',game,success=False)
    assert snapshot(game)==before
    assert all(rel in text for rel in ('AMS2 Korean Launcher.exe','AMS2 Korean VR Launcher.exe','text\\game.tdb'))
    checks.append('unknown-files-preserved')
    game,state,old=fixture('v0.84','rollback')
    marker=game/'.mock_failure_after';marker.write_text('3')
    before=snapshot(game);head=(state/'install-state.tsv').read_bytes();rows=(state/'files.tsv').read_bytes()
    text=run('mid-upgrade-failure',game,success=False)
    assert snapshot(game)==before and (state/'install-state.tsv').read_bytes()==head and (state/'files.tsv').read_bytes()==rows
    assert '복구 완료' in text
    marker.unlink();run('failure-retry',game);exact(game)
    game,state,old=fixture('v0.84','interrupted')
    marker=game/'.mock_crash_after';marker.write_text('3')
    run('process-interrupted',game,success=False)
    assert (game/'Backup/AMS2-Korean-Upgrade/current/pending.tsv').exists()
    marker.unlink();text=run('interrupted-recovery-retry',game);exact(game)
    assert '전체 복구 완료' in text
    assert not (game/'Backup/AMS2-Korean-Upgrade/current/pending.tsv').exists()
    game,state,old=fixture('v0.84','cm-upgrade')
    capture=work/'analysis/cm-coexistence-20260915/current-capture'
    cmrows=json.loads((capture/'comparison.json').read_text(encoding='utf-8'))
    mods=game/'Mods';mods.mkdir();shutil.copy2(capture/'cm-state.json',mods/'state.json')
    protected={}
    for row in cmrows:
        rel=row['path'];live=game/rel
        shutil.copy2(live,game/(rel+'.orig'));protected[rel+'.orig']=sha(game/(rel+'.orig'))
        shutil.copy2(capture/rel,live)
    marker=b'UNRELATED_MOD_DATA_RETAINED'
    sample=game/cmrows[0]['path'];sample.write_bytes(sample.read_bytes()+marker)
    times={r['path']:(game/r['path']).stat().st_mtime_ns for r in cmrows}
    beforecm=sha(mods/'state.json')
    run('cm-native-plus-unrelated-mod-upgrade',game);exact(game)
    assert sample.read_bytes().endswith(marker)
    assert all((game/r).stat().st_mtime_ns==mtime for r,mtime in times.items())
    assert all(sha(game/r)==h for r,h in protected.items()) and sha(mods/'state.json')==beforecm
    checks.append('cm-times-orig-and-unrelated-data-preserved')
    (mods/'state.json').rename(mods/'state.disabled.json')
    run('cm-disabled-uninstall',game,'--uninstall')
    parent_package=a.output/'parent-package'
    shutil.copytree(a.package,parent_package)
    harness=parent_package/'Verify-UpgradeParent.exe'
    subprocess.run([r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe','/nologo','/reference:System.Core.dll','/out:'+str(harness),str(pathlib.Path(__file__).with_name('Verify-UpgradeParent.cs'))],check=True,capture_output=True)
    for vr in (False,True):
        label='updater-parent-vr' if vr else 'updater-parent-normal'
        game,state,old=fixture('v0.84',label)
        launcher=game/('AMS2 Korean VR Launcher.exe' if vr else 'AMS2 Korean Launcher.exe')
        shutil.copy2(harness,launcher)
        rows=table(state/'files.tsv')
        row=next(r for r in rows if r['relative_path']==launcher.name)
        row['after_sha256']=sha(launcher);row['after_bytes']=str(launcher.stat().st_size)
        write(state/'files.tsv',rows)
        result=subprocess.run([str(harness),str(parent_package/('AMS2 한국어 패치 오픈베타 '+a.version+'.exe')),str(game),str(launcher)]+(['vr'] if vr else []),capture_output=True,timeout=300)
        (a.output/(label+'.log')).write_bytes(result.stdout+result.stderr)
        assert result.returncode==0,(label,result.stderr[-3000:]);exact(game);checks.append(label)
    report={'status':'PASS','checks':checks,'public_releases_cataloged':len(coverage),'real_game_modified':False,'game_executed':False,'cli_sha256':sha(a.cli),'installer_sha256':sha(a.package/('AMS2 한국어 패치 오픈베타 '+a.version+'.exe'))}
    (a.output/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
