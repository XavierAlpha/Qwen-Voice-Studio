"""Backend contracts tested without real weights or a CUDA device."""
from pathlib import Path
from types import SimpleNamespace, ModuleType
import sys
import threading
import pytest
from studio.engine import QwenEngine, cancellable_talker, Cancelled
from studio.schema import Runtime


def fake_cuda(monkeypatch, major=7, free_gib=6):
    torch=pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:True)
    monkeypatch.setattr(torch.cuda,'get_device_capability',lambda i:(major,5))
    monkeypatch.setattr(torch.cuda,'is_bf16_supported',lambda:major>=8)
    monkeypatch.setattr(torch.cuda,'mem_get_info',lambda i:(free_gib*1024**3,free_gib*1024**3))
    return torch


def test_automatic_cpu_when_no_cuda(tmp_path,monkeypatch):
    torch=pytest.importorskip('torch')
    monkeypatch.setattr(torch.cuda,'is_available',lambda:False)
    runtime,reason=QwenEngine(tmp_path).resolve_runtime({},Runtime())
    assert runtime.device=='cpu' and 'CPU' in reason


def test_automatic_no_fp16_on_turing(tmp_path,monkeypatch):
    fake_cuda(monkeypatch)
    engine=QwenEngine(tmp_path)
    monkeypatch.setattr('studio.inference_runtime.mixed_device_available',lambda:True)
    runtime,_=engine.resolve_runtime({'weight_bytes':5*1024**3},Runtime())
    assert runtime.device=='cuda_fp32'
    assert runtime.gpu_gib==3.0  # no VRAM-based rewriting


def test_automatic_fp32_small_model(tmp_path,monkeypatch):
    fake_cuda(monkeypatch)
    runtime,_=QwenEngine(tmp_path).resolve_runtime({'weight_bytes':1024**3},Runtime())
    assert runtime.device=='cuda_fp32'


def test_automatic_bf16_supported(tmp_path,monkeypatch):
    fake_cuda(monkeypatch,major=8,free_gib=16)
    runtime,_=QwenEngine(tmp_path).resolve_runtime({'weight_bytes':5*1024**3},Runtime())
    assert runtime.device=='cuda_bf16'


def test_no_patched_backend_falls_back_explicitly(tmp_path,monkeypatch):
    fake_cuda(monkeypatch)
    engine=QwenEngine(tmp_path);monkeypatch.setattr('studio.inference_runtime.mixed_device_available',lambda:False)
    runtime,reason=engine.resolve_runtime({'weight_bytes':5*1024**3},Runtime())
    assert runtime.device=='cuda_fp32' and 'CUDA' in reason


def test_auto_ignores_estimated_free_vram_and_model_size(tmp_path, monkeypatch):
    torch=fake_cuda(monkeypatch,major=7,free_gib=0)
    monkeypatch.setattr(torch.cuda,'mem_get_info',lambda *_: (_ for _ in ()).throw(AssertionError('VRAM not probed')))
    requested=Runtime(device='auto',gpu_gib=250.5,cpu_gib=4096.25)
    runtime,reason=QwenEngine(tmp_path).resolve_runtime({'weight_bytes':99*1024**3},requested)
    assert runtime.device=='cuda_fp32'
    assert runtime.gpu_gib==250.5 and runtime.cpu_gib==4096.25


def test_unrestricted_hybrid_budgets_are_preserved(tmp_path):
    runtime=Runtime(device='hybrid',gpu_gib=512.5,cpu_gib=4096.25)
    resolved,reason=QwenEngine(tmp_path).resolve_runtime({},runtime)
    assert resolved is runtime and reason=='explicit'


def test_explicit_runtime_not_silently_changed(tmp_path):
    original=Runtime(device='cpu')
    runtime,reason=QwenEngine(tmp_path).resolve_runtime({},original)
    assert runtime is original and reason=='explicit'


def test_cancellation_injected_at_actual_generate(monkeypatch):
    transformers=ModuleType('transformers')
    transformers.StoppingCriteria=type('StoppingCriteria',(),{})
    transformers.StoppingCriteriaList=list
    monkeypatch.setitem(sys.modules,'transformers',transformers)
    cancel=threading.Event()
    class Talker:
        def generate(self,**kwargs):
            assert kwargs['stopping_criteria']
            cancel.set()
            kwargs['stopping_criteria'][-1](None,None)
    talker=Talker();wrapper=SimpleNamespace(model=SimpleNamespace(talker=talker))
    assert 'generate' not in talker.__dict__
    with pytest.raises(Cancelled):
        with cancellable_talker(wrapper,cancel):talker.generate()
    assert 'generate' not in talker.__dict__
    assert callable(talker.generate)


def test_cancellation_restores_instance_override(monkeypatch):
    transformers=ModuleType('transformers');transformers.StoppingCriteria=type('S',(),{});transformers.StoppingCriteriaList=list
    monkeypatch.setitem(sys.modules,'transformers',transformers)
    original=lambda **kwargs:'ok'
    talker=SimpleNamespace(generate=original)
    with cancellable_talker(SimpleNamespace(model=SimpleNamespace(talker=talker)),threading.Event()):
        assert talker.generate()=='ok'
    assert talker.generate is original


def test_offline_env_is_required_by_server(client):
    import os
    assert os.environ['HF_HUB_OFFLINE']=='1'
    assert os.environ['HF_HUB_DISABLE_TELEMETRY']=='1'


def test_cuda_bf16_rejected_on_old_gpu(tmp_path,monkeypatch):
    fake_cuda(monkeypatch,major=7)
    with pytest.raises(ValueError,match='BF16'):
        QwenEngine(tmp_path).load({'id':'test','mode':'design'},Runtime(device='cuda_bf16'))


def test_auto_reuses_loaded_model_before_free_vram_probe(tmp_path, monkeypatch):
    from studio.engine import QwenEngine
    from studio.schema import Runtime
    engine=QwenEngine(tmp_path)
    runtime=Runtime()
    engine.model=object()
    engine.key=('model-a','signature','resolved-runtime')
    engine.info={'loaded':True,'requested_runtime':runtime.model_dump(),'execution_device':'cuda:0'}
    def must_not_probe(*args):
        raise AssertionError('Resident weights must not cause repeated device selection')
    monkeypatch.setattr(engine,'resolve_runtime',must_not_probe)
    result=engine.load({'id':'model-a','fingerprint':'signature'},runtime)
    assert result['execution_device']=='cuda:0'
