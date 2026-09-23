"""Stop the Validation standalone feed processes."""
from __future__ import annotations
import signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIDS=ROOT/"runtime/pids"
for pidfile in sorted(PIDS.glob("*.pid")):
    try:
        pid=int(pidfile.read_text().strip())
        try: __import__("os").kill(pid,signal.SIGTERM)
        except OSError: pass
    finally:
        pidfile.unlink(missing_ok=True)
print("Validation feed processes stopped.")
