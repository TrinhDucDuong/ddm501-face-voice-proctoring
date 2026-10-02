import pytest

from pipeline.prepare_deploy_env import prepare


def test_exam_and_api_use_same_credential_source(tmp_path):
    import json
    import os
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which('docker'):
        pytest.skip('Docker Compose is required for configuration validation')
    env_file = tmp_path / 'service.env'
    env_file.write_text('API_KEY=file-service-secret\n')
    environment = dict(os.environ, ENV_FILE=str(env_file), API_KEY='unrelated-shell-secret')
    result = subprocess.run(['docker', 'compose', 'config', '--format', 'json'],
                            cwd=Path(__file__).parents[1], env=environment,
                            capture_output=True, text=True, check=True)
    services = json.loads(result.stdout)['services']
    api_environment = services['api']['environment']
    exam_environment = services['legacy-demo']['environment']
    assert api_environment['API_KEY'] == 'file-service-secret'
    assert exam_environment.get('EXAM_SERVICE_API_KEY', exam_environment.get('API_KEY')) == 'file-service-secret'


def test_deploy_secrets_and_existing_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("DEPLOY_POSTGRES_PASSWORD", "long_database_secret_501")
    monkeypatch.setenv("DEPLOY_API_KEY", "long_api_secret_501")
    (tmp_path / ".env.example").write_text(
        "POSTGRES_PASSWORD=biometric_dev_only\nAPI_KEY=demo-internal-key\n"
        "DATABASE_URL=postgresql://user:biometric_dev_only@postgres/db\nCUSTOM=keep\n"
    )
    prepare(tmp_path)
    content = (tmp_path / ".env").read_text()
    assert "user:long_database_secret_501@" in content
    assert "API_KEY=long_api_secret_501" in content
    assert "CUSTOM=keep" in content
    prepare(tmp_path)
    assert (tmp_path / ".env").read_text() == content
    monkeypatch.setenv("DEPLOY_POSTGRES_PASSWORD", "different_database_secret")
    with pytest.raises(ValueError, match="differs"):
        prepare(tmp_path)
    assert (tmp_path / ".env").read_text() == content


def test_deploy_rejects_missing_or_unsafe_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("DEPLOY_POSTGRES_PASSWORD", "$(unsafe)/secret")
    with pytest.raises(ValueError, match="URL-safe"):
        prepare(tmp_path)
    assert not (tmp_path / ".env").exists()


def test_runner_preserves_runtime_values_and_absolute_paths(tmp_path):
    from dotenv import dotenv_values

    from pipeline.prepare_runner_env import prepare as prepare_runner

    runtime, destination = tmp_path / 'runtime folder', tmp_path / 'checkout'
    runtime.mkdir()
    destination.mkdir()
    (runtime / '.env').write_text("API_KEY='secret # with space'\nPOSTGRES_PASSWORD='unchanged'\nCOMPOSE_PROJECT_NAME=existing\n")
    original = (runtime / '.env').read_bytes()
    prepare_runner(destination, runtime)
    config = dotenv_values(destination / '.env')
    assert config['API_KEY'] == 'secret # with space'
    assert config['POSTGRES_PASSWORD'] == 'unchanged'
    assert config['COMPOSE_PROJECT_NAME'] == 'existing'
    assert config['DATA_PATH'] == (runtime / 'data').as_posix()
    assert (runtime / '.env').read_bytes() == original
