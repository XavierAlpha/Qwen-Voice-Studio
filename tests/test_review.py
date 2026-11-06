"""Second-review regression tests: cancellation, offline boundary and adapter contracts."""
import json
from pathlib import Path
import time
from types import SimpleNamespace
import numpy as np
import pytest
from fastapi.testclient import TestClient
from studio.server import create_app
from studio.engine import QwenEngine, Cancelled
from fake_engine import DemoEngine
from studio.audio import split_sentences
from studio.schema import Runtime
from test_core import payload, wait, make_audio

ROOT=Path(__file__).resolve().parents[1]

def test_cancel_running_and_unload_guard(tmp_path):
    class Slow(DemoEngine):
        def generate(self, request,text,ref,cancel):
            for _ in range(60):
                if cancel.is_set():raise Cancelled()
                time.sleep(.01)
            return super().generate(request,text,ref,cancel)
    app=create_app(ROOT,tmp_path,demo=True,engine=Slow())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.headers['x-studio-token']=c.get('/api/bootstrap').json()['token']
        j=c.post('/api/jobs',json=payload()).json()
        for _ in range(40):
            if c.get('/api/jobs/'+j['id']).json()['status']=='running':break
            time.sleep(.02)
        assert c.post('/api/models/unload').status_code==409
        assert c.post('/api/jobs/'+j['id']+'/cancel').status_code==200
        assert wait(c,j['id'])['status']=='cancelled'
        assert c.get('/api/history').json()['total']==0
        assert c.post('/api/models/unload').status_code==200

def test_deleted_track_detaches_job(client):
    job=wait(client,client.post('/api/jobs',json=payload()).json()['id'])
    client.delete('/api/history/'+job['track_id'])
    updated=client.get('/api/jobs/'+job['id']).json()
    assert updated.get('track_id') is None and updated['audio_deleted']

def test_model_failure_does_not_block_next_job(tmp_path):
    class Once(DemoEngine):
        failures=1
        def load(self,record,runtime):
            if self.failures:
                self.failures=0
                raise RuntimeError('Simulated OOM')
            return super().load(record,runtime)
    app=create_app(ROOT,tmp_path,demo=True,engine=Once())
    with TestClient(app, base_url="http://127.0.0.1") as c:
        c.headers['x-studio-token']=c.get('/api/bootstrap').json()['token']
        a=c.post('/api/jobs',json=payload()).json();b=c.post('/api/jobs',json=payload()).json()
        assert wait(c,a['id'])['status']=='failed'
        assert wait(c,b['id'])['status']=='done'

def test_no_swagger_cdn(client):
    assert client.get('/api/docs').status_code==404
    assert client.get('/api/schema').status_code==200

def test_static_xss_text_remains_plain(client):
    text='<img src=x onerror=alert(1)>'
    p=client.post('/api/presets',json={'name':text,'instruct':text}).json()
    assert p['name']==text  # Stored as data; frontend must use textContent.
    script=(ROOT/'ui/app.js').read_text()
    assert 'innerHTML' not in script
    assert 'innerHTML' not in (ROOT/'ui/core.js').read_text()

def test_no_remote_assets():
    html=(ROOT/'ui/index.html').read_text()
    assert 'https://' not in html and 'http://' not in html
    for path in (ROOT/'ui').glob('*.js'):
        assert 'cdn.' not in path.read_text()

def test_punctuation_only_segmentation():
    parts=split_sentences('!'*180,60)
    assert len(parts)==3 and all(len(p)==60 for p in parts)

def test_device_meta_diagnostics():
    torch=pytest.importorskip('torch')
    from studio.device_utils import execution_device
    module=torch.nn.Linear(2,2,device='meta')
    module._hf_hook=SimpleNamespace(execution_device='cuda:0')
    assert str(execution_device(module))=='cuda:0'
    module._hf_hook=SimpleNamespace(execution_device='meta')
    assert str(execution_device(module))=='cpu'
    module._hf_hook=SimpleNamespace(hooks=[SimpleNamespace(execution_device=None),SimpleNamespace(execution_device='cpu')])
    assert str(execution_device(module))=='cpu'

def test_hybrid_requires_official_package(tmp_path, monkeypatch):
    import studio.inference_runtime as runtime_module
    torch=pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    monkeypatch.setattr(torch.cuda,'empty_cache',lambda:None)
    monkeypatch.setattr(torch.cuda,'mem_get_info',lambda i:(6*1024**3,6*1024**3))
    monkeypatch.setattr(runtime_module,'mixed_device_available',lambda:False)
    engine=QwenEngine(tmp_path)
    with pytest.raises(ValueError,match='qwen-tts and accelerate'):
        engine.load({'id':'x','path':'none','name':'test','mode':'design'},Runtime(device='hybrid'))


def test_hybrid_arguments_and_cache(tmp_path, monkeypatch):
    import studio.inference_runtime as runtime_module
    import sys
    import types
    from unittest.mock import Mock
    torch=pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    monkeypatch.setattr(torch.cuda,'empty_cache',lambda:None)
    monkeypatch.setattr(torch.cuda,'mem_get_info',lambda i:(6*1024**3,6*1024**3))
    monkeypatch.setattr(runtime_module,'mixed_device_available',lambda:True)
    patched=Mock()
    monkeypatch.setattr(runtime_module,'install_mixed_device_support',patched)
    model=torch.nn.Linear(2,2)
    model.tts_model_type='voice_design'
    model.hf_device_map={'a':0,'b':'cpu'}
    wrapper=SimpleNamespace(model=model,get_supported_speakers=lambda:[])
    factory=SimpleNamespace(from_pretrained=Mock(return_value=wrapper))
    monkeypatch.setitem(sys.modules,'qwen_tts',types.SimpleNamespace(Qwen3TTSModel=factory))
    engine=QwenEngine(tmp_path)
    record={'id':'x','path':'none','name':'test','mode':'design'}
    one=engine.load(record,Runtime(device="hybrid"));two=engine.load(record,Runtime(device='hybrid'))
    assert one==two and factory.from_pretrained.call_count==1
    assert patched.call_count==1
    kwargs=factory.from_pretrained.call_args.kwargs
    assert kwargs['dtype']==torch.float32 and kwargs['device_map']=='auto'
    assert kwargs['local_files_only'] and kwargs['use_safetensors']
    assert kwargs['trust_remote_code'] is False
    assert kwargs['max_memory'][0]==3*1024**3

def test_production_has_no_demo_models(tmp_path):
    app=create_app(ROOT,tmp_path,model_roots=[tmp_path/'absent'],demo=False)
    with TestClient(app, base_url="http://127.0.0.1") as c:
        data=c.get('/api/bootstrap').json()
        assert not data['demo']
        assert not data['models']
        assert isinstance(app.state.engine,QwenEngine)
