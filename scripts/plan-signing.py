#!/usr/bin/env python3
"""Create a fail-closed signing plan for a flattened-APEX development target-files ZIP."""
import argparse,hashlib,json,pathlib,shlex,zipfile
p=argparse.ArgumentParser(description=__doc__);p.add_argument('inventory',type=pathlib.Path);p.add_argument('--keys',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
r=json.loads(a.inventory.read_text());root=a.keys
if r['missing_apk_metadata'] or r['packaged_apex']:p.error('Unsupported missing metadata or packaged APEX; audit required')
if any(k.startswith(('avb','verity')) for k in r['image_signing']):p.error('Image signing enabled; a separate verity/AVB plan is required')
module=json.loads((root/'android-module-apps-v1/source-mapping.json').read_text());mapping={}
core={'testkey':'releasekey','devkey':'releasekey','platform':'platform','shared':'shared','media':'media','networkstack':'networkstack','bluetooth':'bluetooth','sdk_sandbox':'sdk_sandbox'}
for cert in r['certificates']:
 if cert=='PRESIGNED':continue
 stem=cert.removesuffix('.x509.pem');name=pathlib.PurePosixPath(stem).name
 if stem.startswith('build/make/target/product/security/') and name in core:dest=root/'android-release-v1'/core[name]
 elif cert in module:dest=root/'android-module-apps-v1'/module[cert]
 else:p.error('Unreviewed certificate: '+cert)
 for suffix in ('.pk8','.x509.pem'):
  if not pathlib.Path(str(dest)+suffix).is_file():p.error('Missing signing material: '+str(dest)+suffix)
 mapping[stem]=str(dest)
plan={'status':'development signing plan; not release approval','target_files':r['target_files'],'target_files_sha256':r['target_files_sha256'],'key_map':mapping,'presigned_apks':r['certificates'].get('PRESIGNED',[]),'replace_ota_keys':True,'image_signing':'not enabled in audited input','notes':['Keep PRESIGNED third-party packages unchanged','For user builds regenerate plan with explicit verity signing','Validate actual signed APK certificates and both recovery/system OTA roots before flashing']}
a.output.write_text(json.dumps(plan,indent=2)+'\n');print('Signing plan created:',len(mapping),'key mappings; third-party PRESIGNED packages retained')
