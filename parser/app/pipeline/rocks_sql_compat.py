from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from shared.storage.rocksdb_store import RocksDBStore
class RocksDBReferenceError(Exception):
    """Raised when a reference query is unsupported for the RocksDB adapter."""


@dataclass
class _Row(dict): pass
class RocksCursor:
 def __init__(self,conn):self.conn=conn;self.rows=[];self.i=0
 def execute(self,sql,params=()):self.rows=self.conn._execute(sql,tuple(params or()));self.i=0;return self
 def fetchone(self):
  if self.i>=len(self.rows):return None
  r=self.rows[self.i];self.i+=1;return r
 def fetchall(self):r=self.rows[self.i:];self.i=len(self.rows);return r
class RocksSQLCompatConnection:
 def __init__(self,path:Path,db_name:str):self.path=Path(path);self.db_name=db_name.lower();self.store=RocksDBStore(self.path,create_if_missing=False);self.cache={}
 def cursor(self):return RocksCursor(self)
 def close(self):self.store.close()
 def rows(self,table):
  if table not in self.cache:self.cache[table]=[dict(v) for _,v in self.store.scan(f"{self.db_name}/{table}") if isinstance(v,dict)]
  return list(self.cache[table])
 @staticmethod
 def norm(v):return "" if v is None else str(v).strip()
 def match(self,row,field,op,val):
  a=self.norm(row.get(field));b=self.norm(val)
  if op=="=":return a.upper()==b.upper()
  if op=="LIKE":return re.fullmatch(re.escape(b).replace("%",".*").replace("_","."),a,re.I) is not None
  return False
 def _execute(self,sql,params):
  q=re.sub(r"\s+"," ",sql.strip());m=re.match(r"SELECT (.+?) FROM ([A-Za-z0-9_]+)(?: WHERE (.*?))?(?: ORDER BY ([A-Za-z0-9_]+)(?: (ASC|DESC))?)?(?: LIMIT (\d+))?$",q,re.I)
  if not m:raise RocksDBReferenceError(f"Unsupported reference query: {sql}")
  cols,table,where,order_col,order_dir,limit=m.groups();rows=self.rows(table)
  if where:
   wm=re.match(r"(?:UPPER|LOWER)\(([A-Za-z0-9_]+)\)\s*(=|LIKE)\s*\?",where,re.I) or re.match(r"([A-Za-z0-9_]+)\s*(=|LIKE)\s*\?",where,re.I)
   if not wm:raise RocksDBReferenceError(f"Unsupported WHERE clause: {where}")
   rows=[r for r in rows if self.match(r,wm.group(1),wm.group(2),(params or (None,))[0])]
  if order_col:
   def key(r):
    v=r.get(order_col)
    try:return float(v)
    except:return self.norm(v)
   rows.sort(key=key,reverse=(order_dir or "").upper()=="DESC")
  if limit is not None:rows=rows[:int(limit)]
  if cols.strip()=="*":return[_Row(r) for r in rows]
  selected=[x.strip() for x in cols.split(",")];return[_Row({x:r.get(x) for x in selected}) for r in rows]
