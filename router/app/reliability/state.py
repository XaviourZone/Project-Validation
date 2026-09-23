from __future__ import annotations
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional
from ..utils.time import now_iso
from shared.storage.rocksdb_store import RocksDBStore
class FileState(str,Enum):
 DISCOVERED="DISCOVERED"; WAITING_FOR_STABILITY="WAITING_FOR_STABILITY"; READY="READY"; QUEUED="QUEUED"; SENDING="SENDING"; ACKNOWLEDGED="ACKNOWLEDGED"; PROCESSED="PROCESSED"; RETRYING="RETRYING"; FAILED="FAILED"
@dataclass
class RouterFileState:
 source:str; filename:str; file_path:str; file_size:int; mtime:float; file_hash:str; message_id:str; status:FileState; attempt_count:int; first_seen:str; last_attempt:Optional[str]=None; acknowledged_at:Optional[str]=None; destination:Optional[str]=None; last_error:Optional[str]=None
class FileStateStore:
 def __init__(self,db_path:Path): self.db_path=Path(db_path); self.db_path.parent.mkdir(parents=True,exist_ok=True); self._lock=threading.RLock(); self._db=RocksDBStore(self.db_path)
 def _key(self,s,f,h): return f"{s}|{f}|{h}"
 def _state(self,v):
  if not v:return None
  v=dict(v);v["status"]=FileState(v["status"]);return RouterFileState(**v)
 def _put(self,s): self._db.put("file_states",self._key(s.source,s.filename,s.file_hash),{**s.__dict__,"status":s.status.value});self._db.put("message_index",s.message_id,self._key(s.source,s.filename,s.file_hash))
 def get_state(self,source,filename,file_hash): return self._state(self._db.get("file_states",self._key(source,filename,file_hash)))
 def get_by_message_id(self,message_id):
  k=self._db.get("message_index",message_id);return self._state(self._db.get("file_states",k)) if k else None
 def is_already_processed(self,source,filename,file_hash):
  s=self.get_state(source,filename,file_hash);return bool(s and s.status in (FileState.PROCESSED,FileState.ACKNOWLEDGED))
 def is_in_flight_or_processed(self,source,filename,file_hash):
  s=self.get_state(source,filename,file_hash);return bool(s and s.status in (FileState.READY,FileState.QUEUED,FileState.SENDING,FileState.ACKNOWLEDGED,FileState.PROCESSED,FileState.RETRYING,FileState.FAILED))
 def record_discovered(self,source,filename,file_path,file_size,mtime,file_hash,message_id,status=FileState.DISCOVERED):
  old=self.get_state(source,filename,file_hash);now=old.first_seen if old else now_iso();s=RouterFileState(source,filename,str(file_path),int(file_size),float(mtime),file_hash,message_id,status,old.attempt_count if old else 0,now,old.last_attempt if old else None,old.acknowledged_at if old else None,old.destination if old else None,old.last_error if old else None);self._put(s);return s
 def update_status(self,message_id,status,error=None,destination=None):
  s=self.get_by_message_id(message_id)
  if not s:return
  now=now_iso();s.status=status
  if status in (FileState.ACKNOWLEDGED,FileState.PROCESSED):s.acknowledged_at=now;s.last_error=None
  elif status==FileState.QUEUED:s.destination=destination
  elif status in (FileState.RETRYING,FileState.FAILED,FileState.DISCOVERED):s.last_error=error;s.last_attempt=now
  self._put(s)
 def increment_attempt(self,message_id,error=None):
  s=self.get_by_message_id(message_id)
  if not s:return 1
  s.attempt_count+=1;s.last_attempt=now_iso();s.last_error=error;self._put(s);return s.attempt_count
 def get_incomplete_records(self)->List[RouterFileState]: return [self._state(v) for _,v in self._db.scan("file_states") if v and v.get("status") in {FileState.READY.value,FileState.QUEUED.value,FileState.SENDING.value,FileState.RETRYING.value}]
 def reset_interrupted_states(self):
  n=0
  for _,v in list(self._db.scan("file_states")):
   if v and v.get("status") in {FileState.READY.value,FileState.QUEUED.value,FileState.SENDING.value,FileState.RETRYING.value}:v["status"]=FileState.DISCOVERED.value;self._db.put("file_states",self._key(v["source"],v["filename"],v["file_hash"]),v);n+=1
  return n
 def get_stats(self):
  out={}
  for _,v in self._db.scan("file_states"):
   if v:out[v["status"]]=out.get(v["status"],0)+1
  return out
