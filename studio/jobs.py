"""One inference worker, durable job metadata and cooperative cancellation."""
from pathlib import Path
import logging
import queue
import secrets
import threading
import time
from uuid import uuid4
import numpy as np
from .audio import split_sentences, validate_wave, write_wave, peaks
from .engine import Cancelled, InferencePhaseError
from .schema import Generate, Runtime
from .privacy import failure_details, failure_trace_id

log = logging.getLogger(__name__)
ACTIVE = {"queued", "loading", "running", "cancelling"}

class Jobs:
    def __init__(self, store, registry, engine):
        self.store, self.registry, self.engine = store, registry, engine
        self.pending = queue.Queue(maxsize=32)
        self.lock = threading.RLock()
        self.events = {}
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self.run, name="qwen-inference", daemon=True)
        self.store.recover()
        self.worker.start()

    def submit(self, request: dict, kind="generate"):
        with self.lock:
            if self.stopping.is_set():
                raise ValueError("Server is shutting down")
            if self.pending.full():
                raise ValueError("Queue is full (32 pending jobs)")
            record = self.registry.get(request["model_id"])
            if kind == "generate":
                if record["mode"] != request["mode"]:
                    raise ValueError("Select a model that supports the selected task")
                if request["mode"] == "custom" and request["speaker"] not in record.get("speakers", []):
                    raise ValueError("Speaker does not belong to this model")
                if record.get("languages") and request["language"] not in record["languages"]:
                    raise ValueError("Language is not supported by the selected model")
                if request["mode"] == "custom" and request.get("instruct") and not record.get("capabilities", {}).get("instruct", True):
                    raise ValueError("This model does not support instruction control")
                if request["mode"] == "clone" and not self.store.get("reference", request["reference_id"]):
                    raise ValueError("Upload a reference audio first")
                if request["sampling"]["seed"] == -1:
                    request["sampling"]["seed"] = secrets.randbelow(2147483647)
            job = self.store.put("job", {"kind": kind, "status": "queued", "stage": "queued", "request": request, "model_name": record["name"], "completed": 0, "total": 0})
            self.events[job["id"]] = threading.Event()
            self.pending.put_nowait(job["id"])
            return job

    def change(self, job_id, **changes):
        with self.lock:
            job = self.store.get("job", job_id)
            job.update(changes)
            return self.store.put("job", job)

    def cancel(self, job_id):
        with self.lock:
            job = self.store.get("job", job_id)
            if not job:
                raise ValueError("Job not found")
            if job["status"] in ACTIVE:
                self.events[job_id].set()
                return self.change(job_id, status="cancelled" if job["status"] == "queued" else "cancelling", stage="Cancelling at a generation boundary")
            return job

    def is_busy(self):
        return bool(self.events)

    def run(self):
        while not self.stopping.is_set():
            try:
                job_id = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            cancel = self.events[job_id]
            files = []
            stage = "model_loading"
            try:
                if cancel.is_set():
                    continue
                job = self.change(job_id, status="loading", stage="loading", started=time.time())
                request = job["request"]
                record = self.registry.get(request["model_id"])
                if record.get("path") != "TEST-NO-WEIGHTS":
                    self.registry.register(record["path"])
                    record = self.registry.get(request["model_id"])
                info = self.engine.load(record, Runtime.model_validate(request["runtime"]))
                if cancel.is_set():
                    raise Cancelled()
                if job["kind"] == "load":
                    self.change(job_id, status="done", stage="loaded", finished=time.time(), model_info=info)
                    continue
                req = Generate.model_validate(request)
                parts = split_sentences(req.text, req.chunk_chars) if req.split_text else [req.text]
                reference = self.store.root / "references" / f"{req.reference_id}.wav" if req.mode == "clone" else None
                self.change(job_id, status="running", stage="generating", total=len(parts), model_info=info)
                self.engine.reset_metrics()
                started = time.perf_counter()
                waves, sr = [], None
                for index, text in enumerate(parts):
                    segment_req = req.model_copy(deep=True)
                    segment_req.sampling.seed = (req.sampling.seed + index) % 2147483647
                    stage = "speech_generation"
                    wave, sample_rate = self.engine.generate(segment_req, text, reference, cancel)
                    stage = "waveform_validation"
                    wave = validate_wave(wave, sample_rate)
                    if sr is not None and sample_rate != sr:
                        raise ValueError("Segment sample rates differ")
                    sr = sample_rate
                    if waves and req.pause_ms:
                        waves.append(np.zeros(int(sr * req.pause_ms / 1000), dtype=np.float32))
                    waves.append(wave)
                    self.change(job_id, completed=index + 1)
                if cancel.is_set():
                    raise Cancelled()
                metrics = self.engine.metrics()
                elapsed = time.perf_counter() - started
                combined = np.concatenate(waves)
                stage = "audio_saving"
                audio_id = uuid4().hex
                path = self.store.root / "audio" / f"{audio_id}.wav"
                files.append(path)
                combined = write_wave(path, combined, sr)
                duration = len(combined)/sr
                track = {"id": audio_id, "title": req.text[:36], "text": req.text, "mode": req.mode,
                         "model_name": record["name"], "job_id": job_id, "request": request,
                         "duration": round(duration, 3), "sample_rate": sr, "seconds": round(elapsed, 3),
                         "rtf": round(elapsed/duration, 3), "favorite": False, "peaks": peaks(combined), **metrics}
                # Atomic cancellation vs committing the final result.
                with self.lock:
                    if cancel.is_set():
                        raise Cancelled()
                    finished_job = self.store.get("job", job_id)
                    finished_job.update(status="done", stage="done", finished=time.time(), track_id=audio_id)
                    self.store.put_many([("track", track), ("job", finished_job)])
                files.clear()
            except Cancelled:
                self.change(job_id, status="cancelled", stage="cancelled", finished=time.time())
            except Exception as error:
                phase = error.phase if isinstance(error, InferencePhaseError) else stage
                kind, message = failure_details(error, phase)
                issue = failure_trace_id(error, phase)
                # No exception text/traceback: upstream may put audio paths or
                # reference transcripts in error messages. A short correlation ID
                # and phase can be used to diagnose a future local reproduction.
                log.error("Job %s failed: phase=%s code=%s exception=%s ref=%s",
                          job_id, phase, kind,
                          type(getattr(error, "original", error)).__name__, issue)
                self.change(job_id, status="failed", stage="failed", error=message,
                            error_code=kind, error_stage=phase, error_ref=issue,
                            finished=time.time())
                if kind == "memory":
                    self.engine.unload()
            finally:
                for path in files:
                    path.unlink(missing_ok=True)
                with self.lock:
                    self.events.pop(job_id, None)
                self.pending.task_done()

    def close(self):
        self.stopping.set()
        with self.lock:
            for job_id, event in self.events.items():
                event.set()
                record = self.store.get("job", job_id)
                if record and record["status"] == "queued":
                    self.change(job_id, status="cancelled", stage="shutdown", finished=time.time())
        self.worker.join(timeout=10)
        if not self.worker.is_alive():
            self.engine.unload()
