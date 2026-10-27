#!/usr/bin/env python3
"""Create a fail-closed signing plan for a development target-files ZIP."""
import argparse,hashlib,json,pathlib,shlex,zipfile
from signing_profiles import PROFILES
p=argparse.ArgumentParser(description=__doc__);p.add_argument('inventory',type=pathlib.Path);p.add_argument('--keys',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--profile',choices=sorted(PROFILES),default='eos-t');a=p.parse_args()
r=json.loads(a.inventory.read_text());root=a.keys;profile=PROFILES[a.profile]
if r['missing_apk_metadata'] or r['packaged_apex'] and not profile['apex']:p.error('Unsupported missing metadata or packaged APEX; audit required')
if any(k.startswith(('avb','verity')) for k in r['image_signing']):p.error('Image signing enabled; a separate verity/AVB plan is required')
core={'testkey':'releasekey','devkey':'releasekey','platform':'platform','shared':'shared','media':'media','networkstack':'networkstack','bluetooth':'bluetooth','sdk_sandbox':'sdk_sandbox'}
mapping={};apex_keys={}
def require(dest):
 for suffix in ('.pk8','.x509.pem'):
  if not pathlib.Path(str(dest)+suffix).is_file():p.error('Missing signing material: '+str(dest)+suffix)
 return str(dest)
if profile['apex']:
 # APKs inside APEX payloads are not in the inventory: map every core and module identity up front.
 group=root/profile['groups'][0]
 names={'testkey':'releasekey',**{name:name for name in profile['core'] if name!='releasekey'}}
 for name,dest in names.items():mapping['build/make/target/product/security/'+name]=require(group/dest)
 for stem in profile['modules']:mapping[stem]=require(group/'apps'/pathlib.PurePosixPath(stem).name)
 packaged={pathlib.PurePosixPath(n).name.removesuffix('.capex').removesuffix('.apex')+'.apex' for n in r['packaged_apex']}
 if not packaged<=set(r['apex_keys']):p.error('Packaged APEX missing from META/apexkeys.txt')
 for name in sorted(packaged):
  if r['apex_keys'][name]['private_key']=='PRESIGNED':continue
  apex_keys[name]=require(group/'apex'/name.removesuffix('.apex'))
for cert in r['certificates']:
 if cert=='PRESIGNED':continue
 stem=cert.removesuffix('.x509.pem');name=pathlib.PurePosixPath(stem).name
 if stem in mapping:continue
 if profile['apex']:p.error('Unreviewed certificate: '+cert)
 module=json.loads((root/'android-module-apps-v1/source-mapping.json').read_text())
 if stem.startswith('build/make/target/product/security/') and name in core:dest=root/'android-release-v1'/core[name]
 elif cert in module:dest=root/'android-module-apps-v1'/module[cert]
 else:p.error('Unreviewed certificate: '+cert)
 mapping[stem]=require(dest)
plan={'status':'development signing plan; not release approval','profile':a.profile,'groups':list(profile['groups']),'keys_root':str(root),'target_files':r['target_files'],'target_files_sha256':r['target_files_sha256'],'key_map':mapping,'apex_keys':apex_keys,'misc_info_additions':profile['misc_add'],'presigned_apks':r['certificates'].get('PRESIGNED',[]),'replace_ota_keys':True,'image_signing':'not enabled in audited input','notes':['Keep PRESIGNED third-party packages unchanged','For user builds regenerate plan with explicit verity signing','Validate actual signed APK certificates and both recovery/system OTA roots before flashing']}
a.output.write_text(json.dumps(plan,indent=2)+'\n');print('Signing plan created:',len(mapping),'key mappings,',len(apex_keys),'APEX keys; third-party PRESIGNED packages retained')
