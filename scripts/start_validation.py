"""Start the Validation database manager/console."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=="__main__":
    env=os.environ.copy(); env["VALIDATION_HOME"]=str(ROOT)
    subprocess.run([sys.executable,str(ROOT/"scripts/database_manager.py")],cwd=ROOT,env=env,check=False)
