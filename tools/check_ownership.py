#!/usr/bin/env python3
"""Check that a branch only changes files its owner may edit.

Usage:
    python3 tools/check_ownership.py partner            # compare with origin/main
    python3 tools/check_ownership.py sergei origin/main
    python3 tools/check_ownership.py --login <github-login> [base]   # used by GitHub Actions

Rules (see ownership.json):
- a page listed in ownership.json may be changed only by its owner;
- shared files (ownership.json -> "shared") are reported as SHARED:
  allowed, but the other owner must approve the PR;
- new images in public/images/ are fine for both; changing or deleting an
  existing image is SHARED.
Exit code 1 if the branch touches the other owner's pages.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(ROOT, 'ownership.json'), encoding='utf-8'))

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
if args[0] == '--login':
    login = args[1].lower()
    owner = next((k for k, v in cfg['github'].items() if v and v.lower() == login), None)
    args = args[2:]
    if owner is None:
        print(f'GitHub user "{login}" is not listed in ownership.json -> github. Nothing to check.')
        sys.exit(0)
else:
    owner = args.pop(0)
if owner not in cfg['github']:
    sys.exit(f'Unknown owner "{owner}". Use one of: {", ".join(cfg["github"])}')
base = args[0] if args else 'origin/main'

diff = subprocess.run(['git', 'diff', '--name-status', '--no-renames', f'{base}...HEAD'],
                      cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()

foreign, shared, own = [], [], []
for line in diff:
    status, path = line.split('\t', 1)
    entry = cfg['files'].get(path)
    if entry:
        (own if entry['owner'] == owner else foreign).append(f"{path}  ({entry['url']}, owner: {entry['owner']})")
    elif path.startswith('public/images/') and status == 'A':
        own.append(path + '  (new image)')
    elif any(path == s or (s.endswith('/') and path.startswith(s)) for s in cfg['shared']) or path.startswith('public/images/'):
        shared.append(path)
    elif path.startswith('public/') and status == 'A':
        shared.append(path + '  (NEW PAGE: add it to ownership.json -> files)')
    else:
        shared.append(path)

print(f'Owner: {owner}   base: {base}   changed files: {len(diff)}')
for title, lst in (('OK - own files', own), ('SHARED - needs approval from the other owner', shared),
                   ("NOT ALLOWED - other owner's pages", foreign)):
    if lst:
        print(f'\n{title}:')
        for x in lst:
            print('  ' + x)
sys.exit(1 if foreign else 0)
