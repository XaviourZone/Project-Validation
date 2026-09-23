from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class InputRecord:
    message_id: str
    source: str
    input_file: str
    input_type: str
    payload: Any
    received_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class ParsedRecord:
    message_id: str
    source: str
    record_type: str
    decoded: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)

@dataclass(slots=True)
class FinalRecord:
    message_id: str
    source: str
    data: dict[str, Any]
    provenance: dict[str, Any] = field(default_factory=dict)
