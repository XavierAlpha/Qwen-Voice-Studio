"""Strict, shared request contracts. Never accept arbitrary generation kwargs."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode = Literal["design", "clone", "custom"]
LANGUAGES = ["Auto", "Chinese", "English", "Japanese", "Korean", "German", "French", "Spanish", "Italian", "Portuguese", "Russian"]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Runtime(StrictModel):
    device: Literal["auto", "hybrid", "cpu", "cuda_fp32", "cuda_bf16", "cuda_fp16"] = "auto"
    gpu_gib: float = Field(default=3.0, gt=0, allow_inf_nan=False)
    cpu_gib: float = Field(default=12.0, gt=0, allow_inf_nan=False)
    attention: Literal["sdpa", "eager"] = "sdpa"

class Sampling(StrictModel):
    temperature: float = Field(default=0.9, ge=0.1, le=2, allow_inf_nan=False)
    top_p: float = Field(default=0.9, ge=0.05, le=1, allow_inf_nan=False)
    top_k: int = Field(default=50, ge=1, le=100)
    repetition_penalty: float = Field(default=1.05, ge=1, le=2, allow_inf_nan=False)
    max_new_tokens: int = Field(default=512, ge=64, le=2048)
    seed: int = Field(default=-1, ge=-1, le=2147483647)

class Generate(StrictModel):
    model_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    mode: Mode = "design"
    text: str = Field(min_length=1, max_length=6000)
    language: str = "Chinese"
    instruct: str = Field(default="", max_length=2000)
    speaker: str = Field(default="", max_length=80)
    reference_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    ref_text: str = Field(default="", max_length=2000)
    x_vector_only: bool = False
    consent: bool = False
    split_text: bool = False
    chunk_chars: int = Field(default=180, ge=60, le=500)
    pause_ms: int = Field(default=180, ge=0, le=2000)
    sampling: Sampling = Field(default_factory=Sampling)
    runtime: Runtime = Field(default_factory=Runtime)

    @model_validator(mode="after")
    def check_fields(self):
        if self.language not in LANGUAGES:
            raise ValueError("Unsupported language")
        if not self.split_text and len(self.text) > 600:
            raise ValueError("Enable text segmentation for more than 600 characters")
        if self.mode == "design" and not self.instruct:
            raise ValueError("A voice description is required")
        if self.mode == "custom" and not self.speaker:
            raise ValueError("Select a speaker")
        if self.mode == "clone":
            if not self.reference_id or not self.consent:
                raise ValueError("Reference audio and authorization confirmation are required")
            if not self.x_vector_only and not self.ref_text:
                raise ValueError("Reference transcript is required unless x-vector-only is enabled")
        return self

class Preset(StrictModel):
    name: str = Field(min_length=1, max_length=70)
    instruct: str = Field(min_length=1, max_length=2000)
    language: str = "Chinese"

class Register(StrictModel):
    path: str = Field(min_length=1, max_length=2000)

class PickFolder(StrictModel):
    purpose: Literal["model", "scan"] = "model"
    initial_path: str | None = Field(default=None, max_length=2000)

class Load(StrictModel):
    model_id: str
    runtime: Runtime = Field(default_factory=Runtime)

class TrackEdit(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    favorite: bool | None = None
