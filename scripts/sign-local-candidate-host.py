#!/usr/bin/env python3
"""Native parallel APK signing followed by isolated Linux image/OTA packaging."""
import argparse,fcntl,getpass,hashlib,json,os,pathlib,re,shutil,subprocess,sys,time,traceback,zipfile
import signing_profiles,target_files_meta
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('input',type=pathlib.Path);p.add_argument('output',type=pathlib.Path)
p.add_argument('--jobs',type=int,default=4)
# Linux packaging runtime: arm64 runs Java natively (pinned image and Conscrypt JNI), amd64 is the previous all-Rosetta image.
p.add_argument('--runtime',choices=('arm64','amd64'),default='arm64')
p.add_argument('--keys',type=pathlib.Path,help='Key directory (default: the workspace release keys); for throwaway test sets')
a=p.parse_args();root=pathlib.Path(os.environ.get('EOS_WORKSPACE','/Volumes/eOS-Build'));tools=pathlib.Path(__file__).resolve().parent
if not a.input.is_absolute() or not a.input.is_file() or not a.output.is_absolute() or a.output.exists():p.error('Existing absolute input and new absolute output directory required')
if not 1<=a.jobs<=4:p.error('Use between 1 and 4 signing workers')
keys=a.keys or root/'.local/release-signing'
if not keys.is_absolute() or not keys.is_dir():p.error('Absolute key directory required')
profile_name,profile=signing_profiles.detect(a.input)
def pinned_toolchain():
 # Signing never runs tools from the Actions-writable out/ tree.
 base=root/'.local/signing-toolchain';pin=json.loads((base/profile['pin']).read_text())
 manifest=(base/(pin['toolchain']+'.json')).read_bytes()
 if hashlib.sha256(manifest).hexdigest()!=pin['manifest_sha256']:raise RuntimeError('Signing toolchain manifest does not match its pin')
 files=json.loads(manifest)['files'];top=base/pin['toolchain']
 present={str(f.relative_to(top)) for f in top.rglob('*') if f.is_symlink() or not f.is_dir()}
 if present!=set(files):raise RuntimeError('Signing toolchain has missing or extra files')
 for name,entry in files.items():
  path=top/name
  if 'link' in entry or path.is_symlink():
   if not path.is_symlink() or os.readlink(path)!=entry.get('link'):raise RuntimeError('Signing toolchain link changed: '+name)
   continue
  with path.open('rb') as source:
   if hashlib.file_digest(source,'sha256').hexdigest()!=entry['sha256']:raise RuntimeError('Signing toolchain file changed: '+name)
 return top
def device_releasetools():
 # Device extensions come from the source tree, never from the input target-files.
 if signing_profiles.detect(a.input)[0]!=profile_name:raise RuntimeError('Input profile changed after the password prompt')
 info=target_files_meta.check(a.input,profile)
 with zipfile.ZipFile(a.input) as z:
  embedded=z.read('META/releasetools.py') if 'META/releasetools.py' in z.namelist() else None
 extension=info.get('tool_extensions','')
 if not re.fullmatch(r'device/[a-z0-9_]+/[a-z0-9_]+',extension):raise RuntimeError('Unexpected tool_extensions in input')
 trusted=root/profile['tree']/extension/'releasetools.py'
 if embedded is not None and embedded!=trusted.read_bytes():raise RuntimeError('Input META/releasetools.py differs from '+extension+'/releasetools.py')
 return trusted
# The runner can write the lock directory: never follow a link it leaves there.
lock=os.open(root/'.local/build-lock/build.lock',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o644);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
# Builds take the same lock with Linux flock in OrbStack's VM, which a macOS flock does not see: hold it there too, until exit.
LOCKER="import fcntl,os,sys\nfd=os.open('/lock/build.lock',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o644)\ntry:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError:print('busy',flush=True);sys.exit(75)\nprint('locked',flush=True);sys.stdin.read()"
locker_image=json.loads((root/'.local/signing-toolchain/runtime-arm64.json').read_text())['image'] if a.runtime=='arm64' else 'registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84'
locker=subprocess.Popen(['docker','run','--rm','-i','--network','none','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--mount',f"type=bind,src={root/'.local/build-lock'},dst=/lock",'--entrypoint','python3',locker_image,'-c',LOCKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
if locker.stdout.readline().strip()!='locked':sys.exit('Another build holds the shared lock')
# Ask first so the user can leave during the checks; a failed check discards the passwords.
print(f'Signing profile {profile_name}. Enter the {len(profile["groups"])} signing password(s); input is hidden.',flush=True)
passwords={group:getpass.getpass(group+' key password (hidden): ') for group in profile['groups']}
if not all(passwords.values()):sys.exit('Empty passwords refused')
if any(value!=value.strip() or any(token in value for token in ('\r','\n','\x00',']]]')) for value in passwords.values()):
 sys.exit('Password cannot be represented safely in Android password-file format')
a.output.mkdir(mode=0o700)
# Every stage reads one private snapshot, since the input usually sits in the Actions-writable out/ tree.
snapshot=a.output/'input-target-files.zip'
if subprocess.run(['cp','-c',str(a.input),str(snapshot)],stderr=subprocess.DEVNULL).returncode:shutil.copyfile(a.input,snapshot)
a.input=snapshot
log=(a.output/'signing.log').open('a',buffering=1)
started=time.monotonic();timings={}
def stage_done(name,since):
 timings[name]=round(time.monotonic()-since,1);print(f'[timing] {name}: {timings[name]} s',flush=True)
def runtime_image():
 if a.runtime=='amd64':return ['--platform','linux/amd64'],'registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84',[]
 base=root/'.local/signing-toolchain';pin=json.loads((base/'runtime-arm64.json').read_text())
 # Image IDs are content hashes: running by ID runs exactly the pinned JDK and userland.
 image=pin['image']
 if subprocess.run(['docker','image','inspect','--format','{{.Id}}',image],stdout=subprocess.PIPE,text=True).stdout.strip()!=image:raise RuntimeError('Pinned arm64 runtime image missing; run install-signing-arm64.py')
 jni=base/(toolchain.name+'.arm64')
 with (jni/'libconscrypt_openjdk_jni.so').open('rb') as source:
  if hashlib.file_digest(source,'sha256').hexdigest()!=pin['jni'].get(toolchain.name):raise RuntimeError('arm64 Conscrypt JNI does not match its pin')
 if sorted(os.listdir(jni))!=['libconscrypt_openjdk_jni.so']:raise RuntimeError('Unexpected files next to the arm64 JNI')
 return ['--platform','linux/arm64','-e','EOS_SIGNAPK_JNI=/jni'],image,[(jni,'/jni',True)]
def run(command,**kwargs):
 child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,**kwargs)
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Signing stage failed; see signing.log')
try:
 toolchain=pinned_toolchain();releasetools=device_releasetools()
 print('Signing toolchain verified: '+toolchain.name,flush=True)
 run([sys.executable,str(tools/'audit-signing.py'),str(a.input),'--output',str(a.output/'inventory.json')])
 run([sys.executable,str(tools/'plan-signing.py'),str(a.output/'inventory.json'),'--keys',str(keys),'--profile',profile_name,'--output',str(a.output/'signing-plan.json')])
 run([sys.executable,str(tools/'native-apk-sign.py'),'--input',str(a.input),'--plan',str(a.output/'signing-plan.json'),'--output',str(a.output/'pre-signed-target-files.zip'),'--check-only'])
 # Passwords are sent over private stdin pipes, never argv or the log.
 command=[sys.executable,str(tools/'native-apk-sign.py'),'--input',str(a.input),'--plan',str(a.output/'signing-plan.json'),'--output',str(a.output/'pre-signed-target-files.zip'),'--jobs',str(a.jobs)]
 since=time.monotonic()
 child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 child.stdin.write(json.dumps(passwords));child.stdin.close()
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Native APK signing failed; see signing.log')
 stage_done('native_apk_signing',since)
 # Host holds the lock across both stages. Child skips reacquiring the same lock.
 platform_args,image,extra_mounts=runtime_image()
 command=['docker','run','--rm','-i',*platform_args,'-e','EOS_SIGNING_PROFILE='+profile_name,'--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--network','none','--tmpfs','/dev/shm:rw,nosuid,nodev,noexec,size=16m','-e','EOS_NATIVE_PRESIGNED=1','-e','EOS_SIGNING_PASSWORD_STDIN=1','-e','EOS_SIGNING_LOCK_HELD=1']
 for source,dest,readonly in [(toolchain,'/otatools',True),(releasetools,'/device/releasetools.py',True),(keys,'/keys',True),(tools,'/tools',True),(a.output,'/signed',False),(root/'.local/build-lock','/lock',False),*extra_mounts]:
  command+=['--mount',f'type=bind,src={source},dst={dest}'+(',readonly' if readonly else '')]
 command+=['--workdir','/signed','--entrypoint','python3',image,'/tools/sign-local-candidate.py']
 # Give Linux packaging its own log to avoid two writers to the host log.
 since=time.monotonic()
 child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 child.stdin.write(json.dumps(passwords));child.stdin.close();passwords.clear()
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Linux packaging failed; see signing.log')
 stage_done('linux_packaging_'+a.runtime,since);stage_done('total',started)
 (a.output/'timings.json').write_text(json.dumps({'profile':profile_name,'runtime':a.runtime,'seconds':timings},indent=1)+'\n')
 print('Candidate ready for independent signature checks and device testing.')
except BaseException:
 log.write(traceback.format_exc());raise
finally:
 log.close();locker.stdin.close();locker.wait()
