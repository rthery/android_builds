#!/usr/bin/env python3
"""Print one line per file (type, sha256, path) of a directory, then a hash of those lines.

Type is what Git keeps: link, executable or regular file. Dot entries at the
top (.git) are skipped, as extract_utils keeps them.
"""
import hashlib,os,pathlib,stat,sys

top=pathlib.Path(sys.argv[1])
lines=[]
for path in sorted(top.rglob('*')):
 relative=path.relative_to(top)
 if relative.parts[0].startswith('.'):continue
 mode=path.lstat().st_mode
 if stat.S_ISDIR(mode):continue
 if stat.S_ISLNK(mode):kind,digest='l',hashlib.sha256(os.readlink(path).encode()).hexdigest()
 else:
  with path.open('rb') as f:kind,digest='x' if mode&0o111 else 'f',hashlib.file_digest(f,'sha256').hexdigest()
 lines.append(f'{kind} {digest} {relative}\n')
sys.stdout.writelines(lines)
print('tree',hashlib.sha256(''.join(lines).encode()).hexdigest())
