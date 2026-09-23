"""PostgreSQL adapter used by standalone Validation feeds."""
from __future__ import annotations
import re
import threading
try:
    import psycopg
except ImportError:
    psycopg = None
from parser.app.pipeline.reference_db import VesselContext
from parser.app.models.common import CommonVesselRecord

def _text(v):
    if v is None: return None
    s=str(v).strip()
    return s if s and s.upper() not in {"NONE","NULL","N/A","-"} else None

def _int(v):
    try: return None if v in (None,"") else int(float(str(v).strip()))
    except (TypeError,ValueError): return None

def _float(v):
    try: return None if v in (None,"") else float(str(v).strip())
    except (TypeError,ValueError): return None

def _key(v): return re.sub(r"[^A-Z0-9]","",str(v or "").upper())

def _pick(row,*names):
    wanted={_key(x) for x in names}
    for k,v in row.items():
        if _key(k) in wanted and _text(v) is not None: return v
    return None

class PostgresReferenceDB:
    def __init__(self,cfg):
        if psycopg is None: raise RuntimeError("psycopg is required")
        self.conn=psycopg.connect(**{k:v for k,v in cfg.items() if k in {"host","port","dbname","user","password"}},autocommit=True)
        self.lock=threading.RLock(); self.cache={}; self.cache_max=8192

    def _rows(self,mmsi,imo,callsign,name):
        clauses=[]; params=[]
        if mmsi: clauses.append("identity_mmsi=%s"); params.append(str(mmsi))
        if imo: clauses.append("identity_imo=%s"); params.append(str(imo))
        if callsign: clauses.append("UPPER(identity_callsign)=UPPER(%s)"); params.append(str(callsign).strip())
        if name: clauses.append("UPPER(identity_name)=UPPER(%s)"); params.append(str(name).strip())
        if not clauses: return []
        with self.conn.cursor() as c:
            c.execute("SELECT source,dataset,entity_key,payload FROM reference_records WHERE "+" OR ".join(clauses),params)
            return c.fetchall()

    def _related(self,keys):
        if not keys: return []
        with self.conn.cursor() as c:
            c.execute("SELECT source,dataset,entity_key,payload FROM reference_records WHERE entity_key=ANY(%s)",(list(keys),))
            return c.fetchall()

    def resolve(self,mmsi=None,imo=None,callsign=None,vessel_name=None):
        ck=(_int(mmsi),_int(imo),(str(callsign).strip().upper() if callsign else None),(str(vessel_name).strip().upper() if vessel_name else None))
        with self.lock:
            if ck in self.cache: return self.cache[ck]
            rows=self._rows(*ck)
            if not rows:
                ctx=VesselContext(); self.cache[ck]=ctx; return ctx
            keys={str(r[2]) for r in rows if r[2]}
            if len(keys)>1:
                # Exact identity ambiguity is rejected rather than guessed.
                return VesselContext()
            rows += self._related(keys)
            ctx=VesselContext()
            for source,dataset,entity,payload in rows:
                p=dict(payload or {}); src=str(source).upper(); ds=str(dataset).lower()
                if src=="WRS": self._wrs(ctx,p,entity,ds)
                elif src=="PANS": self._pans(ctx,p,ds)
                elif src=="NSC": self._nsc(ctx,p)
            self.cache[ck]=ctx
            if len(self.cache)>self.cache_max: self.cache.pop(next(iter(self.cache)))
            return ctx

    def _wrs(self,c,p,e,ds):
        if "vessels" in ds:
            c.wrs_matched=True; c.wrs_match_method="REFERENCE"
            c.wrs_vessel_id=_text(_pick(p,"VESSEL_ID")) or _text(e)
            c.wrs_imo=_int(_pick(p,"IMO","ID_IMO")); c.wrs_mmsi=_int(_pick(p,"MMSI","ID_MMSI"))
            c.wrs_vessel_name=_text(_pick(p,"VESSEL_NAME","NAME")); c.wrs_callsign=_text(_pick(p,"CALL_SIGN","CALLSIGN","ID_CALLSIGN"))
            c.wrs_vessel_type=_text(_pick(p,"VESSEL_TYPE","TYPE")); c.wrs_status=_text(_pick(p,"STATUS"))
            c.wrs_gross=_float(_pick(p,"GROSS","GRT","GROSS_TONNAGE"))
        if "dimension" in ds:
            c.wrs_loa=_float(_pick(p,"LOA","LENGTH")); c.wrs_breadth=_float(_pick(p,"BREADTH_EXTREME","BREADTH","BEAM","WIDTH")); c.wrs_draft=_float(_pick(p,"DRAFT","DRAUGHT"))
        if "vigilance" in ds: c.wrs_vigilance_score=_float(_pick(p,"SCORE","VIGILANCE_SCORE"))
        if "calling" in ds:
            c.wrs_calling_place=_text(_pick(p,"PLACE","DESTINATION")); c.wrs_calling_arrival=_text(_pick(p,"ARRIVAL_DATE","ARRIVAL")); c.wrs_calling_sailing=_text(_pick(p,"SAILING_DATE","DEPARTURE"))
        if "type_cargo" in ds or "ais_type" in ds: c.wrs_ais_type_code=_int(_pick(p,"ID","TYPE_ID","AIS_TYPE"))
        if "status" in ds: c.wrs_status_decode=_text(_pick(p,"STATUS_DECODE","DESCRIPTION"))

    def _pans(self,c,p,ds):
        if "vespro" in ds:
            c.pans_matched=True; c.pans_match_method="REFERENCE"
            c.pans_vessel_name=_text(_pick(p,"VesselName","VESSEL_NAME","NAME")); c.pans_callsign=_text(_pick(p,"CallSign","CALLSIGN","CALL_SIGN"))
            c.pans_beam=_float(_pick(p,"Beam","BEAM")); c.pans_loa=_float(_pick(p,"LOA","Length","LENGTH")); c.pans_max_draft=_float(_pick(p,"MaxDraft","MAX_DRAFT","DRAFT"))
            c.pans_grt=_float(_pick(p,"GRT","GrossTonnage","GROSS")); c.pans_vessel_type=_text(_pick(p,"VesselType","VESSEL_TYPE","TYPE"))
            c.pans_mmsi=_text(_pick(p,"MMSI","ID_MMSI")); c.pans_imo=_int(_pick(p,"IMO","ID_IMO"))
        elif "calinf" in ds or "calinv" in ds:
            c.pans_matched=True; c.pans_match_method="REFERENCE"
            c.pans_org_dep=_text(_pick(p,"Origin","OriginDeparture","ORG_DEP")); c.pans_lpc=_text(_pick(p,"LastPortOfCall","LPC")); c.pans_npc=_text(_pick(p,"NextPortOfCall","NPC"))
            c.pans_eta=_text(_pick(p,"ETA")); c.pans_etd=_text(_pick(p,"ETD"))
        elif "berman" in ds:
            c.pans_matched=True; c.pans_match_method="REFERENCE"
            c.pans_berman_dest=_text(_pick(p,"Destination","DESTINATION")); c.pans_berman_lpc=_text(_pick(p,"LastPortOfCall","LPC"))
            c.pans_berman_eta=_text(_pick(p,"ETA")); c.pans_berman_etd=_text(_pick(p,"ETD")); c.pans_draft_fwd=_float(_pick(p,"DraftFwd","DRAFT_FWD")); c.pans_draft_aft=_float(_pick(p,"DraftAft","DRAFT_AFT"))
            c.pans_vcn=_text(_pick(p,"VCN")); c.pans_cargo_description=_text(_pick(p,"CargoDescription","CARGO_DESCRIPTION")); c.pans_cargo_tonnage=_float(_pick(p,"TotalCargoTonnage","CARGO_TONNAGE")); c.pans_hazardous=_text(_pick(p,"HazCargoOnBoard","HAZARDOUS"))

    def _nsc(self,c,p):
        c.nsc_matched=True; c.nsc_match_method="REFERENCE"
        c.nsc_vessel_name=_text(_pick(p,"VESSEL_NAME","NAME")); c.nsc_imo=_int(_pick(p,"ID_IMO","IMO")); c.nsc_mmsi=_int(_pick(p,"ID_MMSI","MMSI"))
        c.nsc_callsign=_text(_pick(p,"ID_CALLSIGN","CALLSIGN","CALL_SIGN")); c.nsc_type=_text(_pick(p,"TYPE","VESSEL_TYPE")); c.nsc_region=_text(_pick(p,"SOURCE_REGION","REGION"))
        c.nsc_begin_date=_text(_pick(p,"BEGIN_DATE")); c.nsc_end_date=_text(_pick(p,"END_DATE"))

    def close(self):
        try: self.conn.close()
        except Exception: pass

class PostgresLiveDB:
    def __init__(self,cfg):
        if psycopg is None: raise RuntimeError("psycopg is required")
        self.conn=psycopg.connect(**{k:v for k,v in cfg.items() if k in {"host","port","dbname","user","password"}},autocommit=True)
    def upsert_record(self,source,rec:CommonVesselRecord):
        sql="""INSERT INTO live_vessels
        (source_id,mmsi,imo,callsign,vessel_name,latitude,longitude,sog,cog,heading,nav_status,vessel_type,destination,eta,length_m,beam_m,draft_m,source_timestamp,updated_at,xml_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),'GENERATED')
        ON CONFLICT(source_id,mmsi) DO UPDATE SET imo=EXCLUDED.imo,callsign=EXCLUDED.callsign,vessel_name=EXCLUDED.vessel_name,latitude=EXCLUDED.latitude,longitude=EXCLUDED.longitude,sog=EXCLUDED.sog,cog=EXCLUDED.cog,heading=EXCLUDED.heading,nav_status=EXCLUDED.nav_status,vessel_type=EXCLUDED.vessel_type,destination=EXCLUDED.destination,eta=EXCLUDED.eta,length_m=EXCLUDED.length_m,beam_m=EXCLUDED.beam_m,draft_m=EXCLUDED.draft_m,source_timestamp=EXCLUDED.source_timestamp,updated_at=now(),xml_status='GENERATED'"""
        with self.conn.cursor() as c:
            c.execute(sql,(source,rec.mmsi,rec.imo,rec.callsign,rec.vessel_name,rec.latitude,rec.longitude,rec.sog,rec.cog,rec.true_heading,rec.nav_status,rec.vessel_type,rec.destination,rec.eta,rec.length,rec.width,rec.draught,rec.timestamp))
    def close(self):
        try: self.conn.close()
        except Exception: pass
