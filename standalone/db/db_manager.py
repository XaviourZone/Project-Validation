#!/usr/bin/env python3
"""
Validation PostgreSQL DB manager.

Responsibilities:
- initialise the shared PostgreSQL schema
- import WRS/NSC folders on demand
- continuously watch PANS XML files
- preserve current rows by UPSERT and retain every replaced version in history
- expose a small offline Flask console for status, search and imports

No feed parsing/enrichment logic lives here.
"""
from __future__ import annotations
import csv, hashlib, json, logging, os, re, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
from threading import Event, Thread
from typing import Any

import psycopg
from psycopg.rows import dict_row
from flask import Flask, jsonify, request, render_template_string

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "db" / "config.json"
SCHEMA_PATH = ROOT / "db" / "schema.sql"
LOG_DIR = ROOT / "db" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_DIR / "db_manager.log", encoding="utf-8")],
)
log = logging.getLogger("validation.db")

app = Flask(__name__)
STOP = Event()
WORKER: Thread | None = None

def load_config() -> dict:
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    data.setdefault("host","127.0.0.1"); data.setdefault("port",5432)
    data.setdefault("database","validation"); data.setdefault("user","validation")
    data.setdefault("password",""); data.setdefault("web_host","127.0.0.1")
    data.setdefault("web_port",5055); data.setdefault("pans_folder","")
    data.setdefault("poll_seconds",2)
    return data

CFG = load_config()

def connect():
    return psycopg.connect(
        host=CFG["host"], port=int(CFG["port"]), dbname=CFG["database"],
        user=CFG["user"], password=CFG.get("password",""), row_factory=dict_row,
        connect_timeout=5,
    )

def wait_for_db():
    while not STOP.is_set():
        try:
            with connect() as c:
                c.execute("SELECT 1")
                log.info("PostgreSQL ready at %s:%s/%s", CFG["host"], CFG["port"], CFG["database"])
                return
        except Exception as exc:
            log.warning("PostgreSQL unavailable: %s", exc)
            STOP.wait(2)
    raise RuntimeError("DB manager stopped while waiting for PostgreSQL")

def init_schema():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as c:
        c.execute(sql)
        c.commit()

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def clean_key(v: Any) -> str:
    s=str(v or "").strip()
    s=re.sub(r"\s+","_",s)
    return s[:500] or "ROW"

def clean_column(v: Any) -> str:
    s=str(v or "").strip()
    s=re.sub(r"[\s\-./\\()\[\]]+","_",s).upper().strip("_")
    return s or "UNKNOWN_COLUMN"

def csv_rows(path: Path):
    last=None
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try:
            with path.open("r",encoding=enc,newline="") as f:
                reader=csv.reader(f)
                try: raw=next(reader)
                except StopIteration: return
                headers=[]; used=set()
                for x in raw:
                    base=clean_column(x)
                    if not base: headers.append(""); continue
                    name=base; n=1
                    while name in used:
                        n+=1; name=f"{base}_{n}"
                    used.add(name); headers.append(name)
                for row in reader:
                    values=list(row[:len(headers)])+[""]*max(0,len(headers)-len(row))
                    yield {h: values[i].strip() for i,h in enumerate(headers) if h}
            return
        except UnicodeDecodeError as exc:
            last=exc
    raise UnicodeError(f"Cannot decode {path}: {last}")

def nsc_region(path: Path) -> str:
    for part in reversed(path.parts):
        token=re.sub(r"[^A-Za-z0-9]+","_",part).strip("_").upper()
        if token in ("EAST","NSC_EAST") or token.startswith("NSC_EAST_"): return "EAST"
        if token in ("WEST","NSC_WEST") or token.startswith("NSC_WEST_"): return "WEST"
    return "UNKNOWN"

def flatten_xml(element: ET.Element, result=None):
    result = result if result is not None else {}
    tag=element.tag.split("}")[-1]
    if element.text and element.text.strip():
        value=element.text.strip()
        existing=next((k for k in result if k.lower()==tag.lower()),None)
        result[existing or tag]=value if existing is None else f"{result[existing]}; {value}"
    for child in element: flatten_xml(child,result)
    return result

def pans_table(root_tag: str):
    return {
        "VesselProfile":"pans_vespro",
        "VoyageRegistration":"pans_calinf",
        "VesselCallNumber":"pans_calinv",
        "BerthManagement":"pans_berman",
    }.get(root_tag)

def row_key(source: str, table: str, data: dict, source_hash: str, index: int) -> str:
    preferred = (
        "VESSEL_ID","IMO","IMONumber","MMSINumber","MMSI","ID_IMO","ID_MMSI",
        "VCN","CallSign","CALL_SIGN","VESSEL_NAME","VesselName"
    )
    identity=[str(data[k]).strip() for k in preferred if k in data and str(data[k]).strip()]
    if identity:
        return "|".join(identity[:2])
    return f"{source_hash[:20]}:{index}"

def upsert_row(conn, source: str, table: str, key: str, data: dict, source_file: str, source_hash: str):
    old=conn.execute(
        "SELECT data,source_file,source_hash FROM reference_rows WHERE source_name=%s AND table_name=%s AND row_key=%s",
        (source,table,key)
    ).fetchone()
    if old:
        conn.execute(
            "INSERT INTO reference_row_history(source_name,table_name,row_key,data,source_file,source_hash) VALUES(%s,%s,%s,%s,%s,%s)",
            (source,table,key,old["data"],old["source_file"],old["source_hash"])
        )
    conn.execute(
        """INSERT INTO reference_rows(source_name,table_name,row_key,data,source_file,source_hash)
           VALUES(%s,%s,%s,%s,%s,%s)
           ON CONFLICT(source_name,table_name,row_key) DO UPDATE SET
             data=EXCLUDED.data, source_file=EXCLUDED.source_file,
             source_hash=EXCLUDED.source_hash, updated_at=now()""",
        (source,table,key,json.dumps(data,ensure_ascii=False),source_file,source_hash)
    )

def import_csv_reference(source: str, folder: Path) -> dict:
    if not folder.is_dir(): raise ValueError(f"Folder does not exist: {folder}")
    if source=="WRS":
        datasets=next((p for p in folder.iterdir() if p.is_dir() and p.name.lower()=="datasets"),None)
        decode=next((p for p in folder.iterdir() if p.is_dir() and p.name.lower() in ("decode","decode files")),None)
        if not datasets or not decode: raise ValueError("WRS requires Datasets and Decode/Decode files")
        files=[(p,"wrs_datasets_"+p.stem.lower().replace(".","_")) for p in datasets.rglob("*.csv")]
        files += [(p,"wrs_decode_"+p.stem.lower().replace(".","_")) for p in decode.rglob("*.csv")]
    elif source=="NSC":
        all_files=list(folder.rglob("*.csv"))
        files=[(p,"nsc_vessels") for p in all_files if nsc_region(p) in ("EAST","WEST")]
        regions={nsc_region(p) for p,_ in files}
        if regions != {"EAST","WEST"}: raise ValueError("NSC requires both EAST and WEST data")
    else:
        raise ValueError(source)
    total=0
    with connect() as conn:
        for path,table in sorted(files):
            fh=sha256(path)
            for i,row in enumerate(csv_rows(path)):
                if source=="NSC": row["SOURCE_REGION"]=nsc_region(path)
                upsert_row(conn,source,table,row_key(source,table,row,fh,i),row,str(path),fh)
                total+=1
        conn.commit()
    return {"source":source,"files":len(files),"rows":total}

def import_pans_file(path: Path) -> int:
    fh=sha256(path)
    root=ET.parse(path).getroot()
    table=pans_table(root.tag.split("}")[-1])
    if not table: return 0
    data={str(k).replace("-","_").replace(" ","_"):str(v) for k,v in flatten_xml(root).items()}
    with connect() as conn:
        upsert_row(conn,"PANS",table,row_key("PANS",table,data,fh,0),data,str(path),fh)
        conn.execute(
            """INSERT INTO ingest_file(source_name,file_path,file_hash,status,records)
               VALUES('PANS',%s,%s,'DONE',1)
               ON CONFLICT(source_name,file_hash) DO UPDATE SET status='DONE',records=1,last_attempt=now(),error=NULL""",
            (str(path),fh)
        )
        conn.execute("DELETE FROM pans_pending WHERE file_path=%s",(str(path),))
        conn.commit()
    return 1

def watch_pans():
    while not STOP.is_set():
        folder=Path(CFG.get("pans_folder") or "")
        if folder.is_dir():
            for path in sorted(folder.rglob("*.xml")):
                try:
                    fh=sha256(path)
                    with connect() as conn:
                        known=conn.execute("SELECT 1 FROM ingest_file WHERE source_name='PANS' AND file_hash=%s AND status='DONE'",(fh,)).fetchone()
                    if known: continue
                    import_pans_file(path)
                    log.info("PANS imported: %s",path)
                except Exception as exc:
                    log.error("PANS import failed for %s: %s",path,exc)
                    try:
                        with connect() as conn:
                            conn.execute(
                                """INSERT INTO pans_pending(file_path,file_hash,status,last_error,last_attempt)
                                   VALUES(%s,%s,'PENDING',%s,now())
                                   ON CONFLICT(file_path) DO UPDATE SET status='PENDING',last_error=%s,last_attempt=now()""",
                                (str(path),fh,str(exc),str(exc))
                            ); conn.commit()
                    except Exception: pass
        STOP.wait(max(1,int(CFG.get("poll_seconds",2))))

@app.get("/")
def index():
    return render_template_string(PAGE)

@app.get("/api/status")
def status():
    try:
        with connect() as c:
            rows=c.execute("SELECT source_name,COUNT(*) AS rows FROM reference_rows GROUP BY source_name ORDER BY source_name").fetchall()
            hist=c.execute("SELECT COUNT(*) AS n FROM reference_row_history").fetchone()["n"]
            pending=c.execute("SELECT COUNT(*) AS n FROM pans_pending WHERE status='PENDING'").fetchone()["n"]
            return jsonify({"database":"UP","current":rows,"history_rows":hist,"pans_pending":pending})
    except Exception as exc:
        return jsonify({"database":"DOWN","error":str(exc)}),503

@app.post("/api/import/<source>")
def import_source(source):
    source=source.upper()
    payload=request.get_json(silent=True) or {}
    folder=payload.get("folder","")
    try:
        result=import_csv_reference(source,Path(folder).expanduser().resolve())
        return jsonify({"status":"PASS",**result})
    except Exception as exc:
        return jsonify({"status":"FAIL","error":str(exc)}),400

@app.post("/api/pans/folder")
def set_pans_folder():
    folder=(request.get_json(silent=True) or {}).get("folder","")
    p=Path(folder).expanduser().resolve()
    if not p.is_dir(): return jsonify({"error":"folder does not exist"}),400
    CFG["pans_folder"]=str(p)
    CONFIG_PATH.write_text(json.dumps(CFG,indent=2),encoding="utf-8")
    return jsonify({"status":"PASS","pans_folder":str(p)})

@app.post("/api/source")
def add_source():
    x=request.get_json(silent=True) or {}
    with connect() as c:
        c.execute("""INSERT INTO source(source_id,source_name,enabled,description) VALUES(%s,%s,%s,%s)
                     ON CONFLICT(source_id) DO UPDATE SET source_name=EXCLUDED.source_name,enabled=EXCLUDED.enabled,description=EXCLUDED.description,updated_at=now()""",
                  (int(x["source_id"]),str(x["source_name"]).strip(),bool(x.get("enabled",True)),x.get("description")))
        c.commit()
    return jsonify({"status":"PASS"})

@app.post("/api/mapping")
def add_mapping():
    x=request.get_json(silent=True) or {}
    with connect() as c:
        c.execute("""INSERT INTO field_mapping(source_id,input_field,target_field,transformation,priority,enabled)
                     VALUES(%s,%s,%s,%s,%s,%s)
                     ON CONFLICT(source_id,input_field,target_field) DO UPDATE SET transformation=EXCLUDED.transformation,priority=EXCLUDED.priority,enabled=EXCLUDED.enabled""",
                  (x.get("source_id"),x["input_field"],x["target_field"],x.get("transformation"),int(x.get("priority",1)),bool(x.get("enabled",True))))
        c.commit()
    return jsonify({"status":"PASS"})

def import_unlocode_csv(path: Path):
    total=0
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        reader=csv.DictReader(f)
        with connect() as conn:
            for row in reader:
                norm={clean_column(k):str(v or "").strip() for k,v in row.items()}
                country=norm.get("COUNTRY") or norm.get("COUNTRY_CODE") or ""
                location=norm.get("LOCATION") or norm.get("LOCATION_CODE") or ""
                code=(norm.get("LOCODE") or (country+location)).replace(" ","").upper()
                name=norm.get("NAME") or norm.get("NAMEWODIACRITICS") or ""
                if len(code)!=5 or not name:continue
                conn.execute("""INSERT INTO unlocode(code,country_code,location_code,name,subdivision,status)
                                VALUES(%s,%s,%s,%s,%s,%s)
                                ON CONFLICT(code) DO UPDATE SET country_code=EXCLUDED.country_code,location_code=EXCLUDED.location_code,name=EXCLUDED.name,subdivision=EXCLUDED.subdivision,status=EXCLUDED.status,updated_at=now()""",
                             (code,country,location,norm.get("NAME") or name,norm.get("SUBDIVISION") or norm.get("SUBDIV"),norm.get("STATUS")))
                total+=1
            conn.commit()
    return total

@app.post("/api/unlocode/import")
def import_unlocode():
    path=Path((request.get_json(silent=True) or {}).get("path","")).expanduser().resolve()
    if not path.is_file(): return jsonify({"error":"CSV file does not exist"}),400
    try:return jsonify({"status":"PASS","rows":import_unlocode_csv(path)})
    except Exception as exc:return jsonify({"status":"FAIL","error":str(exc)}),400

@app.post("/api/unlocode")
def add_unlocode():
    x=request.get_json(silent=True) or {}
    code=str(x["code"]).replace(" ","").upper()
    with connect() as c:
        c.execute("""INSERT INTO unlocode(code,country_code,location_code,name,subdivision,status)
                     VALUES(%s,%s,%s,%s,%s,%s)
                     ON CONFLICT(code) DO UPDATE SET country_code=EXCLUDED.country_code,location_code=EXCLUDED.location_code,name=EXCLUDED.name,subdivision=EXCLUDED.subdivision,status=EXCLUDED.status,updated_at=now()""",
                  (code,x.get("country_code"),x.get("location_code"),x["name"],x.get("subdivision"),x.get("status")))
        c.commit()
    return jsonify({"status":"PASS"})

@app.post("/api/destination")
def add_destination():
    x=request.get_json(silent=True) or {}
    with connect() as c:
        c.execute("""INSERT INTO destination_mapping(source_code,destination_code,destination_name,enabled)
                     VALUES(%s,%s,%s,%s)
                     ON CONFLICT(source_code,destination_code,destination_name) DO UPDATE SET enabled=EXCLUDED.enabled""",
                  (x["source_code"],x.get("destination_code"),x["destination_name"],bool(x.get("enabled",True))))
        c.commit()
    return jsonify({"status":"PASS"})

@app.post("/api/reference-row")
def add_reference_row():
    x=request.get_json(silent=True) or {}
    source=str(x["source"]).upper();table=str(x["table"]);key=str(x["row_key"]);data=x["data"]
    with connect() as c:
        upsert_row(c,source,table,key,data,x.get("source_file","MANUAL"),x.get("source_hash","MANUAL"))
        c.commit()
    return jsonify({"status":"PASS"})

@app.get("/api/config")
def config_data():
    with connect() as c:
        return jsonify({
          "sources":c.execute("SELECT * FROM source ORDER BY source_id").fetchall(),
          "mappings":c.execute("SELECT * FROM field_mapping ORDER BY source_id,priority,id").fetchall(),
          "unlocode_count":c.execute("SELECT COUNT(*) AS n FROM unlocode").fetchone()["n"],
          "destination_count":c.execute("SELECT COUNT(*) AS n FROM destination_mapping").fetchone()["n"]
        })

@app.get("/api/search")
def search():
    source=request.args.get("source")
    table=request.args.get("table")
    text=request.args.get("q","").strip()
    limit=min(int(request.args.get("limit","100")),500)
    where=[]; args=[]
    if source: where.append("source_name=%s"); args.append(source.upper())
    if table: where.append("table_name=%s"); args.append(table)
    if text: where.append("data::text ILIKE %s"); args.append("%"+text+"%")
    clause=(" WHERE "+" AND ".join(where)) if where else ""
    with connect() as c:
        rows=c.execute(f"SELECT source_name,table_name,row_key,data,updated_at FROM reference_rows{clause} ORDER BY updated_at DESC LIMIT %s",(*args,limit)).fetchall()
    return jsonify(rows)

PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Validation DB Manager</title>
<style>body{font-family:Arial;background:#101418;color:#eee;margin:32px}button,input,textarea{padding:8px;margin:4px}pre{background:#171d22;padding:16px;overflow:auto}.card{border:1px solid #39434c;padding:16px;margin:12px 0;border-radius:8px}textarea{width:90%;height:90px;background:#0d1114;color:#eee}</style></head>
<body><h1>Validation — PostgreSQL Reference Manager</h1>
<div class=card><button onclick=refresh()>Refresh</button><pre id=status></pre></div>
<div class=card><h3>WRS / NSC import</h3><input id=refpath size=70 placeholder="Source folder path"><button onclick=imp('WRS')>Import WRS</button><button onclick=imp('NSC')>Import NSC</button></div>
<div class=card><h3>PANS live folder</h3><input id=pans size=70 placeholder="PANS folder path"><button onclick=setPans()>Set Folder</button></div>
<div class=card><h3>Source ID</h3><input id=sid placeholder="1"><input id=sname placeholder="SAIS_IOR"><input id=sdesc placeholder="description"><button onclick=addSource()>Save</button></div>
<div class=card><h3>Field mapping</h3><input id=msid placeholder="source id"><input id=mi placeholder="input field"><input id=mt placeholder="target field"><input id=mx placeholder="transformation"><button onclick=addMapping()>Save</button></div>
<div class=card><h3>UN/LOCODE</h3><input id=upath size=60 placeholder="CSV file path"><button onclick=importUnlocode()>Import CSV</button><br><input id=ucode placeholder="INBOM"><input id=uname placeholder="MUMBAI"><input id=ucountry placeholder="IN"><input id=uloc placeholder="BOM"><button onclick=addUnlocode()>Save</button></div>
<div class=card><h3>Destination mapping</h3><input id=dsource placeholder="MSIS"><input id=dcode placeholder="INBOM"><input id=dname placeholder="MUMBAI"><button onclick=addDestination()>Save</button></div>
<div class=card><h3>Manual reference row</h3><input id=rsource placeholder="WRS"><input id=rtable placeholder="wrs_datasets_vessels"><input id=rkey placeholder="VESSEL_ID"><textarea id=rdata placeholder='{"VESSEL_ID":"...","MMSI":"..."}'></textarea><button onclick=addRow()>Upsert</button></div>
<div class=card><h3>Reference search</h3><input id=q size=50 placeholder="MMSI / IMO / name / text"><button onclick=search()>Search</button><pre id=out></pre></div>
<script>
async function post(url,obj){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(obj)});return r.json();}
async function refresh(){document.getElementById('status').textContent=JSON.stringify(await (await fetch('/api/config')).json(),null,2);}
async function imp(s){document.getElementById('out').textContent=JSON.stringify(await post('/api/import/'+s,{folder:document.getElementById('refpath').value}),null,2);refresh();}
async function setPans(){document.getElementById('out').textContent=JSON.stringify(await post('/api/pans/folder',{folder:document.getElementById('pans').value}),null,2);}
async function addSource(){document.getElementById('out').textContent=JSON.stringify(await post('/api/source',{source_id:+sid.value,source_name:sname.value,description:sdesc.value}),null,2);refresh();}
async function addMapping(){document.getElementById('out').textContent=JSON.stringify(await post('/api/mapping',{source_id:+msid.value,input_field:mi.value,target_field:mt.value,transformation:mx.value}),null,2);refresh();}
async function importUnlocode(){document.getElementById("out").textContent=JSON.stringify(await post("/api/unlocode/import",{path:document.getElementById("upath").value}),null,2);refresh();}\nasync function addUnlocode(){document.getElementById('out').textContent=JSON.stringify(await post('/api/unlocode',{code:ucode.value,name:uname.value,country_code:ucountry.value,location_code:uloc.value}),null,2);refresh();}
async function addDestination(){document.getElementById('out').textContent=JSON.stringify(await post('/api/destination',{source_code:dsource.value,destination_code:dcode.value,destination_name:dname.value}),null,2);refresh();}
async function addRow(){document.getElementById('out').textContent=JSON.stringify(await post('/api/reference-row',{source:rsource.value,table:rtable.value,row_key:rkey.value,data:JSON.parse(rdata.value)}),null,2);refresh();}
async function search(){const r=await fetch('/api/search?q='+encodeURIComponent(q.value));document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2);}
refresh();
</script></body></html>"""


def main():
    global CFG, WORKER
    wait_for_db()
    init_schema()
    WORKER=Thread(target=watch_pans,daemon=True,name="PANS-Watcher")
    WORKER.start()
    log.info("DB manager web console: http://%s:%s",CFG["web_host"],CFG["web_port"])
    app.run(host=CFG["web_host"],port=int(CFG["web_port"]),debug=False,use_reloader=False)

if __name__=="__main__":
    try: main()
    except KeyboardInterrupt: STOP.set()
