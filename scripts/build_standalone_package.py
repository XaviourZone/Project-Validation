from pathlib import Path
import json, shutil, compileall, zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"standalone_package"

def write(p, s):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

def main():
    if OUT.exists(): shutil.rmtree(OUT)
    for name in ("db","router","parser","forwarder"):
        (OUT/name).mkdir(parents=True)

    shutil.copytree(ROOT/"shared", OUT/"db"/"shared")
    for name in ("router","parser","forwarder"):
        shutil.copytree(ROOT/name, OUT/name, dirs_exist_ok=True)

    for p in (
        OUT/"router/logs", OUT/"router/state",
        OUT/"parser/logs", OUT/"parser/state",
        OUT/"forwarder/logs", OUT/"forwarder/state",
    ):
        shutil.rmtree(p, ignore_errors=True)

    for p in (
        OUT/"router/DATA_INFLOW/SAIS_IOR", OUT/"router/DATA_INFLOW/SAIS_GLOBAL",
        OUT/"router/DATA_INFLOW/MSIS", OUT/"router/DATA_INFLOW/LRIT",
        OUT/"parser/reference", OUT/"forwarder/spool/pending",
        OUT/"forwarder/spool/delivered", OUT/"forwarder/spool/failed",
        OUT/"forwarder/output", OUT/"router/logs", OUT/"router/state",
        OUT/"parser/logs", OUT/"parser/state", OUT/"forwarder/logs", OUT/"forwarder/state",
    ):
        p.mkdir(parents=True, exist_ok=True)

    router={
      "http_host":"127.0.0.1","http_port":5000,"data_inflow_base_dir":"router/DATA_INFLOW",
      "parser_destinations":{"SAIS":{"host":"127.0.0.1","port":5010},"MSIS":{"host":"127.0.0.1","port":5011},"LRIT":{"host":"127.0.0.1","port":5012},"VATMS":{"host":"127.0.0.1","port":5013},"NAIS":{"host":"127.0.0.1","port":5014}},
      "sources":{
        "SAIS_IOR":{"type":"file","folder":"SAIS_IOR","parser":"SAIS","enabled":True,"poll_interval_seconds":1.0,"stability_window_seconds":1.0,"file_patterns":["*.csv","*.txt","*"],"preserve_file":True},
        "SAIS_GLOBAL":{"type":"file","folder":"SAIS_GLOBAL","parser":"SAIS","enabled":True,"poll_interval_seconds":1.0,"stability_window_seconds":1.0,"file_patterns":["*.csv","*.txt","*"],"preserve_file":True},
        "MSIS":{"type":"file","folder":"MSIS","parser":"MSIS","enabled":True,"poll_interval_seconds":1.0,"stability_window_seconds":1.0,"file_patterns":["*.csv","*.txt","*"],"preserve_file":True},
        "LRIT":{"type":"file","folder":"LRIT","parser":"LRIT","enabled":True,"poll_interval_seconds":1.0,"stability_window_seconds":1.0,"file_patterns":["*.csv","*.txt","*"],"preserve_file":True},
        "VATMS_EAST":{"type":"tcp","remote_host":"127.0.0.1","remote_port":5020,"parser":"VATMS","enabled":False,"framing":"line","delimiter":"\n","max_line_length":65536,"reconnect_initial_delay":2.0,"reconnect_max_delay":60.0,"reconnect_multiplier":2.0},
        "VATMS_WEST":{"type":"tcp","remote_host":"127.0.0.1","remote_port":5021,"parser":"VATMS","enabled":False,"framing":"line","delimiter":"\n","max_line_length":65536,"reconnect_initial_delay":2.0,"reconnect_max_delay":60.0,"reconnect_multiplier":2.0},
        "NAIS":{"type":"tcp","remote_host":"127.0.0.1","remote_port":5022,"parser":"NAIS","enabled":False,"framing":"line","delimiter":"\n","max_line_length":65536,"reconnect_initial_delay":2.0,"reconnect_max_delay":60.0,"reconnect_multiplier":2.0}},
      "retry":{"max_attempts":5,"initial_delay_seconds":2.0,"max_delay_seconds":60.0,"backoff_multiplier":2.0},
      "queue":{"max_size":10000,"worker_count":4,"high_watermark_ratio":0.8}}
    parser={
      "http_host":"127.0.0.1","http_port":5001,
      "endpoints":{"SAIS":{"port":5010,"sources":["SAIS_IOR","SAIS_GLOBAL"],"framing":"ndjson"},"MSIS":{"port":5011,"sources":["MSIS"],"framing":"ndjson"},"LRIT":{"port":5012,"sources":["LRIT"],"framing":"ndjson"},"VATMS":{"port":5013,"sources":["VATMS_EAST","VATMS_WEST"],"framing":"ndjson"},"NAIS":{"port":5014,"sources":["NAIS"],"framing":"ndjson"}},
      "xml_spool_dir":"forwarder/spool/pending",
      "reference_databases":{"wrs":"parser/reference/wrs","pans":"parser/reference/pans","nsc":"parser/reference/nsc"},
      "logging":{"level":"INFO","log_path":"parser/logs/parser.log"}}
    forwarder={
      "http_host":"127.0.0.1","http_port":5050,
      "spool":{"input_dir":"forwarder/spool/pending","archive_dir":"forwarder/spool/delivered","failed_dir":"forwarder/spool/failed","state_db":"forwarder/state/delivery","secret_file":"forwarder/state/forwarder_secrets.json","poll_interval_seconds":1,"claim_timeout_seconds":300},
      "retry":{"max_attempts":5,"initial_delay_seconds":2.0,"max_delay_seconds":60.0,"multiplier":2.0},
      "destinations":{"LOCAL":{"enabled":True,"protocol":"local","local_path":"forwarder/output"},"D-DIODE-01":{"enabled":False,"protocol":"sftp","host":"127.0.0.1","port":22,"remote_path":"/home/ddiode/txserver/in/","username":"ddiode","private_key_file":"","connect_timeout_seconds":10,"verify_remote_size":True}},
      "logging":{"level":"INFO"}}

    write(OUT/"router/control.json",json.dumps(router,indent=2))
    write(OUT/"parser/control.json",json.dumps(parser,indent=2))
    write(OUT/"forwarder/control.json",json.dumps(forwarder,indent=2))
    write(OUT/"router/requirements.txt","PyYAML>=6.0.0\namulet-rocksdb>=1.0.5,<2\n")
    write(OUT/"parser/requirements.txt","PyYAML>=6.0.0\namulet-rocksdb>=1.0.5,<2\n")
    write(OUT/"forwarder/requirements.txt","PyYAML>=6.0.0\nparamiko>=3.4,<5\namulet-rocksdb>=1.0.5,<2\n")

    common='''from __future__ import annotations
import json, os, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"db"))
def load(): return json.loads((HERE/"control.json").read_text(encoding="utf-8"))
def prepare_env():
    os.environ["VALIDATION_HOME"]=str(ROOT)
    os.environ["PYTHONPATH"]=os.pathsep.join([str(ROOT),str(ROOT/"db"),os.environ.get("PYTHONPATH","")])
def main():
    if sys.version_info[:2] not in {(3,11),(3,12)}:
        raise SystemExit("Use Python 3.11 or 3.12: approved RocksDB Windows wheels target those versions.")
    prepare_env()
'''
    write(OUT/"router/start.py",common+'''import yaml
c=load(); p=HERE/"config/sources.yaml"; cfg=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
cfg["data_inflow"]["base_dir"]=c["data_inflow_base_dir"]
cfg["parser_destinations"]={k:{**cfg.get("parser_destinations",{}).get(k,{}),**v} for k,v in c["parser_destinations"].items()}
cfg["monitoring"]={"enabled":True,"http_host":c["http_host"],"http_port":c["http_port"]}
for name,val in c["sources"].items(): cfg.setdefault("sources",{}).setdefault(name,{}).update(val)
cfg["state"]["db_path"]="router/state/router_state"; p.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
main()
import runpy; runpy.run_module("router.app.main",run_name="__main__")
''')
    write(OUT/"parser/start.py",common+'''import yaml
c=load(); p=HERE/"config/parser.yaml"; cfg=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
cfg["server"]={"http_host":c["http_host"],"http_port":c["http_port"]}; cfg["endpoints"]=c["endpoints"]; cfg["output"]={"xml_spool_dir":c["xml_spool_dir"]}; cfg["reference_databases"]=c["reference_databases"]; cfg["logging"]=c["logging"]
p.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
main()
import runpy; runpy.run_module("parser.app.main",run_name="__main__")
''')
    write(OUT/"forwarder/start.py",common+'''import yaml
c=load(); p=HERE/"config/forwarder.yaml"; cfg=yaml.safe_load(p.read_text(encoding="utf-8")) or {}
cfg["server"]={"http_host":c["http_host"],"http_port":c["http_port"]}; cfg["spool"]=c["spool"]; cfg["retry"]=c["retry"]; cfg["destinations"]=c["destinations"]; cfg["logging"]=c["logging"]
p.write_text(yaml.safe_dump(cfg,sort_keys=False),encoding="utf-8")
main()
import runpy; runpy.run_module("forwarder.app.main",run_name="__main__")
''')
    write(OUT/"db/README.md","Shared RocksDB storage implementation used by Router, Parser and Forwarder. SQLite is not used at runtime.\n")
    write(OUT/"README.md","Validation standalone four-service package. No web UI. Run each service with python start.py. Controls are in control.json. Ports: Router 5000; Parser 5001; Parser inputs 5010-5014; Forwarder 5050. Use Python 3.11 or 3.12.\n")
    if not compileall.compile_dir(str(OUT),quiet=1): raise SystemExit("compile failed")
    zip_path=ROOT/"validation-standalone-5050.zip"
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path,"w",zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob("*"):
            if p.is_file(): z.write(p,p.relative_to(OUT))
    print(zip_path)

if __name__=="__main__":
    main()
