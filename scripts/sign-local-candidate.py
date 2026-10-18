#!/usr/bin/env python3
"""Isolated local development-candidate packaging; never installs or publishes."""
import gzip,fcntl,getpass,hashlib,io,json,os,pathlib,shutil,subprocess,sys,tempfile,traceback,zipfile
os.umask(0o077)
native=os.environ.get('EOS_NATIVE_PRESIGNED')=='1'
logpath='/signed/packaging.log' if native else '/signed/signing.log'
def run_logged(command,env):
 with open(logpath,'a',buffering=1) as log:
  process=subprocess.Popen(command,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  for line in process.stdout:print(line,end='',flush=True);log.write(line)
  if process.wait():raise RuntimeError('Packaging subprocess failed; see '+logpath)
def main():
 if os.environ.get('EOS_SIGNING_LOCK_HELD')!='1':
  lock=open('/lock/build.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 input_path='/signed/pre-signed-target-files.zip' if native else '/input/target-files.zip'
 if not native:
  for script,args in [('audit-signing.py',[input_path,'--output','/signed/inventory.json']),('plan-signing.py',['/signed/inventory.json','--keys','/keys','--output','/signed/signing-plan.json'])]:
   subprocess.run([sys.executable,'/tools/'+script,*args],check=True)
 plan=json.loads(pathlib.Path('/signed/signing-plan.json').read_text())
 if native:
  report=json.loads(pathlib.Path('/signed/native-signing-report.json').read_text())
  with open(input_path,'rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
  if report['output_sha256']!=actual or report['input_sha256']!=plan['target_files_sha256']:
   raise RuntimeError('Native signing input/report hash mismatch')
  inventory=json.loads(pathlib.Path('/signed/inventory.json').read_text())
  if len(report['apks'])!=inventory['apk_count'] or not all(entry['signature_verified'] for entry in report['apks']):
   raise RuntimeError('Incomplete native APK verification report')
 supplied=json.load(sys.stdin) if os.environ.get('EOS_SIGNING_PASSWORD_STDIN')=='1' else None
 with tempfile.TemporaryDirectory(dir='/dev/shm',prefix='signing-keys-') as keydir:
  # Upstream ZipWrite chmods/utimes certificate files: use disposable encrypted-key/cert copies.
  destinations={}
  for original in set(plan['key_map'].values()):
   path=pathlib.Path(original);group=path.parent.name
   if group not in ('android-release-v1','android-module-apps-v1'):raise RuntimeError('Unknown key group')
   source=pathlib.Path('/keys')/group/path.name;dest=pathlib.Path(keydir)/group/path.name
   dest.parent.mkdir(parents=True,exist_ok=True)
   for suffix in ('.pk8','.x509.pem'):shutil.copyfile(str(source)+suffix,str(dest)+suffix)
   destinations[original]=str(dest)
  mappings={source:destinations[dest] for source,dest in plan['key_map'].items()}
  releasekey=str(pathlib.Path(keydir)/'android-release-v1/releasekey')
  passwords={}
  for group in ('android-release-v1','android-module-apps-v1'):
   password=supplied[group] if supplied is not None else getpass.getpass(group+' key password (hidden): ')
   if not isinstance(password,str) or not password or password!=password.strip() or any(token in password for token in ('\r','\n','\x00',']]]')):
    raise RuntimeError('Password cannot be represented safely in Android password-file format')
   for value in set(mappings.values()):
    if '/'+group+'/' in value:
     result=subprocess.run(['openssl','pkcs8','-inform','DER','-in',value+'.pk8','-passin','stdin','-out','/dev/null'],input=(password+'\n').encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     if result.returncode:raise RuntimeError('Key password verification failed')
     passwords[value]=password
  fd,pwpath=tempfile.mkstemp(dir='/dev/shm',prefix='key-passwords-')
  try:
   with os.fdopen(fd,'w') as out:
    for key,password in passwords.items():out.write('[[[ '+password+' ]]] '+key+'\n')
   if supplied is not None:supplied.clear()
   env=os.environ.copy();env.update(ANDROID_PW_FILE=pwpath,EDITOR='/bin/false',LD_LIBRARY_PATH='/android/out/host/linux-x86/lib64')
   env['PATH']='/android/out/host/linux-x86/bin:'+env['PATH']
   command=['/android/out/host/linux-x86/bin/sign_target_files_apks','-o']
   for source,dest in sorted(mappings.items()):command+=['-k',source+'='+dest]
   command+=[input_path,'/signed/signed-target-files.zip']
   run_logged(command,env)
   if native:
    with zipfile.ZipFile('/signed/signed-target-files.zip') as signed:
     for entry in report['apks']:
      with signed.open(entry['path']) as apk:
       stream=gzip.GzipFile(fileobj=apk) if entry['path'].endswith('.gz') else apk
       actual=hashlib.file_digest(stream,'sha256').hexdigest()
      if actual!=entry['signed_payload_sha256']:raise RuntimeError('APK changed during Linux packaging: '+entry['path'])
    print('All native APK signatures preserved through target-files packaging.',flush=True)
   expected=subprocess.check_output(['openssl','x509','-in',releasekey+'.x509.pem','-outform','DER'])
   with zipfile.ZipFile('/signed/signed-target-files.zip') as z:
    for name in ('SYSTEM/etc/security/otacerts.zip','RECOVERY/RAMDISK/system/etc/security/otacerts.zip'):
     with zipfile.ZipFile(io.BytesIO(z.read(name))) as certs:
      if len(certs.namelist())!=1:raise RuntimeError('Unexpected OTA trust roots')
      actual=subprocess.check_output(['openssl','x509','-outform','DER'],input=certs.read(certs.namelist()[0]))
      if actual!=expected:raise RuntimeError('OTA certificate mismatch')
   run_logged(['/android/out/host/linux-x86/bin/ota_from_target_files','-k',releasekey,'/signed/signed-target-files.zip','/signed/local-candidate.zip'],env)
   with open('/signed/local-candidate.zip','rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
   pathlib.Path('/signed/local-candidate.zip.sha256').write_text(digest+'  local-candidate.zip\n')
   print('Local candidate signed; OTA trust stores checked. Not installed, runtime tested or approved for publication.')
  finally:os.unlink(pwpath)
try:main()
except BaseException:
 with open(logpath,'a') as log:log.write(traceback.format_exc())
 raise
