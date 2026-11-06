from pathlib import Path
import threading
import time
import pytest
import numpy as np
from fastapi.testclient import TestClient
from studio.server import create_app
from studio.instance import InstanceLock
from studio.audio import write_wave, validate_wave
from studio.privacy import public_error
from fake_engine import DemoEngine
from test_core import payload, wait, make_audio
from model_fixtures import make_model
from studio.models import Registry
from studio.store import Store

ROOT=Path(__file__).resolve().parents[1]


def test_single_process_data_lock(tmp_path):
    first=InstanceLock(tmp_path)
    try:
        with pytest.raises(RuntimeError):InstanceLock(tmp_path)
    finally:first.close()
    second=InstanceLock(tmp_path);second.close()


def test_unicode_model_directory(tmp_path):
    folder=make_model(tmp_path/'\u6a21\u578b'/'\u58f0\u97f3\u8bbe\u8ba1')
    registry=Registry(Store(tmp_path/'data'),[tmp_path/'\u6a21\u578b'])
    records=registry.scan();assert len(records)==1 and records[0]['status']=='ready'


def test_weight_header_corruption_detected(tmp_path):
    folder=make_model(tmp_path/'model');(folder/'model.safetensors').write_bytes(b'not-real-weights'*10)
    registry=Registry(Store(tmp_path/'data'),[folder])
    record=registry.scan()[0]
    assert record['status']=='incomplete'
    assert any('invalid_weight_header' in item for item in record['issues'])


def test_privacy_valueerror_not_echoed():
    message=public_error(ValueError('PERSONAL-TRANSCRIPT /home/ExampleUser/a.wav'))
    assert 'PERSONAL' not in message and 'ExampleUser' not in message


def test_active_job_guards_configuration_and_cleanup(tmp_path):
    class Slow(DemoEngine):
        def generate(self,request,text,reference,cancel):
            for _ in range(80):
                if cancel.is_set():
                    from studio.engine import Cancelled
                    raise Cancelled()
                time.sleep(.01)
            return super().generate(request,text,reference,cancel)
    app=create_app(ROOT,tmp_path,demo=True,engine=Slow())
    with TestClient(app,base_url='http://127.0.0.1') as client:
        client.headers['X-Studio-Token']=client.get('/api/bootstrap').json()['token']
        job=client.post('/api/jobs',json=payload()).json()
        pref=client.get('/api/preferences').json()
        assert client.put('/api/preferences',json=pref).status_code==409
        assert client.post('/api/privacy/clear',headers={'X-Confirm-Clear':'clear-local-history'}).status_code==409
        assert client.delete('/api/models/demo_design').status_code==409
        client.post('/api/jobs/'+job['id']+'/cancel')
        assert wait(client,job['id'])['status']=='cancelled'


def test_history_search_literal_not_wildcard(client):
    wait(client,client.post('/api/jobs',json=payload()).json()['id'])
    assert client.get('/api/history?q=%25').json()['total']==0
    assert client.get('/api/history?q=test').json()['total']==1


def test_shutdown_rejects_submission(tmp_path):
    app=create_app(ROOT,tmp_path,demo=True,engine=DemoEngine())
    app.state.jobs.close()
    with pytest.raises(ValueError,match='shutting'):
        app.state.jobs.submit({'model_id':'demo_design'})


def test_clean_start_without_any_inference_dependency(tmp_path):
    app=create_app(ROOT,tmp_path,model_roots=[],engine=DemoEngine())
    with TestClient(app,base_url='http://127.0.0.1') as client:
        boot=client.get('/api/bootstrap').json()
        assert boot['models']==[] and not boot['demo']
        assert not boot['preferences']['remember_drafts']
        assert client.get('/').status_code==200


def test_health_and_security_headers(client):
    response=client.get('/api/health')
    from studio import __version__
    assert response.json()['version'] == __version__
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    assert response.headers['x-frame-options']=='DENY'


def test_registration_does_not_expose_path(tmp_path):
    model=make_model(tmp_path/'renamed')
    app=create_app(ROOT,tmp_path/'data',model_roots=[],engine=DemoEngine())
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['X-Studio-Token']=c.get('/api/bootstrap').json()['token']
        result=c.post('/api/models',json={'path':str(model)})
        assert result.status_code==200
        assert 'path' not in result.json()
        assert str(tmp_path) not in c.get('/api/models').text
        assert c.post('/api/models',json={'path':'https://example.test/weights'}).status_code==400


def test_unregistered_model_not_deleted(tmp_path):
    folder=make_model(tmp_path/'model')
    app=create_app(ROOT,tmp_path/'data',model_roots=[folder],engine=DemoEngine())
    with TestClient(app,base_url='http://127.0.0.1') as c:
        boot=c.get('/api/bootstrap').json();c.headers['X-Studio-Token']=boot['token']
        assert c.delete('/api/models/'+boot['models'][0]['id']).status_code==200
        assert (folder/'model.safetensors').is_file()


def test_shape_and_nonfinite_audio_rejected():
    for wave in [np.ones((3,4)),[1,np.inf], [1,np.nan]]:
        with pytest.raises(ValueError):validate_wave(wave,24000)


def test_failed_write_removes_partial(tmp_path, monkeypatch):
    def fail(path, *args, **kwargs):
        Path(path).write_bytes(b'partial')
        raise OSError('simulated disk full')
    monkeypatch.setattr('studio.audio.sf.write', fail)
    with pytest.raises(OSError):
        write_wave(tmp_path/'audio.wav', np.ones(100), 24000)
    assert not list(tmp_path.iterdir())


def test_file_lease_release_on_disconnect(tmp_path):
    import asyncio
    from studio.files import FileLeases
    path=tmp_path/'audio.wav';path.write_bytes(b'1234')
    leases=FileLeases();response=leases.response(path)
    assert leases.busy(path)
    async def send(message):raise ConnectionError('disconnected')
    async def receive():return {'type':'http.disconnect'}
    scope={'type':'http','method':'GET','headers':[], 'path':'/api/audio/test'}
    with pytest.raises(ConnectionError):asyncio.run(response(scope,receive,send))
    assert not leases.busy()
    response.release()  # Idempotent cleanup.
    assert not leases.busy()


def test_delete_and_clear_guard_active_audio_response(client):
    job=wait(client,client.post('/api/jobs',json=payload()).json()['id'])
    track=job['track_id'];store=client.app.state.store
    response=client.app.state.file_leases.response(store.root/'audio'/f'{track}.wav')
    try:
        assert client.delete('/api/history/'+track).status_code==409
        assert client.post('/api/privacy/clear',headers={'X-Confirm-Clear':'clear-local-history'}).status_code==409
    finally:response.release()
    assert client.delete('/api/history/'+track).status_code==200
