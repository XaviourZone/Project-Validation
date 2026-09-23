"""Validation operator console.

The console is a control/monitoring plane only. Router, Parser and Forwarder
remain independent OS processes and can be started/stopped directly without
the console. The console can optionally control an individual service, but
closing the console never stops a service.

Router source configuration is edited directly in router/config/sources.yaml
and the Router is restarted only when the operator explicitly applies a
configuration change.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import yaml
from parser.reference.reference_importer import import_reference

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "console" / "config" / "console.yaml"
ROUTER_CONFIG = ROOT / "router" / "config" / "sources.yaml"
WEB_ROOT = ROOT / "console" / "web"
LOG_ROOT = ROOT / "logs"

SERVICE_DEFAULTS = {
    "router": {
        "command": ["router.app.main", "--config", "router/config/sources.yaml"],
        "health_url": "http://127.0.0.1:18080/status",
        "log_file": "logs/router.log",
    },
    "parser": {
        "command": ["parser.app.main", "--config", "parser/config/parser.yaml"],
        "health_url": "http://127.0.0.1:18081/health",
        "log_file": "logs/parser.log",
    },
    "forwarder": {
        "command": ["forwarder.app.main", "--config", "forwarder/config/forwarder.yaml"],
        "health_url": "http://127.0.0.1:18082/health",
        "log_file": "logs/forwarder.log",
    },
}


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_yaml(path: Path, cfg: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def ensure_runtime_dirs() -> None:
    for rel in (
        "DATA_INFLOW/SAIS_IOR",
        "DATA_INFLOW/SAIS_GLOBAL",
        "DATA_INFLOW/MSIS",
        "DATA_INFLOW/LRIT",
        "forwarder/spool/pending",
        "forwarder/spool/delivered",
        "forwarder/spool/failed",
        "router/state",
        "parser/state",
        "parser/reference",
        "forwarder/state",
        "logs",
    ):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def _router_base_dir(cfg: dict[str, Any]) -> Path:
    raw = Path(str((cfg.get("data_inflow") or {}).get("base_dir", "DATA_INFLOW")))
    return raw if raw.is_absolute() else ROOT / raw


def _source_path(cfg: dict[str, Any], source: dict[str, Any]) -> Path:
    raw = Path(str(source.get("folder", "")))
    if raw.is_absolute():
        return raw
    return _router_base_dir(cfg) / raw


def _router_source_entries() -> list[dict[str, Any]]:
    cfg = load_yaml(ROUTER_CONFIG)
    result = []
    for name, raw in (cfg.get("sources") or {}).items():
        item = dict(raw or {})
        entry = {
            "name": name,
            "type": str(item.get("type", "")),
            "parser": str(item.get("parser", "")),
            "enabled": bool(item.get("enabled", False)),
            "config": item,
        }
        if entry["type"] == "file":
            folder = _source_path(cfg, item)
            entry.update({
                "folder": str(folder),
                "exists": folder.is_dir(),
                "patterns": list(item.get("file_patterns") or []),
                "poll_interval_seconds": float(item.get("poll_interval_seconds", 1.0)),
                "stability_window_seconds": float(item.get("stability_window_seconds", 1.0)),
                "preserve_file": bool(item.get("preserve_file", False)),
                "processed_folder": str(item.get("processed_folder", "")),
            })
        elif entry["type"] == "tcp":
            entry.update({
                "host": str(item.get("remote_host", "")),
                "port": int(item.get("remote_port", 0)),
                "framing": str(item.get("framing", "line")),
                "delimiter": str(item.get("delimiter", "\\n")),
                "max_line_length": int(item.get("max_line_length", 65536)),
                "reconnect_initial_delay": float(item.get("reconnect_initial_delay", 2.0)),
                "reconnect_max_delay": float(item.get("reconnect_max_delay", 60.0)),
                "reconnect_multiplier": float(item.get("reconnect_multiplier", 2.0)),
            })
        result.append(entry)
    return result


def router_sources() -> dict[str, Any]:
    cfg = load_yaml(ROUTER_CONFIG)
    return {
        "base_dir": str(_router_base_dir(cfg)),
        "parser_destinations": cfg.get("parser_destinations") or {},
        "sources": _router_source_entries(),
    }


def update_router_source(name: str, values: dict[str, Any]) -> dict[str, Any]:
    cfg = load_yaml(ROUTER_CONFIG)
    sources = cfg.setdefault("sources", {})
    if name not in sources:
        raise ValueError(f"Unknown Router source: {name}")

    current = sources[name] or {}
    stype = str(current.get("type", "")).lower()
    if stype == "file":
        if "folder" in values:
            folder = Path(str(values["folder"]).strip()).expanduser()
            if not folder.is_absolute():
                folder = (ROOT / folder).resolve()
            else:
                folder = folder.resolve()
            if not folder.is_dir():
                raise ValueError(f"Folder does not exist: {folder}")
            current["folder"] = str(folder)
        if "enabled" in values:
            current["enabled"] = bool(values["enabled"])
        if "parser" in values:
            current["parser"] = str(values["parser"]).strip()
        if "file_patterns" in values:
            patterns = values["file_patterns"]
            if not isinstance(patterns, list) or not patterns or any(not str(x).strip() for x in patterns):
                raise ValueError("file_patterns must be a non-empty list")
            current["file_patterns"] = [str(x).strip() for x in patterns]
        for key in ("poll_interval_seconds", "stability_window_seconds"):
            if key in values:
                val = float(values[key])
                if val <= 0:
                    raise ValueError(f"{key} must be > 0")
                current[key] = val
        if "preserve_file" in values:
            current["preserve_file"] = bool(values["preserve_file"])
        if "processed_folder" in values:
            current["processed_folder"] = str(values["processed_folder"] or "")
    elif stype == "tcp":
        if "enabled" in values:
            current["enabled"] = bool(values["enabled"])
        if "parser" in values:
            current["parser"] = str(values["parser"]).strip()
        if "remote_host" in values:
            host = str(values["remote_host"]).strip()
            if not host:
                raise ValueError("remote_host cannot be empty")
            current["remote_host"] = host
        if "remote_port" in values:
            port = int(values["remote_port"])
            if not 1 <= port <= 65535:
                raise ValueError("remote_port must be 1-65535")
            current["remote_port"] = port
        if "framing" in values:
            framing = str(values["framing"]).strip()
            if framing not in ("line", "length_prefixed", "raw_block"):
                raise ValueError("Unsupported framing")
            current["framing"] = framing
        if "delimiter" in values:
            current["delimiter"] = str(values["delimiter"])
        for key in ("max_line_length",):
            if key in values:
                val = int(values[key])
                if val < 1:
                    raise ValueError(f"{key} must be > 0")
                current[key] = val
        for key in ("reconnect_initial_delay", "reconnect_max_delay", "reconnect_multiplier"):
            if key in values:
                val = float(values[key])
                if val <= 0:
                    raise ValueError(f"{key} must be > 0")
                current[key] = val
    else:
        raise ValueError(f"Unsupported Router source type: {stype}")

    sources[name] = current
    save_yaml(ROUTER_CONFIG, cfg)
    return next(x for x in _router_source_entries() if x["name"] == name)


def router_status() -> dict[str, Any]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:18080/status", timeout=2.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def browse_folder(title: str) -> dict[str, Any]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title=title)
        root.destroy()
        return {
            "success": bool(selected),
            "path": selected or "",
            "message": "Folder selected." if selected else "No folder selected.",
        }
    except Exception as exc:
        return {
            "success": False,
            "path": "",
            "message": f"Native folder picker unavailable: {exc}",
        }


class ServiceController:
    """Optional process control. Services are independent and are not owned by Console."""

    def __init__(self, name: str, definition: dict[str, Any]):
        self.name = name
        self.definition = definition
        self.process: subprocess.Popen | None = None
        self.log_handle = None
        self.started_at: float | None = None
        self.last_error = ""
        self.lock = threading.RLock()

    def _command(self) -> list[str]:
        configured = self.definition.get("command") or SERVICE_DEFAULTS[self.name]["command"]
        return [sys.executable, "-m", *map(str, configured)]

    def _health(self) -> dict[str, Any]:
        url = self.definition.get("health_url") or SERVICE_DEFAULTS[self.name]["health_url"]
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return {
                    "reachable": True,
                    "status": payload.get("status", payload.get("overall_status", "OK")),
                    "data": payload,
                }
        except Exception as exc:
            return {"reachable": False, "status": "UNREACHABLE", "error": str(exc)}

    def refresh_process(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            code = self.process.returncode
            self.process = None
            if code not in (0, None):
                self.last_error = f"process exited with code {code}"

    def start(self) -> dict[str, Any]:
        with self.lock:
            self.refresh_process()
            if self.process is not None:
                return {"success": True, "message": f"{self.name} is already running", **self.status()}
            ensure_runtime_dirs()
            log_path = ROOT / str(self.definition.get("log_file", f"logs/{self.name}.log"))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_handle = log_path.open("a", encoding="utf-8", buffering=1)
            env = os.environ.copy()
            env["VALIDATION_HOME"] = str(ROOT)
            env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            try:
                self.process = subprocess.Popen(
                    self._command(), cwd=str(ROOT), env=env,
                    stdin=subprocess.DEVNULL, stdout=self.log_handle,
                    stderr=subprocess.STDOUT, creationflags=flags,
                )
                self.started_at = time.time()
                self.last_error = ""
                return {"success": True, "message": f"{self.name} start requested", **self.status()}
            except Exception as exc:
                self.last_error = str(exc)
                if self.log_handle:
                    self.log_handle.close()
                    self.log_handle = None
                return {"success": False, "error": str(exc), **self.status()}

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.refresh_process()
            if self.process is None:
                return {"success": True, "message": f"{self.name} is not owned by this console process", **self.status()}
            proc = self.process
            try:
                if os.name == "nt":
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            finally:
                self.process = None
                self.started_at = None
                if self.log_handle:
                    self.log_handle.close()
                    self.log_handle = None
            return {"success": True, "message": f"{self.name} stopped", **self.status()}

    def restart(self) -> dict[str, Any]:
        self.stop()
        time.sleep(0.5)
        return self.start()

    def status(self) -> dict[str, Any]:
        self.refresh_process()
        owned = self.process is not None and self.process.poll() is None
        health = self._health()
        reachable = bool(health.get("reachable"))
        if reachable:
            state = "RUNNING"
        elif owned:
            state = "STARTING"
        else:
            state = "STOPPED"
        return {
            "name": self.name,
            "state": state,
            "owned_by_console": owned,
            "pid": self.process.pid if owned else None,
            "uptime_seconds": round(time.time() - self.started_at, 1) if owned and self.started_at else 0,
            "health": health,
            "last_error": self.last_error,
        }


class ReferenceManager:
    @staticmethod
    def _find_child(folder: Path, name: str) -> Path | None:
        if not folder.exists():
            return None
        wanted = name.casefold()
        return next((p for p in folder.iterdir() if p.name.casefold() == wanted), None)

    def status(self) -> dict[str, Any]:
        cfg = load_yaml(CONFIG_PATH)
        entries = []
        for name, item in (cfg.get("reference") or {}).items():
            item = item or {}
            source = Path(str(item.get("source_folder", ""))) if item.get("source_folder") else None
            if source and not source.is_absolute():
                source = ROOT / source
            store = Path(str(item.get("store_path", "")))
            if not store.is_absolute():
                store = ROOT / store
            required = {}
            if source and source.is_dir():
                for folder_name in item.get("required_folders", []):
                    child = self._find_child(source, str(folder_name))
                    if name.upper() == "WRS" and str(folder_name).casefold() == "decode":
                        child = child or self._find_child(source, "Decode files")
                    required[str(folder_name)] = bool(child and child.is_dir())
            manifest_path = store / "REFERENCE_MANIFEST.json"
            manifest = {}
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            manifests = bool(store.is_dir() and (manifest_path.is_file() or any(store.glob("MANIFEST*"))))
            entries.append({
                "name": name,
                "source_folder": str(source) if source else "",
                "source_exists": bool(source and source.is_dir()),
                "required": required,
                "store_path": str(store),
                "store_ready": manifests,
                "rows": int(manifest.get("rows", 0) or 0),
                "tables": manifest.get("tables", {}),
                "files_loaded": len(manifest.get("files", []) or []),
                "last_import": manifest.get("created_at"),
                "status": "READY" if manifests else ("SOURCE READY" if source and source.is_dir() and all(required.values()) else "NOT CONFIGURED"),
            })
        return {"databases": entries}

    def set_source(self, name: str, folder: str) -> dict[str, Any]:
        cfg = load_yaml(CONFIG_PATH)
        if name not in (cfg.get("reference") or {}):
            raise ValueError(f"Unknown reference database: {name}")
        path = Path(folder).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"Folder does not exist: {path}")
        cfg["reference"][name]["source_folder"] = str(path)
        save_yaml(CONFIG_PATH, cfg)
        return self.status()

    def load(self, name: str) -> dict[str, Any]:
        cfg = load_yaml(CONFIG_PATH)
        if name not in (cfg.get("reference") or {}):
            raise ValueError(f"Unknown reference database: {name}")
        entry = cfg["reference"][name] or {}
        source = str(entry.get("source_folder", "")).strip()
        if not source:
            raise ValueError(f"{name} source folder is not configured")
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_dir():
            raise ValueError(f"Reference source folder does not exist: {source_path}")
        if self._parser_health().get("reachable"):
            raise ValueError("Stop Parser before loading a reference database, then load it and start Parser again.")
        target = Path(str(entry.get("store_path", "")))
        if not target.is_absolute():
            target = ROOT / target
        result = import_reference(name, source_path, target)
        return {"success": True, "database": name, "manifest": result, "status": self.status()}

    @staticmethod
    def _parser_health() -> dict[str, Any]:
        try:
            with urllib.request.urlopen("http://127.0.0.1:18081/health", timeout=1.0) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:
            return {"reachable": False}


class Console:
    def __init__(self):
        ensure_runtime_dirs()
        cfg = load_yaml(CONFIG_PATH)
        self.services = {
            name: ServiceController(name, (cfg.get("services") or {}).get(name, defaults))
            for name, defaults in SERVICE_DEFAULTS.items()
        }
        self.reference = ReferenceManager()

    def status(self) -> dict[str, Any]:
        services = {name: ctrl.status() for name, ctrl in self.services.items()}
        return {
            "system": "OPERATOR CONSOLE",
            "services": services,
            "router": router_status(),
            "reference": self.reference.status(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }


CONSOLE = Console()


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload: Any, code: int = 200):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/status":
                return self._json(CONSOLE.status())
            if path == "/api/router/sources":
                return self._json(router_sources())
            if path == "/api/router/status":
                return self._json(router_status())
            if path == "/api/router/browse":
                return self._json(browse_folder("Select Router source folder"))
            if path == "/api/reference/status":
                return self._json(CONSOLE.reference.status())
            if path == "/api/reference/browse":
                return self._json(browse_folder("Select reference source folder"))
            if path == "/api/health":
                return self._json({"status": "READY", "service": "validation-console"})
            if path in ("/", "/index.html"):
                data = (WEB_ROOT / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith("/static/"):
                file_path = (WEB_ROOT / path.removeprefix("/static/")).resolve()
                if WEB_ROOT.resolve() not in file_path.parents or not file_path.is_file():
                    return self._json({"error": "not found"}, 404)
                data = file_path.read_bytes()
                ctype = "text/css" if file_path.suffix == ".css" else "text/javascript"
                self.send_response(200)
                self.send_header("Content-Type", ctype + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            return self._json({"error": "not found"}, 404)
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._body()
            if path == "/api/router/source":
                name = str(body.pop("name", "")).strip()
                return self._json({"success": True, "source": update_router_source(name, body)})
            if path == "/api/reference/source":
                name = str(body.get("name", "")).strip()
                folder = str(body.get("folder", "")).strip()
                return self._json({"success": True, "reference": CONSOLE.reference.set_source(name, folder)})
            if path == "/api/service/":
                return self._json({"error": "service name required"}, 400)
            if path.startswith("/api/service/"):
                parts = path.split("/")
                if len(parts) == 5 and parts[-1] in ("start", "stop", "restart"):
                    name, action = parts[-2], parts[-1]
                    if name not in CONSOLE.services:
                        return self._json({"error": "unknown service"}, 404)
                    return self._json(getattr(CONSOLE.services[name], action)())
            if path == "/api/reference/load":
                name = str(body.get("name", "")).strip()
                return self._json(CONSOLE.reference.load(name))
            if path == "/api/reference/validate":
                name = str(body.get("name", ""))
                status = CONSOLE.reference.status()
                match = next((x for x in status["databases"] if x["name"] == name), None)
                if not match:
                    return self._json({"success": False, "message": "Unknown reference database"}, 404)
                missing = [k for k, v in match["required"].items() if not v]
                ok = match["source_exists"] and not missing
                return self._json({"success": ok, "message": "Reference source is valid." if ok else "Reference source validation failed.", "status": match}, 200 if ok else 400)
            return self._json({"error": "not found"}, 404)
        except Exception as exc:
            return self._json({"success": False, "error": str(exc)}, 400)

    def log_message(self, fmt, *args):
        return


def run():
    cfg = load_yaml(CONFIG_PATH)
    host = str((cfg.get("server") or {}).get("host", "127.0.0.1"))
    port = int((cfg.get("server") or {}).get("port", 8080))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    print(f"[VALIDATION] Operator Console: http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
