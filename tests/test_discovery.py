"""Model discovery contract; all weights are tiny layout-only fixtures."""
from pathlib import Path
import json
import shutil
import pytest
from studio.config import Config, Preferences
from studio.models import Registry, inspect_model
from studio.store import Store
from model_fixtures import make_model

@pytest.mark.parametrize("task,size,mode,instruct", [
    ("voice_design", "1b7", "design", True), ("base", "1b7", "clone", False),
    ("base", "0b6", "clone", False), ("custom_voice", "1b7", "custom", True),
    ("custom_voice", "0b6", "custom", False),
])
def test_config_not_filename(tmp_path, task, size, mode, instruct):
    folder=make_model(tmp_path/'renamed-checkpoint',task,size)
    record=inspect_model(folder)
    assert record['mode']==mode and record['status']=='ready'
    assert record['capabilities']['instruct']==instruct
    assert record['languages']==['Auto','Chinese','English']
    assert record['size'] in {'0.6B','1.7B'}

@pytest.mark.parametrize('missing', ['model.safetensors','speech_tokenizer/model.safetensors','speech_tokenizer/config.json','speech_tokenizer/preprocessor_config.json','vocab.json','tokenizer_config.json'])
def test_incomplete_never_loadable(tmp_path, missing):
    folder=make_model(tmp_path/'weights');(folder/missing).unlink()
    registry=Registry(Store(tmp_path/'data'),[folder])
    records=registry.scan()
    assert len(records)==1 and records[0]['status']=='incomplete'
    with pytest.raises(ValueError):registry.get(records[0]['id'])
    with pytest.raises(ValueError):registry.register(str(folder))


def test_shards_and_traversal(tmp_path):
    folder=make_model(tmp_path/'weights',shards=True)
    assert inspect_model(folder)['status']=='ready'
    (folder/'model-00002-of-00002.safetensors').unlink()
    assert inspect_model(folder)['status']=='incomplete'
    index=folder/'model.safetensors.index.json'
    for value in ('../outside.safetensors','C:\\weights.safetensors',[],3):
        index.write_text(json.dumps({'weight_map':{'a':value}}))
        assert inspect_model(folder)['status']=='incomplete'


def test_hf_snapshot_and_dedup(tmp_path):
    folder=make_model(tmp_path/'hub/models--Qwen--Voice/snapshots/abcdef')
    registry=Registry(Store(tmp_path/'data'),[tmp_path/'hub',folder,folder])
    records=registry.scan();assert len(records)==1
    assert 'path' not in records[0] and 'fingerprint' not in records[0]
    assert records[0]['name']=='Qwen3-TTS 1.7B VoiceDesign'


def test_missing_marked_and_restored(tmp_path):
    folder=make_model(tmp_path/'weights');registry=Registry(Store(tmp_path/'data'),[folder])
    first=registry.scan()[0]
    moved=folder.with_name('moved');folder.rename(moved)
    assert registry.scan()[0]['status']=='missing'
    moved.rename(folder)
    assert registry.scan()[0]['id']==first['id']
    assert registry.scan()[0]['status']=='ready'


def test_no_implicit_directory_symlink_traversal(tmp_path):
    outside=make_model(tmp_path/'outside/weights');root=tmp_path/'allowed';root.mkdir()
    try:(root/'linked').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Symlink creation unavailable')
    registry=Registry(Store(tmp_path/'data'),[root]);assert registry.scan()==[]
    registry.roots=[root/'linked'];assert len(registry.scan())==1


def test_hf_file_symlinks_supported(tmp_path):
    folder=make_model(tmp_path/'snapshot');weight=folder/'model.safetensors'
    blob=tmp_path/'blob';weight.rename(blob)
    try:weight.symlink_to(blob)
    except OSError:pytest.skip('Symlink creation unavailable')
    assert inspect_model(folder)['status']=='ready'


def test_irrelevant_and_malformed_configs_are_bounded(tmp_path):
    for name,content in [('bad','not-json'),('other','{"model_type":"qwen_image"}'),('array','[]')]:
        path=tmp_path/name;path.mkdir();(path/'config.json').write_text(content)
    make_model(tmp_path/'good')
    registry=Registry(Store(tmp_path/'data'),[tmp_path]);assert len(registry.scan())==1
    assert registry.last_scan['errors']==2


def test_huge_config_rejected(tmp_path):
    folder=make_model(tmp_path/'weights');(folder/'config.json').write_text(' '*(1024*1024+1))
    with pytest.raises(ValueError):inspect_model(folder)


def test_quantized_or_unknown_not_misrepresented(tmp_path):
    folder=make_model(tmp_path/'weights');cfg=json.loads((folder/'config.json').read_text())
    cfg['quantization_config']={'quant_method':'unknown'}
    (folder/'config.json').write_text(json.dumps(cfg))
    assert 'quantized_checkpoint_needs_specific_backend' in inspect_model(folder)['issues']
    cfg.pop('quantization_config');cfg['tts_model_type']='future'
    (folder/'config.json').write_text(json.dumps(cfg))
    assert 'unsupported_task' in inspect_model(folder)['issues']


def test_lfs_pointer_not_a_weight(tmp_path):
    folder=make_model(tmp_path/'weights');(folder/'model.safetensors').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:xxx\n')
    assert inspect_model(folder)['status']=='incomplete'


def test_config_persistence_and_cache_env(tmp_path,monkeypatch):
    cfg=Config(tmp_path,tmp_path/'data')
    cfg.save(Preferences(model_roots=['models'],discover_hf_cache=True,remember_drafts=False))
    monkeypatch.setenv('HF_HUB_CACHE',str(tmp_path/'hub'))
    new=Config(tmp_path,tmp_path/'data')
    assert new.roots()==[tmp_path/'models',tmp_path/'hub']
    assert not new.value.remember_drafts
    assert not list((tmp_path/'data').glob('*.tmp'))

@pytest.mark.parametrize('value',[{'model_roots':['https://example.test/model']},{'scan_depth':100},{'backend':'anything'},{'engine_root':'https://example.test/code'},{'unknown':True}])
def test_config_validation(value):
    with pytest.raises(ValueError):Preferences(**value)
