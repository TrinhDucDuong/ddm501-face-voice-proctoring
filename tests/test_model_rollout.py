import pytest

from pipeline.model_rollout import reload_with_rollback


class Registry:
    def __init__(self):
        self.alias = '2'
        self.calls = []

    def set_registered_model_alias(self, name, alias, version):
        self.calls.append((name, alias, version))
        self.alias = version

    def delete_registered_model_alias(self, name, alias):
        self.calls.append((name, alias, None))
        self.alias = None


def test_reload_failure_restores_previous_champion():
    client = Registry()
    served = []

    def reload():
        served.append(client.alias)

    def ready():
        return {'model_version': '1' if client.alias == '2' else client.alias}

    with pytest.raises(RuntimeError, match='rollback'):
        reload_with_rollback(client, 'bundle', '2', '1', reload, ready, observe_seconds=0)
    assert client.alias == '1' and served == ['2', '1']


def test_successful_reload_keeps_new_champion():
    client = Registry()
    served = []
    result = reload_with_rollback(client, 'bundle', '2', '1',
                                  lambda: served.append(client.alias),
                                  lambda: {'model_version': client.alias}, observe_seconds=0)
    assert result['status'] == 'healthy' and client.alias == '2'
    assert served == ['2'] and client.calls == []


def test_rejected_challenger_does_not_reload_or_rollback_incumbent():
    client = Registry()
    calls = []
    result = reload_with_rollback(client, 'bundle', '2', '1',
                                  lambda: calls.append('reload'),
                                  lambda: {'model_version': '2'}, observe_seconds=0,
                                  candidate_version='3')
    assert result['status'] == 'skipped'
    assert calls == [] and client.alias == '2' and client.calls == []


def test_first_promotion_failure_clears_unhealthy_champion_alias():
    client = Registry()
    with pytest.raises(RuntimeError, match='no previous champion'):
        reload_with_rollback(client, 'bundle', '2', None, lambda: None,
                             lambda: {'model_version': 'unready'}, observe_seconds=0)
    assert client.alias is None
    assert client.calls == [('bundle', 'champion', None)]
