#!/usr/bin/env python3
from __future__ import annotations
import csv,io,json,math,re,time,socket,logging
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from _runtime import db_connect,sha256,ref_rows,unlocode,write_xml,files_in_folder,already_processed,mark_file,get_vessel_state,update_vessel_state

# ================= OPERATOR SETTINGS =================
SOURCE="MSIS"; SOURCE_ID=3
INPUT_MODE="FOLDER"; INPUT_FOLDER=r"./input/MSIS"; FILE_PATTERNS=["*.csv","*.txt","*.nmea","*.log"]
POLL_SECONDS=2; RUN_ONCE=False
TCP_HOST="127.0.0.1"; TCP_PORT=20001
OUTPUT_FOLDER=r"./output/MSIS"
FORWARD_ENABLED=False; FORWARD_HOST="127.0.0.1"; FORWARD_PORT=10001
DB_HOST="127.0.0.1"; DB_PORT=5432; DB_NAME="validation"; DB_USER="validation"; DB_PASSWORD=""
WRS_MATCH=("MMSI","IMO","CALLSIGN","VESSEL_NAME")
PANS_MATCH=("IMO","MMSI","CALLSIGN","VESSEL_NAME")
NSC_MATCH=("MMSI","IMO","CALLSIGN","VESSEL_NAME")
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | MSIS | %(message)s")
log=logging.getLogger(SOURCE)

NAV={0:"UNDER WAY USING ENGINE",1:"ANCHORED",2:"NOT UNDER COMMAND",3:"RESTRICTED MANOEUVRABILITY",4:"CONSTRAINED BY HER DRAUGHT",5:"MOORED",6:"AGROUND",7:"ENGAGED IN FISHING",8:"UNDER WAY SAILING"}
TYPE={20:"WIG",30:"FISHING VESSEL",31:"TOWING VESSEL",32:"TOWING VESSEL WITH LENGTH OF TOW EXCEEDING 200 M OR BREADTH EXCEEDING 25 M",33:"VESSEL ENGAGED IN DREDGING OR UNDERWATER OPERATIONS",34:"VESSEL ENGAGED IN DIVING OPERATIONS",35:"VESSEL ENGAGED IN MILITARY OPERATIONS",36:"SAILING VESSEL",37:"PLEASURE CRAFT",40:"HSC",50:"PILOT VESSEL",51:"SEARCH AND RESCUE VESSEL",52:"TUG",53:"PORT TENDER",54:"VESSEL WITH ANTI-POLLUTION FACILITIES OR EQUIPMENT",55:"LAW ENFORCEMENT VESSEL",58:"MEDICAL TRANSPORT",59:"SHIP ACCORDING TO RR RESOLUTION NO. 18",60:"PASSENGER SHIP",70:"CARGO SHIP",80:"TANKER",90:"OTHER VESSEL"}
CHARSET="@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_ !\"#$%&'()*+,-./0123456789:;<=>?"

def clean(v):
    if v is None:return None
    s=str(v).strip().strip('"')
    return None if not s or s.upper() in ("NONE","NULL","N/A","-","NAN") else s
def num(v,i=False):
    try:
        if clean(v) is None:return None
        x=float(v); return int(x) if i else x
    except:return None
def valid_mmsi(v):
    x=num(v,True);return x if x and 100000000<=x<=999999999 else None
def valid_imo(v):
    x=num(v,True);return x if x and 1000000000<=x<=9999999999 else None
def rad(v):
    x=num(v);return math.radians(x) if x is not None else None
def ms(v):
    x=num(v);return x*0.514444 if x is not None else None
def epoch(v):
    if v is None:return None
    try:
        x=float(v);return int(x if x>1e11 else x*1000)
    except:pass
    try:
        d=datetime.fromisoformat(str(v).replace("Z","+00:00"));d=d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return int(d.timestamp()*1000)
    except:return None

def parse_payload(text):
    out=[]
    for i,row in enumerate(csv.DictReader(io.StringIO(text)),1):
        try:
            out.append({"mmsi":num(row.get("mmsi") or row.get("MMSI"),True),"imo":num(row.get("imo") or row.get("IMO"),True),
            "vessel_name":clean(row.get("ship_name") or row.get("vessel_name") or row.get("name")),
            "callsign":clean(row.get("callsign") or row.get("call_sign")),"latitude":num(row.get("latitude") or row.get("lat")),
            "longitude":num(row.get("longitude") or row.get("lon") or row.get("lng")),"sog":num(row.get("sog") or row.get("speed")),
            "cog":num(row.get("cog") or row.get("course")),"heading":num(row.get("true_heading") or row.get("heading")),
            "nav_status":num(row.get("navigation_status") or row.get("navigatetion_status") or row.get("nav_status"),True),
            "draft":num(row.get("draught") or row.get("draft")),"vessel_type":clean(row.get("type_and_cargo") or row.get("vessel_type") or row.get("type")),
            "destination":clean(row.get("destination") or row.get("voyage_destination")),"eta":clean(row.get("eta") or row.get("ETA")),
            "length":num(row.get("length") or row.get("loa")),"width":num(row.get("width") or row.get("beam")),
            "timestamp":clean(row.get("updated") or row.get("timestamp") or row.get("time"))})
        except Exception as e:log.warning("MSIS row %d rejected: %s",i,e)
    return out

def find(conn,source,table,field,value,order,conn_record=None):
    for method in order:
        f={"MMSI":"MMSI","IMO":"IMO","CALLSIGN":"CALL_SIGN","VESSEL_NAME":"VESSEL_NAME","PANS_IMO":"IMONumber","PANS_MMSI":"MMSINumber","PANS_CALLSIGN":"CallSign","PANS_NAME":"VesselName","NSC_MMSI":"ID_MMSI","NSC_IMO":"ID_IMO","NSC_CALLSIGN":"ID_CALLSIGN","NSC_NAME":"VESSEL_NAME"}[method]
        v=value
        if method=="IMO":v=conn_record.get("id.imo")
        if method=="MMSI":v=conn_record.get("id.mmsi")
        if method=="CALLSIGN":v=conn_record.get("id.callsign")
        if method=="VESSEL_NAME":v=conn_record.get("vessel.name")
        if method=="PANS_IMO":v=conn_record.get("id.imo")
        if method=="PANS_MMSI":v=conn_record.get("id.mmsi")
        if method=="PANS_CALLSIGN":v=conn_record.get("id.callsign")
        if method=="PANS_NAME":v=conn_record.get("vessel.name")
        if method=="NSC_MMSI":v=conn_record.get("id.mmsi")
        if method=="NSC_IMO":v=conn_record.get("id.imo")
        if method=="NSC_CALLSIGN":v=conn_record.get("id.callsign")
        if method=="NSC_NAME":v=conn_record.get("vessel.name")
        if v in (None,""):continue
        rows=ref_rows(conn,source,table,f,v,2)
        if len(rows)==1:return rows[0]["data"],method
        if len(rows)>1:log.warning("Ambiguous %s %s=%s",source,f,v)
    return None,None

def enrich(conn,n):
    wrs,wm=find(conn,"WRS","wrs_datasets_vessels","",None,WRS_MATCH,n)
    pans,pm=find(conn,"PANS","pans_vespro","",None,("PANS_IMO","PANS_MMSI","PANS_CALLSIGN","PANS_NAME"),n)
    nsc,nm=find(conn,"NSC","nsc_vessels","",None,("NSC_MMSI","NSC_IMO","NSC_CALLSIGN","NSC_NAME"),n)
    prov={}
    def setif(k,*vals):
        if n.get(k) in (None,""):
            for source,val in vals:
                if val not in (None,""):
                    n[k]=val;prov[k]={"source":source,"value":val};return
    setif("vessel.name",("NSC",nsc and nsc.get("VESSEL_NAME")),("PANS",pans and pans.get("VesselName")),("WRS",wrs and wrs.get("VESSEL_NAME")))
    setif("id.callsign",("NSC",nsc and nsc.get("ID_CALLSIGN")),("PANS",pans and pans.get("CallSign")),("WRS",wrs and wrs.get("CALL_SIGN")))
    if not valid_imo(n.get("id.imo")):
        for src,val in (("NSC",nsc and nsc.get("ID_IMO")),("PANS",pans and pans.get("IMONumber")),("WRS",wrs and wrs.get("IMO"))):
            if valid_imo(val):n["id.imo"]=valid_imo(val);prov["id.imo"]={"source":src,"value":val};break
    vid=wrs and wrs.get("VESSEL_ID")
    if vid:
        d=ref_rows(conn,"WRS","wrs_datasets_vessel_dimensions","VESSEL_ID",vid,1)
        if d:
            x=d[0]["data"];setif("vessel.length",("WRS",x.get("LOA")));setif("vessel.beam",("WRS",x.get("BREADTH_EXTREME")));setif("vessel.draft",("WRS",x.get("DRAFT")))
        v=ref_rows(conn,"WRS","wrs_datasets_vigilance","VESSEL_ID",vid,1)
        if v:
            score=num(v[0]["data"].get("SCORE"))
            if score is not None:n["id.mmsi.destination"]=int(score);n["cat.identity"]=1 if score<300 else (4 if score>600 else 3)
        c=ref_rows(conn,"WRS","wrs_datasets_callings","VESSEL_ID",vid,1)
        if c:
            x=c[0]["data"];setif("voyage.destination",("WRS",x.get("PLACE")));setif("voyage.arrival",("WRS",x.get("ARRIVAL_DATE")));setif("voyage.departure",("WRS",x.get("SAILING_DATE")))
    setif("vessel.length",("PANS",pans and pans.get("LOA")));setif("vessel.beam",("PANS",pans and pans.get("Beam")));setif("vessel.draft",("PANS",pans and pans.get("MaxDraft")))
    setif("vessel.description",("PANS",pans and pans.get("VesselType")),("NSC",nsc and nsc.get("TYPE")),("WRS",wrs and wrs.get("VESSEL_TYPE")))
    setif("ais.typeAndCargo",("PANS",pans and pans.get("VesselType")),("NSC",nsc and nsc.get("TYPE")),("WRS",wrs and wrs.get("VESSEL_TYPE")))
    if pans:
        rows=ref_rows(conn,"PANS","pans_calinf","IMONumber",pans.get("IMONumber"),1) if pans.get("IMONumber") else []
        if rows:
            x=rows[0]["data"];setif("voyage.origin",("PANS",x.get("OriginalPortOfDep")));setif("voyage.departure",("PANS",x.get("LastPortOfCall")));setif("voyage.destination",("PANS",x.get("DockORTOCode")));setif("voyage.eta",("PANS",x.get("EDTA")));setif("voyage.etd",("PANS",x.get("EDTD")))
        rows=ref_rows(conn,"PANS","pans_berman","IMONumber",pans.get("IMONumber"),1) if pans.get("IMONumber") else []
        if rows:
            x=rows[0]["data"];setif("voyage.destination",("PANS",x.get("DestinationPortl")),("PANS",x.get("Portcode")));setif("voyage.arrival",("PANS",x.get("EDTA")));setif("voyage.etd",("PANS",x.get("EDTD")))
    if n.get("voyage.destination"):n["voyage.destination"]=unlocode(conn,n["voyage.destination"])
    if n.get("id.mmsi"):
        hist=get_vessel_state(conn,n["id.mmsi"])
        for k in ("id.imo","id.callsign","vessel.name","ais.typeAndCargo","vessel.length","vessel.beam","vessel.draft","voyage.destination","voyage.eta","voyage.origin","voyage.arrival","voyage.departure"):
            if n.get(k) in (None,"") and hist.get(k) not in (None,""):n[k]=hist[k]
    remarks=[f"FEED     | SOURCE           : {SOURCE}"]
    if wrs:remarks.append("WRS      | VESSEL_ID        : "+str(wrs.get("VESSEL_ID")))
    if pans:remarks.append("PANS     | VESSEL TYPE      : "+str(pans.get("VesselType") or "UNAVAILABLE"))
    if nsc:remarks.append("NSC      | REGION           : "+str(nsc.get("SOURCE_REGION") or "UNAVAILABLE"))
    n["vessel.remarks"]="\n".join(remarks)
    n["_raw"]={"enrichment_provenance":prov,"matches":{"WRS":wm,"PANS":pm,"NSC":nm}}
    return n

SPECS={"ais.lenToBow":("qv","m"),"ais.lenToStern":("qv","m"),"ais.navStatus":("sv",None),"ais.typeAndCargo":("sv",None),"ais.widthToPort":("qv","m"),"ais.widthToStarboard":("qv","m"),"app.message.id":("sv",None),"cat.annotation":("sv",None),"cat.category":("sv",None),"cat.identity":("sv",None),"foreign.track.number":("sv",None),"id.callsign":("sv",None),"id.imo":("iv",None),"id.mmsi":("iv",None),"id.mmsi.destination":("iv",None),"kinematic.course.true":("qv","rad"),"kinematic.flag.3d":("bv",None),"kinematic.heading.true":("qv","rad"),"kinematic.pos.lla.alt":("qv","m"),"kinematic.pos.lla.lat":("qv","rad"),"kinematic.pos.lla.lon":("qv","rad"),"kinematic.speed":("qv","m/s"),"sys.source.id":("iv",None),"sys.track.number":("iv",None),"timestamp.receipt":("tv",None),"timestamp.source":("tv",None),"track.flag.active":("bv",None),"track.quality":("iv",None),"vessel.beam":("qv","m"),"vessel.description":("sv",None),"vessel.draft":("qv","m"),"vessel.grosstonnage":("qv","t"),"vessel.length":("qv","m"),"vessel.name":("sv",None),"vessel.remarks":("sv",None),"voyage.arrival":("sv",None),"voyage.departure":("sv",None),"voyage.destination":("sv",None),"voyage.eta":("tv",None),"voyage.etd":("tv",None),"voyage.origin":("sv",None)}
def normalize(r):
    return {"ais.lenToBow":None,"ais.lenToStern":None,"ais.navStatus":NAV.get(num(r.get("nav_status"),True),clean(r.get("nav_status"))),"ais.typeAndCargo":TYPE.get(num(r.get("vessel_type"),True),clean(r.get("vessel_type"))),"ais.widthToPort":None,"ais.widthToStarboard":None,"app.message.id":num(r.get("message_type"),True),"cat.annotation":SOURCE,"cat.category":"Surface","cat.identity":"Unknown","foreign.track.number":valid_mmsi(r.get("mmsi")),"id.callsign":clean(r.get("callsign")),"id.imo":valid_imo(r.get("imo")),"id.mmsi":valid_mmsi(r.get("mmsi")),"id.mmsi.destination":None,"kinematic.course.true":rad(r.get("cog")),"kinematic.flag.3d":False,"kinematic.heading.true":rad(r.get("heading")),"kinematic.pos.lla.alt":None,"kinematic.pos.lla.lat":rad(r.get("latitude")),"kinematic.pos.lla.lon":rad(r.get("longitude")),"kinematic.speed":ms(r.get("sog")),"sys.source.id":SOURCE_ID,"sys.track.number":valid_mmsi(r.get("mmsi")),"timestamp.receipt":int(time.time()*1000),"timestamp.source":epoch(r.get("timestamp")),"track.flag.active":True,"track.quality":15,"vessel.beam":num(r.get("width")),"vessel.description":None,"vessel.draft":num(r.get("draft")),"vessel.grosstonnage":None,"vessel.length":num(r.get("length")),"vessel.name":clean(r.get("vessel_name")),"vessel.remarks":None,"voyage.arrival":None,"voyage.departure":None,"voyage.destination":clean(r.get("destination")),"voyage.eta":r.get("eta"),"voyage.etd":None,"voyage.origin":None}

def xmlval(tag,v):
    if v is None or (isinstance(v,str) and not v.strip()):return None
    if tag=="bv":return "true" if bool(v) else "false"
    if tag=="iv":
        try:return str(int(float(v)))
        except:return None
    if tag=="tv":
        x=epoch(v);return str(x) if x is not None else None
    if tag=="qv":
        try:return str(v) if math.isfinite(float(v)) else None
        except:return None
    return str(v).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def make_xml(n):
    lines=['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>','<ns2:XTracks xmlns="http://www.raytheon.com/athena/ctrack/common/1.1" xmlns:ns2="http://www.raytheon.com/athena/ctrack/xtrack/1.1">','  <ns2:XTrack verbose="true">']
    for f,(tag,u) in SPECS.items():
        v=xmlval(tag,n.get(f))
        if v is None:continue
        lines += ["    <ns2:A>",f"      <id>{f}</id>",f"      <{tag}{(' u="'+u+'"') if u else ''}>{v}</{tag}>","    </ns2:A>"]
    lines += ["  </ns2:XTrack>","</ns2:XTracks>"];doc="\n".join(lines);ET.fromstring(doc);return doc
def process(conn,path,text):
    count=0
    for i,r in enumerate(parse_payload(text),1):
        n=enrich(conn,normalize(r))
        if n["id.mmsi"] is None and n["id.imo"] is None:log.warning("Record %d has no valid identity; XML rejected",i);continue
        if n["kinematic.pos.lla.lat"] is not None and not -math.pi/2<=n["kinematic.pos.lla.lat"]<=math.pi/2:continue
        xml=make_xml(n)
        if n["id.mmsi"]:update_vessel_state(conn,n["id.mmsi"],n,n.get("timestamp.source"),SOURCE)
        write_xml(Path(OUTPUT_FOLDER),SOURCE,str(path),i,xml,{"enabled":FORWARD_ENABLED,"host":FORWARD_HOST,"port":FORWARD_PORT} if FORWARD_ENABLED else None)
        count+=1
    conn.commit();return count
def main():
    folder=Path(INPUT_FOLDER).expanduser().resolve()
    while True:
        with db_connect({"DB_HOST":DB_HOST,"DB_PORT":DB_PORT,"DB_NAME":DB_NAME,"DB_USER":DB_USER,"DB_PASSWORD":DB_PASSWORD}) as conn:
            for p in files_in_folder(folder,FILE_PATTERNS):
                fh=sha256(p)
                if already_processed(conn,SOURCE,fh):continue
                try:c=process(conn,p,p.read_text(encoding="utf-8",errors="replace"));mark_file(conn,SOURCE,p,fh,"DONE",c);conn.commit()
                except Exception as e:conn.rollback();mark_file(conn,SOURCE,p,fh,"FAILED",0,str(e));conn.commit();log.exception("File failed: %s",p)
        if RUN_ONCE:break
        time.sleep(POLL_SECONDS)
if __name__=="__main__":main()
