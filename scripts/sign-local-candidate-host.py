#!/usr/bin/env python3
"""Native parallel APK signing followed by isolated Linux image/OTA packaging."""
import argparse,fcntl,getpass,json,os,pathlib,subprocess,sys,traceback
os.umask(0o077)
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('input',type=pathlib.Path);p.add_argument('output',type=pathlib.Path)
p.add_argument('--jobs',type=int,default=2)
a=p.parse_args();root=pathlib.Path(os.environ.get('EOS_WORKSPACE','/Volumes/eOS-Build'));tools=pathlib.Path(__file__).resolve().parent
if not a.input.is_absolute() or not a.input.is_file() or not a.output.is_absolute() or a.output.exists():p.error('Existing absolute input and new absolute output directory required')
if not 1<=a.jobs<=4:p.error('Use between 1 and 4 signing workers')
lock=(root/'.local/build-lock/build.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
a.output.mkdir(mode=0o700)
log=(a.output/'signing.log').open('a',buffering=1)
def run(command,**kwargs):
 child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,**kwargs)
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Signing stage failed; see signing.log')
try:
 run([sys.executable,str(tools/'audit-signing.py'),str(a.input),'--output',str(a.output/'inventory.json')])
 run([sys.executable,str(tools/'plan-signing.py'),str(a.output/'inventory.json'),'--keys',str(root/'.local/release-signing'),'--output',str(a.output/'signing-plan.json')])
 run([sys.executable,str(tools/'native-apk-sign.py'),'--input',str(a.input),'--plan',str(a.output/'signing-plan.json'),'--output',str(a.output/'pre-signed-target-files.zip'),'--check-only'])
 print('Waiting for the two signing passwords in this Terminal; input is hidden.',flush=True)
 passwords={group:getpass.getpass(group+' key password (hidden): ') for group in ('android-release-v1','android-module-apps-v1')}
 if not all(passwords.values()):raise RuntimeError('Empty passwords refused')
 if any(not isinstance(value,str) or not value or value!=value.strip() or any(token in value for token in ('\r','\n','\x00',']]]')) for value in passwords.values()):
  raise RuntimeError('Password cannot be represented safely in Android password-file format')
 # Passwords are sent over private stdin pipes, never argv or the log.
 command=[sys.executable,str(tools/'native-apk-sign.py'),'--input',str(a.input),'--plan',str(a.output/'signing-plan.json'),'--output',str(a.output/'pre-signed-target-files.zip'),'--jobs',str(a.jobs)]
 child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 child.stdin.write(json.dumps(passwords));child.stdin.close()
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Native APK signing failed; see signing.log')
 # Host holds the lock across both stages. Child skips reacquiring the same lock.
 command=['docker','run','--rm','-i','--platform','linux/amd64','--user','1000:1000','--cap-drop','ALL','--security-opt','no-new-privileges','--network','none','--tmpfs','/dev/shm:rw,nosuid,nodev,noexec,size=16m','-e','EOS_NATIVE_PRESIGNED=1','-e','EOS_SIGNING_PASSWORD_STDIN=1','-e','EOS_SIGNING_LOCK_HELD=1']
 for source,dest,readonly in [(root/'src/android','/android',True),(root/'.local/release-signing','/keys',True),(tools,'/tools',True),(a.output,'/signed',False),(root/'.local/build-lock','/lock',False)]:
  command+=['--mount',f'type=bind,src={source},dst={dest}'+(',readonly' if readonly else '')]
 command+=['--workdir','/android','--entrypoint','python3','registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84','/tools/sign-local-candidate.py']
 # Give Linux packaging its own log to avoid two writers to the host log.
 child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
 child.stdin.write(json.dumps(passwords));child.stdin.close();passwords.clear()
 for line in child.stdout:sys.stdout.write(line);sys.stdout.flush();log.write(line)
 if child.wait():raise RuntimeError('Linux packaging failed; see signing.log')
 print('Candidate ready for independent signature checks and device testing.')
except BaseException:
 log.write(traceback.format_exc());raise
finally:log.close()
