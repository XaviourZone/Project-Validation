from __future__ import annotations

import argparse
import shutil
from pathlib import Path

def forward_once(xml_spool: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    forwarded = 0
    for src in sorted(xml_spool.glob("*.xml")):
        dst = destination / src.name
        if dst.exists():
            continue
        shutil.copy2(src, dst)
        forwarded += 1
    return forwarded

def main() -> None:
    ap = argparse.ArgumentParser(description="Project-Validation Forwarder")
    ap.add_argument("--input", required=True)
    ap.add_argument("--destination", required=True)
    args = ap.parse_args()
    print(f"forwarded={forward_once(Path(args.input), Path(args.destination))}")

if __name__ == "__main__":
    main()
