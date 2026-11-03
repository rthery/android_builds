#!/usr/bin/env python3
"""Signer certificates (DER) of an APK or APEX from its APK Signature Scheme v3 or v2 block.

Reads certificates only; it does not verify the signatures (apksigner or releasetools did).
"""
import struct
V2,V3=0x7109871a,0xf05368c0
def _sequence(data):
 position=0
 while position<len(data):
  length,=struct.unpack_from('<I',data,position);position+=4
  if position+length>len(data):raise ValueError('Truncated length-prefixed field')
  yield data[position:position+length];position+=length
def _signing_block(data):
 end=data.rfind(b'PK\x05\x06',max(0,len(data)-65557))
 if end<0:raise ValueError('No end of central directory')
 directory,=struct.unpack_from('<I',data,end+16)
 if data[directory-16:directory]!=b'APK Sig Block 42':raise ValueError('No APK signing block')
 size,=struct.unpack_from('<Q',data,directory-24)
 start=directory-size-8
 if start<0 or struct.unpack_from('<Q',data,start)[0]!=size:raise ValueError('Bad APK signing block size')
 pairs={};position=start+8
 while position<directory-24:
  length,=struct.unpack_from('<Q',data,position);kind,=struct.unpack_from('<I',data,position+8)
  pairs[kind]=data[position+12:position+8+length];position+=8+length
 return pairs
def signer_certs(data):
 """Return the first certificate of each signer, preferring v3 over v2."""
 pairs=_signing_block(data)
 block=pairs.get(V3) or pairs.get(V2)
 if block is None:raise ValueError('No v2 or v3 signature')
 certs=[]
 for signer in _sequence(next(_sequence(block))):
  signed_data=next(_sequence(signer))
  fields=_sequence(signed_data);next(fields)
  certs.append(next(_sequence(next(fields))))
 return certs
