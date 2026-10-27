#!/usr/bin/env python3
"""Unpack a trusted otatools.zip into a read-only, hash-pinned signing toolchain."""
import argparse,hashlib,json,os,pathlib,stat,sys,zipfile
from signing_profiles import PROFILES
os.umask(0o022)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('otatools',type=pathlib.Path)
p.add_argument('--profile',choices=sorted(PROFILES),default='eos-t',help='Pins the toolchain for this profile only')
p.add_argument('--root',type=pathlib.Path,default=pathlib.Path(os.environ.get('EOS_WORKSPACE','/Volumes/eOS-Build'))/'.local/signing-toolchain')
a=p.parse_args()
with a.otatools.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
target=a.root/digest
if target.exists():p.error('Toolchain already installed: '+str(target))
a.root.mkdir(mode=0o700,parents=True,exist_ok=True)
files={}
with zipfile.ZipFile(a.otatools) as z:
 for info in z.infolist():
  name=pathlib.PurePosixPath(info.filename)
  if name.is_absolute() or '..' in name.parts:sys.exit('Unsafe path in otatools.zip: '+info.filename)
  mode=info.external_attr>>16
  if info.is_dir():continue
  dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True)
  if stat.S_ISLNK(mode):
   # Only sibling links, e.g. bin/dump.f2fs -> fsck.f2fs.
   link=z.read(info).decode()
   if '/' in link or link in ('','.','..'):sys.exit('Unsafe symlink in otatools.zip: '+info.filename)
   dest.symlink_to(link);files[str(name)]={'link':link};continue
  data=z.read(info);dest.write_bytes(data)
  executable=bool(mode&0o111)
  dest.chmod(0o555 if executable else 0o444)
  files[str(name)]={'sha256':hashlib.sha256(data).hexdigest(),'executable':executable}
for name,entry in files.items():
 if 'link' in entry and name.rsplit('/',1)[0]+'/'+entry['link'] not in files and entry['link'] not in files:sys.exit('Dangling symlink in otatools.zip: '+name)
for directory in sorted((d for d in target.rglob('*') if d.is_dir() and not d.is_symlink()),key=lambda d:len(d.parts),reverse=True):directory.chmod(0o555)
target.chmod(0o555)
manifest=json.dumps({'otatools_sha256':digest,'files':dict(sorted(files.items()))},indent=1).encode()
(a.root/(digest+'.json')).write_bytes(manifest)
pin={'toolchain':digest,'manifest_sha256':hashlib.sha256(manifest).hexdigest()}
(a.root/PROFILES[a.profile]['pin']).write_text(json.dumps(pin,indent=1)+'\n')
print(f'Installed {len(files)} files in {target}; pinned in {a.root/PROFILES[a.profile]["pin"]}')
