"""Native-picker contracts with an injected Windows selector (no GUI in CI)."""
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fake_engine import DemoEngine
from studio import native_dialog
from studio.server import create_app
from studio.native_dialog import NativeFolderPicker, PickerBusy, PickerError

ROOT = Path(__file__).resolve().parents[1]


class FakePicker:
    def __init__(self, path):
        self.path = path
        self.requests = []
        self.failure = None

    def available(self):
        return True

    def pick(self, purpose, initial_path):
        self.requests.append((purpose, initial_path))
        if self.failure:
            raise self.failure
        return self.path


def test_api_folder_selection_requires_same_origin_token_and_valid_purpose(tmp_path):
    folder = tmp_path / 'speech models';folder.mkdir()
    picker=FakePicker(str(folder))
    app=create_app(ROOT,tmp_path/'data',demo=True,engine=DemoEngine(),folder_picker=picker)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/bootstrap').json()['native_folder_picker'] is True
        assert client.post('/api/native/folder',json={'purpose':'scan'}).status_code==403
        client.headers['X-Studio-Token']=client.get('/api/bootstrap').json()['token']
        assert client.post('/api/native/folder',headers={'Origin':'https://bad.example'},json={'purpose':'scan'}).status_code==403
        assert client.post('/api/native/folder',json={'purpose':'invalid'}).status_code==422
        choice=client.post('/api/native/folder',json={'purpose':'model','initial_path':str(tmp_path)})
        assert choice.status_code==200 and choice.json()=={'path':str(folder),'cancelled':False}
        assert picker.requests==[('model',str(tmp_path))]
        picker.path=None
        response=client.post('/api/native/folder',json={'purpose':'scan'})
        assert response.status_code==200 and response.json()=={'path':None,'cancelled':True}
        picker.failure=PickerBusy('Another folder selector is open.')
        assert client.post('/api/native/folder',json={'purpose':'scan'}).status_code==409
        picker.failure=PickerError('Native dialog unavailable')
        assert client.post('/api/native/folder',json={'purpose':'scan'}).status_code==503


def test_nonwindows_picker_returns_unavailable_without_spawning(tmp_path, monkeypatch):
    monkeypatch.setattr(native_dialog.platform, 'system', lambda:'Linux')
    picker=NativeFolderPicker()
    assert picker.available() is False
    with pytest.raises(PickerError):
        picker.pick('model',str(tmp_path))
    app=create_app(ROOT,tmp_path/'data',demo=True,engine=DemoEngine(),folder_picker=picker)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        token=client.get('/api/bootstrap').json()['token']
        assert client.get('/api/bootstrap').json()['native_folder_picker'] is False
        assert client.post('/api/native/folder',headers={'x-studio-token':token},json={'purpose':'model'}).status_code==503


def test_windows_powershell_receives_path_in_env_not_executable_code(tmp_path, monkeypatch):
    target=tmp_path/'中文 model';target.mkdir()
    calls=[]
    def run(args, **options):
        calls.append((args,options))
        return SimpleNamespace(returncode=0,stdout=base64.b64encode(str(target).encode('utf-8')).decode('ascii')+'\n',stderr='')
    monkeypatch.setattr(native_dialog,'_powershell',lambda:'powershell.exe')
    monkeypatch.setattr(native_dialog,'_interactive_session',lambda:True)
    monkeypatch.setattr(native_dialog.subprocess,'run',run)
    picker=NativeFolderPicker()
    assert picker.pick('scan',str(tmp_path))==str(target)
    args, options = calls[0]
    assert args[:3]==['powershell.exe','-NoProfile','-STA']
    assert options['env']['QVS_PICKER_START']==str(tmp_path)
    assert str(tmp_path) not in args[-1]
    assert options['timeout']>30 and options['check'] is False
    assert 'shell' not in options


def test_cancel_malformed_output_and_busy_lock(tmp_path,monkeypatch):
    monkeypatch.setattr(native_dialog,'_powershell',lambda:'powershell.exe')
    monkeypatch.setattr(native_dialog,'_interactive_session',lambda:True)
    picker=NativeFolderPicker()
    assert picker.lock.acquire(False)
    with pytest.raises(PickerBusy):picker.pick()
    picker.lock.release()
    monkeypatch.setattr(native_dialog.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout=''))
    assert picker.pick() is None
    monkeypatch.setattr(native_dialog.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=0,stdout='bad-%%%'))
    with pytest.raises(PickerError):picker.pick()
    assert picker.lock.acquire(False)
    picker.lock.release()


def test_many_sequential_model_roots_persist(tmp_path):
    picker=FakePicker(None)
    app=create_app(ROOT,tmp_path/'data',demo=True,engine=DemoEngine(),folder_picker=picker)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['x-studio-token']=c.get('/api/bootstrap').json()['token']
        value=c.get('/api/preferences').json()
        roots=[str(tmp_path/f'model-{i}') for i in range(24)]
        value['model_roots']=roots
        assert c.put('/api/preferences',json=value).status_code==200
        assert c.get('/api/preferences').json()['model_roots']==roots
        assert c.post('/api/models/scan').status_code==200
