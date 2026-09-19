"""Build an embedded ownership catalog from SHA256-verified official release ZIPs.

No version-pair rules: every manifest entry is verified against its ZIP payload.
Release metadata is obtained independently using gh api repos/choi3724/AMS2_KR/releases.
"""
import argparse, csv, hashlib, io, json, pathlib, zipfile, subprocess

def digest(data):
    return hashlib.sha256(data).hexdigest().upper()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--releases',type=pathlib.Path,required=True)
    p.add_argument('--archives',type=pathlib.Path,required=True)
    p.add_argument('--output',type=pathlib.Path,required=True)
    p.add_argument('--download-missing',action='store_true')
    a=p.parse_args()
    raw=a.releases.read_bytes()
    releases=json.loads(raw.decode('utf-16' if raw.startswith(b'\xff\xfe') else 'utf-8-sig'))
    records=set(); coverage=[]
    paths=list(a.archives.rglob('*.zip'))
    for release in releases:
        if release.get('draft'): continue
        for asset in release['assets']:
            if not asset['name'].endswith('.zip'): continue
            expected=asset.get('digest','').removeprefix('sha256:').upper()
            candidates=[x for x in paths if x.name==asset['name']]
            archive=next((x for x in candidates if digest(x.read_bytes())==expected),None)
            if archive is None and a.download_missing:
                dest=a.output/'official-archives'/release['tag_name']
                dest.mkdir(parents=True,exist_ok=True)
                subprocess.run(['gh','release','download',release['tag_name'],'--repo','choi3724/AMS2_KR','--pattern',asset['name'],'--dir',str(dest)],check=True)
                archive=dest/asset['name']
                if digest(archive.read_bytes())!=expected: raise ValueError('Downloaded asset digest mismatch')
            if archive is None: raise ValueError('Verified archive missing: '+asset['name'])
            count=0
            with zipfile.ZipFile(archive) as z:
                names={n.replace('\\','/'):n for n in z.namelist()}
                for name in names:
                    if '/manifest/direct-files' not in name or not name.endswith('.tsv'): continue
                    root=name.split('/manifest/')[0]
                    table=list(csv.DictReader(io.StringIO(z.read(names[name]).decode('utf-8-sig')),delimiter='\t'))
                    for row in table:
                        rel=row['relative_path'].replace('\\','/').lower()
                        if ':' in rel or any(v in ('','..','.') for v in rel.split('/')): raise ValueError(rel)
                        sha=row['sha256'].upper(); size=int(row['bytes'])
                        payloads=[n for n in names if n.lower().startswith(root.lower()+'/payload/') and n.lower().endswith('/'+rel)]
                        if not any(len(z.read(names[n]))==size and digest(z.read(names[n]))==sha for n in payloads):
                            raise ValueError('Payload mismatch: '+release['tag_name']+' '+rel)
                        records.add((rel,str(size),sha,row['role'],release['tag_name'],expected)); count+=1
            coverage.append({'tag':release['tag_name'],'asset':asset['name'],'sha256':expected,'entries':count})
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'ownership.tsv').write_text('relative_path\tbytes\tsha256\trole\trelease\tasset_sha256\n'+''.join('\t'.join(r)+'\n' for r in sorted(records)),encoding='utf-8')
    (a.output/'coverage.json').write_text(json.dumps(coverage,indent=2),encoding='utf-8')
    print(json.dumps({'releases':len(coverage),'records':len(records),'output':str(a.output)}))

if __name__=='__main__': main()
