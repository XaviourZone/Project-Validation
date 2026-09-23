#!/usr/bin/env python3
"""Seed the PostgreSQL configuration tables with the established source IDs and parser mappings."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"feeds"))
from _runtime import db_connect
CFG=json.loads((Path(__file__).resolve().parent/"config.json").read_text(encoding="utf-8"))
sources={1:"SAIS_IOR",2:"SAIS_GLOBAL",3:"MSIS",4:"LRIT",5:"VATMS_EAST",6:"VATMS_WEST",7:"NAIS"}
maps={
1:[("MMSI","id.mmsi","integer"),("IMO","id.imo","integer"),("CALLSIGN","id.callsign","string"),("VESSEL_NAME","vessel.name","string")],
2:[("MMSI","id.mmsi","integer"),("IMO","id.imo","integer"),("CALLSIGN","id.callsign","string"),("VESSEL_NAME","vessel.name","string")],
3:[("mmsi","id.mmsi","integer"),("imo","id.imo","integer"),("callsign","id.callsign","string"),("ship_name","vessel.name","string"),("type_and_cargo","ais.typeAndCargo","AIS type decode")],
4:[("mmsi","id.mmsi","integer"),("imo","id.imo","integer"),("callsign","id.callsign","string"),("vessel_name","vessel.name","string")],
5:[("NMEA MMSI","id.mmsi","integer"),("NMEA IMO","id.imo","integer"),("NMEA callsign","id.callsign","string")],
6:[("TMVTD MMSI","id.mmsi","integer"),("TMVTD IMO","id.imo","integer"),("TMVTD callsign","id.callsign","string")],
7:[("ABVDM MMSI","id.mmsi","integer"),("ABVDM IMO","id.imo","integer"),("ABVDM callsign","id.callsign","string")]
}
with db_connect({"DB_HOST":CFG["host"],"DB_PORT":CFG["port"],"DB_NAME":CFG["database"],"DB_USER":CFG["user"],"DB_PASSWORD":CFG.get("password","")}) as conn:
    for sid,name in sources.items():
        conn.execute("INSERT INTO source(source_id,source_name) VALUES(%s,%s) ON CONFLICT(source_id) DO UPDATE SET source_name=EXCLUDED.source_name",(sid,name))
    for sid,items in maps.items():
        for inp,target,transform in items:
            conn.execute("""INSERT INTO field_mapping(source_id,input_field,target_field,transformation)
                            VALUES(%s,%s,%s,%s)
                            ON CONFLICT(source_id,input_field,target_field) DO UPDATE SET transformation=EXCLUDED.transformation""",
                         (sid,inp,target,transform))
    conn.commit()
print("Default source IDs and mappings seeded.")
