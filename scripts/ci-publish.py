#!/usr/bin/env python3
"""Publish a locally signed package for a CI release build.

prepare: check that zips/ci-signed/<build run> was signed from the target-files
that build run produced, verify the OTA signature against the committed
release certificate and write the feed, checksums and release notes.
upload: create the release in this repository, upload the package and its
provenance files, and replace the feed asset when asked. In promote mode it
only checks that the release already holds this package, marks it as the
latest release and replaces the feed asset.
"""
import argparse,hashlib,http.client,json,os,pathlib,shutil,subprocess,sys,time,urllib.error,urllib.parse,urllib.request,zipfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('device');p.add_argument('mode',choices=('publish','promote'));p.add_argument('tree')
p.add_argument('step',choices=('prepare','upload'))
p.add_argument('build_run')
p.add_argument('update_feed',choices=('true','false'))
a=p.parse_args()
if not a.build_run.isdigit():sys.exit('Invalid build run id')
recipe=pathlib.Path(__file__).resolve().parent.parent
config=recipe/'devices'/a.device/a.tree
env=os.environ
release_dir=pathlib.Path('/work/zips/ci')/a.build_run
signed_dir=pathlib.Path('/work/zips/ci-signed')/a.build_run
# The testing and release jobs of one run each prepare their own copy.
publish_dir=release_dir/f"publish-{env['GITHUB_RUN_ID']}-{env.get('GITHUB_JOB','publish')}-{env.get('GITHUB_RUN_ATTEMPT','1')}"
server,repository=env['GITHUB_SERVER_URL'],env['GITHUB_REPOSITORY']
conf=dict(line.split('=',1) for line in (config/'build.conf').read_text().splitlines() if line[:1].isupper() and '=' in line)

def fail(message):sys.exit('Refusing to publish: '+message)
def sha256(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def output(name,value):
 with open(env['GITHUB_OUTPUT'],'a') as f:f.write(f'{name}={value}\n')

def changelog(tag):
 """The release's section of CHANGELOG.md, which the maintainer writes before publishing."""
 path=config/'CHANGELOG.md'
 if not path.exists():fail(f'{path} is missing')
 sections=path.read_text().split('\n## ')
 body=next((s.split('\n',1)[1].strip() for s in sections[1:] if s.split('\n',1)[0].strip()==tag),None)
 if not body:fail(f'{path.name} has no section for {tag}')
 return body

def prepare():
 info=json.loads((release_dir/'release.json').read_text())
 if info['run']!=a.build_run:fail('release.json belongs to another run')
 if sha256(release_dir/info['target_files'])!=info['target_files_sha256']:fail('target-files changed since the build run')
 report=json.loads((signed_dir/'native-signing-report.json').read_text())
 if report['input_sha256']!=info['target_files_sha256']:fail('the signed package was made from another target-files')
 check=json.loads((signed_dir/'independent-verification.json').read_text())
 package=signed_dir/'local-candidate.zip'
 if check.get('target_files_sha256')!=info['target_files_sha256'] or check.get('ota_sha256')!=sha256(package):
  fail('independent-verification.json does not cover this package')
 subprocess.run([sys.executable,'-I',recipe/'scripts/verify-ota-signature.py',package,config/'releasekey.x509.pem'],check=True)
 if publish_dir.exists():fail(f'{publish_dir} exists')
 publish_dir.mkdir()
 if not conf.get('BUILD_FEED_ASSET'):fail('build.conf has no BUILD_FEED_ASSET')
 current=publish_dir/'current-feed.json'
 url=f'{server}/{repository}/releases/download/ota-feed/{conf["BUILD_FEED_ASSET"]}'
 feed=['--feed-name',conf['BUILD_FEED_ASSET']]
 try:
  with urllib.request.urlopen(url) as response:current.write_bytes(response.read())
  feed+=['--current-feed',current]
 except urllib.error.HTTPError as error:
  # The first release of a tree has no feed yet.
  if error.code!=404:raise
 subprocess.run([sys.executable,'-I',recipe/'scripts/make-ota-feed.py',signed_dir,'--device',a.device,
  '--releases-repo',repository,'--filename-prefix',conf.get('BUILD_PACKAGE_PREFIX','lineage-'),'--out',publish_dir,*feed],check=True)
 checksum=next(publish_dir.glob('*.zip.sha256'))
 name=checksum.name.removesuffix('.sha256')
 shutil.copyfile(package,publish_dir/name)
 if sha256(publish_dir/name)!=check['ota_sha256']:fail('package copy differs')
 for extra in ('resolved.xml','release.json','vendor-tree.txt'):shutil.copyfile(release_dir/extra,publish_dir/extra)
 # A first install needs this recovery; verify-signed-candidate.py checked it matches the copy the package installs.
 recovery=publish_dir/name.replace('.zip','-recovery.img')
 with zipfile.ZipFile(signed_dir/'signed-target-files.zip') as signed:recovery.write_bytes(signed.read('IMAGES/recovery.img'))
 recovery.with_name(recovery.name+'.sha256').write_text(f'{sha256(recovery)}  {recovery.name}\n')
 output('recovery',recovery)
 # An "Android:" line (new Android or LineageOS version) leads; the security patch level comes next.
 changes=changelog(info['lineage_version']).split('\n')
 patch=f"- Security patch level: {info['security_patch']}."
 changes.insert(1 if changes[0].startswith('- Android:') else 0,patch)
 changes='\n'.join(changes)
 install=(f'- Install and update instructions: {server}/{repository}/blob/main/devices/{a.device}/{a.tree}/INSTALL.md\n'
  if (config/'INSTALL.md').exists() else '')
 run_url=lambda run:f'{server}/{repository}/actions/runs/{run}'
 runs=(f'[Build and release run]({run_url(a.build_run)})' if a.build_run==env['GITHUB_RUN_ID']
  else f'[Build run]({run_url(a.build_run)}) · [Publish run]({run_url(env["GITHUB_RUN_ID"])})')
 (publish_dir/'notes.md').write_text(f"""LineageOS {info['lineage_version'].split('-')[0]} for the Nexus 5X ({a.device}).

- Test report: https://{repository.split('/')[0]}.github.io/{repository.split('/')[1]}/{a.tree}/{info['lineage_version']}/
{install}- {runs}

## Changes

{changes}

Verify the download: `gh attestation verify {name} -R {repository}`
""")
 output('package',publish_dir/name)
 output('publish_dir',publish_dir)

def api(method,url,token,data=None,content_type='application/json'):
 body=json.dumps(data).encode() if isinstance(data,dict) else data
 request=urllib.request.Request(url,data=body,method=method,headers={
  'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':content_type})
 if isinstance(data,pathlib.Path):
  request.data=data.open('rb');request.add_header('Content-Length',str(data.stat().st_size))
 try:
  with urllib.request.urlopen(request) as response:
   text=response.read()
 except urllib.error.HTTPError as error:
  if error.code!=404:print(f'{method} {url}: HTTP {error.code} {error.read().decode(errors="replace")[:500]}',file=sys.stderr)
  raise
 return json.loads(text) if text else None

def send_asset(url,path,token):
 """Streams one asset and returns GitHub's reply, read even when it closes the upload early."""
 target=urllib.parse.urlsplit(url)
 connection=http.client.HTTPSConnection(target.netloc,timeout=600)
 connection.putrequest('POST',target.path+'?'+target.query)
 for key,value in (('Authorization','Bearer '+token),('Accept','application/vnd.github+json'),
  ('Content-Type','application/octet-stream'),('Content-Length',str(path.stat().st_size))):connection.putheader(key,value)
 connection.endheaders()
 sent,failure=0,None
 try:
  with path.open('rb') as f:
   while chunk:=f.read(1<<20):connection.send(chunk);sent+=len(chunk)
 except OSError as error:failure=error
 try:
  response=connection.getresponse();status,body=response.status,response.read(1000)
 except (OSError,http.client.HTTPException) as error:status,body=None,repr(error).encode()
 connection.close()
 if status==201 and failure is None:return
 raise ConnectionError(f'upload of {path.name} stopped after {sent} of {path.stat().st_size} bytes: '
  f'{failure!r}, GitHub replied {status} {body[:500]!r}')

def upload_asset(release,path,token,name=None):
 name=name or path.name
 url=release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(name)
 for attempt in range(1,4):
  # A dropped upload can leave a partial asset under the name, which blocks the next try.
  for asset in api('GET',release['url']+'/assets?per_page=100',token):
   if asset['name']==name:
    if asset['state']=='uploaded' and asset['size']==path.stat().st_size:return
    api('DELETE',asset['url'],token)
  try:
   send_asset(url,path,token);return
  except (ConnectionError,TimeoutError,OSError) as error:
   print(f'Attempt {attempt}: {error}',flush=True)
   if attempt==3:raise
   time.sleep(30*attempt)

def promote(release,name,token):
 asset=next((x for x in release['assets'] if x['name']==name),None)
 if asset is None:fail(f'release {release["tag_name"]} has no {name}')
 expected=(publish_dir/(name+'.sha256')).read_text().split()[0]
 if asset.get('digest') not in (None,'sha256:'+expected):fail(f'{name} on the release is another package')
 checksum=next((x for x in release['assets'] if x['name']==name+'.sha256'),None)
 if checksum is None:fail(f'release {release["tag_name"]} has no {name}.sha256')
 # The public download URL avoids sending the token on to the storage redirect.
 with urllib.request.urlopen(checksum['browser_download_url']) as response:published=response.read().decode().split()[0]
 if published!=expected:fail(f'{name}.sha256 on the release names another package')
 api('PATCH',release['url'],token,{'prerelease':False,'make_latest':'true'})
 print('Promoted:',release['html_url'])
 output('release_url',release['html_url'])

def upload():
 info=json.loads((publish_dir/'release.json').read_text())
 token=env['GITHUB_TOKEN']
 name=next(publish_dir.glob('*.zip.sha256')).name.removesuffix('.sha256')
 tag=name.removeprefix(conf.get('BUILD_PACKAGE_PREFIX','lineage-')).removesuffix('.zip')
 if a.mode=='promote':
  try:promote(api('GET',f'https://api.github.com/repos/{repository}/releases/tags/{tag}',token),name,token)
  except urllib.error.HTTPError as error:
   if error.code==404:fail(f'no release {tag} to promote; publish it first')
   raise
  update_feed(info,token);return
 # The release points at the recipe commit that built the package, also when a publish run redoes it.
 # The job token cannot point a ref at a commit whose workflows differ from main's: a publish run needs the tag made beforehand.
 try:tagged=api('GET',f'https://api.github.com/repos/{repository}/git/ref/tags/{tag}',token)['object']['sha']
 except urllib.error.HTTPError as error:
  if error.code!=404:raise
  tagged=None
 if tagged not in (None,info['commit']):fail(f'tag {tag} points at {tagged}, not {info["commit"]}')
 drafts=[r for r in api('GET',f'https://api.github.com/repos/{repository}/releases?per_page=30',token) if r['draft'] and r['tag_name']==tag]
 try:
  release=drafts[0] if drafts else api('GET',f'https://api.github.com/repos/{repository}/releases/tags/{tag}',token)
  if not tagged and release['target_commitish']!=info['commit']:fail(f'release {tag} exists for another commit')
 except urllib.error.HTTPError as error:
  if error.code!=404:raise
  if tagged is None and info['commit']!=env['GITHUB_SHA']:fail(f'create tag {tag} at {info["commit"]} first')
  # Created as a draft and published once every asset is up, so nobody sees an empty release.
  release=api('POST',f'https://api.github.com/repos/{repository}/releases',token,{
   'tag_name':tag,'name':f'{tag} ({a.device})','body':(publish_dir/'notes.md').read_text(),
   'draft':True,'prerelease':a.update_feed!='true',**({} if tagged else {'target_commitish':info['commit']})})
 recovery=publish_dir/name.replace('.zip','-recovery.img')
 for path in (publish_dir/name,publish_dir/(name+'.sha256'),recovery,recovery.with_name(recovery.name+'.sha256'),
  publish_dir/'resolved.xml',publish_dir/'release.json',publish_dir/'vendor-tree.txt'):
  upload_asset(release,path,token)
 release=api('PATCH',release['url'],token,{'draft':False,'prerelease':a.update_feed!='true','make_latest':'true' if a.update_feed=='true' else 'false'})
 print('Release:',release['html_url'])
 output('release_url',release['html_url'])
 if a.update_feed=='true':update_feed(info,token)

def update_feed(info,token):
 feed=conf['BUILD_FEED_ASSET']
 try:feed_release=api('GET',f'https://api.github.com/repos/{repository}/releases/tags/ota-feed',token)
 except urllib.error.HTTPError as error:
  if error.code!=404:raise
  feed_release=api('POST',f'https://api.github.com/repos/{repository}/releases',token,{
   'tag_name':'ota-feed','target_commitish':env['GITHUB_SHA'],'name':'OTA feed','make_latest':'false',
   'body':'Updater feed files, one per ROM, Android base and device. Never rename this tag or its assets.'})
 for asset in feed_release['assets']:
  if asset['name']==feed:api('DELETE',asset['url'],token)
 upload_asset(feed_release,publish_dir/feed,token)
 print('Feed updated:',feed,'build',info['build_number'])

prepare() if a.step=='prepare' else upload()
