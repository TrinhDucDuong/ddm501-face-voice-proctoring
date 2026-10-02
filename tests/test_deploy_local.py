"""Local Windows deployment boundary checks; CI on Ubuntu skips host-specific tests."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'pipeline' / 'deploy_local.ps1'


def _runtime_root():
    if sys.platform != 'win32':
        pytest.skip('Windows Docker Desktop deployment check')
    value = os.environ.get('DDM501_RUNTIME_ROOT')
    if not value:
        pytest.skip('DDM501_RUNTIME_ROOT is not configured')
    return value


def _invoke(revision):
    return subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
         '-File', str(SCRIPT), '-Workspace', str(ROOT),
         '-RuntimeRoot', _runtime_root(), '-Revision', revision, '-Preflight'],
        capture_output=True, text=True, timeout=120,
    )


def test_deployment_preflight_stages_exact_checkout():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result = _invoke(revision)
    assert result.returncode == 0, result.stderr
    assert f'Preflight OK: {revision}' in result.stdout


def test_deployment_rejects_other_revision_before_staging():
    result = _invoke('0' * 40)
    assert result.returncode != 0
    assert 'Checkout revision does not match' in result.stderr
