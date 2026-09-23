#!/usr/bin/env python3
"""One-time local PostgreSQL bootstrap. Prompts for the administrator password; nothing is stored in Git."""
from __future__ import annotations
import getpass,json
from pathlib import Path
import psycopg
from psycopg import sql
CFG=Path(__file__).with_name("config.json")
def main():
    c=json.loads(CFG.read_text(encoding="utf-8"))
    host=c["host"];port=int(c["port"]);app_user=c["user"];app_db=c["database"];app_pw=c.get("password","")
    admin=input("PostgreSQL administrator user [postgres]: ").strip() or "postgres"
    admin_pw=getpass.getpass("PostgreSQL administrator password: ")
    with psycopg.connect(host=host,port=port,dbname="postgres",user=admin,password=admin_pw,autocommit=True) as conn:
        exists=conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s",(app_user,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(app_user),sql.Literal(app_pw)))
        elif app_pw:
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(app_user),sql.Literal(app_pw)))
        db=conn.execute("SELECT 1 FROM pg_database WHERE datname=%s",(app_db,)).fetchone()
        if not db:
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(app_db),sql.Identifier(app_user)))
    print(f"PostgreSQL role/database ready: {app_user}/{app_db}")
if __name__=="__main__":main()
