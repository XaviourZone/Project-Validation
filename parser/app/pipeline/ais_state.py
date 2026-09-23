from __future__ import annotations
import threading
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Dict,Optional
from shared.storage.rocksdb_store import RocksDBStore
AIS_STATE_FIELDS=("imo","vessel_name","callsign","vessel_type","length","width","draught","destination","eta","nav_status","rot","sog","cog","true_heading","latitude","longitude")
class AISStateDB:
 def __init__(self,db_path:Optional[Path]=None,history_limit:int=100):self.path=Path(db_path or Path(__file__).resolve().parents[2]/"state"/"ais_state");self.path.parent.mkdir(parents=True,exist_ok=True);self.history_limit=max(10,int(history_limit));self._lock=threading.RLock();self._db=RocksDBStore(self.path)
 def merge_record(self,record):
  mmsi=getattr(record,"mmsi",None)
  if not mmsi or not(100000000<=int(mmsi)<=999999999):return record
  mmsi=int(mmsi);mt=getattr(record,"app_message_id",None);now=datetime.now(timezone.utc).isoformat();incoming={f:getattr(record,f,None) for f in AIS_STATE_FIELDS if getattr(record,f,None) not in(None,"")};state=self._db.get("vessel",str(mmsi)) or {}
  if incoming.get("latitude") is not None and incoming.get("longitude") is not None:state.update({"last_position_latitude":incoming["latitude"],"last_position_longitude":incoming["longitude"],"last_position_timestamp":getattr(record,"timestamp",None),"last_position_source":getattr(record,"source",None)})
  state.update(incoming);state.update({"mmsi":mmsi,"last_message_type":int(mt) if mt is not None else state.get("last_message_type"),"last_timestamp":getattr(record,"timestamp",None),"last_source":getattr(record,"source",None),"updated_at":now});self._db.put("vessel",str(mmsi),state)
  if mt is not None:hist=self._db.get("history",str(mmsi)) or [];hist.insert(0,{"mmsi":mmsi,"message_type":int(mt),"timestamp":getattr(record,"timestamp",None),"source":getattr(record,"source",None),"payload":incoming,"updated_at":now});self._db.put("history",str(mmsi),hist[:self.history_limit])
  for f in AIS_STATE_FIELDS:
   if getattr(record,f,None) in(None,"") and f in state:
    try:setattr(record,f,state[f])
    except Exception:pass
  return record
 def get(self,mmsi:int)->Optional[Dict[str,Any]]:return self._db.get("vessel",str(int(mmsi)))
 def recent_messages(self,mmsi:int,limit:int=20):return(self._db.get("history",str(int(mmsi))) or [])[:int(limit)]
 def close(self):self._db.close()
