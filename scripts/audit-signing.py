#!/usr/bin/env python3
"""Inventory shipped APK certificates, APEX format and OTA trust in target-files."""
import argparse,collections,hashlib,json,pathlib,shlex,zipfile
p=argparse.ArgumentParser(description=__doc__);p.add_argument('target_files',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path);a=p.parse_args()
partitions={'SYSTEM','SYSTEM_EXT','PRODUCT','VENDOR','ODM'}
with zipfile.ZipFile(a.target_files) as z:
 names=z.namelist(); apks=[n for n in names if n.endswith('.apk') and n.split('/')[0] in partitions]
 certs={}
 for line in z.read('META/apkcerts.txt').decode().splitlines():
  row=dict(item.split('=',1) for item in shlex.split(line));certs[row['name']]=row['certificate']
 shipped=collections.defaultdict(list);missing=[]
 for apk in apks:
  cert=certs.get(pathlib.PurePosixPath(apk).name)
  if cert is None: missing.append(apk)
  else: shipped[cert].append(apk)
 info=dict(line.split('=',1) for line in z.read('META/misc_info.txt').decode().splitlines() if '=' in line)
 with a.target_files.open('rb') as source: digest=hashlib.file_digest(source,'sha256').hexdigest()
 result={'target_files':a.target_files.name,'target_files_sha256':digest,'apk_count':len(apks),'certificates':dict(sorted(shipped.items())),'missing_apk_metadata':missing,'packaged_apex':[n for n in names if n.endswith(('.apex','.capex')) and n.split('/')[0] in partitions],'flattened_apex':sorted({n.split('/')[2] for n in names if n.startswith('SYSTEM/apex/') and len(n.split('/'))>3}),'image_signing':{k:v for k,v in info.items() if k.startswith(('avb','verity','ab_update','default_system_dev_certificate'))},'ota_trust_entries':[n for n in names if n.endswith('/otacerts.zip') or n.endswith('/res/keys')],'ota_keys':z.read('META/otakeys.txt').decode().split(),'status':'inventory only, not a signature or migration verification'}
 out=json.dumps(result,indent=2)+'\n'
 if a.output:a.output.write_text(out)
 else:print(out,end='')
 if missing:raise SystemExit('Shipped APKs missing certificate metadata')
