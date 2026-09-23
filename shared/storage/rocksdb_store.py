"""Thread-safe RocksDB JSON/key-value storage used by all Validation services."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any, Iterable
try:
    from rocksdb import RocksDB
except ImportError as exc:
    raise RuntimeError("RocksDB runtime is required. Install the approved offline amulet-rocksdb wheel.") from exc

class RocksDBStore:
    def __init__(self, path: str | Path, create_if_missing: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = RocksDB(str(self.path), create_if_missing=create_if_missing)
        self._lock = threading.RLock()

    @staticmethod
    def _key(namespace: str, key: str) -> bytes:
        return f"{namespace}\x1f{key}".encode("utf-8")

    @staticmethod
    def _encode(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")

    @staticmethod
    def _decode(value: bytes | None) -> Any:
        return None if value is None else json.loads(value.decode("utf-8"))

    def get(self, namespace: str, key: str) -> Any:
        with self._lock:
            return self._decode(self._db.get(self._key(namespace, key)))

    def put(self, namespace: str, key: str, value: Any) -> None:
        with self._lock:
            self._db.put(self._key(namespace, key), self._encode(value))

    def delete(self, namespace: str, key: str) -> None:
        with self._lock:
            self._db.delete(self._key(namespace, key))

    def put_many(self, namespace: str, records: Iterable[tuple[str, Any]]) -> None:
        with self._lock:
            for key, value in records:
                self._db.put(self._key(namespace, key), self._encode(value))

    def scan(self, namespace: str):
        prefix = f"{namespace}\x1f".encode("utf-8")
        with self._lock:
            for raw_key, raw_value in self._db.iter(prefix=prefix):
                key = raw_key.decode("utf-8")[len(prefix):]
                yield key, self._decode(raw_value)

    def close(self) -> None:
        close = getattr(self._db, "close", None)
        if close:
            close()
