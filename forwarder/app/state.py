from __future__ import annotations
import threading
from datetime import datetime,timezone
from pathlib import Path
from shared.storage.rocksdb_store import RocksDBStore
class DeliveryState:
 def __init__(self,path:Path):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._lock=threading.RLock();self._db=RocksDBStore(self.path)
 @staticmethod
 def _now():return datetime.now(timezone.utc).isoformat()
 def get(self,output_id,destination):return self._db.get("deliveries",f"{output_id}|{destination}")
 def ensure(self,output_id,destination,sha256,filename):
  k=f"{output_id}|{destination}";r=self._db.get("deliveries",k) or {};n=self._now();r.update({"output_id":output_id,"destination":destination,"sha256":sha256,"filename":filename,"state":r.get("state","PENDING"),"attempts":r.get("attempts",0),"last_error":r.get("last_error"),"created_at":r.get("created_at",n),"updated_at":n,"delivered_at":r.get("delivered_at")});self._db.put("deliveries",k,r)
 def mark(self,output_id,destination,state,attempts=None,error=None):
  k=f"{output_id}|{destination}";r=self._db.get("deliveries",k) or {};n=self._now();r.update({"state":state,"attempts":r.get("attempts",0) if attempts is None else attempts,"last_error":None if state=="DELIVERED" else error,"updated_at":n});r["delivered_at"]=n if state=="DELIVERED" else r.get("delivered_at");self._db.put("deliveries",k,r)
 def counts(self):
  o={}
  for _,v in self._db.scan("deliveries"):
   if v:o[v.get("state")]=o.get(v.get("state"),0)+1
  return o
 def recent(self,limit=20):
  rows=[v for _,v in self._db.scan("deliveries") if v];rows.sort(key=lambda x:x.get("updated_at",""),reverse=True);return[{k:r.get(k) for k in ("output_id","destination","filename","state","attempts","last_error","updated_at")} for r in rows[:int(limit)]]
