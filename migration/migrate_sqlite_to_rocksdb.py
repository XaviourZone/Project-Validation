#!/usr/bin/env python3
"""One-time legacy SQLite -> RocksDB migration. SQLite is used only here to read legacy files."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
from typing import Any
from shared.storage.rocksdb_store import RocksDBStore

def _json(v):
    if v in (None,""): return {}
    try:
        x=json.loads(v); return x if isinstance(x,dict) else {}
    except Exception: return {}

def migrate_one(source:Path,target:Path,database_name:str)->dict[str,Any]:
    if not source.exists(): raise FileNotFoundError(source)
    if target.exists() and any(target.iterdir()): raise FileExistsError(f"Target RocksDB already exists and is non-empty: {target}")
    store=RocksDBStore(target); manifest={"source":str(source),"target":str(target),"database":database_name,"tables":{}}
    conn=sqlite3.connect(f"file:{source}?mode=ro",uri=True);conn.row_factory=sqlite3.Row
    try:
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        for table in tables:
            cols=[r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')];rows=[dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')];manifest["tables"][table]={"columns":cols,"rows":len(rows)}
            if database_name=="router_state" and table=="file_states":
                for r in rows:
                    key=f"{r['source']}|{r['filename']}|{r['file_hash']}";store.put("file_states",key,r)
                    if r.get("message_id") is not None:store.put("message_index",str(r["message_id"]),key)
            elif database_name=="ais_state" and table=="ais_vessel_state":
                for r in rows:
                    state=_json(r.get("state_json"));state.update({"mmsi":int(r["mmsi"]),"last_message_type":r.get("last_message_type"),"last_timestamp":r.get("last_timestamp"),"last_source":r.get("last_source"),"updated_at":r.get("updated_at")});store.put("vessel",str(int(r["mmsi"])),state)
            elif database_name=="ais_state" and table=="ais_message_state":
                grouped={}
                for r in rows: grouped.setdefault(int(r["mmsi"]),[]).append({"mmsi":int(r["mmsi"]),"message_type":int(r["message_type"]),"timestamp":r.get("timestamp"),"source":r.get("source"),"payload":_json(r.get("payload_json")),"updated_at":r.get("updated_at")})
                for mmsi,items in grouped.items():store.put("history",str(mmsi),list(reversed(items[-100:])))
            elif database_name=="track_state" and table=="track_state":
                for r in rows:store.put("track",str(int(r["mmsi"])),r)
            elif database_name=="track_state" and table=="mmsi_reference":
                for r in rows:store.put("reference",str(int(r["mmsi"])),{"mmsi":int(r["mmsi"]),"values":_json(r.get("values_json")),"last_tx_iso":r.get("last_tx_iso"),"last_source":r.get("last_source"),"updated_at":r.get("updated_at")})
            elif database_name=="forwarder" and table=="deliveries":
                for r in rows:store.put("deliveries",f"{r['output_id']}|{r['destination']}",r)
            else:
                for i,r in enumerate(rows):store.put(f"{database_name}/{table}",str(i),r)
    finally:
        conn.close();store.put("__migration__","manifest",manifest);store.close()
    return manifest

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--source",action="append",required=True);ap.add_argument("--target-root",required=True);args=ap.parse_args()
    root=Path(args.target_root);root.mkdir(parents=True,exist_ok=True);reports=[]
    for src in args.source:
        p=Path(src);report=migrate_one(p,root/p.stem,p.stem);reports.append(report);print(f"MIGRATED {p} -> {root/p.stem}")
        for table,info in report["tables"].items():print(f"  {table}: {info['rows']} rows")
    (root/"migration_manifest.json").write_text(json.dumps(reports,indent=2,ensure_ascii=False),encoding="utf-8");return 0
if __name__=="__main__":raise SystemExit(main())
