"""Shared I/O and PostgreSQL access only. No feed business rules live here."""
from __future__ import annotations
import hashlib, json, logging, socket
from pathlib import Path
from typing import Any, Iterable
import psycopg
from psycopg.rows import dict_row

log=logging.getLogger("validation.feed.runtime")

def db_connect(cfg: dict):
    return psycopg.connect(host=cfg["DB_HOST"],port=int(cfg["DB_PORT"]),dbname=cfg["DB_NAME"],user=cfg["DB_USER"],password=cfg.get("DB_PASSWORD",""),row_factory=dict_row,connect_timeout=5)

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def ref_rows(conn,source:str,table:str,field:str,value:Any,limit:int=2):
    if value in (None,""): return []
    # Values are stored as JSON strings because source datasets have mixed types.
    return conn.execute(
        "SELECT data FROM reference_rows WHERE source_name=%s AND table_name=%s AND upper(COALESCE(data->>%s,''))=upper(%s) LIMIT %s",
        (source,table,field,str(value),limit)
    ).fetchall()

def unlocode(conn,value:Any):
    if value in (None,""): return value
    code="".join(str(value).upper().split())
    row=conn.execute("SELECT name FROM unlocode WHERE code=%s",(code,)).fetchone()
    return row["name"] if row else value

def send_tcp(host:str,port:int,payload:str):
    with socket.create_connection((host,int(port)),timeout=10) as s:
        s.sendall(payload.encode("utf-8"))

def stable_output_name(source:str,source_file:str,index:int,xml:str):
    digest=hashlib.sha256(xml.encode("utf-8")).hexdigest()[:16]
    stem=Path(source_file).stem
    return f"{source}_{stem}_{index}_{digest}.xml"

def write_xml(output:Path,source:str,source_file:str,index:int,xml:str,forward:dict|None=None):
    output.mkdir(parents=True,exist_ok=True)
    target=output/stable_output_name(source,source_file,index,xml)
    temp=target.with_suffix(".xml.part")
    temp.write_text(xml,encoding="utf-8")
    temp.replace(target)
    if forward and forward.get("enabled"):
        send_tcp(forward["host"],int(forward["port"]),xml)
    return target

def already_processed(conn,source,file_hash):
    row=conn.execute("SELECT status FROM ingest_file WHERE source_name=%s AND file_hash=%s",(source,file_hash)).fetchone()
    return bool(row and row["status"]=="DONE")

def mark_file(conn,source,path,file_hash,status,records=0,error=None):
    conn.execute(
        """INSERT INTO ingest_file(source_name,file_path,file_hash,status,records,error)
           VALUES(%s,%s,%s,%s,%s,%s)
           ON CONFLICT(source_name,file_hash) DO UPDATE SET file_path=EXCLUDED.file_path,status=EXCLUDED.status,records=EXCLUDED.records,error=EXCLUDED.error,last_attempt=now()""",
        (source,str(path),file_hash,status,records,error)
    )

def files_in_folder(folder:Path,patterns:Iterable[str]):
    seen=set()
    for pattern in patterns:
        for p in sorted(folder.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.add(p); yield p

def get_vessel_state(conn,mmsi:int):
    row=conn.execute("SELECT values FROM vessel_state WHERE mmsi=%s",(int(mmsi),)).fetchone()
    return dict(row["values"]) if row and row["values"] else {}

def update_vessel_state(conn,mmsi:int,values:dict,timestamp=None,source:str=""):
    if not mmsi: return
    old=get_vessel_state(conn,mmsi)
    merged=dict(old)
    for k,v in values.items():
        if v not in (None,""): merged[k]=v
    conn.execute("INSERT INTO vessel_state_history(mmsi,values,event_timestamp,source) VALUES(%s,%s,%s,%s)",
                 (int(mmsi),json.dumps(merged,ensure_ascii=False),timestamp,source))
    conn.execute("""INSERT INTO vessel_state(mmsi,values,last_timestamp,last_source)
                    VALUES(%s,%s,%s,%s)
                    ON CONFLICT(mmsi) DO UPDATE SET values=EXCLUDED.values,last_timestamp=EXCLUDED.last_timestamp,last_source=EXCLUDED.last_source,updated_at=now()""",
                 (int(mmsi),json.dumps(merged,ensure_ascii=False),timestamp,source))
    return merged
