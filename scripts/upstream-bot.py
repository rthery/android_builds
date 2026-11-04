#!/usr/bin/env python3
"""Turn upstream-check.py results into merge PRs, and merge them weekly.

prs: in each fork behind its upstream, points upstream/<branch> at the
upstream head and keeps one open PR from it into the fork branch.
merge: merges each clean PR with a merge commit (upstream SHAs stay, so the
next merge is incremental), then repins the merged forks in the recipe
manifest through a PR on the default branch, merged at once. A fork whose
branch holds commits the recipe does not pin yet is left alone, so a merge
never ships unpinned work. Conflicting PRs stay open for a manual merge.
Runs with a GitHub App token in GH_TOKEN; --dry-run only prints.
"""
import argparse,datetime,json,os,pathlib,re,subprocess,sys,tempfile,time,urllib.error,urllib.request,base64

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('results',type=pathlib.Path,help='upstream-check.py --json output')
p.add_argument('action',choices=['prs','merge'])
p.add_argument('--repo',default=os.environ.get('GITHUB_REPOSITORY','rthery/android_builds'),help='repository holding the recipe')
p.add_argument('--dry-run',action='store_true')
a=p.parse_args()
results=json.loads(a.results.read_text())
branch,fork_branch=results['branch'],results['fork_branch']
mirror=f'upstream/{branch}'
token=os.environ.get('GH_TOKEN','')

def api(method,path,data=None,missing=False):
 req=urllib.request.Request('https://api.github.com/'+path,method=method,data=json.dumps(data).encode() if data is not None else None,
  headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
 try:
  with urllib.request.urlopen(req,timeout=120) as r:
   body=r.read()
   return json.loads(body) if body else None
 except urllib.error.HTTPError as e:
  if missing and e.code==404:return None
  raise SystemExit(f'{method} {path}: {e.code} {e.read().decode()[:300]}')

def act(message,fn,*args,**kw):
 print(('Would ' if a.dry_run else '')+message,flush=True)
 return None if a.dry_run else fn(*args,**kw)

def code(s):
 return '`'+s.replace('`',"'")+'`'

def push_mirror(f):
 # The fork is not in the upstream's fork network: GitHub cannot point a ref at commits it lacks.
 d=tempfile.mkdtemp()
 subprocess.run(['git','init','-q','--bare',d],check=True)
 subprocess.run(['git','-C',d,'fetch','-q',f'https://github.com/{f["upstream"]}',f'refs/heads/{branch}'],check=True)
 subprocess.run(['git','-C',d,'-c',f'http.extraHeader=Authorization: Basic {base64.b64encode(f"x-access-token:{token}".encode()).decode()}',
  'push','-q','--force',f'https://github.com/{f["fork"]}',f'{f["head"]}:refs/heads/{mirror}'],check=True)

def set_mirror(f):
 ref=api('GET',f'repos/{f["fork"]}/git/ref/heads/{mirror}',missing=True)
 if ref and ref['object']['sha']==f['head']:return
 try:
  if ref:api('PATCH',f'repos/{f["fork"]}/git/refs/heads/{mirror}',{'sha':f['head'],'force':True})
  else:api('POST',f'repos/{f["fork"]}/git/refs',{'ref':f'refs/heads/{mirror}','sha':f['head']})
 except SystemExit as e:
  if ' 422 ' not in str(e):raise
  push_mirror(f)

def open_pr(f):
 pulls=api('GET',f'repos/{f["fork"]}/pulls?state=open&base={fork_branch}&head={f["fork"].split("/")[0]}:{mirror}')
 return pulls[0] if pulls else None

def pr_text(f):
 change=f['change']
 title=f'[{f["class"]}] Merge {f["upstream"]} {branch} ({change["total"]} commits)'
 lines=[f'Upstream commits not yet in `{fork_branch}`, from the daily upstream check. Merged weekly when clean.','']
 lines+=[f'- [{sha[:12]}](https://github.com/{f["upstream"]}/commit/{sha}) {code(subject)}' for sha,subject in change['commits'][:50]]
 if change['total']>50:lines.append(f'- and {change["total"]-50} more')
 if f.get('conflicts'):lines+=['','Conflicts with our commits, merge by hand:','']+[f'- {code(n)}' for n in f['conflicts']]
 return title,'\n'.join(lines)

behind=[f for f in results['forks'] if f.get('change') and not f.get('error')]

if a.action=='prs':
 for f in behind:
  act(f'point {f["fork"]} {mirror} at {f["head"][:12]}',set_mirror,f)
  title,body=pr_text(f)
  pr=open_pr(f)
  if pr:act(f'update {pr["html_url"]}: {title}',api,'PATCH',f'repos/{f["fork"]}/pulls/{pr["number"]}',{'title':title,'body':body})
  else:act(f'open a PR in {f["fork"]}: {title}',api,'POST',f'repos/{f["fork"]}/pulls',{'title':title,'body':body,'head':mirror,'base':fork_branch})
 sys.exit(0)

merged={}
for f in behind:
 if f['ours']!=f['pin']:
  print(f'{f["path"]}: skipped, {fork_branch} is at {f["ours"][:12]} but the recipe pins {f["pin"][:12]}');continue
 pr=open_pr(f)
 if not pr:
  print(f'{f["path"]}: no open PR');continue
 # GitHub computes mergeability in the background after a push.
 for _ in range(12):
  pr=api('GET',f'repos/{f["fork"]}/pulls/{pr["number"]}')
  if pr['mergeable'] is not None:break
  time.sleep(5)
 if not pr['mergeable'] or pr['mergeable_state'] not in ('clean','unstable','has_hooks'):
  print(f'{f["path"]}: not merged, {pr["html_url"]} is {pr["mergeable_state"]}');continue
 done=act(f'merge {pr["html_url"]}',api,'PUT',f'repos/{f["fork"]}/pulls/{pr["number"]}/merge',
  {'merge_method':'merge','sha':pr['head']['sha'],'commit_title':f'Merge {f["upstream"]} {branch} into {fork_branch}'})
 merged[f['path']]={'sha':done['sha'] if done else '0'*40,'title':pr['title'],'url':pr['html_url']}
if not merged:
 print('Nothing merged; recipe unchanged');sys.exit(0)

recipe=results['recipe']
main=api('GET',f'repos/{a.repo}')['default_branch']
current=api('GET',f'repos/{a.repo}/contents/{recipe}?ref={main}')
text=base64.b64decode(current['content']).decode()
for path,m in merged.items():
 text,n=re.subn(rf'(<project path="{re.escape(path)}" [^>]*?revision=")[0-9a-f]{{40}}',rf'\g<1>{m["sha"]}',text)
 if n!=1:raise SystemExit(f'{path}: {n} pins found in {recipe}')
today=datetime.date.today()
device,tree=pathlib.PurePosixPath(recipe).parts[1:3]
title=f'{device}: {tree}: Merge upstream {today}'
body='\n'.join(f'- {path}: {m["title"]} ({m["url"]})' for path,m in merged.items())
work=f'upstream/repin-{tree}-{today}'
if a.dry_run:
 print(f'Would repin {", ".join(merged)} in {recipe} through {work}');sys.exit(0)
base=api('GET',f'repos/{a.repo}/git/ref/heads/{main}')['object']['sha']
api('POST',f'repos/{a.repo}/git/refs',{'ref':f'refs/heads/{work}','sha':base})
api('PUT',f'repos/{a.repo}/contents/{recipe}',{'message':f'{title}\n\n{body}','content':base64.b64encode(text.encode()).decode(),'sha':current['sha'],'branch':work})
pr=api('POST',f'repos/{a.repo}/pulls',{'title':title,'body':body,'head':work,'base':main})
api('PUT',f'repos/{a.repo}/pulls/{pr["number"]}/merge',{'merge_method':'squash','commit_title':title,'commit_message':body})
api('DELETE',f'repos/{a.repo}/git/refs/heads/{work}')
print(f'Repinned through {pr["html_url"]}')
