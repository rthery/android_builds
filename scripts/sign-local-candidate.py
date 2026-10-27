#!/usr/bin/env python3
"""Isolated local development-candidate packaging; never installs or publishes."""
import gzip,fcntl,getpass,hashlib,io,json,os,pathlib,re,shutil,subprocess,sys,tempfile,time,traceback,zipfile
import apk_signers,signing_profiles,target_files_meta
os.umask(0o077)
native=os.environ.get('EOS_NATIVE_PRESIGNED')=='1'
logpath='/signed/packaging.log' if native else '/signed/signing.log'
def run_logged(command,env,cwd=None):
 with open(logpath,'a',buffering=1) as log:
  process=subprocess.Popen(command,env=env,cwd=cwd,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
  for line in process.stdout:print(line,end='',flush=True);log.write(line)
  if process.wait():raise RuntimeError('Packaging subprocess failed; see '+logpath)
def stage(message):
 print(time.strftime('%H:%M:%S')+' '+message+'...',flush=True)
def check_mac_permissions(path,key_map):
 # A test certificate left in mac_permissions gives platform apps the default seinfo and they fail to start.
 test_certs=set()
 for source in key_map:
  if not source.startswith('build/make/target/product/security/'):continue
  pem=pathlib.Path('/otatools')/(source+'.x509.pem')
  if not pem.is_file():raise RuntimeError('Missing source certificate '+source)
  test_certs.add(subprocess.check_output(['openssl','x509','-in',str(pem),'-outform','DER']).hex())
 found=0
 with zipfile.ZipFile(path) as z:
  for name in z.namelist():
   if not name.endswith('mac_permissions.xml'):continue
   found+=1
   for signature in re.findall(r'signature="([0-9a-fA-F]+)"',z.read(name).decode()):
    if signature.lower() in test_certs:raise RuntimeError('Test certificate left in '+name)
 if not found:raise RuntimeError('No mac_permissions.xml in signed target-files')
def der(pem):return subprocess.check_output(['openssl','x509','-in',pem,'-outform','DER'])
def check_apex(path,apex_keys,payloads,allowed,env):
 # Container and payload keys of every APEX, and the signer of every APK inside its payload, must be ours.
 with zipfile.ZipFile(path) as z:
  names=set(z.namelist())
  for name,key in sorted(apex_keys.items()):
   stem='SYSTEM/apex/'+name.removesuffix('.apex')
   member=next(n for n in (stem+'.apex',stem+'.capex') if n in names)
   container=z.read(member);expected=[der(key+'.x509.pem')]
   if apk_signers.signer_certs(container)!=expected:raise RuntimeError('APEX container not signed by its key: '+member)
   apex=zipfile.ZipFile(io.BytesIO(container)).read('original_apex') if member.endswith('.capex') else container
   if member.endswith('.capex') and apk_signers.signer_certs(apex)!=expected:raise RuntimeError('Compressed APEX inner container not signed by its key: '+member)
   public=subprocess.check_output(['/otatools/bin/avbtool','extract_public_key','--key',payloads[name],'--output','/dev/stdout'],env=env)
   if zipfile.ZipFile(io.BytesIO(apex)).read('apex_pubkey')!=public:raise RuntimeError('APEX payload key mismatch: '+member)
   with tempfile.TemporaryDirectory(dir='/tmp') as work:
    pathlib.Path(work,'a.apex').write_bytes(apex)
    subprocess.run(['/otatools/bin/deapexer','--debugfs_path','/otatools/bin/debugfs_static','--fsckerofs_path','/otatools/bin/fsck.erofs','extract',work+'/a.apex',work+'/x'],env=env,check=True,stdout=subprocess.DEVNULL)
    for apk in pathlib.Path(work,'x').rglob('*.apk'):
     if not set(apk_signers.signer_certs(apk.read_bytes()))<=allowed:raise RuntimeError('APK in '+member+' not signed by a planned key: '+apk.name)
 print('All',len(apex_keys),'APEX containers, payloads and inner APKs carry planned keys.',flush=True)
def main():
 if os.environ.get('EOS_SIGNING_LOCK_HELD')!='1':
  lock=os.open('/lock/build.lock',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o644);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 input_path='/signed/pre-signed-target-files.zip' if native else '/input/target-files.zip'
 profile_name=os.environ.get('EOS_SIGNING_PROFILE','eos-t');detected,profile=signing_profiles.detect(input_path)
 if detected!=profile_name:raise RuntimeError('Input is '+detected+', not '+profile_name)
 target_files_meta.check(input_path,profile)
 if not native:
  for script,args in [('audit-signing.py',[input_path,'--output','/signed/inventory.json']),('plan-signing.py',['/signed/inventory.json','--keys','/keys','--profile',profile_name,'--output','/signed/signing-plan.json'])]:
   subprocess.run([sys.executable,'/tools/'+script,*args],check=True)
 plan=json.loads(pathlib.Path('/signed/signing-plan.json').read_text())
 groups=plan.get('groups',['android-release-v1','android-module-apps-v1']);keys_root=pathlib.PurePosixPath(plan.get('keys_root','/keys'));apex_keys=plan.get('apex_keys',{})
 if plan.get('profile','eos-t')!=profile_name or tuple(groups)!=profile['groups']:raise RuntimeError('Signing plan does not match the input profile')
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
  destinations={};key_groups={}
  for original in set(plan['key_map'].values())|set(apex_keys.values()):
   relative=pathlib.PurePosixPath(original).relative_to(keys_root)
   if relative.parts[0] not in groups or '..' in relative.parts:raise RuntimeError('Unknown key group')
   source=pathlib.Path('/keys',relative);dest=pathlib.Path(keydir,relative)
   dest.parent.mkdir(parents=True,exist_ok=True)
   for suffix in ('.pk8','.x509.pem'):shutil.copyfile(str(source)+suffix,str(dest)+suffix)
   destinations[original]=str(dest);key_groups[str(dest)]=relative.parts[0]
  mappings={source:destinations[dest] for source,dest in plan['key_map'].items()}
  apex_containers={name:destinations[key] for name,key in apex_keys.items()}
  releasekey=mappings['build/make/target/product/security/testkey']
  passwords={};payloads={}
  for group in groups:
   password=supplied[group] if supplied is not None else getpass.getpass(group+' key password (hidden): ')
   if not isinstance(password,str) or not password or password!=password.strip() or any(token in password for token in ('\r','\n','\x00',']]]')):
    raise RuntimeError('Password cannot be represented safely in Android password-file format')
   for value in set(destinations.values()):
    if key_groups[value]==group:
     result=subprocess.run(['openssl','pkcs8','-inform','DER','-in',value+'.pk8','-passin','stdin','-out','/dev/null'],input=(password+'\n').encode(),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
     if result.returncode:raise RuntimeError('Key password verification failed')
     passwords[value]=password
   for name,value in apex_containers.items():
    if key_groups[value]!=group:continue
    # avbtool takes no password: the APEX payload key is a plaintext copy in tmpfs, deleted with keydir.
    payloads[name]=value+'.pem'
    subprocess.run(['openssl','pkcs8','-inform','DER','-in',value+'.pk8','-passin','stdin','-out',payloads[name]],input=(password+'\n').encode(),check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  fd,pwpath=tempfile.mkstemp(dir='/dev/shm',prefix='key-passwords-')
  try:
   with os.fdopen(fd,'w') as out:
    for key,password in passwords.items():out.write('[[[ '+password+' ]]] '+key+'\n')
   if supplied is not None:supplied.clear()
   env={'HOME':'/tmp','LANG':'C.UTF-8','PATH':'/otatools/bin:/usr/bin:/bin','LD_LIBRARY_PATH':'/otatools/lib64','ANDROID_PW_FILE':pwpath,'EDITOR':'/bin/false','PYTHONUNBUFFERED':'1'}
   # On arm64, signapk loads the Conscrypt JNI built for arm64 instead of the x86 one in otatools.
   jni=['--signapk_shared_library_path',os.environ['EOS_SIGNAPK_JNI']] if os.environ.get('EOS_SIGNAPK_JNI') else []
   command=['/otatools/bin/sign_target_files_apks','-p','/otatools',*jni,'-s','/device/releasetools.py','-o']
   for source,dest in sorted(mappings.items()):command+=['-k',source+'='+dest]
   for name,dest in sorted(apex_containers.items()):command+=['-e',name+'='+dest,'--extra_apex_payload_key',name+'='+payloads[name]]
   command+=[input_path,'/signed/signed-target-files.zip']
   stage('Re-signing target-files and rebuilding images')
   # ReplaceCerts opens each source key relative to cwd and silently skips missing ones.
   run_logged(command,env,cwd='/otatools')
   check_mac_permissions('/signed/signed-target-files.zip',plan['key_map'])
   if apex_keys:check_apex('/signed/signed-target-files.zip',apex_containers,payloads,{der(v+'.x509.pem') for v in destinations.values()},env)
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
    extra=target_files_meta.parse_dictionary(target_files_meta.text(z,'META/misc_info.txt'),'META/misc_info.txt').get('extra_recovery_keys','').split()
    for name,keys in (('SYSTEM/etc/security/otacerts.zip',[]),('RECOVERY/RAMDISK/system/etc/security/otacerts.zip',extra)):
     wanted=sorted([expected]+[der('/otatools/'+key+'.x509.pem') for key in keys])
     with zipfile.ZipFile(io.BytesIO(z.read(name))) as certs:
      actual=sorted(subprocess.check_output(['openssl','x509','-outform','DER'],input=certs.read(entry)) for entry in certs.namelist())
     if actual!=wanted:raise RuntimeError('OTA trust roots mismatch in '+name)
   stage('Building and signing the OTA package')
   run_logged(['/otatools/bin/ota_from_target_files','-p','/otatools',*jni,'-s','/device/releasetools.py','-k',releasekey,'/signed/signed-target-files.zip','/signed/local-candidate.zip'],env)
   with open('/signed/local-candidate.zip','rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
   pathlib.Path('/signed/local-candidate.zip.sha256').write_text(digest+'  local-candidate.zip\n')
   print('Local candidate signed; OTA trust stores checked. Not installed, runtime tested or approved for publication.')
  finally:os.unlink(pwpath)
try:main()
except BaseException:
 with open(logpath,'a') as log:log.write(traceback.format_exc())
 raise
