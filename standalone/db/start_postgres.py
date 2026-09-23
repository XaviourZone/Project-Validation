#!/usr/bin/env python3
from __future__ import annotations
import json,shutil,subprocess,time
from pathlib import Path
import socket
CFG=Path(__file__).with_name("config.json")
def cfg():
    x=json.loads(CFG.read_text(encoding="utf-8"));x.setdefault("pg_ctl","");x.setdefault("pg_data","");return x
def open_port(host,port):
    try:
        with socket.create_connection((host,int(port)),timeout=1):return True
    except:return False
def main():
    c=cfg();host=c.get("host","127.0.0.1");port=int(c.get("port",5432))
    if open_port(host,port):print(f"PostgreSQL already reachable at {host}:{port}");return
    pgctl=c.get("pg_ctl") or shutil.which("pg_ctl");data=c.get("pg_data","")
    if not pgctl or not data:raise SystemExit("PostgreSQL is not reachable. Configure pg_ctl and pg_data in db/config.json or start PostgreSQL as an OS service.")
    subprocess.run([pgctl,"-D",data,"-w","start"],check=True)
    for _ in range(30):
        if open_port(host,port):return
        time.sleep(1)
    raise SystemExit("PostgreSQL did not become reachable")
if __name__=="__main__":main()
