from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import rocksdb  # type: ignore
except ImportError as exc:  # pragma: no cover
    rocksdb = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

class RocksReferenceStore:
    """Minimal RocksDB wrapper for Parser-owned reference data."""

    def __init__(self, path: str | Path, create_if_missing: bool = True) -> None:
        if rocksdb is None:
            raise RuntimeError(
                "python-rocksdb is not installed; install the offline dependency before starting the parser"
            ) from _IMPORT_ERROR
        options = rocksdb.Options(create_if_missing=create_if_missing)
        self.path = str(Path(path))
        self.db = rocksdb.DB(self.path, options)

    @staticmethod
    def encode(value: dict[str, Any]) -> bytes:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")

    @staticmethod
    def decode(value: bytes | None) -> dict[str, Any] | None:
        if value is None:
            return None
        return json.loads(value.decode("utf-8"))

    def get(self, key: str) -> dict[str, Any] | None:
        return self.decode(self.db.get(key.encode("utf-8")))

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.db.put(key.encode("utf-8"), self.encode(value))
