"""Shared runtime for standalone Validation feed programs."""
from __future__ import annotations
import hashlib
import json
import logging
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.app.models.common import ParserEnvelope
from parser.app.pipeline.processor import PipelineProcessor
from parser.app.pipeline.ais_state import AISStateDB
from parser.app.pipeline.track_state import TrackStateDB
from scripts.postgres_reference import PostgresReferenceDB, PostgresLiveDB

PARSER_CLASSES = {
    "SAIS": ("parser.app.parsers.sais", "SAISParser"),
    "MSIS": ("parser.app.parsers.msis", "MSISParser"),
    "LRIT": ("parser.app.parsers.lrit", "LRITParser"),
    "VATMS": ("parser.app.parsers.vatms", "VATMSParser"),
    "NAIS": ("parser.app.parsers.nais", "NAISParser"),
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def make_logger(source):
    logger = logging.getLogger("validation.feed." + source)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        (ROOT / "runtime/logs").mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(ROOT / "runtime/logs" / f"{source}.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
        logger.addHandler(h)
        logger.addHandler(logging.StreamHandler(sys.stdout))
    return logger

def write_status(source, status, **extra):
    d = ROOT / "runtime/status"
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{source}.json"
    tmp = d / f".{source}.json.tmp"
    tmp.write_text(json.dumps({"source":source,"status":status,"updated_at":utc_now(),**extra}, indent=2), encoding="utf-8")
    tmp.replace(target)

def parser_instance(name):
    module_name, class_name = PARSER_CLASSES[name]
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)()

class FeedRunner:
    def __init__(self, config):
        self.cfg = config
        self.source = config["SOURCE_ID"]
        self.logger = make_logger(self.source)
        self.reference_db = PostgresReferenceDB(config["DATABASE"])
        self.live_db = PostgresLiveDB(config["DATABASE"])
        output = Path(config["DESTINATION"].get("folder", "runtime/xml/pending"))
        if not output.is_absolute():
            output = ROOT / output
        self.processor = PipelineProcessor(
            reference_db=self.reference_db,
            track_state_db=TrackStateDB(),
            ais_state_db=AISStateDB(),
            xml_output_dir=output,
        )
        self.parser = parser_instance(config["PARSER_NAME"])
        self.stop_event = threading.Event()
        self.processed_files = set()

    def route(self, payload, filename=None):
        router = self.cfg.get("ROUTER", {})
        if not router.get("enabled"):
            return False
        host, port = str(router["host"]), int(router["port"])
        envelope = {
            "message_id": f"{self.source}-{time.time_ns()}",
            "source": self.source,
            "input_type": self.cfg["INPUT"]["type"],
            "received_at": utc_now(),
            "filename": filename,
            "payload": payload,
        }
        raw = (json.dumps(envelope, ensure_ascii=False) + "\n").encode()
        with socket.create_connection((host, port), timeout=float(router.get("timeout_seconds", 5))) as s:
            s.sendall(raw)
        return True

    def process(self, payload, filename=None):
        message_id = f"{self.source}-{time.time_ns()}"
        if self.route(payload, filename):
            return {"success": True, "routed": True, "message_id": message_id}
        envelope = ParserEnvelope(
            message_id=message_id, source=self.source,
            input_type=self.cfg["INPUT"]["type"], received_at=utc_now(),
            payload=payload, filename=filename,
            file_size=len(payload.encode("utf-8")),
            file_hash=hashlib.sha256(payload.encode()).hexdigest(),
        )
        result, _ = self.processor.process_envelope(envelope, fallback_source_parser=self.parser)
        updated = 0
        for rec in result.records:
            try:
                self.live_db.upsert_record(self.source, rec)
                updated += 1
            except Exception as exc:
                self.logger.error("Live update failed for MMSI=%s: %s", rec.mmsi, exc)
        return {"success":result.success,"message_id":message_id,"records_parsed":result.records_parsed,
                "records_rejected":result.records_rejected,"live_updated":updated,"errors":result.errors[-20:]}

    def run_folder(self):
        inp = self.cfg["INPUT"]
        folder = Path(inp["folder"]).expanduser()
        if not folder.is_absolute():
            folder = ROOT / folder
        folder.mkdir(parents=True, exist_ok=True)
        pattern = inp.get("pattern", "*")
        while not self.stop_event.is_set():
            paths = sorted(folder.rglob(pattern) if inp.get("recursive", True) else folder.glob(pattern))
            for path in paths:
                key = str(path.resolve())
                if key in self.processed_files or not path.is_file():
                    continue
                try:
                    payload = path.read_text(encoding=inp.get("encoding","utf-8"), errors="replace")
                    self.logger.info("Processed %s: %s", path, self.process(payload, path.name))
                    self.processed_files.add(key)
                except Exception as exc:
                    self.logger.exception("Failed %s: %s", path, exc)
            self.stop_event.wait(float(inp.get("poll_seconds", 1.0)))

    def _tcp(self, conn, framing):
        with conn:
            conn.settimeout(2)
            buf = b""
            while not self.stop_event.is_set():
                try:
                    data = conn.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break
                buf += data
                if framing == "LINE":
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        if raw.strip():
                            self.process(raw.decode("utf-8","replace"))
                else:
                    self.process(buf.decode("utf-8","replace"))
                    buf = b""

    def run_tcp_server(self):
        inp = self.cfg["INPUT"]
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((str(inp.get("host","0.0.0.0")), int(inp["port"])))
        srv.listen(16); srv.settimeout(1)
        try:
            while not self.stop_event.is_set():
                try: conn, _ = srv.accept()
                except socket.timeout: continue
                threading.Thread(target=self._tcp, args=(conn,str(inp.get("framing","LINE")).upper()), daemon=True).start()
        finally:
            srv.close()

    def run_tcp_client(self):
        inp = self.cfg["INPUT"]
        delay = 1
        while not self.stop_event.is_set():
            try:
                with socket.create_connection((str(inp["host"]),int(inp["port"])),timeout=5) as conn:
                    delay = 1
                    self._tcp(conn,str(inp.get("framing","LINE")).upper())
            except Exception as exc:
                self.logger.warning("TCP reconnect: %s", exc)
                self.stop_event.wait(delay); delay=min(delay*2,30)

    def run(self):
        write_status(self.source,"RUNNING",parser=self.cfg["PARSER_NAME"],input=self.cfg["INPUT"])
        try:
            typ = self.cfg["INPUT"]["type"].upper()
            if typ == "FOLDER": self.run_folder()
            elif typ == "TCP_SERVER": self.run_tcp_server()
            elif typ == "TCP_CLIENT": self.run_tcp_client()
            else: raise ValueError("Unsupported INPUT.type: " + typ)
        except Exception as exc:
            write_status(self.source,"ERROR",error=str(exc))
            raise
        finally:
            self.stop_event.set()
            self.reference_db.close(); self.live_db.close()
            write_status(self.source,"STOPPED")
