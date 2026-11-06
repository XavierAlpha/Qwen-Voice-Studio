"""Validated audio IO, bounded uploads and sentence-aware text segmentation."""
from pathlib import Path
import io
import re
import shutil
import subprocess
import numpy as np
import soundfile as sf

MAX_UPLOAD = 25 * 1024 * 1024

def validate_wave(audio, sample_rate: int) -> np.ndarray:
    wave = np.asarray(audio, dtype=np.float32)
    if wave.ndim == 2 and 1 in wave.shape:
        wave = wave.reshape(-1)
    if wave.ndim != 1 or not wave.size or not 8000 <= int(sample_rate) <= 192000:
        raise ValueError("Invalid waveform dimensions or sample rate")
    if not np.isfinite(wave).all():
        raise ValueError("Audio contains NaN/Inf; try FP32, not FP16")
    peak = float(np.max(np.abs(wave)))
    if peak < 1e-8:
        raise ValueError("The generated waveform is silent")
    # Do not normalize valid quiet speech upward. Only prevent clipping.
    return wave * (0.98 / peak) if peak > 1 else wave

def write_wave(path: Path, wave, sample_rate: int):
    wave = validate_wave(wave, sample_rate)
    temp = path.with_suffix(".part")
    try:
        sf.write(temp, wave, sample_rate, format="WAV", subtype="PCM_16")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    return wave

def read_reference(data: bytes) -> tuple[np.ndarray, int]:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Reference audio must be under 25 MiB")
    try:
        with sf.SoundFile(io.BytesIO(data)) as audio:
            if not 8000 <= audio.samplerate <= 192000 or audio.channels > 2:
                raise ValueError("Use mono or stereo audio at 8-192 kHz")
            if not 0.5 <= audio.frames / audio.samplerate <= 60:
                raise ValueError("Reference audio must be 0.5-60 seconds")
            wave = audio.read(dtype="float32", always_2d=True).mean(axis=1)
            rate = audio.samplerate
    except sf.LibsndfileError:
        raise ValueError("Unsupported audio. Upload WAV, FLAC, or OGG; convert other formats first.") from None
    return validate_wave(wave, rate), rate

def split_sentences(text: str, limit: int) -> list[str]:
    sentences = re.findall(r"[^\n.!?\u3002\uff01\uff1f]+[.!?\u3002\uff01\uff1f]*|[.!?\u3002\uff01\uff1f]+|\n+", text)
    result, current = [], ""
    for sentence in sentences:
        if sentence.isspace():
            if current.strip():
                result.append(current.strip())
                current = ""
            continue
        while len(sentence) > limit:
            if current.strip():
                result.append(current.strip())
                current = ""
            cut = sentence.rfind(" ", 0, limit + 1)
            cut = cut if cut > limit // 2 else limit
            result.append(sentence[:cut].strip())
            sentence = sentence[cut:].lstrip()
        if len(current) + len(sentence) > limit and current.strip():
            result.append(current.strip())
            current = ""
        current += sentence
    if current.strip():
        result.append(current.strip())
    return result or [text.strip()]

def peaks(wave: np.ndarray, count: int = 200) -> list[float]:
    # Constant-size waveform envelope for browser previews, not fake animation.
    return [round(float(np.max(np.abs(a))), 5) if len(a) else 0 for a in np.array_split(wave, count)]

def export_audio(source: Path, fmt: str) -> Path:
    if fmt == "wav":
        return source
    if fmt not in {"flac", "mp3"}:
        raise ValueError("Unsupported export format")
    target = source.with_suffix("." + fmt)
    if target.is_file():
        return target
    temp = target.with_suffix(target.suffix + ".part")
    try:
        if fmt == "flac":
            wave, rate = sf.read(source)
            sf.write(temp, wave, rate, format="FLAC", subtype="PCM_16")
        else:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ValueError("MP3 export needs FFmpeg on PATH; WAV and FLAC work without it")
            result = subprocess.run([ffmpeg, "-nostdin", "-y", "-v", "error", "-i", str(source), "-map_metadata", "-1", "-codec:a", "libmp3lame", "-q:a", "2", "-f", "mp3", str(temp)], capture_output=True, timeout=120)
            if result.returncode:
                raise ValueError("FFmpeg could not export MP3")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    return target
