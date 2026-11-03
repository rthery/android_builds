#!/usr/bin/env python3
"""Rewrite a device's packages.xml from development to release signing identities.

Only certificate and keyset public-key values listed in the signing plan's key_map are
replaced; every other byte is preserved. Unknown certificates (third-party apps) are kept.
Packages the candidate still ships with a mapped source certificate (PRESIGNED prebuilts
such as CtsShim) move to a new certificate index that keeps the old certificate.
"""
import argparse, base64, collections, hashlib, json, pathlib, re, subprocess, sys
import xml.etree.ElementTree as ET


def certificate(path):
    pem = pathlib.Path(str(path) + '.x509.pem')
    der = subprocess.run(['openssl', 'x509', '-in', str(pem), '-outform', 'DER'], capture_output=True, check=True).stdout
    public = subprocess.run(['openssl', 'x509', '-in', str(pem), '-noout', '-pubkey'], capture_output=True, check=True).stdout
    spki = subprocess.run(['openssl', 'pkey', '-pubin', '-outform', 'DER'], input=public, capture_output=True, check=True).stdout
    return der, base64.b64encode(spki).decode()


def report_paths(code_path):
    relative = code_path.lstrip('/')
    first, _, rest = relative.partition('/')
    if first == 'system':
        bases = ['SYSTEM/' + rest]
    elif first == 'apex':
        bases = ['SYSTEM/apex/' + rest]
    else:
        bases = [first.upper() + '/' + rest, 'SYSTEM/' + relative]
    return bases if relative.endswith('.apk') else [base + '/' for base in bases]


def android_signatures(text):
    """Resolve certificates the way PackageSignatures.readCertsListXml does."""
    read, result, owner = [], {}, None
    for match in re.finditer(r'<(package|shared-user) name="([^"]+)"[^>]*[^/]>|</(?:package|shared-user)>|<cert index="(\d+)"(?: key="([0-9A-Fa-f]+)")? />', text):
        if match.group(1):
            owner = (match.group(1), match.group(2))
        elif match.group(3) is None:
            owner = None
        elif owner:
            index = int(match.group(3))
            if match.group(4):
                read.extend([None] * (index - len(read)))
                read.append(match.group(4).lower())
                key = match.group(4).lower()
            else:
                key = read[index] if index < len(read) else None
            result.setdefault(owner, []).append(key)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('packages', type=pathlib.Path, help='packages.xml pulled from the device')
    p.add_argument('--plan', type=pathlib.Path, required=True, help='signing-plan.json of the candidate')
    p.add_argument('--report', type=pathlib.Path, required=True, help='native-signing-report.json of the candidate')
    p.add_argument('--source-root', type=pathlib.Path, required=True, help='Android checkout holding the source certificates')
    p.add_argument('--output', type=pathlib.Path, required=True)
    p.add_argument('--summary', type=pathlib.Path, required=True)
    a = p.parse_args()
    if a.output.exists() or a.summary.exists():
        p.error('Output files must not exist')

    data = a.packages.read_bytes()
    if data.startswith(b'ABX'):
        sys.exit('Binary ABX database; convert it to XML on the device first')
    root = ET.fromstring(data)

    plan = json.loads(a.plan.read_text())
    mapping = {}
    for source, dest in plan['key_map'].items():
        old_der, old_spki = certificate(a.source_root / source)
        new_der, new_spki = certificate(dest)
        if old_der.hex() in mapping:
            sys.exit('Duplicate source certificate: ' + source)
        mapping[old_der.hex()] = {'source': source, 'dest': dest, 'spki': (old_spki, new_spki),
                                  'new_der': new_der, 'new_sha256': hashlib.sha256(new_der).hexdigest()}
    new_ders = {m['new_der'].hex() for m in mapping.values()}

    certs = {c.get('index'): c.get('key') for c in root.iter('cert') if c.get('key')}
    if any(key.lower() in new_ders for key in certs.values()):
        sys.exit('Database already contains a release certificate; refusing to migrate twice')
    users = collections.defaultdict(list)
    for package in root.iter('package'):
        sigs = package.find('sigs')
        for cert in ([] if sigs is None else sigs.iter('cert')):
            users[cert.get('index')].append(package)

    signed = {entry['path']: entry['certificate_sha256'] for entry in json.loads(a.report.read_text())['apks']}
    migrated, kept, problems, kept_old = [], [], [], {}
    for index, key in sorted(certs.items(), key=lambda item: int(item[0])):
        entry = mapping.get(key.lower())
        names = sorted(package.get('name') for package in users[index])
        if entry is None:
            kept.append({'index': index, 'certificate_sha256': hashlib.sha256(bytes.fromhex(key)).hexdigest(), 'packages': names})
            continue
        for package in users[index]:
            prefixes = report_paths(package.get('codePath', ''))
            found = {sha for path, sha in signed.items() if any(path == prefix or (prefix.endswith('/') and path.startswith(prefix)) for prefix in prefixes)}
            if found == {hashlib.sha256(bytes.fromhex(key)).hexdigest()}:
                kept_old.setdefault(index, []).append(package.get('name'))
            elif found != {entry['new_sha256']}:
                problems.append(package.get('name') + ': candidate APK certificates ' + (', '.join(sorted(found)) or 'not found'))
        migrated.append({'index': index, 'source': entry['source'], 'dest': entry['dest'], 'packages': names,
                         'kept_old_certificate': sorted(kept_old.get(index, []))})
    for shared in root.iter('shared-user'):
        members = [package.get('name') for package in root.iter('package') if package.get('sharedUserId') == shared.get('userId')]
        moved = {name for names in kept_old.values() for name in names}
        if moved & set(members) and not set(members) <= moved:
            problems.append('shared user ' + shared.get('name') + ' would mix old and new certificates')
    if problems:
        sys.exit('Candidate does not match the database:\n  ' + '\n  '.join(problems))

    text = data.decode('utf-8')
    counts = collections.Counter()
    moved = {name: index for index, names in kept_old.items() for name in names}
    moved_users = {shared.get('name') for shared in root.iter('shared-user')
                   if any(package.get('sharedUserId') == shared.get('userId') and package.get('name') in moved for package in root.iter('package'))}
    split = set(kept_old)
    values = {}
    for index, key in certs.items():
        entry = mapping.get(key.lower())
        new = entry['new_der'].hex() if entry else key
        values[(index, False)] = new.upper() if key.isupper() else new
        if index in split:
            values[(index, True)] = key
    # Android appends each defining <cert key=...> to its list, so indexes are renumbered in first-use order.
    numbering = {}
    owner = None

    def rewrite(match):
        nonlocal owner
        token = match.group(0)
        if match.group('open'):
            owner = (match.group('kind'), match.group('name'))
            return token
        if match.group('close'):
            owner = None
            return token
        index = match.group('index')
        kept = bool(owner and ((owner[0] == 'package' and owner[1] in moved) or (owner[0] == 'shared-user' and owner[1] in moved_users)) and index in split)
        counts['split'] += kept
        identity = (index, kept)
        if identity in numbering:
            return '<cert index="' + str(numbering[identity]) + '" />'
        numbering[identity] = len(numbering)
        if mapping.get(certs[index].lower()) and not kept:
            counts['cert'] += 1
        return '<cert index="' + str(numbering[identity]) + '" key="' + values[identity] + '" />'

    def replace_spki(match):
        for entry in mapping.values():
            if match.group(2) == entry['spki'][0]:
                counts['public-key'] += 1
                return match.group(1) + entry['spki'][1] + match.group(3)
        return match.group(0)

    text = re.sub(r'(?P<open><(?P<kind>package|shared-user) name="(?P<name>[^"]+)"[^>]*[^/]>)|(?P<close></(?:package|shared-user)>)'
                  r'|<cert index="(?P<index>\d+)"(?: key="[0-9A-Fa-f]+")? />', rewrite, text)
    text = re.sub(r'(<public-key\b[^>]*\bvalue=")([A-Za-z0-9+/=]+)(")', replace_spki, text)
    expected_spki = sum(1 for key in root.iter('public-key') if any(key.get('value') == m['spki'][0] for m in mapping.values()))
    if counts['cert'] != len(migrated) or counts['public-key'] != expected_spki or len(numbering) != len(certs) + len(split):
        sys.exit('Replacement count mismatch: ' + json.dumps(counts))
    expected = {}
    for package in root.iter('package'):
        for cert in package.find('sigs').iter('cert'):
            key = certs[cert.get('index')].lower()
            keep = package.get('name') in moved or mapping.get(key) is None
            expected.setdefault(('package', package.get('name')), []).append(key if keep else mapping[key]['new_der'].hex())
    for shared in root.iter('shared-user'):
        for cert in shared.iter('cert'):
            key = certs[cert.get('index')].lower()
            keep = shared.get('name') in moved_users or mapping.get(key) is None
            expected.setdefault(('shared-user', shared.get('name')), []).append(key if keep else mapping[key]['new_der'].hex())
    if android_signatures(text) != expected:
        sys.exit('Rewritten database does not read back as intended')

    a.output.write_text(text, encoding='utf-8')
    summary = {'input_sha256': hashlib.sha256(data).hexdigest(), 'output_sha256': hashlib.sha256(text.encode()).hexdigest(),
               'migrated_certificates': migrated, 'kept_old_certificate_indexes': sorted(split, key=int), 'split_references': counts['split'],
               'migrated_public_keys': counts['public-key'], 'kept_certificates': kept}
    a.summary.write_text(json.dumps(summary, indent=1) + '\n')
    print(f"Migrated {len(migrated)} certificates covering {sum(len(m['packages']) for m in migrated)} packages and "
          f"{counts['public-key']} keyset keys; kept {len(kept)} third-party certificates.")


if __name__ == '__main__':
    main()
