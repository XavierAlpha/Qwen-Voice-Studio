"""Cross-platform process lock: one inference worker per data directory."""
from pathlib import Path
import os


class InstanceLock:
    def __init__(self, data: Path):
        data.mkdir(parents=True, exist_ok=True)
        self.stream = (data / "instance.lock").open("a+b")
        self.stream.seek(0)
        if not self.stream.read(1):
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise RuntimeError("This data directory is already in use by another server") from None

    def close(self):
        self.stream.close()
