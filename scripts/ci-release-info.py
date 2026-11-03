#!/usr/bin/env python3
"""Write release.json for a CI target-files: hashes, build properties and provenance."""
import argparse,hashlib,json,pathlib,re,zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('target_files',type=pathlib.Path)
p.add_argument('--run',required=True)
p.add_argument('--commit',required=True)
p.add_argument('--build-number',required=True)
p.add_argument('--vendor-revision',required=True)
p.add_argument('--out',type=pathlib.Path,required=True)
a=p.parse_args()

def props(data):
 return dict(line.split('=',1) for line in data.decode().splitlines() if line and not line.startswith('#') and '=' in line)

with a.target_files.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
with zipfile.ZipFile(a.target_files) as z:
 system=props(z.read('SYSTEM/build.prop'))
 fingerprints={f'{name} {key}':value for name in z.namelist() if name.endswith('build.prop')
  for key,value in props(z.read(name)).items() if re.fullmatch(r'ro\.(\w+\.)?build\.fingerprint',key)}
# A target-files rerun without installclean leaves some partitions on the old build number.
if not fingerprints or len(set(fingerprints.values()))!=1 or a.build_number not in next(iter(fingerprints.values())):
 raise SystemExit(f'Partition fingerprints disagree or miss the build number: {fingerprints}')
info={
 'run':a.run,'commit':a.commit,'build_number':a.build_number,'vendor_blobs_revision':a.vendor_revision,
 'target_files':a.target_files.name,'target_files_sha256':digest,'fingerprint':next(iter(fingerprints.values())),
 'lineage_version':system.get('ro.lineage.version'),'build_date_utc':system.get('ro.build.date.utc'),
 'security_patch':system.get('ro.build.version.security_patch'),
}
a.out.write_text(json.dumps(info,indent=1)+'\n')
print(json.dumps(info,indent=1))
