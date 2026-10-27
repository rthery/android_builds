#!/usr/bin/env python3
"""Write the Updater feed for one signed full OTA package.

Reads the signing output directory (signed-target-files.zip and the OTA zip),
checks that the package matches the signed build, and writes the feed JSON plus
the release asset name and checksum file. Uploading stays a manual step.
"""
import argparse,hashlib,json,pathlib,re,sys,zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('signing_dir',type=pathlib.Path)
p.add_argument('--device',required=True)
p.add_argument('--package',default='local-candidate.zip',help='OTA zip inside signing_dir')
p.add_argument('--releases-repo',default='rthery/android_builds-releases')
p.add_argument('--channel',default='stable')
p.add_argument('--current-feed',type=pathlib.Path,help='published feed; the new build must be newer')
p.add_argument('--out',type=pathlib.Path,required=True,help='output directory')
a=p.parse_args()

def fail(message):sys.exit('Refusing feed: '+message)

def props(data):
 values={}
 for line in data.decode().splitlines():
  if line and not line.startswith('#') and '=' in line:
   key,value=line.split('=',1);values[key]=value
 return values

package=a.signing_dir/a.package
with zipfile.ZipFile(a.signing_dir/'signed-target-files.zip') as z:system=props(z.read('SYSTEM/build.prop'))
with zipfile.ZipFile(package) as z:metadata=props(z.read('META-INF/com/android/metadata'))

version=system['ro.lineage.version']
filename='e-'+version+'.zip'
timestamp=system['ro.build.date.utc']
checks={
 'device':(system['ro.lineage.device'],a.device),
 'OTA device':(metadata.get('pre-device'),a.device),
 'OTA type':(metadata.get('ota-type'),'BLOCK'),
 'OTA timestamp':(metadata.get('post-timestamp'),timestamp),
 'OTA incremental':(metadata.get('post-build-incremental'),system['ro.build.version.incremental']),
 'OTA SDK':(metadata.get('post-sdk-level'),system['ro.build.version.sdk']),
 'OTA security patch':(metadata.get('post-security-patch-level'),system['ro.build.version.security_patch']),
}
for name,(actual,expected) in checks.items():
 if actual!=expected:fail(f'{name} is {actual!r}, expected {expected!r}')
if system['ro.build.tags']!='release-keys' or not metadata.get('post-build','').endswith('/release-keys'):fail('build is not signed with release keys')
if not re.fullmatch(r'\d+\.\d+(\.\d+)?',system['ro.lineage.build.version']):fail('unexpected ro.lineage.build.version')
if not re.fullmatch(r'\d+(\.\d+){0,2}',system['ro.build.version.release']):fail('unexpected Android version')

sha256=hashlib.sha256();md5=hashlib.md5()
with package.open('rb') as f:
 for block in iter(lambda:f.read(1<<20),b''):sha256.update(block);md5.update(block)
entry={
 'datetime':int(timestamp),'timestamp':int(timestamp),
 'filename':filename,'id':sha256.hexdigest(),'md5sum':md5.hexdigest(),
 'romtype':system['ro.lineage.releasetype'].lower(),'channel':a.channel,
 'size':package.stat().st_size,
 'url':f'https://github.com/{a.releases_repo}/releases/download/{version}/{filename}',
 'version':system['ro.lineage.build.version'],'display_version':version,
 'android_version':system['ro.build.version.release'],'api_level':int(system['ro.build.version.sdk']),
}
if a.current_feed:
 for old in json.loads(a.current_feed.read_text())['response']:
  if int(old['datetime'])>=entry['datetime']:fail(f'{old["filename"]} is not older than this build')

a.out.mkdir(parents=True,exist_ok=True)
feed=a.out/f'{a.device}-{entry["romtype"]}.json'
feed.write_text(json.dumps({'error':None,'id':None,'response':[entry]},indent=1)+'\n')
(a.out/(filename+'.sha256')).write_text(f'{entry["id"]}  {filename}\n')
print(f'{feed}\nRelease tag {version}: upload {package} as {filename} with {filename}.sha256')
