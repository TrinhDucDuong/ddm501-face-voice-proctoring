"""Operate the authorized repository using Git Credential Manager without logging secrets."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
TEAM_REPOSITORY = 'FSB-MSA36HN/DDM501-face-voice-proctoring'


def repository():
    remotes = subprocess.run(['git', 'remote'], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.splitlines()
    name = 'fsb' if 'fsb' in remotes else 'origin'
    if name not in remotes:
        raise ValueError('Configure an HTTPS remote for the FSB team repository')
    remote = subprocess.run(['git', 'remote', 'get-url', name], cwd=ROOT,
                            capture_output=True, text=True, check=True).stdout.strip()
    match = re.fullmatch(r'https://github.com/([^/]+/[^/]+?)(?:\.git)?',remote)
    if not match or match[1].lower() != TEAM_REPOSITORY.lower():
        raise ValueError(f'Remote {name} must point to the FSB team repository over HTTPS')
    return TEAM_REPOSITORY


def client():
    repo = repository()
    credential = subprocess.run(['git','credential','fill'],input='protocol=https\nhost=github.com\n\n',
        capture_output=True,text=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'},timeout=30)
    entries = dict(line.split('=',1) for line in credential.stdout.splitlines() if '=' in line)
    if not entries.get('password'):
        raise ValueError('Git Credential Manager does not contain GitHub authorization')
    session = requests.Session()
    session.headers.update({'Authorization':'Bearer '+entries['password'],'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    return session, repo


def call(session, method, path, **kwargs):
    response = session.request(method,'https://api.github.com/'+path,timeout=30,**kwargs)
    if not response.ok:
        raise RuntimeError(f'GitHub API rejected {method} {path}: HTTP {response.status_code}')
    return response.json() if response.content else None


def register(session, repo):
    folder = (ROOT / 'data/github-runner').resolve()
    if not folder.is_relative_to(ROOT.resolve()):
        raise ValueError('Runner path must remain inside the project')
    folder.mkdir(parents=True,exist_ok=True)
    if (folder / '.runner').exists():
        print('Project runner is already configured')
        return folder
    release = call(session,'GET','repos/actions/runner/releases/latest')
    asset = next(a for a in release['assets'] if a['name'].startswith('actions-runner-win-x64-') and a['name'].endswith('.zip'))
    digest = asset.get('digest','')
    if not digest.startswith('sha256:'):
        match = re.search(r'([a-f0-9]{64})\s+' + re.escape(asset['name']),release.get('body',''))
        if match is None:
            raise ValueError('Runner download does not provide a SHA-256 digest')
        digest = 'sha256:' + match[1]
    archive = folder / 'runner.zip'
    with requests.get(asset['browser_download_url'],stream=True,timeout=60) as response:
        response.raise_for_status()
        with archive.open('wb') as output:
            for chunk in response.iter_content(1024*1024):
                output.write(chunk)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest.split(':',1)[1]:
        raise ValueError('Runner SHA-256 verification failed')
    with zipfile.ZipFile(archive) as package:
        if any(not (folder / name).resolve().is_relative_to(folder) for name in package.namelist()):
            raise ValueError('Unsafe runner archive path')
        package.extractall(folder)
    token = call(session,'POST',f'repos/{repo}/actions/runners/registration-token')['token']
    result = subprocess.run(['cmd.exe','/c','config.cmd','--unattended','--url','https://github.com/'+repo,
        '--token',token,'--name','ddm501-local-windows','--labels','ddm501-demo','--work','_work'],cwd=folder,capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Runner registration failed; token and command output are redacted')
    print('Runner registered:',release['tag_name'])
    return folder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--register-runner',action='store_true')
    parser.add_argument('--dispatch',action='store_true')
    args = parser.parse_args()
    session, repo = client()
    if args.register_runner:
        register(session,repo)
        call(session,'PUT',f'repos/{repo}/environments/demo',json={'deployment_branch_policy':{'protected_branches':False,'custom_branch_policies':True}})
        existing = call(session,'GET',f'repos/{repo}/environments/demo/deployment-branch-policies')
        if not any(p['name']=='main' for p in existing['branch_policies']):
            call(session,'POST',f'repos/{repo}/environments/demo/deployment-branch-policies',json={'name':'main','type':'branch'})
    if args.dispatch:
        call(session,'POST',f'repos/{repo}/actions/workflows/ci.yml/dispatches',json={'ref':'main','inputs':{'deploy':True}})
    runs = call(session,'GET',f'repos/{repo}/actions/runs?per_page=5')
    runners = call(session,'GET',f'repos/{repo}/actions/runners')
    report = {'repository':repo,'runs':[{k:r.get(k) for k in ['id','html_url','head_sha','status','conclusion']} for r in runs['workflow_runs']],
              'runners':[{k:r[k] for k in ['id','name','status']} for r in runners['runners']]}
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/github-actions.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
