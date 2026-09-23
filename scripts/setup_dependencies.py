#!/usr/bin/env python3
"""Validation dependency bootstrap.

Creates/uses a local .venv and a repository-local offline wheelhouse.

Online machine:
    python scripts/setup_dependencies.py
    # downloads required wheels into offline/wheels and installs them

Offline machine:
    python scripts/setup_dependencies.py
    # uses offline/wheels if present; no Internet is required

The same command is therefore suitable before start_all. If packages are
already installed in .venv it does nothing. If a package is missing it first
tries the local wheelhouse; if the wheelhouse is incomplete and Internet is
available it downloads the missing wheels, then installs everything locally.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
WHEELHOUSE = ROOT / "offline" / "wheels"
VENV = ROOT / ".venv"
REQUIREMENTS = [
    ROOT / "router" / "requirements.txt",
    ROOT / "parser" / "requirements.txt",
    ROOT / "forwarder" / "requirements.txt",
    ROOT / "console" / "requirements.txt",
]
REQUIRED_MODULES = {
    "yaml": "PyYAML",
    "rocksdb": "amulet-rocksdb",
    "paramiko": "paramiko",
}

def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    print("[DEPS]", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, check=check)

def python_in_venv() -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"

def ensure_venv() -> Path:
    py = python_in_venv()
    if py.exists():
        return py
    print(f"[DEPS] Creating local virtual environment: {VENV}")
    venv.EnvBuilder(with_pip=True, clear=False).create(VENV)
    if not py.exists():
        raise RuntimeError(f"Virtual environment Python was not created: {py}")
    return py

def installed_missing(py: Path) -> list[str]:
    code = (
        "import importlib.util;"
        "mods=" + repr(list(REQUIRED_MODULES)) + ";"
        "print(' '.join(m for m in mods if importlib.util.find_spec(m) is None))"
    )
    out = subprocess.check_output([str(py), "-c", code], cwd=ROOT, text=True).strip()
    return out.split() if out else []

def wheelhouse_has_any() -> bool:
    return WHEELHOUSE.is_dir() and any(WHEELHOUSE.glob("*.whl"))

def download_wheels(py: Path) -> bool:
    WHEELHOUSE.mkdir(parents=True, exist_ok=True)
    ok = True
    for req in REQUIREMENTS:
        result = run([
            str(py), "-m", "pip", "download",
            "--only-binary=:all:",
            "--dest", str(WHEELHOUSE),
            "-r", str(req),
        ], check=False)
        if result.returncode != 0:
            ok = False
            print(f"[DEPS] Could not download {req.name}.")
    return ok

def install_from_wheelhouse(py: Path) -> None:
    if not wheelhouse_has_any():
        raise RuntimeError(
            f"No offline wheels found in {WHEELHOUSE}. "
            "Run this script once on an Internet-connected machine first."
        )
    for req in REQUIREMENTS:
        run([
            str(py), "-m", "pip", "install",
            "--no-index",
            "--find-links", str(WHEELHOUSE),
            "-r", str(req),
        ])

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true",
                    help="Download/update wheels into offline/wheels.")
    ap.add_argument("--install", action="store_true",
                    help="Install only from offline/wheels; never use Internet.")
    ap.add_argument("--check", action="store_true",
                    help="Only check the local environment.")
    args = ap.parse_args()

    print(f"[DEPS] Platform: {platform.platform()}")
    print(f"[DEPS] Python: {sys.version.split()[0]}")
    py = ensure_venv()

    if args.check:
        missing = installed_missing(py)
        if missing:
            print("[DEPS] Missing:", ", ".join(missing))
            return 2
        print("[DEPS] PASS: required modules available in .venv")
        return 0

    if args.download:
        if not download_wheels(py):
            print("[DEPS] WARNING: one or more downloads failed.")
        if wheelhouse_has_any():
            install_from_wheelhouse(py)
        else:
            raise RuntimeError("No wheels were downloaded.")
    elif args.install:
        install_from_wheelhouse(py)
    else:
        missing = installed_missing(py)
        if missing:
            print("[DEPS] Missing modules:", ", ".join(missing))
            print("[DEPS] Trying existing offline/wheels first.")
            if wheelhouse_has_any():
                try:
                    install_from_wheelhouse(py)
                except subprocess.CalledProcessError:
                    print("[DEPS] Local wheelhouse is incomplete/incompatible.")
                    print("[DEPS] Trying Internet download...")
                    if not download_wheels(py):
                        raise RuntimeError(
                            "Dependencies are missing, offline/wheels is incomplete, "
                            "and Internet download failed. Put the correct wheels "
                            "in offline/wheels and rerun."
                        )
                    install_from_wheelhouse(py)
            else:
                print("[DEPS] No local wheelhouse. Trying Internet download...")
                if not download_wheels(py):
                    raise RuntimeError(
                        "Dependencies are missing and Internet download failed. "
                        "Run this script on an Internet-connected machine or copy "
                        "the offline/wheels directory from one."
                    )
                install_from_wheelhouse(py)
        else:
            print("[DEPS] PASS: required modules already installed.")

    missing = installed_missing(py)
    if missing:
        raise RuntimeError("Dependency installation incomplete: " + ", ".join(missing))
    print("[DEPS] PASS: Validation runtime dependencies ready.")
    print(f"[DEPS] Python: {py}")
    print(f"[DEPS] Wheelhouse: {WHEELHOUSE}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
