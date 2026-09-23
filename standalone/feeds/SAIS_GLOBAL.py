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
SOURCE="SAIS_GLOBAL"; SOURCE_ID=2
INPUT_MODE="FOLDER"; INPUT_FOLDER=r"./input/SAIS_GLOBAL"; FILE_PATTERNS=["*.csv","*.txt","*.nmea","*.log"]
POLL_SECONDS=2; RUN_ONCE=False
TCP_HOST="127.0.0.1"; TCP_PORT=20001
OUTPUT_FOLDER=r"./output/SAIS_GLOBAL"
FORWARD_ENABLED=False; FORWARD_HOST="127.0.0.1"; FORWARD_PORT=10001
DB_HOST="127.0.0.1"; DB_PORT=5432; DB_NAME="validation"; DB_USER="validation"; DB_PASSWORD=""
WRS_MATCH=("MMSI","IMO","CALLSIGN","VESSEL_NAME")
PANS_MATCH=("IMO","MMSI","CALLSIGN","VESSEL_NAME")
NSC_MATCH=("MMSI","IMO","CALLSIGN","VESSEL_NAME")
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | SAIS_GLOBAL | %(message)s")
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

def decode6(payload):
    bits=""
    for c in payload:
        v=ord(c)-48
        if v>40:v-=8
        if not 0<=v<=63:raise ValueError("invalid AIS 6-bit character")
        bits+=f"{v:06b}"
    return bits
def sint(bits):
    v=int(bits,2);n=len(bits);return v-(1<<n) if v&(1<<(n-1)) else v
def astr(bits):
    return "".join(CHARSET[int(bits[i:i+6],2)] for i in range(0,len(bits)-5,6) if CHARSET[int(bits[i:i+6],2)]!="@").strip()
def checksum(line):
    if "*" not in line:return True
    body,s=line.rsplit("*",1);s=s[:2];x=0
    for c in body[1:]:x^=ord(c)
    try:return len(s)==2 and x==int(s,16)
    except:return False

def parse_ais(line):
    if line.startswith("\\"):
        z=line.find("\\",1)
        if z>=0:line=line[z+1:].lstrip()
    if not line.startswith(("!","$")):raise ValueError("bad NMEA prefix")
    if not checksum(line):raise ValueError("checksum failed")
    p=line.split(","); total=int(p[1]) if len(p)>1 and p[1].isdigit() else 1
    if total!=1: raise ValueError("multipart AIS must be supplied as a complete sentence group")
    payload=p[5];fill=0
    if len(p)>6:
        try:fill=int(p[6].split("*",1)[0] or 0)
        except:pass
    b=decode6(payload);b=b[:-fill] if fill else b
    if len(b)<38:raise ValueError("AIS payload too short")
    t=int(b[:6],2);m=int(b[8:38],2);r={"mmsi":m,"message_type":t,"timestamp":datetime.now(timezone.utc).isoformat()}
    if t in (1,2,3) and len(b)>=137:
        r.update(nav_status=int(b[38:42],2),sog=(int(b[50:60],2)/10 if int(b[50:60],2)!=1023 else None),longitude=sint(b[61:89])/600000,latitude=sint(b[89:116])/600000,cog=(int(b[116:128],2)/10 if int(b[116:128],2)!=3600 else None),heading=(int(b[128:137],2) if int(b[128:137],2)!=511 else None))
    elif t==5 and len(b)>=422:
        r.update(imo=int(b[40:70],2) or None,callsign=astr(b[70:112]),vessel_name=astr(b[112:232]),vessel_type=int(b[232:240],2),length=int(b[240:249],2)+int(b[249:258],2),width=int(b[258:264],2)+int(b[264:270],2),draft=int(b[294:302],2)/10 if int(b[294:302],2) else None,destination=astr(b[302:422]))
    elif t==18 and len(b)>=133:
        r.update(sog=(int(b[46:56],2)/10 if int(b[46:56],2)!=1023 else None),longitude=sint(b[57:85])/600000,latitude=sint(b[85:112])/600000,cog=(int(b[112:124],2)/10 if int(b[112:124],2)!=3600 else None),heading=(int(b[124:133],2) if int(b[124:133],2)!=511 else None))
    elif t==19 and len(b)>=309:
        r.update(sog=(int(b[46:56],2)/10 if int(b[46:56],2)!=1023 else None),longitude=sint(b[57:85])/600000,latitude=sint(b[85:112])/600000,cog=(int(b[112:124],2)/10 if int(b[112:124],2)!=3600 else None),heading=(int(b[124:133],2) if int(b[124:133],2)!=511 else None),vessel_name=astr(b[143:263]),vessel_type=int(b[263:271],2))
    elif t==21 and len(b)>=249:r.update(vessel_type=int(b[38:42],2),vessel_name=astr(b[43:163]),longitude=sint(b[164:192])/600000,latitude=sint(b[192:219])/600000)
    elif t==24 and len(b)>=160:
        part=int(b[38:40],2)
        if part==0:r["vessel_name"]=astr(b[40:160])
        elif part==1:r.update(vessel_type=int(b[40:48],2),callsign=astr(b[90:132]))
    elif t==27 and len(b)>=104:r.update(sog=(int(b[46:54],2) if int(b[46:54],2)!=127 else None),cog=(int(b[55:64],2)*2 if int(b[55:64],2)!=511 else None),longitude=sint(b[64:84])/600,latitude=sint(b[84:104])/600)
    return r

def parse_payload(text):
    out=[]
    for line in text.splitlines():
        if not line.strip():continue
        try:out.append(parse_ais(line.strip()))
        except Exception as e:log.warning("Rejected NMEA: %s",e)
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
