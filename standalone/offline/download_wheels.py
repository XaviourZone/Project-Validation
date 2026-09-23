#!/usr/bin/env python3
"""Download Linux-targeted wheels on an Internet-connected staging machine."""
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
WHEELS=ROOT/"offline"/"wheels";WHEELS.mkdir(parents=True,exist_ok=True)
ap=argparse.ArgumentParser()
ap.add_argument("--platform",default="manylinux_2_17_x86_64",help="target wheel platform for final Ubuntu host")
ap.add_argument("--python-version",default="3.13",help="target Python version, e.g. 3.13")
args=ap.parse_args()
abi="cp"+args.python_version.replace(".","")
cmd=[sys.executable,"-m","pip","download","--only-binary=:all:","--dest",str(WHEELS),
     "--platform",args.platform,"--python-version",args.python_version,"--implementation","cp","--abi",abi,
     "-r",str(ROOT/"requirements.txt")]
print(" ".join(cmd))
subprocess.run(cmd,check=True)
print("Offline wheels written to",WHEELS)
