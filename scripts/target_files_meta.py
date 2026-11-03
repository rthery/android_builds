#!/usr/bin/env python3
"""Fail-closed check of the target-files metadata that releasetools reads; parses it exactly as releasetools does."""
import collections,posixpath,re,stat,struct,sys,zipfile
from signing_profiles import PROFILES,detect
# Exact misc_info keys this pipeline supports; an unknown key may make the tools run or read something else.
MISC_KEYS={'recovery_api_version','fstab_version','blocksize','boot_size','boot_images','recovery_size','recovery_mount_options','tool_extensions','default_system_dev_certificate','mkbootimg_args','recovery_mkbootimg_args','mkbootimg_version_args','mkbootimg_init_args','multistage_support','blockimgdiff_versions','full_recovery_image','system_size','system_selinux_fc','building_system_image','userdata_size','userdata_selinux_fc','building_userdata_image','cache_fs_type','cache_size','cache_selinux_fc','building_cache_image','oem_selinux_fc','building_oem_image','ext_mkuserimg','fs_type','extfs_sparse_flag','erofs_sparse_flag','squashfs_sparse_flag','f2fs_sparse_flag','root_dir','allow_non_ab','lpmake','super_metadata_device','vintf_enforce','vintf_include_empty_vendor_sku','xz_ramdisks'}
TOOL_KEYS={'ext_mkuserimg':'mkuserimg_mke2fs','lpmake':'lpmake'}
PATH_KEYS={'system_selinux_fc','userdata_selinux_fc','cache_selinux_fc','oem_selinux_fc','root_dir'}
# Every META entry releasetools may read; others (dynamic partitions, postinstall, AVB, A/B, base_fs) change what it does.
META_ENTRIES={'META/','META/apex_info.pb','META/apexkeys.txt','META/apkcerts.txt','META/boot_filesystem_config.txt','META/file_contexts.bin','META/filesystem_config.txt','META/misc_info.txt','META/otakeys.txt','META/recovery_filesystem_config.txt','META/releasetools.py','META/root_filesystem_config.txt'}
# mkbootimg inputs outside RAMDISK/; vendor_boot, init_boot and ramdisk fragments are not supported.
BOOT_ENTRIES={'','base','cmdline','kernel','pagesize'}
BOOT_TEXT={'base','cmdline','pagesize'}
# Top-level folders of a bullhead target-files; others (BOOTABLE_IMAGES, VENDOR_BOOT, INIT_BOOT, PREBUILT_IMAGES, RADIO...) change what releasetools builds or ships.
TOP_DIRS={'BOOT','IMAGES','INSTALL','META','OTA','RECOVERY','ROOT','SYSTEM'}
IMAGE_ENTRIES={'','boot.img','cache.img','recovery.img','system.img','system.map','userdata.img'}
# Files releasetools opens or writes by path in the extracted tree; no symlink may sit on them or their folders.
# The RAMDISK/etc/recovery.fstab fallbacks (etc is a link to /system/etc) are only read when RAMDISK/system/etc/recovery.fstab is missing, which check() refuses.
PROTECTED_PATHS=('SYSTEM/build.prop','SYSTEM/etc/build.prop','RECOVERY/RAMDISK/system/etc/recovery.fstab','BOOT/RAMDISK/system/etc/recovery.fstab','SYSTEM/vendor/etc/recovery-resource.dat','SYSTEM/vendor/etc/recovery.img','SYSTEM/vendor/bin/install-recovery.sh','SYSTEM/etc/recovery-resource.dat','SYSTEM/etc/recovery.img','SYSTEM/bin/install-recovery.sh')
PROTECTED_LINKS={'/'.join(path.split('/')[:i]) for path in PROTECTED_PATHS for i in range(2,path.count('/')+2)}
# Symlinks are kept as links in images and ramdisks; anywhere else releasetools would follow them.
LINK_PREFIXES=('SYSTEM/','ROOT/','BOOT/RAMDISK/','RECOVERY/RAMDISK/')
def check_entry(z,info,profile):
 # releasetools extracts with Info-ZIP unzip, which honours Unicode path extra fields (0x7075) and the UTF-8 flag that
 # zipfile reads differently: only zip64 extras, plain ASCII names and the data-descriptor flag are accepted.
 if any(not 32<=ord(c)<127 for c in info.filename):raise RuntimeError('Non-ASCII target-files entry name '+repr(info.filename))
 if info.flag_bits&~0x8:raise RuntimeError('Unsupported zip flags on '+info.filename)
 z.fp.seek(info.header_offset);header=z.fp.read(30)
 if len(header)!=30 or header[:4]!=b'PK\x03\x04':raise RuntimeError('Bad local header for '+info.filename)
 name_length,extra_length=struct.unpack('<HH',header[26:30])
 local_name=z.fp.read(name_length);local_extra=z.fp.read(extra_length)
 if local_name!=info.filename.encode('ascii'):raise RuntimeError('Local and central names differ for '+info.filename)
 for extra in (info.extra,local_extra):
  position=0
  while position<len(extra):
   if position+4>len(extra):raise RuntimeError('Malformed extra field on '+info.filename)
   kind,length=struct.unpack('<HH',extra[position:position+4]);position+=4+length
   if position>len(extra):raise RuntimeError('Malformed extra field on '+info.filename)
   # soong_zip's SHA-256 field: signature 0x9514 and a digest, ignored by unzip and zipfile.
   if kind==0x4967 and profile['sha256_extra'] and length==34 and extra[position-34:position-32]==b'\x14\x95':continue
   if kind!=0x0001:raise RuntimeError('Unsupported extra field 0x%04x on %s'%(kind,info.filename))
 mode=(info.external_attr>>16)&0o170000
 if mode not in (0,stat.S_IFREG,stat.S_IFDIR,stat.S_IFLNK):raise RuntimeError('Unsupported entry type on '+info.filename)
 if mode==stat.S_IFLNK and not info.filename.startswith(LINK_PREFIXES):raise RuntimeError('Symlink outside image trees: '+info.filename)
 if mode==stat.S_IFLNK and info.filename in PROTECTED_LINKS:raise RuntimeError('Symlink on a path releasetools opens: '+info.filename)
 return mode==stat.S_IFLNK
def text(z,name):
 # Printable ASCII and \n only: no \r, \v, \f, \x1c-\x1e, \x85 or U+2028/2029, so splitlines(), text-mode reads and split('\n') agree.
 data=z.read(name)
 if any(not (32<=c<127 or c==10) for c in data):raise RuntimeError('Control or non-ASCII character in '+name)
 return data.decode('ascii')
def parse_dictionary(content,name):
 # Same as common.LoadDictionaryFromLines, but a line without '=' or a repeated key is refused instead of skipped or overwritten.
 info={}
 for line in content.split('\n'):
  line=line.strip()
  if not line or line.startswith('#'):continue
  if '=' not in line:raise RuntimeError('Line without = in '+name)
  key,value=line.split('=',1)
  if key in info:raise RuntimeError('Repeated key in '+name+': '+key)
  info[key]=value
 return info
def check_misc_info(info,profile):
 for key,value in info.items():
  if key in profile['misc']:
   if value!=profile['misc'][key]:raise RuntimeError('Unexpected misc_info '+key)
   continue
  if key not in MISC_KEYS:raise RuntimeError('Unsupported misc_info key '+key)
  if key in TOOL_KEYS and value!=TOOL_KEYS[key]:raise RuntimeError('Unexpected misc_info '+key)
  if key=='xz_ramdisks' and value!='true':raise RuntimeError('Unexpected misc_info '+key)
  if key=='default_system_dev_certificate' and value!='build/make/target/product/security/testkey':raise RuntimeError('Unexpected misc_info '+key)
  # Build-time paths; the tools redirect them into the input, so they must stay plain out/ paths.
  if key in PATH_KEYS and not (re.fullmatch(r'out/target/product/[a-z0-9_]+/[A-Za-z0-9_./-]+',value) and '..' not in value.split('/')):
   raise RuntimeError('Unexpected misc_info '+key)
  # Tool arguments may hold flags and numbers only, never paths.
  if key.endswith('_args') and not all(re.fullmatch(r'--[a-z_]+|[0-9A-Za-z.-]+',token) for token in value.split()):
   raise RuntimeError('Unexpected misc_info '+key)
def check(path,profile=None):
 """Validate the input's metadata against a signing profile (default eos-t) and return its misc_info dictionary."""
 profile=profile or PROFILES['eos-t']
 with zipfile.ZipFile(path) as z:
  names=z.namelist()
  for name in names:
   # Allowlists compare raw names, so every name must be canonical: no '/x', '\\', '', '.' or '..' parts.
   path=name[:-1] if name.endswith('/') else name
   if not path or path.startswith('/') or '\\' in name or any(part in ('','.','..') for part in path.split('/')) or posixpath.normpath(path)!=path:
    raise RuntimeError('Non-canonical target-files entry '+repr(name))
  # Case-insensitive, so a META/X variant cannot shadow META/x on a case-insensitive extraction.
  # Profiles may allow case-only variants of regular files below listed folders, never in META/.
  folded=collections.defaultdict(list)
  for name in names:folded[name.rstrip('/').lower()].append(name)
  allowed=profile['case_duplicates']
  for variants in folded.values():
   if len(variants)>1 and not (allowed and all(name.startswith(allowed) and not name.endswith('/') for name in variants)):raise RuntimeError('Repeated entry names in target-files')
  links={info.filename for info in z.infolist() if check_entry(z,info,profile)}
  fstab='RECOVERY/RAMDISK/system/etc/recovery.fstab'
  if fstab not in names or fstab in links:raise RuntimeError('Missing '+fstab)
  # unzip defers symlinks, but an entry below a link name would still resolve through the link once extracted.
  for name in names:
   parts=name.rstrip('/').split('/')
   if any('/'.join(parts[:i]) in links for i in range(1,len(parts))):raise RuntimeError('Entry below a symlink: '+name)
  for name in names:
   top,_,rest=name.partition('/')
   if name.startswith('META/') and name not in META_ENTRIES and name not in profile['meta']:raise RuntimeError('Unsupported target-files entry '+name)
   if top not in TOP_DIRS or '/RAMDISK_FRAGMENTS/' in '/'+name:raise RuntimeError('Unsupported target-files entry '+name)
   if top=='IMAGES' and rest not in IMAGE_ENTRIES:raise RuntimeError('Unsupported target-files entry '+name)
   if top in ('BOOT','RECOVERY') and not rest.startswith('RAMDISK/') and rest not in BOOT_ENTRIES:raise RuntimeError('Unsupported target-files entry '+name)
   if name.startswith('META/') and name.endswith('.txt') or top in ('BOOT','RECOVERY') and rest in BOOT_TEXT:text(z,name)
  for top in ('BOOT','RECOVERY'):
   for arg in BOOT_TEXT:
    name=top+'/'+arg
    # mkbootimg gets the content minus trailing newlines as one argument.
    if name in names and '\n' in text(z,name).rstrip('\n'):raise RuntimeError('Multi-line '+name)
  if text(z,'META/otakeys.txt').split():raise RuntimeError('META/otakeys.txt must be empty: the OTA key comes from the signer')
  for name in ('META/apkcerts.txt','META/apexkeys.txt'):text(z,name)
  for name in ('SYSTEM/build.prop','SYSTEM/etc/build.prop'):
   # releasetools follows 'import' lines to other files by path; builds here have none.
   if name in names and any(line.strip().startswith('import') for line in text(z,name).split('\n')):raise RuntimeError('import statement in '+name)
  info=parse_dictionary(text(z,'META/misc_info.txt'),'META/misc_info.txt')
 check_misc_info(info,profile)
 return info
if __name__=='__main__':
 for argument in sys.argv[1:]:name,profile=detect(argument);check(argument,profile);print('Metadata accepted ('+name+'): '+argument)
