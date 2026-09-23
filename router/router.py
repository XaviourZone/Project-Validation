from __future__ import annotations

import argparse
from pathlib import Path

def stable_file(path: Path, stable_seconds: float = 2.0) -> bool:
    # Placeholder only. Replace with the existing Validation stable-file logic
    # when the source implementation is available.
    return path.is_file()

def route_once(input_dir: Path, parser_spool: Path, pattern: str = "*.csv") -> int:
    parser_spool.mkdir(parents=True, exist_ok=True)
    routed = 0
    for src in sorted(input_dir.glob(pattern)):
        if not stable_file(src):
            continue
        dst = parser_spool / src.name
        if dst.exists():
            continue
        dst.write_bytes(src.read_bytes())
        routed += 1
    return routed

def main() -> None:
    ap = argparse.ArgumentParser(description="Project-Validation Router")
    ap.add_argument("--input", required=True)
    ap.add_argument("--parser-spool", required=True)
    ap.add_argument("--pattern", default="*.csv")
    args = ap.parse_args()
    print(f"routed={route_once(Path(args.input), Path(args.parser_spool), args.pattern)}")

if __name__ == "__main__":
    main()
