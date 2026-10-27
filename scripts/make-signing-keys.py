#!/usr/bin/env python3
"""Generate a password-encrypted key set for a signing profile, like development/tools/make_key.

Keys are made with OpenSSL in the pinned arm64 runtime image, offline. The password is asked
twice with hidden input and reaches the container over stdin only. APEX keys are RSA-4096 and
also serve as payload keys: the signer decrypts them to a tmpfs PEM at signing time.
"""
import argparse,getpass,json,os,pathlib,shlex,subprocess,sys,zipfile
from signing_profiles import PROFILES
INNER=r'''
import hashlib,json,os,pathlib,subprocess,sys
request=json.load(sys.stdin);password=request['password'];root=pathlib.Path('/out');fingerprints={}
def run(command,data=None):return subprocess.run(command,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
for key in request['keys']:
 prefix=root/key['name'];prefix.parent.mkdir(mode=0o700,exist_ok=True)
 if pathlib.Path(str(prefix)+'.pk8').exists() or pathlib.Path(str(prefix)+'.x509.pem').exists():sys.exit('Refusing to overwrite '+key['name'])
 plain='/dev/shm/key.pem'
 try:
  run(['openssl','genrsa','-f4','-out',plain,str(key['bits'])])
  run(['openssl','req','-new','-x509','-sha256','-key',plain,'-out',str(prefix)+'.x509.pem','-days','10000','-subj',key['subject']])
  run(['openssl','pkcs8','-in',plain,'-topk8','-v1','PBE-SHA1-3DES','-outform','DER','-out',str(prefix)+'.pk8','-passout','stdin'],(password+'\n').encode())
 finally:
  if os.path.exists(plain):os.unlink(plain)
 private=run(['openssl','pkey','-inform','DER','-in',str(prefix)+'.pk8','-passin','stdin','-pubout'],(password+'\n').encode())
 public=run(['openssl','x509','-in',str(prefix)+'.x509.pem','-pubkey','-noout'])
 if private!=public:sys.exit('Key and certificate differ for '+key['name'])
 fingerprints[key['name']]=hashlib.sha256(run(['openssl','x509','-in',str(prefix)+'.x509.pem','-outform','DER'])).hexdigest()
 print('generated',key['name'],flush=True)
(root/'fingerprints.json').write_text(json.dumps(fingerprints,indent=2)+'\n')
'''
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--profile',choices=sorted(k for k,v in PROFILES.items() if v['apex']),required=True)
p.add_argument('--target-files',type=pathlib.Path,required=True,help='Lists the APEX modules that need keys')
p.add_argument('--subject',default='/O=rthery Android builds/OU=LineageOS release signing/CN=')
p.add_argument('--password-stdin',action='store_true',help='Throwaway test sets only')
p.add_argument('output',type=pathlib.Path,help='New directory, named after the key group')
a=p.parse_args();profile=PROFILES[a.profile]
if not a.output.is_absolute() or a.output.exists() or a.output.name!=profile['groups'][0]:p.error('Absolute, new output directory named '+profile['groups'][0]+' required')
root=pathlib.Path(os.environ.get('EOS_WORKSPACE','/Volumes/eOS-Build'))
image=json.loads((root/'.local/signing-toolchain/runtime-arm64.json').read_text())['image']
with zipfile.ZipFile(a.target_files) as z:
 rows={row['name']:row for row in (dict(i.split('=',1) for i in shlex.split(line)) for line in filter(str.strip,z.read('META/apexkeys.txt').decode().splitlines()))}
 shipped={pathlib.PurePosixPath(n).name.removesuffix('.capex').removesuffix('.apex')+'.apex' for n in z.namelist() if n.startswith('SYSTEM/') and n.endswith(('.apex','.capex'))}
 apex=sorted(name.removesuffix('.apex') for name in shipped if rows[name]['private_key']!='PRESIGNED')
keys=[{'name':n,'bits':2048} for n in profile['core']]+[{'name':'apps/'+pathlib.PurePosixPath(s).name,'bits':2048} for s in profile['modules']]+[{'name':'apex/'+n,'bits':4096} for n in apex]
for key in keys:key['subject']=a.subject+key['name'].rsplit('/',1)[-1]
if a.password_stdin:password=sys.stdin.readline().rstrip('\n')
else:
 print(f'{len(keys)} keys for {a.profile} in {a.output}. One password for all of them; input is hidden.')
 password=getpass.getpass('New key password: ')
 if password!=getpass.getpass('Repeat it: '):sys.exit('Passwords differ')
if len(password)<16 or password!=password.strip() or any(t in password for t in ('\r','\n','\x00',']]]')):sys.exit('Use at least 16 characters, no surrounding spaces, no ]]]')
os.umask(0o077);a.output.mkdir(mode=0o700)
mapping={s+'.x509.pem':'apps/'+pathlib.PurePosixPath(s).name for s in profile['modules']}
(a.output/'source-mapping.json').write_text(json.dumps(mapping,indent=2)+'\n')
command=['docker','run','--rm','-i','--network','none','--user',f'{os.getuid()}:{os.getgid()}','--cap-drop','ALL','--security-opt','no-new-privileges','--tmpfs','/dev/shm:rw,nosuid,nodev,noexec,size=4m','--mount',f'type=bind,src={a.output},dst=/out',image,'python3','-c',INNER]
result=subprocess.run(command,input=json.dumps({'password':password,'keys':keys}),text=True)
password=None
if result.returncode:sys.exit('Key generation failed; delete '+str(a.output)+' before retrying')
print(f'Done: {len(keys)} encrypted keys and certificates in {a.output}; certificate SHA-256 in fingerprints.json.')
