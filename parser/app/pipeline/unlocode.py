"""Offline UN/LOCODE resolver backed by the Validation PostgreSQL reference DB.

If PostgreSQL is unavailable, the existing bundled JSON remains a safe fallback
for compatibility with older deployments.
"""
import json
import os
from pathlib import Path
import unicodedata
from typing import Any, Dict, Optional

_CACHE: Optional[Dict[str, str]] = None
_NAME_CACHE: Optional[Dict[str, str]] = None

def _default_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "config" / "unlocode.json"

def _normalise_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").strip())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())

def _load_json():
    global _CACHE, _NAME_CACHE
    try:
        data=json.loads(_default_path().read_text(encoding="utf-8"))
        if not isinstance(data,dict): data={}
    except Exception:
        data={}
    _CACHE={str(k).strip().upper().replace(" ",""):str(v).strip() for k,v in data.items() if str(k).strip() and str(v).strip()}
    _NAME_CACHE={}
    for code,name in _CACHE.items():
        _NAME_CACHE.setdefault(_normalise_name(name),name)

def _load():
    global _CACHE, _NAME_CACHE
    if _CACHE is not None: return
    _CACHE={}; _NAME_CACHE={}
    try:
        import psycopg
        cfg={
            "host":os.environ.get("VALIDATION_DB_HOST","127.0.0.1"),
            "port":int(os.environ.get("VALIDATION_DB_PORT","5432")),
            "dbname":os.environ.get("VALIDATION_DB_NAME","validation"),
            "user":os.environ.get("VALIDATION_DB_USER","validation"),
            "password":os.environ.get("VALIDATION_DB_PASSWORD","CHANGE_ME"),
        }
        with psycopg.connect(**cfg) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT code,name FROM unlocode_records")
                for code,name in cur.fetchall():
                    if code and name:
                        c=str(code).strip().upper().replace(" ","")
                        _CACHE[c]=str(name).strip()
                        _NAME_CACHE.setdefault(_normalise_name(name),str(name).strip())
        if _CACHE: return
    except Exception:
        pass
    _load_json()

def resolve_destination(value: Any) -> Any:
    if value is None: return value
    text=str(value).strip()
    if not text: return value
    _load()
    code="".join(text.upper().split())
    if len(code)==5 and code[:2].isalpha() and code[2:].isalnum():
        return _CACHE.get(code,value)
    return (_NAME_CACHE or {}).get(_normalise_name(text),value)
