#!/usr/bin/env python3
"""Tamper cases for target_files_meta; run: python3 -m unittest test_target_files_meta (from scripts/)."""
import pathlib,re,stat,struct,tempfile,unittest,zipfile
import target_files_meta
MISC='''recovery_api_version=3
fstab_version=2
blocksize=131072
boot_images=boot.img
xz_ramdisks=true
tool_extensions=device/lge/bullhead
default_system_dev_certificate=build/make/target/product/security/testkey
mkbootimg_args=--ramdisk_offset 0x02000000 --tags_offset 0x01E00000
system_selinux_fc=out/target/product/bullhead/obj/ETC/file_contexts.bin_intermediates/file_contexts.bin
root_dir=out/target/product/bullhead/root
ext_mkuserimg=mkuserimg_mke2fs
super_metadata_device=
'''
def entries(**changes):
 files={'META/misc_info.txt':MISC,'META/otakeys.txt':'\n','META/apkcerts.txt':'name="A.apk" certificate="PRESIGNED" private_key=""\n','META/apexkeys.txt':'','META/releasetools.py':'','BOOT/cmdline':'console=ttyHSL0\n','BOOT/base':'0x00000000\n','BOOT/pagesize':'4096\n','BOOT/kernel':'','BOOT/RAMDISK/init':'','RECOVERY/RAMDISK/system/etc/recovery.fstab':'/system ext4 /dev/block/x\n','RECOVERY/cmdline':'console=ttyHSL0\n','SYSTEM/build.prop':''}
 files.update(changes)
 return {name:content for name,content in files.items() if content is not None}
class MetaTest(unittest.TestCase):
 def check(self,infos=(),patch=None,**changes):
  with tempfile.NamedTemporaryFile(suffix='.zip') as handle:
   with zipfile.ZipFile(handle.name,'w') as z:
    for name,content in entries(**changes).items():z.writestr(name,content.encode('utf-8') if isinstance(content,str) else content)
    for info,content in infos:z.writestr(info,content)
   if patch:
    data=bytearray(pathlib.Path(handle.name).read_bytes());patch(data);pathlib.Path(handle.name).write_bytes(data)
   return target_files_meta.check(handle.name,self.profile)
 profile=None
 def refused(self,infos=(),patch=None,**changes):
  with self.assertRaises(RuntimeError):self.check(infos,patch,**changes)
 def test_baseline_accepted(self):
  self.assertEqual(self.check()['tool_extensions'],'device/lge/bullhead')
 def test_parsed_like_releasetools(self):
  info=self.check(**{'META/misc_info.txt':'# comment\n  blocksize=4096  \n\n'+MISC.replace('blocksize=131072\n','')})
  self.assertEqual(info['blocksize'],'4096')
 def test_line_separators_refused(self):
  # splitlines() breaks on these, releasetools' split('\n') does not (and text-mode reads turn \r into \n).
  for separator in ('\r','\x0b','\x0c','\x1c','\x1d','\x1e','\x85',' ',' '):
   with self.subTest(separator=repr(separator)):
    self.refused(**{'META/misc_info.txt':MISC+'vintf_enforce=true'+separator+'avb_enable=true\n'})
 def test_other_controls_refused(self):
  for char in ('\x00','\t','\x7f','\xe9'):
   with self.subTest(char=repr(char)):self.refused(**{'META/misc_info.txt':MISC+'fs_type=ext4'+char+'\n'})
 def test_line_without_equals_refused(self):
  self.refused(**{'META/misc_info.txt':MISC+'avb_enable\n'})
 def test_repeated_key_refused(self):
  self.refused(**{'META/misc_info.txt':MISC+'ext_mkuserimg=mkuserimg_mke2fs\n'})
 def test_unknown_key_after_strip_refused(self):
  self.refused(**{'META/misc_info.txt':MISC+'   avb_enable=true\n'})
 def test_unexpected_values_refused(self):
  for line in ('ext_mkuserimg=/tmp/x\n','root_dir=out/target/product/bullhead/../../x\n','mkbootimg_init_args=--kernel /tmp/k\n','xz_ramdisks=false\n'):
   key=line.split('=')[0]
   misc=''.join(l+'\n' for l in MISC.splitlines() if not l.startswith(key+'='))+line
   with self.subTest(line=line):self.refused(**{'META/misc_info.txt':misc})
 def test_extra_meta_entries_refused(self):
  for name in ('META/dynamic_partitions_info.txt','META/postinstall_config.txt','META/ab_partitions.txt','META/vbmeta_digest.txt','META/system_base_fs.txt','META/liblz4.so'):
   with self.subTest(name=name):self.refused(**{name:''})
 def test_ramdisk_fragments_and_vendor_boot_refused(self):
  for name in ('VENDOR_BOOT/RAMDISK_FRAGMENTS/dlkm/mkbootfs_args','VENDOR_BOOT/vendor_cmdline','INIT_BOOT/RAMDISK/init','BOOT/RAMDISK_FRAGMENTS/x/prebuilt_ramdisk','BOOT/dtb','RECOVERY/second'):
   with self.subTest(name=name):self.refused(**{name:''})
 def test_boot_args_refused(self):
  self.refused(**{'BOOT/cmdline':'console=ttyHSL0\rskip_initramfs\n'})
  self.refused(**{'RECOVERY/pagesize':'4096\n2048\n'})
 def test_otakeys_must_be_empty(self):
  self.refused(**{'META/otakeys.txt':'build/make/target/product/security/testkey\n'})
 def test_apkcerts_separator_refused(self):
  self.refused(**{'META/apkcerts.txt':'name="A.apk" certificate="PRESIGNED" private_key=""\rname="B.apk" certificate="x" private_key=""\n'})
 def test_non_canonical_names_refused(self):
  for name in ('/META/dynamic_partitions_info.txt','META\\ab_partitions.txt','./META/ab_partitions.txt','META/./ab_partitions.txt','META/../META/ab_partitions.txt','META//ab_partitions.txt','SYSTEM//build.prop','SYSTEM/./x','//','.'):
   with self.subTest(name=name):self.refused(**{name:''})
 def test_case_variants_refused(self):
  for name in ('META/MISC_INFO.txt','meta/misc_info.txt','System/build.prop'):
   with self.subTest(name=name):self.refused(**{name:''})
  self.refused(**{'META/':'','META':''})
 def test_unicode_path_extra_refused(self):
  # Info-ZIP unzip would extract this as META/ab_partitions.txt; zipfile sees SYSTEM/x.
  for where in ('central','local'):
   info=zipfile.ZipInfo('SYSTEM/x')
   field=b'\x01'+struct.pack('<I',zipfile.crc32(b'SYSTEM/x'))+b'META/ab_partitions.txt'
   extra=struct.pack('<HH',0x7075,len(field))+field
   if where=='central':info.extra=extra
   with self.subTest(where=where):
    if where=='central':self.refused([(info,'')])
    else:self.refused([(info,'')],patch=lambda data:self.add_local_extra(data,b'SYSTEM/x',extra))
 def header(self,data,signature,name_at,name):
  # Offset of the local (PK\x03\x04, name at +30) or central (PK\x01\x02, name at +46) header for name.
  offset=-1
  while True:
   offset=data.index(signature,offset+1)
   length_at=26 if name_at==30 else 28;name_length=struct.unpack('<H',data[offset+length_at:offset+length_at+2])[0]
   if bytes(data[offset+name_at:offset+name_at+name_length])==name:return offset,name_length
 def add_local_extra(self,data,name,extra):
  offset,name_length=self.header(data,b'PK\x03\x04',30,name)
  data[offset+28:offset+30]=struct.pack('<H',len(extra));data[offset+30+name_length:offset+30+name_length]=extra
  # Later headers moved: rewrite the central directory offsets.
  for match in re.finditer(b'PK\x01\x02',bytes(data)):
   position=match.start()+42;value=struct.unpack('<I',data[position:position+4])[0]
   if value>offset:data[position:position+4]=struct.pack('<I',value+len(extra))
  end=bytes(data).rindex(b'PK\x05\x06')+16
  data[end:end+4]=struct.pack('<I',struct.unpack('<I',data[end:end+4])[0]+len(extra))
 def test_utf8_flag_and_non_ascii_refused(self):
  def set_flag(data):
   offset,_=self.header(data,b'PK\x01\x02',46,b'SYSTEM/build.prop')
   data[offset+9]|=0x08
  self.refused(patch=set_flag)
  self.refused(**{'SYSTEM/caf\xe9':''})
 def test_local_name_mismatch_refused(self):
  self.refused(patch=lambda data:data.__setitem__(slice(data.index(b'SYSTEM/build.prop'),data.index(b'SYSTEM/build.prop')+6),b'SYSTEX'))
 def test_symlinks(self):
  def link(name):
   info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;return info,'/etc/passwd'
  self.check([link('SYSTEM/bin/sh'),link('RECOVERY/RAMDISK/bin')])
  for name in ('META/misc_info.txt','META/apkcerts.txt','BOOT/cmdline','RECOVERY/kernel','IMAGES/boot.img','OTA/bin/updater'):
   with self.subTest(name=name):self.refused([link(name)],**{name:None})
  self.refused([link('SYSTEM/lib')],**{'SYSTEM/lib/x.so':''})
 def test_top_level_and_images_allowlist(self):
  for name in ('BOOTABLE_IMAGES/boot.img','RADIO/modem.img','VENDOR/build.prop','PREBUILT_IMAGES/dtbo.img','IMAGES/vbmeta.img','IMAGES/vendor_boot.img','top.txt'):
   with self.subTest(name=name):self.refused(**{name:''})
  self.check(**{'IMAGES/boot.img':'','OTA/bin/updater':'','INSTALL/bin/backuptool.sh':''})
 def test_symlinks_on_read_paths_refused(self):
  def link(name):
   info=zipfile.ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16;return info,'/etc'
  for name in ('SYSTEM/etc','SYSTEM/vendor','SYSTEM/vendor/etc','SYSTEM/vendor/bin','SYSTEM/bin','RECOVERY/RAMDISK/system','RECOVERY/RAMDISK/system/etc','BOOT/RAMDISK/system/etc'):
   with self.subTest(name=name):self.refused([link(name)])
  self.refused([link('SYSTEM/build.prop')],**{'SYSTEM/build.prop':None})
  self.refused([link('RECOVERY/RAMDISK/system/etc/recovery.fstab')],**{'RECOVERY/RAMDISK/system/etc/recovery.fstab':None})
  self.check([link('RECOVERY/RAMDISK/etc')])
  self.refused(**{'RECOVERY/RAMDISK/system/etc/recovery.fstab':None})
 def test_build_prop_import_refused(self):
  self.refused(**{'SYSTEM/build.prop':'ro.a=b\nimport /system/../META/misc_info.prop\n'})
  self.refused(**{'SYSTEM/etc/build.prop':'ro.a=b\rimport /system/x.prop\n'})
 def test_special_files_refused(self):
  info=zipfile.ZipInfo('SYSTEM/fifo');info.create_system=3;info.external_attr=(stat.S_IFIFO|0o644)<<16
  self.refused([(info,'')])
 def test_missing_misc_info_refused(self):
  with self.assertRaises(KeyError):self.check(**{'META/misc_info.txt':None})
def sha256_extra(signature=b'\x14\x95',length=34):
 return struct.pack('<HH',0x4967,length)+signature+bytes(length-2)
class Lineage222Test(MetaTest):
 profile=target_files_meta.PROFILES['lineage-22.2']
 def test_a15_additions_accepted(self):
  info=zipfile.ZipInfo('SYSTEM/x');info.extra=sha256_extra()
  self.check([(info,b'')],**{'META/fastboot-info.txt':'version 1\n','META/misc_info.txt':MISC+'virtual_ab_cow_version=2\nboard_non_ab_ota_disable_compression=true\nextra_recovery_keys=vendor/lineage/build/target/product/security/lineage\n',
   'SYSTEM/system_ext/etc/terminfo/h/hp2621A':'','SYSTEM/system_ext/etc/terminfo/h/hp2621a':''})
 def test_a15_additions_bounded(self):
  for signature,length in ((b'\x00\x00',34),(b'\x14\x95',36)):
   info=zipfile.ZipInfo('SYSTEM/x');info.extra=sha256_extra(signature,length)
   with self.subTest(length=length):self.refused([(info,b'')])
  for line in ('virtual_ab_cow_version=3','board_non_ab_ota_disable_compression=false','ab_update=true','extra_recovery_keys=build/make/target/product/security/testkey','extra_recovery_keys=vendor/lineage/build/target/product/security/lineage /tmp/x'):
   with self.subTest(line=line):self.refused(**{'META/misc_info.txt':MISC+line+'\n'})
  for name in ('META/liblz4.so','META/update_engine_config.txt','META/ab_partitions.txt'):
   with self.subTest(name=name):self.refused(**{name:''})
  self.refused(**{'SYSTEM/etc/terminfo/h/hpA':'','SYSTEM/etc/terminfo/h/hpa':''})
class EosTAdditionsRefusedTest(MetaTest):
 def test_a15_additions_refused(self):
  info=zipfile.ZipInfo('SYSTEM/x');info.extra=sha256_extra()
  self.refused([(info,b'')])
  self.refused(**{'META/fastboot-info.txt':''})
  self.refused(**{'META/misc_info.txt':MISC+'extra_recovery_keys=vendor/lineage/build/target/product/security/lineage\n'})
  self.refused(**{'SYSTEM/system_ext/etc/terminfo/h/hp2621A':'','SYSTEM/system_ext/etc/terminfo/h/hp2621a':''})
if __name__=='__main__':unittest.main()
