"""Minimal single-port Validation operator console.

The console is intentionally dependency-light: stdlib HTTP server plus PyYAML.
It is the operator/control plane. Router, Parser and Forwarder remain separate
runtime services and keep their existing processing responsibilities.
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
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "console" / "config" / "console.yaml"
WEB_ROOT = ROOT / "console" / "web"
LOG_ROOT = ROOT / "logs"

SERVICE_DEFAULTS = {
    "router": {
        "command": ["router.app.main", "--config", "router/config/sources.yaml"],
        "health_url": "http://127.0.0.1:18080/health",
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


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def save_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def ensure_runtime_dirs() -> None:
    for rel in [
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
    ]:
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


class ServiceController:
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
        return [sys.executable, "-m", *[str(x) for x in configured]]

    def _health(self) -> dict[str, Any]:
        url = self.definition.get("health_url") or SERVICE_DEFAULTS[self.name]["health_url"]
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                raw = response.read().decode("utf-8")
                payload = json.loads(raw) if raw else {}
                return {"reachable": True, "status": payload.get("status", payload.get("overall_status", "OK")), "data": payload}
        except Exception as exc:
            return {"reachable": False, "status": "UNREACHABLE", "error": str(exc)}

    def refresh_process(self) -> None:
        with self.lock:
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
            creationflags = 0
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

            try:
                self.process = subprocess.Popen(
                    self._command(),
                    cwd=str(ROOT),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=self.log_handle,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                )
                self.started_at = time.time()
                self.last_error = ""
                return {"success": True, "message": f"{self.name} start requested", **self.status()}
            except Exception as exc:
                self.last_error = str(exc)
                try:
                    self.log_handle.close()
                except Exception:
                    pass
                self.log_handle = None
                return {"success": False, "error": str(exc), **self.status()}

    def stop(self) -> dict[str, Any]:
        with self.lock:
            self.refresh_process()
            if self.process is None:
                return {"success": True, "message": f"{self.name} is already stopped", **self.status()}

            proc = self.process
            try:
                if os.name == "nt":
                    proc.terminate()
                else:
                    proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
            except Exception as exc:
                self.last_error = str(exc)
                return {"success": False, "error": str(exc), **self.status()}
            finally:
                self.process = None
                self.started_at = None
                if self.log_handle:
                    try:
                        self.log_handle.close()
                    except Exception:
                        pass
                    self.log_handle = None
            return {"success": True, "message": f"{self.name} stopped", **self.status()}

    def restart(self) -> dict[str, Any]:
        self.stop()
        time.sleep(0.5)
        return self.start()

    def status(self) -> dict[str, Any]:
        self.refresh_process()
        process_running = self.process is not None and self.process.poll() is None
        health = self._health() if process_running else {"reachable": False, "status": "STOPPED"}
        if process_running and health["reachable"]:
            state = "RUNNING"
        elif process_running:
            state = "STARTING"
        else:
            state = "STOPPED"
        result = {
            "name": self.name,
            "state": state,
            "pid": self.process.pid if process_running else None,
            "uptime_seconds": round(time.time() - self.started_at, 1) if process_running and self.started_at else 0,
            "health": health,
            "last_error": self.last_error,
        }
        return result


class ReferenceManager:
    def __init__(self):
        self.lock = threading.RLock()

    @staticmethod
    def _find_child(folder: Path, name: str) -> Path | None:
        if not folder.exists():
            return None
        wanted = name.casefold()
        for child in folder.iterdir():
            if child.name.casefold() == wanted:
                return child
        return None

    def _entry(self, name: str, cfg: dict[str, Any]) -> dict[str, Any]:
        source = str(cfg.get("source_folder", "") or "")
        source_path = Path(source) if source else None
        if source_path and not source_path.is_absolute():
            source_path = ROOT / source_path
        store = Path(str(cfg.get("store_path", "")))
        if not store.is_absolute():
            store = ROOT / store

        source_ok = bool(source_path and source_path.is_dir())
        required = {}
        if source_ok:
            for item in cfg.get("required_folders", ["Datasets", "Decode"]):
                p = self._find_child(source_path, str(item))
                required[str(item)] = bool(p and p.is_dir())

        db_files = []
        if store.exists():
            db_files = [p.name for p in store.iterdir() if p.is_file() and p.name in {"CURRENT", "IDENTITY", "OPTIONS", "LOG"} or p.name.startswith("MANIFEST")]
        ready = store.is_dir() and bool(db_files)

        return {
            "name": name,
            "source_folder": str(source_path) if source_path else "",
            "source_exists": source_ok,
            "required": required,
            "store_path": str(store),
            "store_exists": store.exists(),
            "store_ready": ready,
            "status": "READY" if ready else ("SOURCE READY" if source_ok and all(required.values()) else "NOT CONFIGURED"),
        }

    def status(self) -> dict[str, Any]:
        cfg = load_config()
        refs = cfg.get("reference", {}) or {}
        return {"databases": [self._entry(name, item or {}) for name, item in refs.items()]}

    def set_source(self, name: str, folder: str) -> dict[str, Any]:
        folder = str(Path(folder).expanduser().resolve())
        cfg = load_config()
        cfg.setdefault("reference", {}).setdefault(name, {})["source_folder"] = folder
        save_config(cfg)
        return self._entry(name, cfg["reference"][name])

    def validate(self, name: str) -> dict[str, Any]:
        item = self.status()
        match = next((x for x in item["databases"] if x["name"] == name), None)
        if not match:
            raise ValueError(f"Unknown reference database: {name}")
        if not match["source_exists"]:
            return {"success": False, "message": "Source folder is not configured or does not exist.", "status": match}
        missing = [k for k, ok in match["required"].items() if not ok]
        if missing:
            return {"success": False, "message": "Missing required folders: " + ", ".join(missing), "status": match}
        return {"success": True, "message": "Reference source structure is valid.", "status": match}

    def browse(self) -> dict[str, Any]:
        # Browser folder selection is local to the machine hosting the console.
        # On headless RHEL this returns a clear fallback message.
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected = filedialog.askdirectory(title="Select reference source folder")
            root.destroy()
            return {"success": bool(selected), "path": selected or "", "message": "Folder selected." if selected else "No folder selected."}
        except Exception as exc:
            return {"success": False, "path": "", "message": f"Native folder picker unavailable: {exc}"}


class Console:
    def __init__(self):
        ensure_runtime_dirs()
        cfg = load_config()
        self.services = {
            name: ServiceController(name, (cfg.get("services", {}) or {}).get(name, defaults))
            for name, defaults in SERVICE_DEFAULTS.items()
        }
        self.reference = ReferenceManager()
        self.shutdown_event = threading.Event()

    def status(self) -> dict[str, Any]:
        services = {name: controller.status() for name, controller in self.services.items()}
        running = sum(1 for value in services.values() if value["state"] == "RUNNING")
        failed = sum(1 for value in services.values() if value["last_error"])
        ref = self.reference.status()
        ref_ready = sum(1 for x in ref["databases"] if x["store_ready"])
        return {
            "system": "RUNNING" if running == 3 else ("DEGRADED" if running else "STOPPED"),
            "services_running": running,
            "services_failed": failed,
            "services": services,
            "reference": ref,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reference_ready": ref_ready,
        }

    def start_all(self) -> dict[str, Any]:
        result = {}
        for name in ("forwarder", "parser", "router"):
            result[name] = self.services[name].start()
            time.sleep(0.7)
        return {"success": True, "results": result}

    def stop_all(self) -> dict[str, Any]:
        result = {}
        for name in ("router", "parser", "forwarder"):
            result[name] = self.services[name].stop()
        return {"success": True, "results": result}

    def startup(self) -> None:
        cfg = load_config()
        auto = cfg.get("auto_start", {}) or {}
        for name in ("forwarder", "parser", "router"):
            if auto.get(name, False):
                self.services[name].start()
                time.sleep(0.7)

    def shutdown(self) -> None:
        self.stop_all()
        self.shutdown_event.set()


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

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/status":
                self._json(CONSOLE.status())
                return
            if path == "/api/reference/status":
                self._json(CONSOLE.reference.status())
                return
            if path == "/api/reference/browse":
                self._json(CONSOLE.reference.browse())
                return
            if path == "/api/health":
                self._json({"status": "READY", "service": "validation-console"})
                return
            if path == "/" or path == "/index.html":
                data = (WEB_ROOT / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith("/static/"):
                name = path.removeprefix("/static/")
                safe = (WEB_ROOT / name).resolve()
                if WEB_ROOT.resolve() not in safe.parents:
                    self._json({"error": "invalid path"}, 400)
                    return
                if not safe.is_file():
                    self._json({"error": "not found"}, 404)
                    return
                content_type = "text/css" if safe.suffix == ".css" else "text/javascript"
                data = safe.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            body = self._read_json()
            if path == "/api/system/start":
                self._json(CONSOLE.start_all())
                return
            if path == "/api/system/stop":
                self._json(CONSOLE.stop_all())
                return
            for action in ("start", "stop", "restart"):
                prefix = f"/api/service/"
                if path.startswith(prefix) and path.endswith("/" + action):
                    name = path[len(prefix): -len(action) - 1]
                    if name not in CONSOLE.services:
                        self._json({"success": False, "error": "unknown service"}, 404)
                        return
                    result = getattr(CONSOLE.services[name], action)()
                    self._json(result)
                    return
            if path == "/api/reference/source":
                name = str(body.get("name", ""))
                folder = str(body.get("folder", ""))
                if name not in ("WRS", "PANS", "NSC") or not folder:
                    self._json({"success": False, "error": "name and folder are required"}, 400)
                    return
                self._json({"success": True, "database": CONSOLE.reference.set_source(name, folder)})
                return
            if path == "/api/reference/validate":
                name = str(body.get("name", ""))
                self._json(CONSOLE.reference.validate(name))
                return
            if path == "/api/reference/reload":
                # Reference data is opened by the Parser process. A reload is
                # therefore a controlled parser restart after the source check.
                name = str(body.get("name", ""))
                check = CONSOLE.reference.validate(name)
                if not check["success"]:
                    self._json(check, 400)
                    return
                result = CONSOLE.services["parser"].restart()
                self._json({"success": True, "message": "Parser restarted to reopen reference stores.", "result": result})
                return
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._json({"success": False, "error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        return


def run():
    cfg = load_config()
    host = str((cfg.get("server", {}) or {}).get("host", "127.0.0.1"))
    port = int((cfg.get("server", {}) or {}).get("port", 8080))
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True

    def stop_handler(signum=None, frame=None):
        CONSOLE.shutdown()
        try:
            server.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)

    CONSOLE.startup()
    print(f"[VALIDATION] Console: http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        CONSOLE.shutdown()
        server.server_close()


if __name__ == "__main__":
    run()
