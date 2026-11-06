"""Small transactional SQLite store; model weights and audio remain on disk."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import time
from uuid import uuid4

class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        for name in ("audio", "references", "logs"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.path = self.root / "studio.sqlite3"
        with self.db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL, PRIMARY KEY(kind,id))")
            db.execute("CREATE INDEX IF NOT EXISTS records_time ON records(kind,created DESC)")

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute("PRAGMA secure_delete=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def put(self, kind: str, record: dict) -> dict:
        record = {**record}
        record.setdefault("id", uuid4().hex)
        record.setdefault("created", time.time())
        with self.db() as db:
            db.execute("INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, record["id"], record["created"], json.dumps(record, ensure_ascii=False, allow_nan=False)))
        return record

    def get(self, kind: str, key: str) -> dict | None:
        with self.db() as db:
            row = db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, kind: str, limit: int = 1000) -> list[dict]:
        with self.db() as db:
            rows = db.execute("SELECT data FROM records WHERE kind=? ORDER BY created DESC LIMIT ?", (kind, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def delete(self, kind: str, key: str) -> None:
        with self.db() as db:
            db.execute("DELETE FROM records WHERE kind=? AND id=?", (kind, key))

    def recover(self) -> int:
        count = 0
        for record in self.list("job", limit=10000):
            if record["status"] in {"queued", "loading", "running", "cancelling"}:
                record.update(status="interrupted", stage="Service restarted", finished=time.time())
                self.put("job", record)
                count += 1
        return count

    def put_many(self, entries):
        """Commit related rows in one transaction (track + terminal job)."""
        with self.db() as db:
            for kind, item in entries:
                item.setdefault("created", time.time())
                db.execute("INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data", (kind, item["id"], item["created"], json.dumps(item, ensure_ascii=False, allow_nan=False)))

    def clear(self, kinds):
        with self.db() as db:
            for kind in kinds:
                db.execute("DELETE FROM records WHERE kind=?", (kind,))

    def compact(self):
        with self.db() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            db.execute("VACUUM")

    def counts(self):
        with self.db() as db:
            return dict(db.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind").fetchall())

    def history(self, q, mode, favorite, offset, limit):
        where, params = ["kind='track'"], []
        if q:
            # Literal substring search, not user-controlled wildcard matching.
            where.append("instr(lower(json_extract(data,'$.text') || ' ' || json_extract(data,'$.title') || ' ' || json_extract(data,'$.model_name')),lower(?))>0")
            params.append(q)
        if mode != "all":
            where.append("json_extract(data,'$.mode')=?")
            params.append(mode)
        if favorite:
            where.append("json_extract(data,'$.favorite')=1")
        predicate = " AND ".join(where)
        with self.db() as db:
            total = db.execute("SELECT COUNT(*) FROM records WHERE " + predicate, params).fetchone()[0]
            rows = db.execute("SELECT data FROM records WHERE " + predicate + " ORDER BY created DESC LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
        return {"total": total, "items": [json.loads(row[0]) for row in rows]}
