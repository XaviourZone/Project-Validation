#!/usr/bin/env python3
from __future__ import annotations
import subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];WHEELS=ROOT/"offline"/"wheels";WHEELS.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,"-m","pip","download","--only-binary=:all:","--dest",str(WHEELS),"-r",str(ROOT/"requirements.txt")],check=True)
print("Offline wheels written to",WHEELS)
