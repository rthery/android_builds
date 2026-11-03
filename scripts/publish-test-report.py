#!/usr/bin/env python3
"""Add or update the test report of a release on the test-reports branch (GitHub Pages).

Reads report.json from one ROM Bench export, refuses it if anything that
identifies the tester is left, and writes a page with one table per area:
each user-facing requirement listed in test-report-areas.json with a plain
status. Maintainer-only and not-applicable items are left out. The page
depends only on these inputs and test-report-areas.json. Rewrites the index
too. Commit and push the branch afterwards.
"""
import argparse,datetime,html,json,pathlib,re,sys

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('export',type=pathlib.Path,help='folder with report.json')
p.add_argument('site',type=pathlib.Path,help='checkout of the test-reports branch')
p.add_argument('--release',required=True,type=pathlib.Path,help='release.json of the release build')
p.add_argument('--private-values',type=pathlib.Path,help='file with one private value per line that must never appear')
p.add_argument('--repository',default='rthery/android_builds')
a=p.parse_args()

def fail(message):sys.exit('Refusing to publish the report: '+message)

# Second line of defence: ROM Bench masks these, so any match means an old or unmasked export.
LEFTOVERS={
 'MAC address':r'(?i)(?<![0-9a-f:-])(?!(?:00[:-]){5}00)(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f:-])',
 'private IPv4':r'(?<![\w.])(?:10|127\.(?!0\.0\.1)|192\.168|172\.(?:1[6-9]|2\d|3[01])|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7]))\.\d{1,3}\.\d{1,3}(?![\w.])',
 'IPv6 address':r'(?i)(?<![\w:])(?!2606:4700:4700::|2001:4860:4860::|2620:fe::)(?:2[0-9a-f]{3}|3[0-9a-f]{3}|f[cd][0-9a-f]{2}|fe[89ab][0-9a-f]):[0-9a-f:]*[0-9a-f](?![\w:])',
 'email':r'[\w.+-]+@[A-Za-z][A-Za-z0-9-]*(?:\.[A-Za-z][A-Za-z0-9-]*)*\.[A-Za-z]{2,}\b',
 'phone number':r'(?i)\b(?:sip|tel):|\+\d{9,15}\b',
 'IMEI, IMSI or ICCID':r'(?<![\d.])(?:\d{15}|89\d{17,18})(?![\d.])',
 'carrier':r'Network: (?!\[carrier])\S|registration work \((?!\[carrier])|(?i:operator(?:alpha(?:long|short)|name|numeric)?\s*[=:]\s*)(?!\[carrier])[^\s,}\]]',
 'serial number':r'(?i)(?:\[ro\.(?:boot\.)?serialno]: \[|\bserial(?:no)?\s*[=:]\s*)(?!\[serial])[^\]\s,]+',
}

def check(name,text,private):
 found=[label for label,pattern in LEFTOVERS.items() if re.search(pattern,text)]
 # Whole words only, so a short value like a carrier name does not match inside a key.
 found+=['a private value' for value in private if re.search(r'(?i)(?<![A-Za-z0-9])'+re.escape(value)+r'(?![A-Za-z0-9])',text)][:1]
 if found:fail(f'{name} still contains: {", ".join(found)}. Export it again with a ROM Bench that masks identifiers.')

WORKS,LIMITS,BROKEN,UNTESTED='Works','Works with limits',"Doesn't work",'Not tested'
STATUS_CLASS={WORKS:'ok',LIMITS:'limits',BROKEN:'broken',UNTESTED:'untested'}
OUTCOMES={'PASS':WORKS,'LIMITED':LIMITS,'WARN':LIMITS,'WAIVED':LIMITS,'FAIL':BROKEN,'UNTESTED':UNTESTED,'TO_VERIFY':UNTESTED,'NEEDS_SHELL':UNTESTED,'DEBUG_ONLY':UNTESTED}
VERDICTS={'PASS':WORKS,'LIMITED':LIMITS,'FAIL':BROKEN}

def status(requirement):
 """The tester's verdict wins over the automatic outcome; None leaves the row out."""
 if requirement.get('verdict')=='NOT_APPLICABLE' or requirement['outcome'] in ('NOT_APPLICABLE','NOT_ON_DEVICE'):return None
 if requirement.get('mode')=='OUT_OF_SCOPE':return None
 return VERDICTS.get(requirement.get('verdict')) or OUTCOMES.get(requirement['outcome'],UNTESTED)

release=json.loads(a.release.read_text())
report_json=(a.export/'report.json').read_text()
private=[l.strip() for l in a.private_values.read_text().splitlines() if l.strip() and not l.startswith('#')] if a.private_values else []
check('report.json',report_json,private)
report=json.loads(report_json)
fingerprint=release['fingerprint'].replace('test-keys','release-keys')
if report['device'].get('Fingerprint')!=fingerprint:
 fail(f'the report is from {report["device"].get("Fingerprint")}, the release is {fingerprint}')

# "LGE Nexus 5X (bullhead)": the manufacturer is dropped from the title.
named=re.fullmatch(r'(?:\S+ )?(.+?) \((\w+)\)',report['device'].get('Device',''))
if not named:fail(f'cannot read the phone from {report["device"].get("Device")!r}')
phone,device=named.groups()
version=release['lineage_version'].split('-')[0]
tree='lineage-'+version


def limit(requirement):
 """The tester's note says when a limited item works; the page shows it under the label."""
 if status(requirement)!=LIMITS or requirement.get('verdict')!='LIMITED':return None
 return requirement.get('verdictNote') or fail(f'{requirement["id"]} is marked with limits but has no note')

areas=json.loads((pathlib.Path(__file__).resolve().parent/'test-report-areas.json').read_text())
requirements={r['id']:r for r in report['requirements']}
tables=[]
counts={WORKS:0,LIMITS:0,BROKEN:0,UNTESTED:0}
for area,labels in areas.items():
 rows=[(label,status(requirements[rid]),limit(requirements[rid])) for rid,label in labels.items() if rid in requirements]
 rows=[r for r in rows if r[1]]
 for r in rows:counts[r[1]]+=1
 if rows:tables.append((area,rows))

tag=release['lineage_version']
built=datetime.datetime.fromtimestamp(int(release['build_date_utc']),datetime.timezone.utc).strftime('%Y-%m-%d')
tested=report['generatedAt'][:10]
server='https://github.com/'+a.repository
run_url=f'{server}/actions/runs/{release["run"]}'
STYLE='''body{font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px;color:#1b1b1b;background:#fff}main{max-width:820px;margin:auto}
small{display:block;color:#5f6368;font-size:.85em}h2{font-size:1.1em;margin:1.6em 0 .4em}table{border-collapse:collapse;width:100%}table.r{table-layout:fixed}td,th{text-align:left;padding:6px 8px;border-bottom:1px solid #ddd}
th{font-weight:600}td.s{white-space:nowrap;width:9em}a{color:#0b57d0}dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;margin:0}dt{color:#5f6368}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:.9em}.ok{background:#e6f4ea;color:#137333}.limits{background:#fef7e0;color:#8a5a00}
.broken{background:#fce8e6;color:#a50e0e}.untested{background:#f1f3f4;color:#5f6368}.wrap{overflow-x:auto}
@media (prefers-color-scheme:dark){body{color:#e3e3e3;background:#141414}td,th{border-color:#333}a{color:#8ab4f8}dt{color:#9aa0a6}
.ok{background:#0d3b1e;color:#81c995}.limits{background:#3d2e00;color:#fdd663}.broken{background:#4a1410;color:#f28b82}.untested{background:#2b2b2b;color:#9aa0a6}}'''
def page(title,body):
 return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
  f'<title>{html.escape(title)}</title><style>{STYLE}</style></head><body><main>{body}</main></body></html>\n')
def badge(s):return f'<span class="badge {STATUS_CLASS[s]}">{html.escape(s)}</span>'

header=(f'<h1>{html.escape(phone)} ({html.escape(device)})</h1><dl>'
 f'<dt>ROM</dt><dd>LineageOS {html.escape(version)}, built {built}</dd>'
 f'<dt>Security patch</dt><dd>{html.escape(report["device"].get("Security patch",""))}</dd>'
 f'<dt>Build</dt><dd><a href="{html.escape(run_url)}">GitHub Actions run {html.escape(release["run"])}</a></dd>'
 f'<dt>Tested</dt><dd>{html.escape(tested)} with {html.escape(report["app"])}</dd></dl>')
body=header+''.join(
 f'<h2>{html.escape(area)}</h2><div class="wrap"><table class="r">'
 +''.join(f'<tr><td>{html.escape(label)}'+(f'<small>{html.escape(note)}</small>' if note else '')+f'</td><td class="s">{badge(s)}</td></tr>' for label,s,note in rows)
 +'</table></div>' for area,rows in tables)
target=a.site/tree/tag
target.mkdir(parents=True,exist_ok=True)
(target/'index.html').write_text(page(f'{phone} {tag}',body))
stale=target/'report.json'
if stale.exists():stale.unlink()

manifest_path=a.site/'reports.json'
manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else []
entry={'tree':tree,'device':device,'phone':phone,'tag':tag,'tested':tested,'build_run':release['run'],'counts':counts}
manifest=[e for e in manifest if (e['tree'],e['tag'])!=(tree,tag)]+[entry]
manifest.sort(key=lambda e:(e['tree'],e['tag']),reverse=True)
manifest_path.write_text(json.dumps(manifest,indent=1)+'\n')
rows=''.join(
 f'<tr><td><a href="{html.escape(e["tree"])}/{html.escape(e["tag"])}/">{html.escape(e["tag"])}</a></td><td>{html.escape(e["phone"])}</td>'
 f'<td>{html.escape(e["tested"])}</td><td>'+' '.join(f'{badge(s)} {n}' for s,n in e['counts'].items() if n)+'</td></tr>'
 for e in manifest)
(a.site/'index.html').write_text(page('ROM test reports','<h1>ROM test reports</h1>'
 f'<p>Test results for the releases of <a href="{server}">{html.escape(a.repository)}</a>.</p>'
 f'<div class="wrap"><table><tr><th>Release</th><th>Phone</th><th>Tested</th><th>Results</th></tr>{rows}</table></div>'))
(a.site/'.nojekyll').touch()
print(f'Report written to {target}; commit and push the test-reports branch.')
