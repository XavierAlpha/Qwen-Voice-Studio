"""Best-effort diagnostic redaction. Never log request bodies or audio content."""
import logging
import os
from pathlib import Path
import re
import hashlib
import traceback


def redact(value: str) -> str:
    text = str(value)
    homes = {str(Path.home()), os.getenv("USERPROFILE", ""), os.getenv("HOME", "")}
    for home in sorted(homes, key=len, reverse=True):
        if len(home) > 3:
            text = text.replace(home, "<home>")
    text = re.sub(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s\"']+", "<home>", text)
    text = re.sub(r"/(?:home|Users)/[^/\s\"']+", "<home>", text)
    text = re.sub(r"(?i)\b(?:hf_|sk-)[A-Za-z0-9_-]{12,}", "<redacted-token>", text)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<redacted-email>", text)
    return text


class PrivateFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def failure_details(error: Exception, stage: str = "unknown") -> tuple[str, str]:
    """Structured, allowlisted diagnostics without user text or file paths."""
    root = getattr(error, "original", error)
    message = str(root).lower()
    if any(s in message for s in ('shape mismatch', 'size mismatch', 'invalid shape', 'shapes cannot be multiplied', 'is invalid for input of size')):
        return 'checkpoint', 'Model weights or adapter shapes are incompatible with this checkpoint.'
    if "out of memory" in message or 'cuda error: out of memory' in message:
        return "memory", "The inference runtime reported out-of-memory. Your device and budget settings were not automatically changed."
    if "meta tensor" in message or "tensor.item()" in message:
        return "offload", "Mixed-device placement failed. Review the inference diagnostic reference and selected runtime configuration."
    if "nan" in message or ("inf" in message and "audio" in message):
        return "nonfinite", "Nonfinite audio samples (NaN or Inf) were detected. No audio was saved."
    if "cuda" in message and ("assert" in message or "illegal" in message):
        return "cuda", "CUDA execution failed. Restart the server before retrying."
    if "does not support generate_voice_clone" in message or "does not support create_voice_clone_prompt" in message:
        return "wrong_model", "Voice cloning requires a Qwen3-TTS Base checkpoint, not VoiceDesign or CustomVoice."
    if "ref_text is required" in message:
        return "transcript", "Enter the exact reference transcript, or enable speaker-embedding-only mode."
    if "batch size mismatch" in message:
        return "batch", "Reference and text batch sizes do not match. Retry a single sample."
    if "unsupported language" in message:
        return "language", "The selected model does not support that language."
    if "waveform" in message or "sample rate" in message:
        return "audio", "Audio validation failed. Use a short, clear mono WAV reference."
    if isinstance(root, (ImportError, ModuleNotFoundError)):
        return "dependency", "A local inference dependency is missing or incompatible. Check diagnostics."
    if isinstance(root, OSError):
        return "file", "A local file is missing, inaccessible, or busy."
    if stage == "reference_encoding":
        return "reference", "Reference encoding failed. Check the audio file format and the chosen reference transcript / embedding-only mode."
    if stage == "speech_generation":
        return "generation", "Speech generation failed. Check the job reference and your selected generation settings."
    if stage == "waveform_validation":
        return "waveform", "The generated waveform failed validation. No invalid audio was saved."
    if stage == "model_loading":
        return "loading", "Model loading failed. Check model completeness and the selected runtime; details are in the local diagnostics."
    return "unknown", f"Inference failed ({type(root).__name__}). Check local diagnostics."


def failure_trace_id(error: Exception, stage: str = "unknown") -> str:
    """Short issue correlation ID; excludes arguments, local paths and trace text."""
    root = getattr(error, "original", error)
    frames = traceback.extract_tb(root.__traceback__) if root.__traceback__ else []
    trace = "|".join(f"{Path(f.filename).name}:{f.name}:{f.lineno}" for f in frames[-5:])
    return hashlib.sha256(f"{stage}|{type(root).__name__}|{trace}".encode()).hexdigest()[:10]


def public_error(error: Exception, validation=False, stage="unknown") -> str:
    """Useful categories instead of stack traces, paths, prompts or file contents."""
    # Our own validation errors contain no request bodies or absolute paths.
    if validation and isinstance(error, ValueError):
        return redact(str(error))[:500]
    return failure_details(error, stage)[1]
