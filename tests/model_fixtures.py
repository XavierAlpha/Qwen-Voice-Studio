"""Tiny model-layout fixtures, never real model weights."""
import json
import struct
from pathlib import Path


def tiny_weight(path):
    header=json.dumps({"fixture":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}).encode()
    header += b" " * ((-len(header)) % 8)
    path.write_bytes(struct.pack("<Q",len(header))+header+struct.pack("<f",0.1))


def make_model(path: Path, task="voice_design", size="1b7", shards=False):
    path.mkdir(parents=True, exist_ok=True)
    cfg = {"model_type": "qwen3_tts", "tts_model_type": task, "tts_model_size": size,
           "tokenizer_type": "qwen3_tts_tokenizer_12hz", "talker_config": {"spk_id": {"speaker_a": 1} if task == "custom_voice" else {}, "codec_language_id": {"chinese": 1, "english": 2}}}
    (path / "config.json").write_text(json.dumps(cfg))
    for name in ("preprocessor_config.json", "tokenizer_config.json", "vocab.json"):
        (path / name).write_text("{}")
    (path / "merges.txt").write_text("# test")
    codec = path / "speech_tokenizer"
    codec.mkdir(exist_ok=True)
    for name in ("config.json", "preprocessor_config.json"):
        (codec / name).write_text("{}")
    tiny_weight(codec / "model.safetensors")
    if shards:
        for name in ("model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"):
            tiny_weight(path / name)
        (path / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"a": "model-00001-of-00002.safetensors", "b": "model-00002-of-00002.safetensors"}}))
    else:
        tiny_weight(path / "model.safetensors")
    return path
