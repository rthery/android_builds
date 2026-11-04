#!/usr/bin/env python3
"""Report upstream commits that a device tree does not have yet.

The baseline is the resolved manifest of the tree's latest release. Forks in
the recipe (projects replacing a removed <upstream_owner>/<name>) are compared
with the upstream branch they merge from, and a shallow blobless merge-tree
says whether that merge is clean. Every other project tracking a GitHub branch
is compared with the revision the release built. Each moved project is classed
security, core or low (translations only) by the tree's upstream.json.
Read-only for the source repositories; with --issue it keeps one tracking issue
per week and comments when a new conflict or security change shows up.
"""
import argparse,concurrent.futures,datetime,json,os,pathlib,re,subprocess,sys,tempfile,urllib.error,urllib.request
import xml.etree.ElementTree as ET

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('device')
p.add_argument('tree',help='devices/<device>/<tree> recipe')
p.add_argument('--repo',default=os.environ.get('GITHUB_REPOSITORY','rthery/android_builds'),help='repository with the releases')
p.add_argument('--baseline',type=pathlib.Path,help='resolved manifest to compare with instead of the latest release one')
p.add_argument('--report',type=pathlib.Path,required=True,help='markdown report to write')
p.add_argument('--issue',action='store_true',help='update the weekly tracking issue in --repo')
a=p.parse_args()

recipe_dir=pathlib.Path(__file__).resolve().parent.parent/'devices'/a.device/a.tree
rules=json.loads((recipe_dir/'upstream.json').read_text())
conf=(recipe_dir/'build.conf').read_text()
recipe_manifest=recipe_dir/re.search(r'^BUILD_RECIPE_MANIFEST=(\S+)',conf,re.M).group(1)
branch,fork_branch=rules['upstream_branch'],rules['fork_branch']
token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or subprocess.run(['gh','auth','token'],capture_output=True,text=True).stdout.strip()

def gh(*args,**kw):
 return subprocess.run(['gh',*args],capture_output=True,text=True,check=True,**kw).stdout

def api(path,data=None):
 req=urllib.request.Request('https://api.github.com/'+path,data=json.dumps(data).encode() if data else None,
  headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
 try:
  with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
 except urllib.error.HTTPError as e:
  # Compare answers 404 when the two repositories share no fork network.
  if e.code==404:return None
  raise

def git(d,*args,check=True):
 return subprocess.run(['git','-C',d,*args],capture_output=True,text=True,check=check)

tag=next(r['tagName'] for r in json.loads(gh('release','list','-R',a.repo,'--limit','50','--json','tagName'))
 if r['tagName'].startswith(rules['release_tag_prefix']))
work=pathlib.Path(tempfile.mkdtemp(prefix='upstream-check-'))
if not a.baseline:
 gh('release','download',tag,'-R',a.repo,'-p','resolved.xml','-D',str(work))
 a.baseline=work/'resolved.xml'
resolved=ET.parse(a.baseline).getroot()
remotes={r.get('name'):r.get('fetch') for r in resolved.iter('remote')}
default=resolved.find('default')

def github(remote,name):
 fetch=remotes.get(remote or default.get('remote'),'')
 # Lineage's manifest fetches relative to github.com/LineageOS/android.
 base='https://github.com' if fetch=='..' else fetch.rstrip('/')
 if not base.startswith('https://github.com'):return None
 return f'{base}/{name}'[len('https://github.com/'):].removesuffix('.git')

recipe=ET.parse(recipe_manifest).getroot()
removed={e.get('name') for e in recipe.iter('remove-project')}
own=set()
forks=[]
for e in recipe.iter('project'):
 path=e.get('path') or e.get('name')
 upstream=f"{rules['upstream_owner']}/{e.get('name')}"
 if upstream in removed:
  forks.append({'path':path,'fork':github(e.get('remote'),e.get('name')),'upstream':rules.get('fork_upstreams',{}).get(path,upstream)})
 elif e.get('remote')=='rthery':own.add(path)
fork_paths={f['path'] for f in forks}
pins={e.get('path') or e.get('name'):e.get('revision') for e in resolved.iter('project')}
# Generated trees (vendor blobs) are built from the commit the recipe pins, not the one resolved.xml records.
recipe_pins={e.get('path') or e.get('name'):e.get('revision') for e in recipe.iter('project')}

tracked,unchecked=[],[]
for e in resolved.iter('project'):
 path=e.get('path') or e.get('name')
 ref=e.get('upstream') or ''
 if path in fork_paths or path in own or not ref.startswith('refs/heads/'):continue
 repo=github(e.get('remote'),e.get('name'))
 if repo:tracked.append({'path':path,'repo':repo,'branch':ref[len('refs/heads/'):],'revision':recipe_pins.get(path,e.get('revision'))})
 else:unchecked.append(path)

def heads(refs):
 out={}
 for i in range(0,len(refs),100):
  chunk=refs[i:i+100]
  q='query{'+''.join(f'r{j}:repository(owner:{json.dumps(r.split("/")[0])},name:{json.dumps(r.split("/")[1])})'
   f'{{ref(qualifiedName:{json.dumps("refs/heads/"+b)}){{target{{oid}}}}}}' for j,(r,b) in enumerate(chunk))+'}'
  data=(api('graphql',{'query':q}) or {}).get('data') or {}
  for j,key in enumerate(chunk):out[key]=(((data.get(f'r{j}') or {}).get('ref') or {}).get('target') or {}).get('oid')
 return out

head=heads([(t['repo'],t['branch']) for t in tracked]+[(f['upstream'],branch) for f in forks]+[(f['fork'],fork_branch) for f in forks])

def compare(repo,old,new):
 c=api(f'repos/{repo}/compare/{old}...{new}')
 if c is None:return None
 return {'commits':[(x['sha'],x['commit']['message'].splitlines()[0]) for x in c['commits']][::-1],'total':c['total_commits'],
  'files':[{'filename':f['filename'],'patch':f.get('patch')} for f in c.get('files',[])],'truncated':len(c.get('files',[]))>=300}

def classify(path,change):
 names=[(f'{path}/{f["filename"]}',f.get('patch')) for f in change['files']]
 for rule in rules['security']:
  for name,patch in names:
   if re.search(rule['file'],name) and (not rule.get('added') or patch is None
     or any(l.startswith('+') and rule['added'] in l for l in patch.splitlines())):return 'security'
 if names and not change['truncated'] and all(any(re.search(r,n) for r in rules['low']) for n,_ in names):return 'low'
 return 'core'

def check_tracked(t):
 new=head[(t['repo'],t['branch'])]
 if not new:return {**t,'error':f'branch {t["branch"]} not found'}
 if new==t['revision']:return None
 change=compare(t['repo'],t['revision'],new)
 if change is None:return {**t,'error':'compare failed'}
 return {**t,'kind':'tracked','head':new,'change':change,'class':classify(t['path'],change)}

def check_fork(f):
 ours,theirs=head[(f['fork'],fork_branch)],head[(f['upstream'],branch)]
 if not ours or not theirs:return {**f,'error':'branch not found'}
 result={**f,'kind':'fork','head':theirs,'ours':ours}
 d=tempfile.mkdtemp(dir=work)
 git(d,'init','-q','--bare')
 for name,repo in (('fork',f['fork']),('up',f['upstream'])):
  git(d,'remote','add',name,f'https://github.com/{repo}')
  git(d,'config',f'remote.{name}.promisor','true')
  git(d,'config',f'remote.{name}.partialclonefilter','blob:none')
 c=api(f'repos/{f["upstream"]}/compare/{branch}...{f["fork"].replace("/",":")}:{fork_branch}')
 if c:
  base,behind=c['merge_base_commit']['sha'],c['behind_by']
  if behind:
   git(d,'fetch','-q','--depth=1','--filter=blob:none','fork',ours)
   git(d,'fetch','-q','--depth=1','--filter=blob:none','up',theirs,base)
   change=compare(f['upstream'],base,theirs)
 else:
  # Not a GitHub fork of the upstream: fetch both histories without blobs.
  git(d,'fetch','-q','--filter=blob:none','fork',ours)
  git(d,'fetch','-q','--filter=blob:none','up',theirs)
  mb=git(d,'merge-base',ours,theirs,check=False)
  if mb.returncode:return {**result,'error':'no common history with upstream'}
  base=mb.stdout.strip()
  log=git(d,'log','--format=%H %s',f'{base}..{theirs}').stdout.splitlines()
  behind=len(log)
  change={'commits':[tuple(l.split(' ',1)) for l in log],'total':behind,'truncated':False,
   'files':[{'filename':n,'patch':None} for n in git(d,'diff','--name-only',base,theirs).stdout.split()]}
 if pins.get(f['path'])!=ours:result['unreleased']=True
 if not behind:return result
 merge=git(d,'merge-tree','--write-tree','--name-only','--no-messages',f'--merge-base={base}',ours,theirs,check=False)
 if merge.returncode>1:return {**result,'error':merge.stderr.strip()[:200]}
 return {**result,'change':change,'class':classify(f['path'],change),'conflicts':merge.stdout.split()[1:] if merge.returncode else []}

with concurrent.futures.ThreadPoolExecutor(8) as pool:
 results=[r for r in pool.map(check_fork,forks) if r]+[r for r in pool.map(check_tracked,tracked) if r]
moved=[r for r in results if r.get('change')]
errors=[r for r in results if r.get('error')]
order={'security':0,'core':1,'low':2}
moved.sort(key=lambda r:(order[r['class']],r['path']))
conflicts=[r for r in moved if r.get('conflicts')]
alerts=sorted({f'conflict:{r["path"]}' for r in conflicts}|{f'security:{r["path"]}' for r in moved if r['class']=='security'})

def code(s):
 # Code spans keep upstream subjects from mentioning users or linking issues here.
 return '`'+s.replace('`',"'")+'`'

today=datetime.date.today()
counts={k:sum(r['class']==k for r in moved) for k in order}
lines=[f'## {a.tree} upstream check, {today}','',
 (f'Baseline: {a.baseline.name}.' if a.baseline.parent!=work else f'Baseline: release [{tag}](https://github.com/{a.repo}/releases/tag/{tag}).')+f' Checked {len(forks)} forks and {len(tracked)} branch-tracked projects.','']
if moved:
 lines+=[f'{len(moved)} moved: {counts["security"]} security, {counts["core"]} core, {counts["low"]} low. '
  f'{len(conflicts)} fork merges conflict.','','| Project | Kind | New commits | Class | Merge |','|---|---|---|---|---|']
 for r in moved:
  merge='n/a' if r['kind']!='fork' else (f'conflict ({len(r["conflicts"])} files)' if r['conflicts'] else 'clean')
  lines.append(f'| {r["path"]} | {r["kind"]} | {r["change"]["total"]} | {r["class"]} | {merge} |')
 lines.append('')
 for r in moved:
  repo=r['upstream'] if r['kind']=='fork' else r['repo']
  lines+=[f'<details><summary>{r["path"]} ({repo}): {r["change"]["total"]} commits, {r["class"]}</summary>','']
  lines+=[f'- [{sha[:12]}](https://github.com/{repo}/commit/{sha}) {code(subject)}' for sha,subject in r['change']['commits'][:30]]
  if r['change']['total']>30:lines.append(f'- and {r["change"]["total"]-30} more')
  if r.get('conflicts'):lines+=['','Conflicting files:','']+[f'- {code(n)}' for n in r['conflicts']]
  lines+=['','</details>','']
else:lines+=['Nothing moved upstream.','']
unreleased=[r['path'] for r in results if r.get('unreleased')]
if unreleased:lines+=[f'Fork branches with commits after the release: {", ".join(unreleased)}.','']
if errors:lines+=['Errors:','']+[f'- {r["path"]}: {code(r["error"])}' for r in errors]+['']
if unchecked:lines+=[f'Not on GitHub, not checked: {", ".join(unchecked)}.','']
lines.append(f'<!-- upstream-check {json.dumps(alerts)} -->')
body='\n'.join(lines)
if len(body)>60000:body=re.sub(r'<details>.*?</details>\n','',body,flags=re.S)
a.report.write_text(body+'\n')
print(body)

if a.issue:
 label='upstream-check'
 gh('label','create',label,'-R',a.repo,'--color','0e8a16','--description','Daily upstream check','--force')
 year,week,_=today.isocalendar()
 title=f'Upstream {a.tree}: week {year}-W{week:02}'
 issues=json.loads(gh('issue','list','-R',a.repo,'--label',label,'--state','open','--json','number,title,body'))
 current=next((i for i in issues if i['title']==title),None)
 if current:
  seen=re.search(r'<!-- upstream-check (.*?) -->',current['body'])
  new=sorted(set(alerts)-set(json.loads(seen.group(1)) if seen else []))
  gh('issue','edit',str(current['number']),'-R',a.repo,'--body-file','-',input=body)
  if new:gh('issue','comment',str(current['number']),'-R',a.repo,'--body-file','-',
   input='New since the last check:\n\n'+'\n'.join(f'- {n.replace(":"," in ",1)}' for n in new))
 elif moved or errors:
  url=gh('issue','create','-R',a.repo,'--title',title,'--label',label,'--assignee',a.repo.split('/')[0],'--body-file','-',input=body).strip()
  for i in issues:gh('issue','close',str(i['number']),'-R',a.repo,'--comment',f'Superseded by {url}.')
if errors:sys.exit(1)
