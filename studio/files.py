"""Protect in-flight audio responses from deletion without buffering audio in RAM."""
from collections import Counter
from pathlib import Path
import threading
from fastapi.responses import FileResponse


class LeasedFileResponse(FileResponse):
    def __init__(self, path, release, **kwargs):
        super().__init__(path, **kwargs)
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.release()


class FileLeases:
    def __init__(self):
        self.lock = threading.Lock()
        self.counts = Counter()

    def busy(self, path: Path | None = None) -> bool:
        with self.lock:
            return bool(self.counts) if path is None else bool(self.counts[path.resolve()])

    def response(self, path: Path, **kwargs):
        key = path.resolve()
        with self.lock:
            self.counts[key] += 1
        released = False

        def release():
            nonlocal released
            with self.lock:
                if released:
                    return
                released = True
                self.counts[key] -= 1
                if not self.counts[key]:
                    del self.counts[key]
        try:
            return LeasedFileResponse(path, release, **kwargs)
        except Exception:
            release()
            raise
