"""Reload a promoted champion and restore its predecessor if readiness regresses."""
from __future__ import annotations

import json
import os
import time


def reload_with_rollback(client, model_name, new_version, previous_version, reload, ready,
                         observe_seconds: int = 30, candidate_version: str | None = None) -> dict:
    if candidate_version is not None and candidate_version != new_version:
        return {'status': 'skipped', 'champion': new_version,
                'reason': 'challenger_was_not_promoted'}

    def verify():
        state = ready()
        if state.get('model_version') != new_version:
            raise RuntimeError('Serving version differs from Registry champion')
        return state

    try:
        reload()
        verify()
        deadline = time.monotonic() + max(0, observe_seconds)
        while time.monotonic() < deadline:
            time.sleep(min(5, deadline - time.monotonic()))
            verify()
        return {'status': 'healthy', 'champion': new_version, 'observed_seconds': observe_seconds}
    except Exception as cause:
        if not previous_version or previous_version == new_version:
            client.delete_registered_model_alias(model_name, 'champion')
            raise RuntimeError('Serving failed and no previous champion is recorded') from cause
        client.set_registered_model_alias(model_name, 'champion', previous_version)
        reload()
        restored = ready()
        if restored.get('model_version') != previous_version:
            raise RuntimeError('Serving failed and rollback was not healthy') from cause
        raise RuntimeError(f'Serving failed; rollback restored champion {previous_version}') from cause


def main():
    import requests
    from mlflow import MlflowClient

    client = MlflowClient(tracking_uri=os.environ['MLFLOW_TRACKING_URI'])
    model = os.getenv('MLFLOW_MODEL_NAME', 'face-voice-risk-bundle')
    champion = client.get_model_version_by_alias(model, 'champion')
    candidate = client.get_model_version_by_alias(model, 'candidate')
    previous = champion.tags.get('rollback_version')
    session = requests.Session()
    session.trust_env = False
    base = os.environ['API_URL'].rstrip('/')
    headers = {'X-API-Key': os.environ['API_KEY']}

    def reload():
        response = session.post(base + '/v1/admin/reload-model', headers=headers, timeout=90)
        response.raise_for_status()

    def ready():
        response = session.get(base + '/ready', timeout=20)
        response.raise_for_status()
        return response.json()

    result = reload_with_rollback(client, model, champion.version, previous, reload, ready,
                                  observe_seconds=int(os.getenv('MODEL_OBSERVE_SECONDS', '30')),
                                  candidate_version=candidate.version)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
