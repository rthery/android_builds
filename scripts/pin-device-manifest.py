#!/usr/bin/env python3
"""Pin a device manifest and changes.json from a synced tree's `repo manifest -r` output.

Fork projects (entries with a repository in the existing changes.json) are
pointed at their personal fork at the given branch tip. Their base is the
revision the synced manifest asked for (repo's m/<manifest branch> ref).
"""
import argparse,json,pathlib,subprocess,sys
import xml.etree.ElementTree as ET

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('resolved',type=pathlib.Path,help='output of repo manifest -r')
p.add_argument('device_dir',type=pathlib.Path,help='e.g. devices/bullhead')
p.add_argument('--tree',type=pathlib.Path,required=True,help='synced source tree')
p.add_argument('--branch',required=True,help='fork branch, e.g. eos-4.4-t')
p.add_argument('--manifest-branch',required=True,help='repo manifest branch, e.g. v4.4-t')
a=p.parse_args()

def git(path,*args):
 return subprocess.run(['git','-C',str(a.tree/path),*args],check=True,capture_output=True,text=True).stdout.strip()

old=json.loads((a.device_dir/'changes.json').read_text())
forks={e['path']:e for e in old if 'repository' in e}
kept={e['path']:e for e in old if 'repository' not in e}
old_root=ET.parse(a.device_dir/'manifest.xml').getroot()
old_projects={x.get('path'):x for x in old_root.iter('project')}

root=ET.parse(a.resolved).getroot()
remotes={r.get('name'):r for r in root.iter('remote')}
default_remote=root.find('default').get('remote')
for name in ('e-priv','private'):
 if name in remotes and not any(x.get('remote')==name for x in root.iter('project')):root.remove(remotes[name])

changes=[];seen=set()
for project in root.iter('project'):
 path=project.get('path')
 if path in kept:
  # Keep the published recipe for projects that are not pinned to the tree, e.g. extracted vendor blobs.
  replacement=old_projects[path]
  project.attrib.clear();project.attrib.update(replacement.attrib)
  changes.append(kept[path]);seen.add(path);continue
 if path not in forks:continue
 entry=forks[path]
 remote=remotes[project.get('remote') or default_remote]
 upstream_url=remote.get('fetch').rstrip('/')+'/'+project.get('name')
 base=git(path,'rev-parse','refs/remotes/m/'+a.manifest_branch+'^{commit}')
 tip=git(path,'rev-parse','refs/heads/'+a.branch)
 if git(path,'merge-base',base,tip)!=base:sys.exit(f'{path}: {a.branch} is not based on the manifest revision {base}')
 commits=git(path,'rev-list','--reverse',f'{base}..{tip}').split()
 if not commits:sys.exit(f'{path}: no commits on top of {base}')
 repository=entry['repository']
 project.set('name',repository.removeprefix('https://github.com/'))
 project.set('remote','github');project.set('revision',tip)
 project.set('upstream','refs/heads/'+a.branch);project.set('dest-branch','refs/heads/'+a.branch)
 project.attrib.pop('clone-depth',None)
 changes.append({'path':path,'upstream':upstream_url,'base':base,'revision':tip,'branch':a.branch,'repository':repository,'commits':commits})
 seen.add(path)

missing=set(forks)|set(kept)
missing-=seen
if missing:sys.exit('Projects missing from the resolved manifest: '+', '.join(sorted(missing)))
order={e['path']:i for i,e in enumerate(old)}
changes.sort(key=lambda e:order[e['path']])
ET.indent(root,space='  ')
(a.device_dir/'manifest.xml').write_bytes(ET.tostring(root,encoding='utf-8',xml_declaration=True))
(a.device_dir/'changes.json').write_text(json.dumps(changes,indent=2)+'\n')
for e in changes:print(e['path'],e.get('revision',e['base'])[:12],len(e.get('commits',[])))
