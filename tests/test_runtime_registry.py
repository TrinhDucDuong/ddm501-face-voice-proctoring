import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.config import Settings
from app.registry import RegistryLoader


def test_registry_pins_artifact_and_preserves_champion_on_invalid_bundle(monkeypatch, tmp_path):
    from app import registry

    settings = Settings(model_backend='demo')
    loader = RegistryLoader(settings)
    client = Mock()
    client.get_model_version_by_alias.return_value = SimpleNamespace(version='8')
    monkeypatch.setattr(registry,'MlflowClient',lambda:client)
    monkeypatch.setattr(registry.mlflow,'set_tracking_uri',lambda _:None)
    download = Mock(return_value=str(tmp_path))
    monkeypatch.setattr(registry.mlflow.artifacts,'download_artifacts',download)
    path = tmp_path/'thresholds.json'
    path.write_text(json.dumps({'face_threshold':.4,'voice_threshold':.2}))
    assert loader.load().version == '8'
    assert download.call_args.kwargs['artifact_uri'].endswith('/8')
    path.write_text(json.dumps({'face_threshold':float('nan'),'voice_threshold':.2}))
    with pytest.raises(ValueError,match='thresholds'):
        loader.load()
    assert loader.current.face_threshold == .4 and loader.current.version == '8'
    path.unlink()
    with pytest.raises(FileNotFoundError):
        loader.load()
    assert loader.current.version == '8'
