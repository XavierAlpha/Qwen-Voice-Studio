"""Small, validated local configuration. No credentials and no machine defaults."""
from pathlib import Path
import json
import os
import threading
from pydantic import Field, field_validator
from .schema import StrictModel


class Preferences(StrictModel):
    model_roots: list[str] = Field(default_factory=lambda: ["models", "../models"], max_length=128)
    discover_hf_cache: bool = True
    auto_discover: bool = True
    scan_depth: int = Field(default=6, ge=1, le=12)
    remember_drafts: bool = False
    hide_paths: bool = True

    @field_validator("model_roots")
    @classmethod
    def roots_valid(cls, roots):
        result = []
        for root in roots:
            root = root.strip().strip('"')
            if not root or len(root) > 2048 or "\x00" in root or "://" in root:
                raise ValueError("Model roots must be local directory paths")
            if root not in result:
                result.append(root)
        return result


class Config:
    def __init__(self, root: Path, data: Path):
        self.root = root.resolve()
        self.path = data / "config.json"
        self.lock = threading.RLock()
        self.value = Preferences()
        if self.path.exists():
            if self.path.stat().st_size > 128 * 1024:
                raise ValueError("Local configuration is too large")
            stored = json.loads(self.path.read_text(encoding="utf-8-sig"))
            # v3.2 migration: older external backend settings are ignored.
            stored.pop("backend", None)
            stored.pop("engine_root", None)
            self.value = Preferences.model_validate(stored)

    def save(self, value: Preferences):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            with temp.open("w", encoding="utf-8") as stream:
                stream.write(value.model_dump_json(indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            temp.replace(self.path)
            self.value = value
        return value

    def resolve(self, value: str) -> Path:
        path = Path(os.path.expandvars(value)).expanduser()
        return (path if path.is_absolute() else self.root / path).resolve()

    def roots(self) -> list[Path]:
        roots = [self.resolve(p) for p in self.value.model_roots]
        if self.value.discover_hf_cache:
            cache = os.getenv("HF_HUB_CACHE") or os.getenv("HUGGINGFACE_HUB_CACHE")
            home = Path(os.getenv("HF_HOME", str(Path.home() / ".cache" / "huggingface"))).expanduser()
            roots.append(Path(cache).expanduser() if cache else home / "hub")
        return list(dict.fromkeys(roots))
