#!/usr/bin/env python3
"""Check a locally signed release candidate and write independent-verification.json.

Runs the checks the publish job relies on, against the build run's release.json:
the signing input is the attested target-files, the OTA whole-file signature
verifies with the pinned toolchain and against the committed release
certificate, every fingerprint is release-keys for this build number, the
updater script writes only boot and system, no radio or test certificates are
left, and the recovery copies match. Any failure stops without writing the file.
"""
import argparse,hashlib,io,json,pathlib,re,subprocess,sys,tempfile,zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('signed',type=pathlib.Path,help='output directory of sign-local-candidate.sh')
p.add_argument('release',type=pathlib.Path,help='release.json of the build run')
p.add_argument('--cert',type=pathlib.Path,required=True,help='committed release certificate (releasekey.x509.pem)')
p.add_argument('--workspace',type=pathlib.Path,default=pathlib.Path(__file__).resolve().parents[3])
a=p.parse_args()
a.signed,a.release,a.cert,a.workspace=(x.resolve() for x in (a.signed,a.release,a.cert,a.workspace))
recipe=pathlib.Path(__file__).resolve().parent

def fail(message):sys.exit('Verification failed: '+message)
def sha256(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def der(pem):return subprocess.run(['openssl','x509','-outform','DER'],input=pem,capture_output=True,check=True).stdout

info=json.loads(a.release.read_text())
report=json.loads((a.signed/'native-signing-report.json').read_text())
if report['input_sha256']!=info['target_files_sha256']:fail('signed from another target-files')
ota=a.signed/'local-candidate.zip'
ota_sha=sha256(ota)
if (a.signed/'local-candidate.zip.sha256').read_text().split()[0]!=ota_sha:fail('local-candidate.zip.sha256 does not match')

base=a.workspace/'.local/signing-toolchain'
pin=json.loads((base/'current-lineage-22.2.json').read_text())
toolchain=base/pin['toolchain']
image=json.loads((base/'runtime-arm64.json').read_text())['image']
# releasetools still imports the removed imp module; the stub covers its one call.
stub=pathlib.Path(tempfile.mkdtemp())
stub.chmod(0o755)
(stub/'imp.py').write_text('import importlib.util as _u\ndef load_source(n,p):\n s=_u.spec_from_file_location(n,p);m=_u.module_from_spec(s);s.loader.exec_module(m);return m\n')
check=subprocess.run(['docker','run','--rm','--network','none','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges',
 '-v',f'{toolchain}:/otatools:ro','-v',f'{ota}:/ota.zip:ro','-v',f'{a.cert}:/cert.pem:ro','-v',f'{stub}:/stub:ro',
 '-e','PYTHONPATH=/stub:/otatools/releasetools','-e','PATH=/otatools/bin:/usr/bin:/bin','--entrypoint','python3',image,
 '/otatools/releasetools/check_ota_package_signature.py','/cert.pem','/ota.zip'],capture_output=True,text=True)
(stub/'imp.py').unlink();stub.rmdir()
if 'Whole package signature VERIFIED' not in check.stdout:fail('check_ota_package_signature: '+(check.stdout+check.stderr).strip()[-300:])
subprocess.run([sys.executable,'-I',recipe/'verify-ota-signature.py',ota,a.cert],check=True,stdout=subprocess.DEVNULL)

z=zipfile.ZipFile(ota)
meta=dict(l.split('=',1) for l in z.read('META-INF/com/android/metadata').decode().splitlines() if '=' in l)
expected=info['fingerprint'].replace('test-keys','release-keys')
if meta.get('post-build')!=expected:fail(f'post-build {meta.get("post-build")} is not {expected}')
if meta.get('ota-type')!='BLOCK':fail('not a block OTA')
script=z.read('META-INF/com/google/android/updater-script').decode()
targets=sorted({t.rsplit('/',1)[-1] for t in re.findall(r'/dev/block/[\w/.-]+',script)})
if targets!=['boot','system']:fail(f'updater-script writes {targets}')
backups=re.findall(r'run_program\("/tmp/install/bin/backuptool\.sh", "(backup|restore)"',script)
if ':user/' not in expected and backups!=['backup','restore']:fail(f'updater-script runs backuptool {backups}, so addon.d (GApps) would be lost')

signed=zipfile.ZipFile(a.signed/'signed-target-files.zip')
names=set(signed.namelist())
if any(n.startswith('RADIO/') for n in names):fail('RADIO/ entries in the signed target-files')
release=der(a.cert.read_bytes())
test_dir=toolchain/'build/make/target/product/security'
test={der(f.read_bytes()).hex() for f in test_dir.glob('*.x509.pem')}
left=0
for n in sorted(x for x in names if x.endswith('mac_permissions.xml')):
 left+=len({s.lower() for s in re.findall(r'signature="([0-9a-fA-F]+)"',signed.read(n).decode())}&test)
if left:fail(f'{left} test certificate(s) left in mac_permissions')
def otacerts(name):
 inner=zipfile.ZipFile(io.BytesIO(signed.read(name)))
 return [der(inner.read(e)) for e in inner.namelist()]
if release not in otacerts('SYSTEM/etc/security/otacerts.zip'):fail('system otacerts lack the release key')
if release not in otacerts('RECOVERY/RAMDISK/system/etc/security/otacerts.zip'):fail('recovery otacerts lack the release key')
image_bytes=signed.read('IMAGES/recovery.img')
if image_bytes!=signed.read('SYSTEM/vendor/etc/recovery.img'):fail('the recovery copy in system/vendor differs')
m=re.search(r'EMMC:[^:]+:(\d+):([0-9a-f]{40})',signed.read('SYSTEM/vendor/bin/install-recovery.sh').decode())
if not (m and int(m[1])==len(image_bytes) and m[2]==hashlib.sha1(image_bytes).hexdigest()):fail('install-recovery.sh does not match the recovery image')
prints=set()
for n in names:
 if re.search(r'(build\.prop|prop\.default)$',n):
  prints|=set(re.findall(r'^ro\.(?:\w+\.)?build\.fingerprint=(.*)$',signed.read(n).decode(errors='replace'),re.M))
if prints!={expected}:fail(f'fingerprints {sorted(prints)}')

result={'build_run':info['run'],'target_files':info['target_files'],'target_files_sha256':info['target_files_sha256'],
 'ota':ota.name,'ota_sha256':ota_sha,'ota_bytes':ota.stat().st_size,'toolchain':pin['toolchain'],
 'check_ota_package_signature':'Whole package signature VERIFIED (pinned arm64 runtime)','post_build':expected,
 'post_timestamp':int(meta.get('post-timestamp','0')),'ota_type':'BLOCK','updater_script_targets':targets,'addon_d_backup':bool(backups),
 'radio_entries':0,'mac_permissions_test_certs_left':0,'recovery_copies':'match','verified_by':'scripts/verify-signed-candidate.py'}
(a.signed/'independent-verification.json').write_text(json.dumps(result,indent=1)+'\n')
print(f'Verified {ota.name} {ota_sha}')
