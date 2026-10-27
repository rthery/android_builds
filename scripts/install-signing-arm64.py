#!/usr/bin/env python3
"""Build and pin the arm64 packaging runtime and, for one profile, its arm64 Conscrypt JNI.

Needs network once for the image builds. The JNI is compiled offline from the profile's
tree (external/boringssl, external/conscrypt), the same sources as its pinned otatools.
"""
import argparse,hashlib,json,os,pathlib,subprocess,tempfile
from signing_profiles import PROFILES
os.umask(0o022)
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',choices=sorted(PROFILES),required=True);a=p.parse_args()
root=pathlib.Path(os.environ.get('EOS_WORKSPACE','/Volumes/eOS-Build'));base=root/'.local/signing-toolchain';here=pathlib.Path(__file__).resolve().parent/'signing-arm64'
profile=PROFILES[a.profile];toolchain=json.loads((base/profile['pin']).read_text())['toolchain']
def build(dockerfile):
 out=subprocess.run(['docker','build','--platform','linux/arm64','-q','-f',str(here/dockerfile),str(here)],check=True,stdout=subprocess.PIPE,text=True).stdout.strip()
 if not out.startswith('sha256:'):raise RuntimeError('Unexpected image id '+out)
 return out
runtime=build('Dockerfile');builder=build('Dockerfile.jni')
java=subprocess.run(['docker','run','--rm','--network','none',runtime,'java','-version'],check=True,stderr=subprocess.PIPE,text=True).stderr.strip()
tree=root/profile['tree']
with tempfile.TemporaryDirectory() as out:
 mounts=[]
 for sub in ('external/boringssl','external/conscrypt'):mounts+=['--mount',f'type=bind,src={tree/sub},dst=/tree/{sub},readonly']
 subprocess.run(['docker','run','--rm','--network','none','--user','1000:1000',*mounts,'--mount',f'type=bind,src={here},dst=/cmake,readonly','--mount',f'type=bind,src={out},dst=/out',builder,'bash','-c',
  'cmake -S /cmake -B /tmp/b -G Ninja -DTREE=/tree -DJDK=/usr/lib/jvm/java-21-openjdk-arm64 -DCMAKE_BUILD_TYPE=Release >/tmp/log 2>&1 && ninja -C /tmp/b >>/tmp/log 2>&1 && cp /tmp/b/libconscrypt_openjdk_jni.so /out/ || { tail -40 /tmp/log; exit 1; }'],check=True)
 data=(pathlib.Path(out)/'libconscrypt_openjdk_jni.so').read_bytes()
digest=hashlib.sha256(data).hexdigest()
target=base/(toolchain+'.arm64');target.mkdir(mode=0o755,exist_ok=True)
lib=target/'libconscrypt_openjdk_jni.so'
if lib.exists():lib.chmod(0o644)
lib.write_bytes(data);lib.chmod(0o444)
pin_path=base/'runtime-arm64.json'
pin=json.loads(pin_path.read_text()) if pin_path.exists() else {'jni':{}}
pin.update(image=runtime,java_version=java);pin['jni'][toolchain]=digest
pin_path.write_text(json.dumps(pin,indent=1)+'\n')
print(f'Runtime {runtime}\n{java}\nJNI for {a.profile} ({toolchain[:12]}): {digest}\nPinned in {pin_path}')
