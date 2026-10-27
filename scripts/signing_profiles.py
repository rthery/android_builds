#!/usr/bin/env python3
"""Per-ROM signing profiles, selected from the target-files build properties."""
import re,zipfile
# Module app certificates of lineage-22.2, including the APKs inside APEX payloads, mapped to apps/<name>.
LINEAGE_22_2_MODULE_CERTS=('packages/modules/AdServices/adservices/apk/com.android.adservices.api','packages/modules/AppSearch/apk/com.android.appsearch.apk','packages/modules/Connectivity/service/ServiceConnectivityResources/resources-certs/com.android.connectivity.resources','packages/modules/HealthFitness/apk/com.android.healthconnect.controller','packages/modules/HealthFitness/backuprestore/com.android.health.connect.backuprestore','packages/modules/OnDevicePersonalization/federatedcompute/apk/com.android.federatedcompute','packages/modules/Permission/SafetyCenter/Resources/com.android.safetycenter.resources','packages/modules/Uwb/service/ServiceUwbResources/resources-certs/com.android.uwb.resources','packages/modules/Wifi/OsuLogin/certs/com.android.hotspot2.osulogin','packages/modules/Wifi/WifiDialog/certs/com.android.wifi.dialog','packages/modules/Wifi/service/ServiceWifiResources/resources-certs/com.android.wifi.resources')
PROFILES={
 # /e/OS T: flattened APEX, two key groups with their own passwords.
 'eos-t':{'sdk':'33','version':r'4\.[0-9]+(\.[0-9]+)?','tree':'src/android','pin':'current.json','groups':('android-release-v1','android-module-apps-v1'),'apex':False,
  'meta':(),'misc':{},'misc_add':{},'sha256_extra':False,'case_duplicates':()},
 # LineageOS 22.2: packaged APEX signed with apex/<name> keys; one key group and password.
 'lineage-22.2':{'sdk':'35','version':r'22\.2','tree':'src/lineage-22.2','pin':'current-lineage-22.2.json','groups':('lineage-release-v1',),'apex':True,
  'core':('releasekey','platform','shared','media','networkstack','bluetooth','sdk_sandbox','nfc'),'modules':LINEAGE_22_2_MODULE_CERTS,
  # fastboot-info.txt is only read by img_from_target_files; virtual_ab_cow_version and board_non_ab_ota_disable_compression are not read for non-A/B OTAs.
  # extra_recovery_keys: vendor/lineage makes recovery also trust the official LineageOS OTA certificate, read from the toolchain.
  'meta':('META/fastboot-info.txt',),'misc':{'virtual_ab_cow_version':'2','board_non_ab_ota_disable_compression':'true','avb_avbtool':'avbtool','extra_recovery_keys':'vendor/lineage/build/target/product/security/lineage'},
  # sign_target_files_apks signs APEX payloads with misc_info avb_avbtool, which the build writes only with BOARD_AVB_ENABLE;
  # every other reader is gated on an avb_*enable key, so the pre-signed copy gets the tool name and nothing else.
  'misc_add':{'avb_avbtool':'avbtool'},
  # soong_zip adds a SHA-256 extra field; libncurses ships terminfo names that differ only in case.
  'sha256_extra':True,'case_duplicates':('SYSTEM/system_ext/etc/terminfo/',)},
}
def build_props(path):
 with zipfile.ZipFile(path) as z:data=z.read('SYSTEM/build.prop')
 if any(not (32<=c<127 or c==10) for c in data):raise RuntimeError('Control or non-ASCII character in SYSTEM/build.prop')
 return dict(line.split('=',1) for line in data.decode('ascii').split('\n') if '=' in line and not line.lstrip().startswith('#'))
def detect(path):
 """Return (name, profile) for the target-files; refuse anything that is not exactly one known ROM."""
 props=build_props(path)
 found=[(name,p) for name,p in PROFILES.items() if props.get('ro.build.version.sdk')==p['sdk'] and re.fullmatch(p['version'],props.get('ro.lineage.build.version',''))]
 if len(found)!=1:raise RuntimeError('No signing profile for SDK %r, ROM version %r'%(props.get('ro.build.version.sdk'),props.get('ro.lineage.build.version')))
 return found[0]
if __name__=='__main__':
 import sys
 for argument in sys.argv[1:]:print(argument+': '+detect(argument)[0])
