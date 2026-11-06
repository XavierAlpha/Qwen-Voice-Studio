"""Unit + real HTTP integration tests; DemoEngine only returns an explicit test tone."""
import io
import json
from pathlib import Path
import time
from uuid import uuid4
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from studio.server import create_app
from studio.store import Store
from studio.models import Registry
from studio.schema import Generate, Runtime
from studio.audio import split_sentences, validate_wave, read_reference, write_wave
from fake_engine import DemoEngine

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def client(tmp_path):
    app = create_app(ROOT, tmp_path, demo=True, engine=DemoEngine())
    with TestClient(app) as c:
        c.headers['x-studio-token'] = c.get('/api/bootstrap').json()['token']
        yield c

def payload(**changes):
    return {"model_id":"demo_design", "mode":"design", "text":"Hello, this is a test.", "instruct":"A warm adult narrator.", **changes}

def wait(c, job_id):
    for _ in range(100):
        data = c.get('/api/jobs/'+job_id).json()
        if data['status'] not in {'queued','running','loading','cancelling'}:
            return data
        time.sleep(.04)
    pytest.fail('Job timeout')

def make_audio(seconds=1, rate=24000):
    output = io.BytesIO()
    sf.write(output, .1*np.sin(np.arange(int(seconds*rate))*2*np.pi*300/rate), rate, format='WAV')
    return output.getvalue()

def test_generate_download_export_reuse(client):
    response = client.post('/api/jobs',json=payload())
    assert response.status_code == 202
    job=wait(client,response.json()['id'])
    assert job['status']=='done'
    track=client.get('/api/history/'+job['track_id']).json()
    assert track['request']['sampling']['seed']>=0
    assert track['duration']>0
    assert len(track['peaks'])==200
    for fmt in ('wav','flac'):
        response=client.get('/api/audio/'+track['id']+'?format='+fmt)
        assert response.status_code==200
        audio,rate=sf.read(io.BytesIO(response.content))
        assert len(audio)>0 and rate==24000
    assert client.patch('/api/history/'+track['id'],json={'title':'Renamed','favorite':True}).json()['title']=='Renamed'
    assert client.get('/api/history?favorite=true').json()['total']==1
    assert client.get('/api/history?q=Renamed').json()['total']==1
    ref=client.post('/api/history/'+track['id']+'/reference').json()
    assert ref['transcript']==track['text']
    assert client.get('/api/references/'+ref['id']+'/audio').status_code==200
    assert client.delete('/api/history/'+track['id']).status_code==200
    assert client.get('/api/audio/'+track['id']).status_code==404

def test_restored_reference_metadata_is_minimal_and_can_expire(client):
    response = client.post('/api/references', content=make_audio(), headers={'content-type': 'audio/wav', 'x-filename': 'private-speaker-name.wav'})
    assert response.status_code == 201
    ref = response.json()
    info = client.get('/api/references/' + ref['id'])
    assert info.status_code == 200
    assert set(info.json()) == {'id', 'name', 'duration', 'sample_rate'}
    assert info.json()['id'] == ref['id']
    assert 'private-speaker-name' not in str(info.json())
    assert client.delete('/api/references/' + ref['id']).status_code == 200
    assert client.get('/api/references/' + ref['id']).status_code == 404
    assert client.get('/api/references/no-such-reference').status_code == 404


def test_clone(client):
    response=client.post('/api/references',content=make_audio(),headers={'content-type':'audio/wav','x-filename':'voice.wav'})
    assert response.status_code==201
    body=payload(model_id='demo_clone',mode='clone',reference_id=response.json()['id'],ref_text='Hello.',consent=True)
    job=wait(client,client.post('/api/jobs',json=body).json()['id'])
    assert job['status']=='done'

def test_custom(client):
    job=wait(client,client.post('/api/jobs',json=payload(model_id='demo_custom',mode='custom',speaker='Vivian')).json()['id'])
    assert job['status']=='done'

def test_reject_wrong_mode_and_speaker(client):
    assert client.post('/api/jobs',json=payload(mode='custom',speaker='Vivian')).status_code==400
    assert client.post('/api/jobs',json=payload(model_id='demo_custom',mode='custom',speaker='bad')).status_code==400

def test_clone_requires_authorization_and_reference(client):
    assert client.post('/api/jobs',json=payload(mode='clone',model_id='demo_clone')).status_code==422
    assert client.post('/api/jobs',json=payload(mode='clone',model_id='demo_clone',reference_id='0'*32,consent=True,ref_text='test')).status_code==400

def test_presets_crud(client):
    p=client.post('/api/presets',json={'name':'Local','instruct':'A low warm voice'}).json()
    assert p['id']
    response=client.put('/api/presets/'+p['id'],json={'name':'Edited','instruct':'New direction'})
    assert response.json()['name']=='Edited'
    client.delete('/api/presets/'+p['id'])
    assert all(x['id']!=p['id'] for x in client.get('/api/presets').json())

def test_settings_and_load_unload(client):
    runtime=Runtime(device='cpu').model_dump()
    assert client.put('/api/runtime',json=runtime).status_code==200
    assert client.get('/api/bootstrap').json()['runtime']['device']=='cpu'
    j=client.post('/api/models/load',json={'model_id':'demo_design','runtime':runtime}).json()
    assert wait(client,j['id'])['status']=='done'
    assert client.get('/api/system').json()['model']['loaded']
    assert client.post('/api/models/unload').status_code==200
    assert not client.get('/api/system').json()['model']['loaded']

def test_cancel_and_serial_jobs(client):
    first=client.post('/api/jobs',json=payload()).json()
    second=client.post('/api/jobs',json=payload()).json()
    cancelled=client.post('/api/jobs/'+second['id']+'/cancel')
    assert cancelled.status_code==200
    assert wait(client,second['id'])['status']=='cancelled'
    assert wait(client,first['id'])['status']=='done'

def test_segmented_job(client):
    j=client.post('/api/jobs',json=payload(text=('A reasonably long sentence about testing. '*8),split_text=True,chunk_chars=80)).json()
    result=wait(client,j['id'])
    assert result['status']=='done'
    assert result['total']>1 and result['completed']==result['total']

def test_error_job_recovery(tmp_path):
    class BadEngine(DemoEngine):
        def generate(self,*args):
            return np.array([np.nan],dtype='float32'),24000
    app=create_app(ROOT,tmp_path,demo=True,engine=BadEngine())
    with TestClient(app) as c:
        c.headers['x-studio-token']=c.get('/api/bootstrap').json()['token']
        j=c.post('/api/jobs',json=payload()).json()
        result=wait(c,j['id'])
        assert result['status']=='failed' and 'Nonfinite audio samples' in result['error']
        assert c.get('/api/history').json()['total']==0
        assert not list((tmp_path/'audio').glob('*.wav'))

def test_security_csrf_origin_host(client):
    assert client.post('/api/presets',headers={'x-studio-token':''},json={'name':'x','instruct':'y'}).status_code==403
    assert client.post('/api/presets',headers={'origin':'https://evil.example'},json={'name':'x','instruct':'y'}).status_code==403
    assert client.get('/api/bootstrap',headers={'host':'evil.example'}).status_code==400
    response=client.get('/')
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert response.headers['x-content-type-options']=='nosniff'

def test_no_arbitrary_file_download(client):
    for path in ['/api/audio/nope','/api/audio/..%2F..%2Fapp.py','/api/references/nope/audio','/ui/..%2Fapp.py']:
        assert client.get(path).status_code in {400,404}

def test_request_boundaries(client):
    assert client.post('/api/jobs',json=payload(text='')).status_code==422
    assert client.post('/api/jobs',json=payload(text='x'*6001)).status_code==422
    assert client.post('/api/jobs',json=payload(text='x'*601)).status_code==422
    assert client.post('/api/jobs',json=payload(sampling={'temperature':99})).status_code==422
    assert client.post('/api/jobs',json=payload(unwanted='x')).status_code==422
    assert client.post('/api/jobs',json=payload(language='Not a language')).status_code==422
    assert client.get('/api/history?offset=-1').status_code==400
    assert client.get('/api/history?limit=100000').status_code==400

def test_bad_audio_rejected(client):
    for raw in (b'',b'not an audio file',make_audio(.1),make_audio(61)):
        assert client.post('/api/references',content=raw).status_code==400
    assert client.post('/api/references',content=b'x'*(25*1024*1024+1)).status_code==413

def test_filename_is_sanitized(client):
    r=client.post('/api/references',content=make_audio(),headers={'x-filename':'..%2F..%2Fvoice.wav'}).json()
    assert r['name'].startswith('reference-') and 'voice.wav' not in r['name']

def test_model_config_and_registration(tmp_path):
    from model_fixtures import make_model
    store=Store(tmp_path/'data');registry=Registry(store,[])
    folder=make_model(tmp_path/'model')
    model=registry.register(str(folder));assert model['mode']=='design'
    assert registry.register(str(folder))['id']==model['id']
    (folder/'config.json').write_text('{"model_type":"other"}')
    with pytest.raises(ValueError):registry.register(str(folder))

def test_restart_marks_interrupted(tmp_path):
    store=Store(tmp_path)
    record=store.put('job',{'status':'running'})
    assert store.recover()==1
    assert store.get('job',record['id'])['status']=='interrupted'

def test_wave_validation(tmp_path):
    for values in ([np.nan],[np.inf],[0,0],[]):
        with pytest.raises(ValueError):validate_wave(values,24000)
    wave=validate_wave(np.array([2.,-.5]),24000)
    assert max(abs(wave))<=1
    quiet=validate_wave(np.array([.001,-.001]),24000)
    assert max(abs(quiet))==pytest.approx(.001)
    path=tmp_path/'a.wav';write_wave(path,quiet,24000)
    assert path.exists() and not path.with_suffix('.part').exists()

def test_splitting_limits_and_content():
    text='A test. Another longer sentence! '+('abcdefgh'*30)
    parts=split_sentences(text,60)
    assert all(0<len(p)<=60 for p in parts)
    assert ''.join(''.join(parts).split())==''.join(text.split())
    zh='\u4f60\u597d\u3002\u4eca\u5929\u662f\u65b0\u7684\u4e00\u5929\uff01'*12
    parts=split_sentences(zh,60)
    assert ''.join(parts)==zh
