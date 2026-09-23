"""Launch one Validation service as an independent background process.

Used by the Windows all-services launcher so Router, Parser, Forwarder and
Console share the single launcher terminal while their actual service
processes run independently with file-backed logs and PID files.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=["router", "parser", "forwarder", "console"])
    ap.add_argument("module")
    ap.add_argument("module_args", nargs=argparse.REMAINDER)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    log_dir = root / "logs"
    run_dir = root / "run"
    log_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)

    pid_file = run_dir / f"{args.name}.pid"
    log_file = log_dir / f"{args.name}.log"

    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text(encoding="utf-8").strip())
            if old_pid > 0:
                if os.name == "nt":
                    check = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {old_pid}", "/NH"],
                        capture_output=True, text=True, check=False,
                    )
                    if str(old_pid) in check.stdout:
                        print(f"[VALIDATION] {args.name} already running (PID {old_pid})")
                        return 0
                else:
                    os.kill(old_pid, 0)
                    print(f"[VALIDATION] {args.name} already running (PID {old_pid})")
                    return 0
        except (ValueError, OSError):
            pass
        pid_file.unlink(missing_ok=True)

    env = os.environ.copy()
    env["VALIDATION_HOME"] = str(root)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")

    command = [sys.executable, "-m", args.module, *args.module_args]
    with log_file.open("a", encoding="utf-8", buffering=1) as log:
        kwargs = dict(
            cwd=str(root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        if os.name == "nt":
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )
        else:
            kwargs["start_new_session"] = True

        process = subprocess.Popen(command, **kwargs)

    pid_file.write_text(str(process.pid), encoding="utf-8")
    print(f"[VALIDATION] {args.name} started (PID {process.pid})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
