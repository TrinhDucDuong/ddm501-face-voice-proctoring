"""Resolve CI operations to the team repository without accessing credentials."""

import subprocess

import pytest

from pipeline import github_ci

TEAM_URL = 'https://github.com/FSB-MSA36HN/DDM501-face-voice-proctoring.git'
OTHER_URL = 'https://github.com/example/personal-project.git'


@pytest.mark.parametrize(('remotes', 'expected'), [
    ({'origin': OTHER_URL, 'fsb': TEAM_URL}, 'FSB-MSA36HN/DDM501-face-voice-proctoring'),
    ({'origin': TEAM_URL}, 'FSB-MSA36HN/DDM501-face-voice-proctoring'),
    ({'origin': OTHER_URL}, None),
    ({'origin': TEAM_URL, 'fsb': OTHER_URL}, None),
    ({}, None),
])
def test_ci_repository_selection(tmp_path, monkeypatch, remotes, expected):
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    for name, url in remotes.items():
        subprocess.run(['git', 'remote', 'add', name, url], cwd=tmp_path,
                       check=True, capture_output=True)
    monkeypatch.setattr(github_ci, 'ROOT', tmp_path)
    if expected is None:
        with pytest.raises(ValueError, match='FSB'):
            github_ci.repository()
    else:
        assert github_ci.repository() == expected
