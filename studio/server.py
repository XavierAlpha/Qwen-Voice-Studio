"""Single-user, loopback-only API. Static assets, models and audio stay local."""
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import os
import secrets
import shutil
import threading
from urllib.parse import urlparse
from uuid import uuid4
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import __version__
from .schema import Generate, Load, Preset, Register, PickFolder, Runtime, TrackEdit, LANGUAGES
from .store import Store
from .models import Registry
from .engine import QwenEngine
from .jobs import Jobs
from .audio import MAX_UPLOAD, read_reference, write_wave, export_audio
from .config import Config, Preferences
from .privacy import public_error
from .files import FileLeases
from .native_dialog import NativeFolderPicker, PickerError, PickerBusy

DEFAULT_PRESETS = [
    {"id": "warm", "name": "\u6e29\u67d4\u53d9\u8ff0", "instruct": "\u6210\u5e74\u5973\u6027\uff0c\u666e\u901a\u8bdd\u6e05\u6670\uff0c\u97f3\u8272\u67d4\u548c\u81ea\u7136\uff0c\u8bed\u901f\u9002\u4e2d\u3002", "language": "Chinese"},
    {"id": "narrator", "name": "\u7eaa\u5f55\u7247\u65c1\u767d", "instruct": "\u6210\u5e74\u7537\u6027\uff0c\u97f3\u8272\u6e29\u539a\u3001\u4f4e\u6c89\u6709\u5171\u9e23\uff0c\u666e\u901a\u8bdd\uff0c\u8282\u594f\u4ece\u5bb9\u3002", "language": "Chinese"},
    {"id": "bright", "name": "\u6d3b\u529b\u5bf9\u8bdd", "instruct": "\u6210\u5e74\u58f0\u97f3\uff0c\u660e\u4eae\u6e05\u6f88\uff0c\u81ea\u7136\u53e3\u8bed\u611f\uff0c\u8f7b\u677e\u6d3b\u6cfc\u3002", "language": "Chinese"},
]


def create_app(root: Path, data: Path, model_roots=None, demo=False, engine=None, folder_picker=None):
    for key, value in {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "GRADIO_ANALYTICS_ENABLED": "False"}.items():
        os.environ[key] = value
    root, data = root.resolve(), data.resolve()
    store = Store(data)
    config = Config(root, data)
    if model_roots is not None:
        config.save(config.value.model_copy(update={"model_roots": [str(p) for p in model_roots]}))
    registry = Registry(store, config.roots(), config.value.scan_depth)
    if demo:
        if engine is None:
            raise ValueError("Test mode requires an explicitly injected test engine")
        for mode, name in [("design", "VoiceDesign"), ("clone", "Base"), ("custom", "CustomVoice")]:
            store.put("model", {"id": "demo_" + mode, "name": "Qwen3-TTS 1.7B " + name, "mode": mode, "path": "TEST-NO-WEIGHTS", "status": "ready", "speakers": ["Vivian", "Ryan"] if mode == "custom" else [], "size": "1.7B", "capabilities": {"instruct": mode != "clone"}})
    elif config.value.auto_discover:
        registry.scan()
    # Heal an empty preset library left by older privacy-clear releases.
    # Preserve existing user edits and custom presets whenever any are present.
    if not store.list("preset"):
        for preset in DEFAULT_PRESETS:
            store.put("preset", preset)
    if not store.get("settings", "initialized"):
        store.put("settings", {"id": "initialized"})
    engine = engine or QwenEngine(root, config)
    jobs = Jobs(store, registry, engine)
    token = secrets.token_urlsafe(32)
    files_lock = threading.RLock()
    leases = FileLeases()
    picker = folder_picker if folder_picker is not None else NativeFolderPicker()

    @asynccontextmanager
    async def lifespan(app):
        yield
        await asyncio.to_thread(jobs.close)

    app = FastAPI(title="Qwen Voice Studio", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url="/api/schema")
    app.state.store, app.state.jobs, app.state.engine = store, jobs, engine
    app.state.registry, app.state.config = registry, config
    app.state.file_leases = leases
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"] if demo else ["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def secure_local(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.headers.get("sec-fetch-site") == "cross-site" or (origin and urlparse(origin).netloc != request.headers.get("host")):
            return JSONResponse({"detail": "Cross-origin access is disabled"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            if not secrets.compare_digest(request.headers.get("x-studio-token", ""), token):
                return JSONResponse({"detail": "Session expired. Refresh the page."}, status_code=403)
            limit = MAX_UPLOAD if request.url.path == "/api/references" else 128 * 1024
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid content length"}, status_code=400)
            if length < 0 or length > limit:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            # Bound chunked bodies too. Starlette caches this for downstream parsers.
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > limit:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
                body.extend(chunk)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), geolocation=(), microphone=(self)", "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
        # Prevent mixed HTML/JS versions after an in-place upgrade on Windows.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/ui/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic's default includes input values, potentially exposing transcripts.
        return JSONResponse({"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]}, status_code=422)

    @app.exception_handler(ValueError)
    @app.exception_handler(OSError)
    async def invalid(request, error):
        return JSONResponse({"detail": public_error(error, validation=True)}, status_code=400)

    @app.get("/")
    def index():
        return FileResponse(root / "ui" / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/bootstrap")
    def bootstrap():
        return {"version": __version__, "token": token, "demo": demo, "models": registry.list(), "presets": store.list("preset"), "runtime": (store.get("settings", "runtime") or {}).get("value", Runtime().model_dump()), "languages": LANGUAGES, "mp3": bool(shutil.which("ffmpeg")), "native_folder_picker": bool(picker.available()), "preferences": config.value.model_dump()}

    @app.get("/api/system")
    def system():
        try:
            return engine.hardware()
        except (ImportError, ValueError, OSError) as error:
            return {"cuda": False, "gpu": None, "hybrid_ready": False, "model": engine.info, "error": public_error(error)}

    @app.get("/api/diagnostics")
    def diagnostics():
        import platform
        from importlib.metadata import version, PackageNotFoundError
        packages = {}
        for name in ("torch", "torchaudio", "transformers", "huggingface-hub", "qwen-tts", "accelerate", "fastapi"):
            try:
                packages[name] = version(name)
            except PackageNotFoundError:
                packages[name] = None
        return {"version": __version__, "os": platform.system(), "python": platform.python_version(), "packages": packages, "counts": store.counts(), "offline": True, "scan": registry.last_scan}

    @app.get("/api/preferences")
    def preferences():
        return config.value

    @app.put("/api/preferences")
    def save_preferences(value: Preferences):
        with jobs.lock:
            if jobs.is_busy():
                raise HTTPException(409, "Finish or cancel tasks before changing discovery settings")
            config.save(value)
            registry.roots, registry.depth = config.roots(), value.scan_depth
        return value

    @app.put("/api/runtime")
    def runtime(value: Runtime):
        store.put("settings", {"id": "runtime", "value": value.model_dump()})
        return value

    @app.post("/api/native/folder")
    async def native_folder(value: PickFolder):
        # The folder belongs to the machine running Studio (not a remote browser).
        # Run the STA GUI process outside the event loop, and do not log paths.
        try:
            path = await asyncio.to_thread(picker.pick, value.purpose, value.initial_path)
        except PickerBusy as error:
            raise HTTPException(409, str(error)) from error
        except PickerError as error:
            raise HTTPException(503, str(error)) from error
        return {"path": path, "cancelled": path is None}

    @app.get("/api/models")
    def models():
        return registry.list()

    @app.post("/api/models/scan")
    def scan():
        return registry.list() if demo else registry.scan()

    @app.post("/api/models")
    def register(value: Register):
        return registry.public(registry.register(str(config.resolve(value.path))))

    @app.delete("/api/models/{model_id}")
    def unregister(model_id: str):
        with jobs.lock:
            if jobs.is_busy():
                raise HTTPException(409, "Finish queued tasks before unregistering a model")
            if engine.info.get("model_id") == model_id:
                engine.unload()
            store.delete("model", model_id)
        return {"ok": True}  # Never deletes weights.

    @app.post("/api/models/load", status_code=202)
    def load(value: Load):
        return jobs.submit(value.model_dump(), kind="load")

    @app.post("/api/models/unload")
    def unload():
        with jobs.lock:
            if jobs.is_busy():
                raise HTTPException(409, "Finish or cancel tasks before unloading")
            engine.unload()
        return {"ok": True}

    @app.post("/api/jobs", status_code=202)
    def generate(value: Generate):
        return jobs.submit(value.model_dump())

    @app.get("/api/jobs")
    def job_list():
        return store.list("job", 100)

    @app.get("/api/jobs/{job_id}")
    def job_get(job_id: str):
        result = store.get("job", job_id)
        if not result:
            raise HTTPException(404, "Job not found")
        return result

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return jobs.cancel(job_id)

    @app.get("/api/history")
    def history(q: str = "", mode: str = "all", favorite: bool = False, offset: int = 0, limit: int = 40):
        if offset < 0 or not 1 <= limit <= 100 or len(q) > 200 or mode not in {"all", "design", "clone", "custom"}:
            raise HTTPException(400, "Invalid query")
        return store.history(q, mode, favorite, offset, limit)

    @app.get("/api/history/{track_id}")
    def get_track(track_id: str):
        record = store.get("track", track_id)
        if not record:
            raise HTTPException(404, "Audio not found")
        return record

    @app.patch("/api/history/{track_id}")
    def edit_track(track_id: str, edit: TrackEdit):
        with files_lock:
            record = get_track(track_id)
            record.update(edit.model_dump(exclude_none=True))
            return store.put("track", record)

    @app.delete("/api/history/{track_id}")
    def delete_track(track_id: str):
        with files_lock, jobs.lock:
            track = get_track(track_id)
            if any(leases.busy(data / "audio" / f"{track['id']}.{suffix}") for suffix in ("wav", "flac", "mp3")):
                raise HTTPException(409, "Audio is being served; retry deletion after playback or download")
            for suffix in ("wav", "flac", "mp3"):
                (data / "audio" / f"{track['id']}.{suffix}").unlink(missing_ok=True)
            store.delete("track", track_id)
            job = store.get("job", track["job_id"])
            if job:
                job.update(track_id=None, audio_deleted=True)
                store.put("job", job)
        return {"ok": True}

    @app.get("/api/audio/{track_id}")
    def audio(track_id: str, format: str = "wav", download: bool = False):
        with files_lock:
            record = get_track(track_id)
            path = export_audio(data / "audio" / f"{record['id']}.wav", format)
            media = {"wav": "audio/wav", "flac": "audio/flac", "mp3": "audio/mpeg"}[format]
            return leases.response(path, media_type=media, filename=f"voice-{track_id[:8]}.{format}" if download else None)

    @app.get("/api/history/{track_id}/metadata")
    def metadata(track_id: str):
        record = get_track(track_id)
        req = record["request"]
        return {"mode": record["mode"], "language": req["language"], "sampling": req["sampling"], "duration": record["duration"], "sample_rate": record["sample_rate"]}

    @app.post("/api/references", status_code=201)
    async def upload_reference(request: Request):
        wave, rate = await asyncio.to_thread(read_reference, await request.body())
        key = uuid4().hex
        def save_reference():
            with files_lock:
                path = data / "references" / f"{key}.wav"
                try:
                    write_wave(path, wave, rate)
                    # Do not retain the source filename, which can name a real person.
                    return store.put("reference", {"id": key, "name": "reference-" + key[:8] + ".wav", "duration": round(len(wave) / rate, 2), "sample_rate": rate})
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
        return await asyncio.to_thread(save_reference)

    @app.get("/api/references/{ref_id}/audio")
    def reference_audio(ref_id: str):
        with files_lock:
            record = store.get("reference", ref_id)
            if not record:
                raise HTTPException(404, "Reference not found")
            return leases.response(data / "references" / f"{record['id']}.wav", media_type="audio/wav")

    @app.get("/api/references/{ref_id}")
    def reference_info(ref_id: str):
        record = store.get("reference", ref_id)
        if not record:
            raise HTTPException(404, "Reference not found")
        return {key: record[key] for key in ("id", "name", "duration", "sample_rate")}

    @app.delete("/api/references/{ref_id}")
    def delete_reference(ref_id: str):
        with files_lock, jobs.lock:
            if jobs.is_busy():
                raise HTTPException(409, "Finish or cancel tasks before deleting references")
            record = store.get("reference", ref_id)
            if not record:
                raise HTTPException(404, "Reference not found")
            path = data / "references" / f"{record['id']}.wav"
            if leases.busy(path):
                raise HTTPException(409, "Reference audio is being served; retry after playback")
            path.unlink(missing_ok=True)
            store.delete("reference", ref_id)
            if hasattr(engine, "clone_cache"):
                engine.clone_cache.clear()
        return {"ok": True}

    @app.post("/api/history/{track_id}/reference", status_code=201)
    def use_reference(track_id: str):
        with files_lock:
            track = get_track(track_id)
            if not .5 <= track["duration"] <= 60:
                raise ValueError("Use a generated clip between 0.5 and 60 seconds")
            key = uuid4().hex
            shutil.copyfile(data / "audio" / f"{track_id}.wav", data / "references" / f"{key}.wav")
            return store.put("reference", {"id": key, "name": "reference-" + key[:8] + ".wav", "duration": track["duration"], "sample_rate": track["sample_rate"], "transcript": track["text"]})

    @app.post("/api/privacy/clear")
    def clear_private_data(request: Request):
        if request.headers.get("x-confirm-clear") != "clear-local-history":
            raise HTTPException(400, "Explicit confirmation is required")
        with files_lock, jobs.lock:
            if jobs.is_busy():
                raise HTTPException(409, "Finish or cancel tasks before clearing data")
            if leases.busy():
                raise HTTPException(409, "Audio is being served; retry after playback or download")
            engine.unload()
            for folder in ("audio", "references"):
                for file in (data / folder).iterdir():
                    if file.is_file() or file.is_symlink():
                        file.unlink()
            store.clear(("track", "job", "reference", "preset"))
            store.compact()
        return {"ok": True}

    @app.get("/api/presets")
    def presets():
        return store.list("preset")

    @app.post("/api/presets/restore")
    def restore_presets():
        # Restore factory examples without overwriting any customized entry.
        for preset in DEFAULT_PRESETS:
            if not store.get("preset", preset["id"]):
                store.put("preset", preset)
        return store.list("preset")

    @app.post("/api/presets", status_code=201)
    def add_preset(value: Preset):
        return store.put("preset", value.model_dump())

    @app.put("/api/presets/{preset_id}")
    def edit_preset(preset_id: str, value: Preset):
        record = store.get("preset", preset_id)
        if not record:
            raise HTTPException(404, "Preset not found")
        return store.put("preset", {**record, **value.model_dump()})

    @app.delete("/api/presets/{preset_id}")
    def delete_preset(preset_id: str):
        store.delete("preset", preset_id)
        return {"ok": True}

    app.mount("/ui", StaticFiles(directory=root / "ui"), name="ui")
    return app
