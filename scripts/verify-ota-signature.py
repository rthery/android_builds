#!/usr/bin/env python3
"""Verify the whole-file signature of an OTA zip against one certificate.

Same footer parsing as check_ota_package_signature.py; the PKCS#7 check runs
through openssl with only the given certificate, so any other signer fails.
"""
import argparse,pathlib,subprocess,sys,tempfile,zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('package',type=pathlib.Path)
p.add_argument('cert',type=pathlib.Path,help='PEM certificate of the release key')
a=p.parse_args()

def fail(message):sys.exit('OTA signature check failed: '+message)

data=a.package.read_bytes()
footer=data[-6:]
if footer[2:4]!=b'\xff\xff':fail('no signature footer')
signature_start=footer[0]|footer[1]<<8
comment_size=footer[4]|footer[5]<<8
if data[-comment_size-22:-comment_size-18]!=b'PK\x05\x06':fail('end of central directory not where the footer says')
signed=data[:len(data)-comment_size-2]
signature=data[len(data)-signature_start:len(data)-6]
cert_pem=a.cert.read_bytes()
with zipfile.ZipFile(a.package) as z:
 if 'META-INF/com/android/otacert' in z.namelist() and z.read('META-INF/com/android/otacert').strip()!=cert_pem.strip():
  fail('META-INF/com/android/otacert differs from the expected certificate')
with tempfile.TemporaryDirectory() as tmp:
 tmp=pathlib.Path(tmp)
 (tmp/'signed').write_bytes(signed);(tmp/'sig.der').write_bytes(signature)
 result=subprocess.run(['openssl','cms','-verify','-binary','-inform','DER','-in',tmp/'sig.der','-content',tmp/'signed',
  '-certfile',a.cert,'-nointern','-noverify','-out','/dev/null'],capture_output=True,text=True)
 if result.returncode:fail(result.stderr.strip())
print(f'Whole package signature verified with {a.cert.name}')
