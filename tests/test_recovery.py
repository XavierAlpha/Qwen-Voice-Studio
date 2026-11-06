"""Regression coverage for settings, model-state recovery and the default preset library."""
from pathlib import Path
from fastapi.testclient import TestClient
from studio.server import create_app
from studio import __version__
from fake_engine import DemoEngine


def test_factory_presets_restore_without_overwriting_edits(client):
    initial = client.get('/api/presets').json()
    assert len(initial) == 3
    edited = next(row for row in initial if row['id'] == 'warm')
    response = client.put('/api/presets/warm', json={
        'name': 'Personal setting', 'instruct': 'Keep this exact text', 'language': 'English'})
    assert response.status_code == 200
    deleted = next(row for row in initial if row['id'] == 'bright')
    assert client.delete('/api/presets/' + deleted['id']).status_code == 200
    restored = client.post('/api/presets/restore')
    assert restored.status_code == 200
    by_id = {row['id']: row for row in restored.json()}
    assert len(by_id) == 3
    assert by_id['warm']['name'] == 'Personal setting'
    assert by_id['warm']['instruct'] == 'Keep this exact text'
    assert by_id['bright']['name'] == deleted['name']


def test_presets_reappear_after_restart_without_restoring_private_content(tmp_path):
    root = Path(__file__).resolve().parents[1]
    first_app = create_app(root, tmp_path / 'data', demo=True, engine=DemoEngine())
    with TestClient(first_app) as c:
        c.headers['X-Studio-Token'] = c.get('/api/bootstrap').json()['token']
        assert c.post('/api/presets', json={
            'name': 'A secret speaker', 'instruct': 'private custom instructions', 'language': 'Chinese'}).status_code == 201
        response = c.post('/api/privacy/clear', headers={'X-Confirm-Clear': 'clear-local-history'})
        assert response.status_code == 200
        assert c.get('/api/presets').json() == []
    second_app = create_app(root, tmp_path / 'data', demo=True, engine=DemoEngine())
    with TestClient(second_app) as c:
        models = c.get('/api/bootstrap').json()['models']
        assert len(models) == 3 and all(model['status'] == 'ready' for model in models)
        presets = c.get('/api/bootstrap').json()['presets']
        assert len(presets) == 3
        assert 'secret' not in str(presets).lower()
        assert 'private custom' not in str(presets).lower()


def test_browser_assets_are_never_mixed_across_releases(client):
    assert client.get('/api/health').json()['version'] == __version__
    assert client.get('/api/health').headers['Cache-Control'] == 'no-store'
    for path in ('/', '/ui/app.js', '/ui/settings.js', '/ui/styles.css', '/ui/index.html'):
        result = client.get(path)
        # ui/index.html is not directly accessible in some static-mount variants;
        # the root route always serves the canonical HTML document.
        assert result.status_code == 200, path
        assert 'no-store' in result.headers.get('Cache-Control', ''), path
    home = client.get('/').text
    assert f'v={__version__}' in home
