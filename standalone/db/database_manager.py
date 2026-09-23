#!/usr/bin/env python3
from __future__ import annotations
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import psycopg

ROOT=Path(__file__).resolve().parents[2]
STATUS_DIR=ROOT/'runtime'/'status'; STATUS_DIR.mkdir(parents=True,exist_ok=True)
DB=dict(host='127.0.0.1',port=5432,dbname='validation',user='validation',password=os.environ.get('VALIDATION_DB_PASSWORD','CHANGE_ME'))

def db_status():
    try:
        with psycopg.connect(**DB) as con, con.cursor() as cur:
            cur.execute('SELECT current_database()'); db=cur.fetchone()[0]
            cur.execute('SELECT dataset_code,status,record_count,last_update FROM validation.reference_status ORDER BY dataset_code')
            refs=[dict(dataset=a,status=b,records=n,last_update=str(u) if u else None) for a,b,n,u in cur.fetchall()]
            return {'ready':True,'database':db,'references':refs}
    except Exception as e: return {'ready':False,'error':str(e)}

def runtime_status():
    out={}
    for p in STATUS_DIR.glob('*.json'):
        try: out[p.stem]=json.loads(p.read_text(encoding='utf-8'))
        except Exception: pass
    return out

PAGE='''<!doctype html><html><head><meta charset="utf-8"><title>Validation</title><style>body{font-family:Segoe UI,Arial;background:#080b0d;color:#e9eef1;margin:28px}pre{background:#11171b;padding:14px;border-radius:6px}</style></head><body><h1>Validation Operator Console</h1><p>Overview · Data Router · Data Parser · Data Forwarder · Reference DB</p><h2>PostgreSQL</h2><pre id="db"></pre><h2>Runtime</h2><pre id="rt"></pre><script>async function r(){const x=await fetch('/api/status').then(z=>z.json());db.textContent=JSON.stringify(x.database,null,2);rt.textContent=JSON.stringify(x.runtime,null,2)}setInterval(r,3000);r()</script></body></html>'''
class H(BaseHTTPRequestHandler):
 def out(self,o,code=200,ctype='application/json'):
  b=(json.dumps(o,default=str) if ctype.startswith('application/json') else o).encode(); self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
 def do_GET(self):
  p=self.path.split('?',1)[0]
  if p=='/api/status': return self.out({'database':db_status(),'runtime':runtime_status()})
  if p in ('/','/index.html'): return self.out(PAGE,ctype='text/html')
  return self.out({'error':'not found'},404)
 def log_message(self,*a): pass
if __name__=='__main__': ThreadingHTTPServer(('127.0.0.1',8090),H).serve_forever()
