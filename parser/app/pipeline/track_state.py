from __future__ import annotations
import threading
from datetime import datetime,timezone
from pathlib import Path
from typing import Any,Optional
from shared.storage.rocksdb_store import RocksDBStore
ACTIVE_THRESHOLD_SECONDS=3*3600
MMSI_REFERENCE_FIELDS=("ais.lenToBow","ais.lenToStern","ais.navStatus","ais.typeAndCargo","ais.widthToPort","ais.widthToStarboard","cat.annotation","cat.category","cat.identity","foreign.track.number","id.callsign","id.imo","id.mmsi","id.mmsi.destination","vessel.beam","vessel.description","vessel.draft","vessel.grosstonnage","vessel.length","vessel.name","voyage.arrival","voyage.departure","voyage.destination","voyage.eta","voyage.etd","voyage.origin")
def _find_default_state_db():return Path(__file__).resolve().parents[2]/"state"/"track_state"
class TrackStateDB:
 def __init__(self,db_path:Optional[Path]=None):self.path=Path(db_path or _find_default_state_db());self.path.parent.mkdir(parents=True,exist_ok=True);self._lock=threading.RLock();self._db=RocksDBStore(self.path)
 def upsert(self,mmsi,imo,vessel_name,latitude,longitude,tx_timestamp_iso,source,reference_values=None):
  now=datetime.now(timezone.utc).isoformat();epoch=None
  if tx_timestamp_iso:
   try:epoch=_iso_to_epoch_s(tx_timestamp_iso)
   except Exception:pass
  old=self._db.get("track",str(int(mmsi))) or {};old.update({"mmsi":int(mmsi),"imo":imo if imo is not None else old.get("imo"),"vessel_name":vessel_name if vessel_name else old.get("vessel_name"),"last_latitude":latitude if latitude is not None else old.get("last_latitude"),"last_longitude":longitude if longitude is not None else old.get("last_longitude"),"last_tx_iso":str(tx_timestamp_iso or now),"last_tx_epoch_s":epoch,"source":source,"updated_at":now});self._db.put("track",str(int(mmsi)),old)
  if reference_values is not None:
   merged=self._db.get("reference",str(int(mmsi))) or {};vals=merged.get("values",{}) if isinstance(merged,dict) else {};vals.update({k:v for k,v in reference_values.items() if k in MMSI_REFERENCE_FIELDS and v not in(None,"")});self._db.put("reference",str(int(mmsi)),{"mmsi":int(mmsi),"values":vals,"last_tx_iso":str(tx_timestamp_iso or now),"last_source":source,"updated_at":now})
  if epoch is None:return True
  return int(datetime.now(timezone.utc).timestamp())-epoch<ACTIVE_THRESHOLD_SECONDS
 def get_reference(self,mmsi):return(self._db.get("reference",str(int(mmsi))) or {}).get("values",{})
 def reference_count(self):return sum(1 for _ in self._db.scan("reference"))
 def get_reference_metadata(self,mmsi):
  v=self._db.get("reference",str(int(mmsi)));return None if not v else {k:v.get(k) for k in ("mmsi","last_tx_iso","last_source","updated_at")}
 def is_active(self,mmsi):
  v=self._db.get("track",str(int(mmsi)));e=None if not v else v.get("last_tx_epoch_s");return bool(e is not None and int(datetime.now(timezone.utc).timestamp())-e<ACTIVE_THRESHOLD_SECONDS)
 def get_track(self,mmsi):return self._db.get("track",str(int(mmsi)))
 def close(self):self._db.close()
def _iso_to_epoch_s(v):
 if v is None:raise ValueError("Timestamp is None")
 if isinstance(v,(int,float)):i=int(v);return i//1000 if i>=100000000000 else i
 s=str(v).strip()
 try:i=int(float(s));return i//1000 if i>=100000000000 else i
 except:pass
 x=s.replace("Z","+00:00");dt=datetime.fromisoformat(x);return int((dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp())
