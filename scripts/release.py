#!/usr/bin/env python3
"""Build, sign and publish a release in one go, with the signing passwords asked first.

Asks for the key passwords and checks them against the key files, starts the
release run, waits for its build job, signs the target-files locally, verifies
the package and approves the run's testing environment, which publishes the
prerelease. The release environment is left for the maintainer to approve after
the OTA test. The passwords stay in this process's memory and are dropped once
signing is done; stopping it at any point publishes nothing.
"""
import argparse,datetime,getpass,json,os,pathlib,subprocess,sys,time
import signing_profiles

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('device');p.add_argument('tree')
p.add_argument('--repository',default='rthery/android_builds')
a=p.parse_args()
scripts=pathlib.Path(__file__).resolve().parent
recipe=scripts.parent
workspace=pathlib.Path(os.environ.get('ROM_WORKSPACE') or recipe.parents[1])
config=recipe/'devices'/a.device/a.tree
profile=signing_profiles.PROFILES.get(a.tree)
if not profile or not (config/'build.conf').is_file():sys.exit(f'No release recipe for {a.device} {a.tree}')

def gh(*args,check=True,**kw):
 env=dict(os.environ,GH_TOKEN=subprocess.run(['gh','auth','token','-u','rthery'],capture_output=True,text=True,check=True).stdout.strip())
 return subprocess.run(['gh',*args],capture_output=True,text=True,check=check,env=env,**kw)
def api(path,*args):return json.loads(gh('api',path,*args).stdout or 'null')
def note(message):print(f'[{datetime.datetime.now():%H:%M:%S}] {message}',flush=True)

tag_date=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')
changelog=(config/'CHANGELOG.md').read_text() if (config/'CHANGELOG.md').exists() else ''
if f'## 22.2-{tag_date}-UNOFFICIAL-{a.device}' not in changelog:
 note(f'Warning: CHANGELOG.md has no section for 22.2-{tag_date}-UNOFFICIAL-{a.device}; the testing job will refuse to publish without it')

passwords={}
for group in profile['groups']:
 password=getpass.getpass(f'{group} key password (hidden): ')
 key=workspace/'.local/release-signing'/group/'releasekey.pk8'
 if not key.exists():key=next((workspace/'.local/release-signing'/group).glob('*.pk8'))
 checked=subprocess.run(['openssl','pkcs8','-inform','DER','-in',str(key),'-passin','stdin','-out','/dev/null'],input=password+'\n',capture_output=True,text=True)
 if checked.returncode:sys.exit(f'Wrong password for {group}')
 passwords[group]=password
note('Passwords checked against the keys.')

started=datetime.datetime.now(datetime.timezone.utc)
gh('workflow','run','build.yml','-R',a.repository,'--ref','main','-f',f'device={a.device}','-f',f'tree={a.tree}','-f','mode=release')
run=None
for _ in range(30):
 time.sleep(5)
 runs=api(f'repos/{a.repository}/actions/workflows/build.yml/runs?event=workflow_dispatch&per_page=5')['workflow_runs']
 run=next((r for r in runs if datetime.datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))>=started-datetime.timedelta(seconds=5)),None)
 if run:break
if not run:sys.exit('The dispatched run did not show up')
run_id=str(run['id'])
note(f'Release run {run["html_url"]}')

while True:
 jobs={j['name']:j for j in api(f'repos/{a.repository}/actions/runs/{run_id}/jobs')['jobs']}
 build=jobs.get('build')
 if build and build['status']=='completed':break
 time.sleep(60)
if build['conclusion']!='success':sys.exit(f'Build job {build["conclusion"]}; nothing signed or published')
info_path=workspace/'zips/ci'/run_id/'release.json'
info=json.loads(info_path.read_text())
note(f'Built {info["target_files"]} ({info["target_files_sha256"][:16]}...)')

signed=workspace/'zips/ci-signed'/run_id
signer=subprocess.Popen(['bash',str(scripts/'sign-local-candidate.sh'),str(workspace/'zips/ci'/run_id/info['target_files']),str(signed),'--passwords-stdin'],stdin=subprocess.PIPE,text=True)
signer.stdin.write(json.dumps(passwords));signer.stdin.close();passwords.clear()
if signer.wait():sys.exit('Signing failed; nothing published')
note('Signed.')

subprocess.run([sys.executable,'-I',str(scripts/'verify-signed-candidate.py'),str(signed),str(info_path),'--cert',str(config/'releasekey.x509.pem')],check=True)
ota=json.loads((signed/'independent-verification.json').read_text())['ota_sha256']

for _ in range(30):
 pending=api(f'repos/{a.repository}/actions/runs/{run_id}/pending_deployments')
 testing=[d['environment']['id'] for d in pending if d['environment']['name']=='testing']
 if testing:break
 time.sleep(10)
else:sys.exit('The testing job is not waiting for approval')
body={'environment_ids':testing,'state':'approved','comment':f'Signed and verified locally: package {ota}'}
gh('api','-X','POST',f'repos/{a.repository}/actions/runs/{run_id}/pending_deployments','--input','-',input=json.dumps(body))
note('Testing approved; publishing the prerelease.')

while True:
 jobs={j['name']:j for j in api(f'repos/{a.repository}/actions/runs/{run_id}/jobs')['jobs']}
 job=jobs.get('testing')
 if job and job['status']=='completed':break
 time.sleep(20)
if job['conclusion']!='success':sys.exit(f'Testing job {job["conclusion"]}: see {run["html_url"]}')
note(f'Prerelease published. After the OTA test, approve "release" on {run["html_url"]} to mark it latest and update the Updater feed.')
