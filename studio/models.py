"""Bounded, config-first discovery of complete local Qwen3-TTS checkpoints."""
from collections import deque
from pathlib import Path
import hashlib
import json
import os
import threading
import time
from .store import Store

TYPES = {"voice_design": "design", "base": "clone", "custom_voice": "custom"}
LABELS = {"design": "VoiceDesign", "clone": "Base", "custom": "CustomVoice"}
SIZES = {"1b7": "1.7B", "0b6": "0.6B", "1.7b": "1.7B", "0.6b": "0.6B"}
SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__", "blobs", ".locks", "logs", "audio", "references"}


def read_json(path: Path, limit=1024 * 1024) -> dict:
    if path.stat().st_size > limit:
        raise ValueError("Configuration exceeds size limit")
    with path.open(encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Configuration must be an object")
    return value


def valid_weight_header(path: Path) -> bool:
    """Check bounded safetensors metadata, not all multi-GB tensor contents."""
    try:
        with path.open("rb") as stream:
            header_len = int.from_bytes(stream.read(8), "little")
            file_size = path.stat().st_size
            if not 2 <= header_len <= min(8 * 1024**2, file_size - 8):
                return False
            header = json.loads(stream.read(header_len))
        if not isinstance(header, dict):
            return False
        tensors = [item for name, item in header.items() if name != "__metadata__"]
        if not tensors:
            return False
        for item in tensors:
            if not isinstance(item, dict) or not isinstance(item.get("shape"), list) or not isinstance(item.get("dtype"), str):
                return False
            offsets = item.get("data_offsets")
            if not isinstance(offsets, list) or len(offsets) != 2 or not all(isinstance(n, int) for n in offsets):
                return False
            if not 0 <= offsets[0] <= offsets[1] <= file_size - header_len - 8:
                return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def weights(folder: Path) -> tuple[list[Path], list[str]]:
    """Check shard indexes and file presence, without reading GB-sized weights."""
    index = folder / "model.safetensors.index.json"
    issues = []
    if index.is_file():
        mapping = read_json(index).get("weight_map")
        if not isinstance(mapping, dict) or not mapping:
            return [], ["invalid_shard_index"]
        if not all(isinstance(n, str) for n in mapping.values()):
            return [], ["invalid_shard_index"]
        names = set(mapping.values())
        if not all(isinstance(n, str) and Path(n).name == n and "/" not in n and "\\" not in n and n.endswith(".safetensors") for n in names):
            return [], ["unsafe_shard_index"]
        files = [folder / name for name in sorted(names)]
    else:
        files = [folder / "model.safetensors"]
    for file in files:
        if not file.is_file() or file.stat().st_size < 16:
            issues.append("missing_weights:" + file.name)
        elif file.stat().st_size < 1024:
            with file.open("rb") as stream:
                if stream.read(42).startswith(b"version https://git-lfs.github.com/spec"):
                    issues.append("lfs_pointer:" + file.name)
        if file.is_file() and not valid_weight_header(file):
            issues.append("invalid_weight_header:" + file.name)
    return files, issues


def inspect_model(path: Path) -> dict | None:
    config_path = path / "config.json"
    if not config_path.is_file():
        return None
    cfg = read_json(config_path)
    if cfg.get("model_type") != "qwen3_tts":
        return None
    task = TYPES.get(cfg.get("tts_model_type"))
    issues = []
    if task is None:
        issues.append("unsupported_task")
    tokenizer_type = cfg.get("tokenizer_type", "")
    if tokenizer_type != "qwen3_tts_tokenizer_12hz":
        issues.append("unsupported_tokenizer")
    if cfg.get("quantization_config"):
        issues.append("quantized_checkpoint_needs_specific_backend")
    main, missing = weights(path)
    issues.extend(missing)
    codec = path / "speech_tokenizer"
    if not (codec / "config.json").is_file():
        issues.append("missing_speech_tokenizer_config")
    else:
        read_json(codec / "config.json")
    codec_files, missing = weights(codec)
    issues.extend("speech_tokenizer/" + item for item in missing)
    for file in ("tokenizer_config.json", "preprocessor_config.json"):
        if not (path / file).is_file():
            issues.append("missing:" + file)
    if not (path / "tokenizer.json").is_file() and not all((path / name).is_file() for name in ("vocab.json", "merges.txt")):
        issues.append("missing_text_tokenizer")
    if not (codec / "preprocessor_config.json").is_file():
        issues.append("missing_codec_preprocessor")
    size = SIZES.get(str(cfg.get("tts_model_size", "")).lower(), str(cfg.get("tts_model_size", "unknown"))[:40])
    talker = cfg.get("talker_config") or {}
    if not isinstance(talker, dict):
        raise ValueError("Invalid talker configuration")
    speakers = talker.get("spk_id") or {}
    languages = talker.get("codec_language_id") or {}
    if not isinstance(speakers, dict) or not isinstance(languages, dict):
        raise ValueError("Invalid language or speaker configuration")
    files = [config_path, *main, *codec_files, codec / "config.json"]
    signature = []
    total = 0
    for file in files:
        if file.is_file():
            stat = file.stat()
            signature.append(f"{file.name}:{stat.st_size}:{stat.st_mtime_ns}")
            if file.suffix == ".safetensors":
                total += stat.st_size
    name = f"Qwen3-TTS {size} {LABELS.get(task, 'Unknown')}"
    # Fine-tuned directories may be renamed; behavior always comes from config.
    return {"mode": task, "name": name, "size": size, "family": "qwen3_tts", "format": "safetensors",
            "speakers": list(speakers)[:256], "languages": ["Auto", *[s.capitalize() for s in languages if isinstance(s, str)]],
            "capabilities": {"instruct": task == "design" or (task == "custom" and size != "0.6B"), "reference": task == "clone"},
            "status": "ready" if not issues else "incomplete", "issues": sorted(set(issues)), "weight_bytes": total,
            "fingerprint": hashlib.sha256("|".join(signature).encode()).hexdigest()[:24]}


class Registry:
    def __init__(self, store: Store, roots: list[Path], depth=6):
        self.store, self.roots, self.depth = store, roots, depth
        self.lock = threading.Lock()
        self.last_scan = {"scanned": 0, "found": 0, "limited": False, "errors": 0}

    def register(self, value: str, strict=True) -> dict:
        if "://" in value or "\x00" in value:
            raise ValueError("Use a local model directory")
        path = Path(value.strip().strip('"')).expanduser().resolve(strict=True)
        result = inspect_model(path)
        if result is None:
            raise ValueError("Not a Qwen3-TTS checkpoint; GGUF and standalone LoRA require a different backend")
        if strict and result["status"] != "ready":
            raise ValueError("Model is incomplete or unsupported: " + ", ".join(result["issues"]))
        key = hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest()[:24]
        record = self.store.get("model", key) or {"id": key}
        record.update(result, path=str(path), checked=time.time())
        return self.store.put("model", record)

    @staticmethod
    def public(record):
        return {key: value for key, value in record.items() if key not in {"path", "fingerprint", "checked"}}

    def list(self):
        return [self.public(item) for item in self.store.list("model")]

    def scan(self):
        with self.lock:
            started = time.monotonic()
            pending = deque((Path(root), 0) for root in self.roots)
            visited, found, errors = set(), set(), 0
            # Validate registered models even when roots were changed.
            for old in self.store.list("model"):
                try:
                    self.register(old["path"], strict=False)
                except (ValueError, OSError, TypeError, AttributeError):
                    old.update(status="missing", issues=["model_unavailable"])
                    self.store.put("model", old)
            while pending and len(visited) < 4096 and time.monotonic() - started < 8:
                path, depth = pending.popleft()
                try:
                    canonical = os.path.normcase(str(path.resolve()))
                    if canonical in visited or not path.is_dir():
                        continue
                    visited.add(canonical)
                    if (path / "config.json").is_file():
                        result = inspect_model(path)
                        if result:
                            record = self.register(str(path), strict=False)
                            found.add(record["id"])
                        # Never descend into an unrelated configured model.
                        continue
                    if (path / "adapter_config.json").is_file():
                        continue
                    if depth < self.depth:
                        with os.scandir(path) as entries:
                            for entry in entries:
                                if len(pending) >= 4096:
                                    break
                                if entry.name in SKIP or entry.name.startswith("."):
                                    continue
                                # Do not follow directory symlinks/junctions implicitly.
                                # Explicitly configured roots and HF *file* symlinks work.
                                p = Path(entry.path)
                                if entry.is_dir(follow_symlinks=False) and not (hasattr(p, "is_junction") and p.is_junction()):
                                    pending.append((p, depth + 1))
                except (OSError, ValueError, TypeError, AttributeError):
                    errors += 1
            self.last_scan = {"scanned": len(visited), "found": len(found), "limited": bool(pending), "errors": errors,
                              "seconds": round(time.monotonic() - started, 3)}
            return self.list()

    def get(self, model_id: str) -> dict:
        record = self.store.get("model", model_id)
        if not record:
            raise ValueError("Model not registered")
        if record.get("status", "ready") != "ready":
            raise ValueError("Model is unavailable or incomplete; refresh the model library")
        return record
