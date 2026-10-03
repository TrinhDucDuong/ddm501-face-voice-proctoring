"""Windows preflight checks using disposable checkout, runtime and release paths."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def deployment(tmp_path):
    if sys.platform != 'win32':
        pytest.skip('Executed by the deployment-preflight Windows CI job')
    workspace = tmp_path / 'checkout with spaces'
    runtime = tmp_path / 'runtime with spaces'
    local_app_data = tmp_path / 'local app data'
    workspace.mkdir()
    runtime.mkdir()
    for name in ('pipeline/deploy_local.ps1', 'pipeline/prepare_runner_env.py', 'docker-compose.yml'):
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    shutil.copyfile(ROOT / '.env.example', runtime / '.env')
    # A real interpreter and dotenv, isolated from the authorized demo runtime.
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', '--system-site-packages',
                    str(runtime / '.venv')], check=True)
    environment = dict(os.environ, LOCALAPPDATA=str(local_app_data))
    environment['PYTHONPATH'] = os.pathsep.join(filter(None, sys.path))
    for arguments in (['init'], ['config', 'core.autocrlf', 'false'], ['add', '.'],
                      ['-c', 'user.name=Deployment Test', '-c', 'user.email=test@example.invalid',
                       '-c', 'commit.gpgsign=false', 'commit', '-m', 'Preflight fixture']):
        subprocess.run(['git', *arguments], cwd=workspace, env=environment,
                       capture_output=True, text=True, check=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=workspace, text=True).strip()
    return workspace, runtime, local_app_data, revision, environment


def _invoke(deployment, revision):
    workspace, runtime, _, _, environment = deployment
    return subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
         '-File', str(workspace / 'pipeline/deploy_local.ps1'), '-Workspace', str(workspace),
         '-RuntimeRoot', str(runtime), '-Revision', revision, '-Preflight'],
        env=environment, capture_output=True, text=True, timeout=120,
    )


def test_deployment_preflight_stages_exact_checkout(deployment):
    workspace, runtime, local_app_data, revision, _ = deployment
    original_env = (runtime / '.env').read_bytes()
    committed_compose = (workspace / 'docker-compose.yml').read_bytes()
    (workspace / 'docker-compose.yml').write_text('uncommitted invalid compose')
    result = _invoke(deployment, revision)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'Preflight OK: {revision}' in result.stdout
    release = local_app_data / 'DDM501/deployments' / revision
    assert (release / 'docker-compose.yml').read_bytes() == committed_compose
    assert (release / '.env').is_file()
    assert (runtime / '.env').read_bytes() == original_env


def test_deployment_rejects_other_revision_before_staging(deployment):
    _, runtime, local_app_data, _, _ = deployment
    original_env = (runtime / '.env').read_bytes()
    result = _invoke(deployment, '0' * 40)
    assert result.returncode != 0
    assert 'Checkout revision does not match' in result.stderr
    assert not (local_app_data / 'DDM501/deployments').exists()
    assert (runtime / '.env').read_bytes() == original_env
