"""Validation PostgreSQL manager + local browser console.

PostgreSQL stores only WRS/PANS/NSC/UNLOCODE reference data and current live
vessel information. Process status is local JSON under runtime/status.
"""
from __future__ import annotations
import csv, hashlib, html, json, os, re, signal, subprocess, sys
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    import psycopg
except ImportError:
    psycopg=None

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/"scripts"; POSTGRES=ROOT/"postgres"; RUNTIME=ROOT/"runtime"
STATUS=RUNTIME/"status"; PIDS=RUNTIME/"pids"
PORT=int(os.environ.get("VALIDATION_CONSOLE_PORT","8080"))

DB={
 "host":os.environ.get("VALIDATION_DB_HOST","127.0.0.1"),
 "port":int(os.environ.get("VALIDATION_DB_PORT","5432")),
 "dbname":os.environ.get("VALIDATION_DB_NAME","validation"),
 "user":os.environ.get("VALIDATION_DB_USER","validation"),
 "password":os.environ.get("VALIDATION_DB_PASSWORD","CHANGE_ME"),
}
FEEDS={x:x+".py" for x in ("SAIS_IOR","SAIS_GLOBAL","MSIS","LRIT","VATMS_EAST","VATMS_WEST","NAIS")}

SCHEMA="""
CREATE TABLE IF NOT EXISTS reference_records(
 id BIGSERIAL PRIMARY KEY, source TEXT NOT NULL, dataset TEXT NOT NULL,
 entity_key TEXT, identity_mmsi TEXT, identity_imo TEXT, identity_callsign TEXT,
 identity_name TEXT, payload JSONB NOT NULL, source_file TEXT, source_hash TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS reference_status(
 source TEXT PRIMARY KEY, source_folder TEXT, record_count BIGINT DEFAULT 0,
 last_update TIMESTAMPTZ, status TEXT DEFAULT 'EMPTY', error TEXT);
CREATE TABLE IF NOT EXISTS unlocode_records(
 code TEXT PRIMARY KEY, country TEXT, location TEXT, name TEXT, payload JSONB,
 updated_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS live_vessels(
 source_id TEXT NOT NULL, mmsi BIGINT NOT NULL, imo BIGINT, callsign TEXT,
 vessel_name TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
 sog DOUBLE PRECISION, cog DOUBLE PRECISION, heading DOUBLE PRECISION,
 nav_status INTEGER, vessel_type TEXT, destination TEXT, eta TEXT,
 length_m DOUBLE PRECISION, beam_m DOUBLE PRECISION, draft_m DOUBLE PRECISION,
 source_timestamp TEXT, updated_at TIMESTAMPTZ DEFAULT now(), xml_status TEXT,
 PRIMARY KEY(source_id,mmsi));
"""

def ensure_dirs():
    for p in (STATUS,RUNTIME/"logs",PIDS,RUNTIME/"xml/pending"): p.mkdir(parents=True,exist_ok=True)

def bin_dir():
    return POSTGRES/"portable"/("windows-x64" if os.name=="nt" else "linux-x64")/"bin"

def exe(name):
    return bin_dir()/(name+".exe" if os.name=="nt" else name)

def run(args,check=True):
    return subprocess.run([str(x) for x in args],cwd=ROOT,text=True,capture_output=True,check=check)

def start_postgres():
    ctl=exe("pg_ctl"); init=exe("initdb"); data=POSTGRES/"data"; data.mkdir(parents=True,exist_ok=True)
    if not ctl.exists(): raise RuntimeError("Portable PostgreSQL binaries are missing under postgres/portable/")
    if not (data/"PG_VERSION").exists():
        pw=POSTGRES/".db-password"
        pw.write_text(DB["password"],encoding="utf-8")
        try:
            run([init,"-D",data,"-U",DB["user"],"--pwfile",pw,"--auth-local=trust","--auth-host=scram-sha-256","--no-locale"])
        finally:
            pw.unlink(missing_ok=True)
    if run([ctl,"status","-D",data],check=False).returncode!=0:
        run([ctl,"start","-D",data,"-l",POSTGRES/"postgres.log","-o",f"-p {DB['port']}"])

def conn():
    if psycopg is None: raise RuntimeError("psycopg is required")
    return psycopg.connect(**DB,autocommit=True)

def init_schema():
    with conn().cursor() as c: c.execute(SCHEMA)

def clean(v):
    return re.sub(r"[\\s\\-./\\()\\[\\]]+","_",str(v or "").strip()).upper().strip("_") or "UNKNOWN"

def rows_csv(path):
    last=None
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try:
            with path.open("r",encoding=enc,newline="") as f:
                r=csv.reader(f); raw=next(r); seen={}; heads=[]
                for h in raw:
                    b=clean(h); seen[b]=seen.get(b,0)+1; heads.append(b if seen[b]==1 else f"{b}_{seen[b]}")
                for row in r:
                    vals=list(row)+[""]*max(0,len(heads)-len(row))
                    yield {heads[i]:vals[i].strip() for i in range(len(heads))}
            return
        except UnicodeDecodeError as e: last=e
    raise UnicodeError(str(last))

def ident(row):
    def p(*names):
        for n in names:
            for k,v in row.items():
                if clean(k)==clean(n) and str(v).strip(): return str(v).strip()
        return None
    return p("MMSI","ID_MMSI"),p("IMO","ID_IMO"),p("CALL_SIGN","CALLSIGN","ID_CALLSIGN"),p("VESSEL_NAME","NAME")

def status(source,folder,count,error=None):
    with conn().cursor() as c:
        c.execute("""INSERT INTO reference_status(source,source_folder,record_count,last_update,status,error)
        VALUES(%s,%s,%s,now(),%s,%s) ON CONFLICT(source) DO UPDATE SET
        source_folder=EXCLUDED.source_folder,record_count=EXCLUDED.record_count,
        last_update=now(),status=EXCLUDED.status,error=EXCLUDED.error""",
        (source,str(folder),count,"ERROR" if error else "READY",error))

def import_csv(source,folder):
    files=sorted(folder.rglob("*.csv"))
    if not files: raise ValueError("No CSV files found")
    total=0
    with conn().cursor() as c:
        c.execute("DELETE FROM reference_records WHERE source=%s",(source,))
        for path in files:
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            for row in rows_csv(path):
                mmsi,imo,call,name=ident(row)
                if source=="NSC":
                    row["SOURCE_REGION"]="EAST" if "EAST" in path.name.upper() or "EAST" in str(path.parent).upper() else "WEST" if "WEST" in path.name.upper() or "WEST" in str(path.parent).upper() else "UNKNOWN"
                entity=row.get("VESSEL_ID") or mmsi or imo or call or name or f"{path}:{total}"
                c.execute("""INSERT INTO reference_records
                (source,dataset,entity_key,identity_mmsi,identity_imo,identity_callsign,identity_name,payload,source_file,source_hash)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                (source,path.stem,str(entity),mmsi,imo,call,name,json.dumps(row,ensure_ascii=False),str(path),digest))
                total+=1
    status(source,folder,total); return total

def flatten_xml(e,out=None):
    out=out or {}; tag=e.tag.split("}")[-1]
    if e.text and e.text.strip(): out[tag]=e.text.strip()
    for child in e: flatten_xml(child,out)
    return out

def import_pans(folder):
    files=sorted(folder.rglob("*.xml"))
    if not files: raise ValueError("No PANS XML files found")
    mapping={"VesselProfile":"pans_vespro","VoyageRegistration":"pans_calinf","VesselCallNumber":"pans_calinv","BerthManagement":"pans_berman"}
    total=0
    with conn().cursor() as c:
        c.execute("DELETE FROM reference_records WHERE source='PANS'")
        for path in files:
            root=ET.parse(path).getroot(); ds=mapping.get(root.tag.split("}")[-1])
            if not ds: continue
            row=flatten_xml(root); mmsi,imo,call,name=ident(row); entity=row.get("VCN") or mmsi or imo or call or name or str(path)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            c.execute("""INSERT INTO reference_records
            (source,dataset,entity_key,identity_mmsi,identity_imo,identity_callsign,identity_name,payload,source_file,source_hash)
            VALUES('PANS',%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
            (ds,str(entity),mmsi,imo,call,name,json.dumps(row,ensure_ascii=False),str(path),digest)); total+=1
    status("PANS",folder,total); return total

def import_unlocode(folder):
    files=sorted(folder.rglob("*.csv"))
    if not files: raise ValueError("No UN/LOCODE CSV files found")
    total=0
    with conn().cursor() as c:
        c.execute("DELETE FROM unlocode_records")
        for path in files:
            for row in rows_csv(path):
                country=row.get("COUNTRY","").strip(); loc=row.get("LOCATION","").strip()
                name=row.get("NAME","").strip()
                if not country or not loc or not name: continue
                code=(country+loc).replace(" ","").upper()
                c.execute("""INSERT INTO unlocode_records(code,country,location,name,payload,updated_at)
                VALUES(%s,%s,%s,%s,%s::jsonb,now()) ON CONFLICT(code) DO UPDATE SET
                country=EXCLUDED.country,location=EXCLUDED.location,name=EXCLUDED.name,payload=EXCLUDED.payload,updated_at=now()""",
                (code,country,loc,name,json.dumps(row,ensure_ascii=False))); total+=1
    status("UNLOCODE",folder,total); return total

def import_reference(source,folder):
    source=source.upper(); folder=Path(folder).expanduser().resolve()
    if not folder.is_dir(): raise ValueError("Folder does not exist: "+str(folder))
    if source=="WRS":
        names={p.name.casefold():p for p in folder.iterdir() if p.is_dir()}
        datasets=names.get("datasets")
        decode=names.get("decode") or names.get("decode files")
        if not datasets or not decode:
            raise ValueError("WRS source must contain Datasets and Decode/Decode Files folders")
        return import_csv("WRS",folder)
    if source=="NSC":
        files=list(folder.rglob("*.csv"))
        east=any("EAST" in p.name.upper() or "EAST" in str(p.parent).upper() for p in files)
        west=any("WEST" in p.name.upper() or "WEST" in str(p.parent).upper() for p in files)
        if not east or not west:
            raise ValueError("NSC source must contain both EAST and WEST CSV data")
        return import_csv("NSC",folder)
    if source=="PANS": return import_pans(folder)
    if source=="UNLOCODE": return import_unlocode(folder)
    raise ValueError("Unsupported reference source: "+source)

def pid_alive(pid):
    if os.name=="nt":
        r=subprocess.run(["tasklist","/FI",f"PID eq {pid}","/NH"],capture_output=True,text=True); return str(pid) in r.stdout
    try: os.kill(pid,0); return True
    except OSError: return False

def start_feed(name):
    script=SCRIPTS/FEEDS[name]; log=(RUNTIME/"logs"/f"{name}.launcher.log").open("a",encoding="utf-8")
    env=os.environ.copy(); env["VALIDATION_HOME"]=str(ROOT); env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH","")
    if os.name=="nt": p=subprocess.Popen([sys.executable,str(script)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else: p=subprocess.Popen([sys.executable,str(script)],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True)
    (PIDS/f"{name}.pid").write_text(str(p.pid),encoding="utf-8"); return p.pid

def stop_feed(name):
    f=PIDS/f"{name}.pid"
    if not f.exists(): return False
    pid=int(f.read_text().strip())
    if pid_alive(pid):
        if os.name=="nt": subprocess.run(["taskkill","/PID",str(pid),"/T","/F"],capture_output=True)
        else: os.kill(pid,signal.SIGTERM)
    f.unlink(missing_ok=True); return True

def service_status():
    out={}
    for p in STATUS.glob("*.json"):
        try: out[p.stem]=json.loads(p.read_text(encoding="utf-8"))
        except Exception: pass
    return out

PAGE="""<!doctype html><html><head><meta charset=utf-8><title>Validation</title>
<style>body{font-family:Arial;background:#111;color:#eee;margin:0}header{padding:18px 24px;background:#181818}nav a{color:#9cf;margin-right:20px}main{padding:24px;max-width:1200px;margin:auto}.card{background:#191919;border:1px solid #333;border-radius:10px;padding:18px;margin:12px 0}.ok{color:#6d9}.bad{color:#f77}button,input,select{padding:7px;margin:4px;background:#111;color:#eee;border:1px solid #555}table{width:100%;border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #333;text-align:left}</style>
</head><body><header><b>VALIDATION</b> &nbsp; <nav><a href="/">Overview</a><a href="/router">Data Router</a><a href="/parser">Data Parser</a><a href="/forwarder">Data Forwarder</a><a href="/reference">Reference DB</a></nav></header><main>{}</main></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def page(self,body,code=200):
        raw=PAGE.replace("{}",body).encode(); self.send_response(code); self.send_header("Content-Type","text/html"); self.end_headers(); self.wfile.write(raw)
    def log_message(self,*a): pass
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query); path=u.path
        if path=="/":
            st=service_status(); body="<div class='card'><h2>Overview</h2>"
            for n in FEEDS:
                s=st.get(n,{}).get("status","STOPPED"); cls="ok" if s=="RUNNING" else "bad"
                body+=f"<p><b>{n}</b> <span class='{cls}'>{html.escape(s)}</span> <button onclick=\"fetch('/api/start?name={n}').then(()=>location.reload())\">Start</button><button onclick=\"fetch('/api/stop?name={n}').then(()=>location.reload())\">Stop</button></p>"
            body+="</div>"
            try:
                with conn().cursor() as c:
                    c.execute("SELECT source,status,record_count,last_update FROM reference_status ORDER BY source"); rows=c.fetchall()
                body+="<div class='card'><h2>Reference DB</h2><table><tr><th>Source</th><th>Status</th><th>Records</th><th>Last Update</th></tr>"
                for r in rows: body+=f"<tr><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>"
                body+="</table></div>"
            except Exception as e: body+="<div class='card bad'>PostgreSQL unavailable: "+html.escape(str(e))+"</div>"
            return self.page(body)
        if path in ("/router","/parser","/forwarder"):
            return self.page("<div class='card'><h2>"+html.escape(path[1:].title())+"</h2><p>Each source is an independent Python process. Runtime status is local JSON.</p></div>")
        if path=="/reference":
            return self.page("""<div class='card'><h2>Reference DB</h2>
            <form action='/api/import'><select name='source'><option>WRS</option><option>PANS</option><option>NSC</option><option>UNLOCODE</option></select>
            <input name='folder' size=70 placeholder='Source folder' required><button>Update</button></form></div>""")
        if path=="/api/start":
            name=q.get("name",[""])[0]
            if name in FEEDS: start_feed(name)
            return self.page("<div class='card ok'>Started.</div>")
        if path=="/api/stop":
            name=q.get("name",[""])[0]
            if name in FEEDS: stop_feed(name)
            return self.page("<div class='card ok'>Stopped.</div>")
        if path=="/api/import":
            try:
                n=import_reference(q.get("source",[""])[0],q.get("folder",[""])[0])
                return self.page(f"<div class='card ok'>Updated {html.escape(q.get('source',[''])[0])}: {n} records.</div>")
            except Exception as e:
                return self.page("<div class='card bad'>Update failed: "+html.escape(str(e))+"</div>",500)
        return self.page("<div class='card bad'>Not found</div>",404)

def main():
    ensure_dirs(); start_postgres(); init_schema()
    print(f"Validation console: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()

if __name__=="__main__": main()
