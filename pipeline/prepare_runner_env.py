"""Reuse authorized local persistence/secrets from a trusted Windows runner checkout."""
import argparse
import io
import os
import re
import subprocess
import zipfile
from pathlib import Path

from dotenv import dotenv_values, set_key


def prepare(destination, runtime):
    runtime = runtime.resolve()
    source = runtime / '.env'
    if not source.is_file():
        raise ValueError('Runner runtime .env is missing')
    config = dict(dotenv_values(source))
    for name, suffix in [('MODELS_PATH','models'),('DATA_PATH','data'),('REPORTS_PATH','reports'),('AIRFLOW_LOGS_PATH','airflow/logs')]:
        config[name] = (runtime / suffix).as_posix()
    # The self-hosted deployment retains the same DB credentials, named volumes
    # and biometric assets. Only trusted main-branch source code is replaced.
    target = destination / '.env'
    target.write_text('', encoding='utf-8')
    for name, value in config.items():
        if value is not None:
            set_key(target, name, value, quote_mode='always')
    target.chmod(0o600)


def stage_deployment(source, runtime, revision, local_app_data):
    """Materialize the exact commit outside OneDrive for reliable Docker binds."""
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Deployment requires a full Git commit SHA')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=source, capture_output=True,
                          text=True, check=True).stdout.strip()
    if head != revision:
        raise ValueError('Checkout does not match the requested deployment commit')
    archive = subprocess.run(['git', 'archive', '--format=zip', revision], cwd=source,
                             capture_output=True, check=True).stdout
    release = (local_app_data / 'DDM501' / 'deployments' / revision).resolve()
    release.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        if any(not (release / name).resolve().is_relative_to(release) for name in package.namelist()):
            raise ValueError('Unsafe deployment archive path')
        package.extractall(release)
    prepare(release, runtime)
    return release


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage-deployment', action='store_true')
    args = parser.parse_args()
    runtime = Path(os.environ['DDM501_RUNTIME_ROOT'])
    if args.stage_deployment:
        print(stage_deployment(Path.cwd(), runtime, os.environ['GITHUB_SHA'], Path(os.environ['LOCALAPPDATA'])))
    else:
        prepare(Path.cwd(), runtime)
