from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.storage.rocksdb_store import RocksDBStore


class RocksReferenceStore:
    """Parser reference-data facade backed only by RocksDB."""

    def __init__(self, path: str | Path, namespace: str = "reference", create_if_missing: bool = True) -> None:
        self.store = RocksDBStore(path, create_if_missing=create_if_missing)
        self.namespace = namespace

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.store.get(self.namespace, key)
        return value if isinstance(value, dict) else None

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.store.put(self.namespace, key, value)

    def scan(self):
        yield from self.store.scan(self.namespace)

    def close(self) -> None:
        self.store.close()
