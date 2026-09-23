"""Build WRS/PANS/NSC reference stores from operator-selected source folders.

Runtime reference stores remain RocksDB. The importer builds a fresh store and
swaps it into place only after all source files have been read successfully.
"""
from __future__ import annotations
import csv, hashlib, json, os, re, shutil, time, uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable
from shared.storage.rocksdb_store import RocksDBStore

def clean_column(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "none": return ""
    text = re.sub(r"[\s\-./\\()\[\]]+", "_", text).upper().strip("_")
    return text or "UNKNOWN_COLUMN"

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()

def csv_rows(path: Path):
    last = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as f:
                reader = csv.reader(f)
                try: raw = next(reader)
                except StopIteration: return
                headers, used = [], set()
                for item in raw:
                    base = clean_column(item)
                    if not base: headers.append(""); continue
                    name, n = base, 1
                    while name in used: n += 1; name = f"{base}_{n}"
                    used.add(name); headers.append(name)
                for row in reader:
                    values = list(row[:len(headers)])
                    values.extend([""] * (len(headers) - len(values)))
                    yield {h: values[i].strip() for i, h in enumerate(headers) if h}
            return
        except UnicodeDecodeError as exc:
            last = exc
    raise UnicodeError(f"Unable to decode CSV {path}: {last}")

def wrs_table(filename: str, decode: bool) -> str:
    stem = Path(filename).stem.lower()
    if decode:
        for prefix in ("wrs.decode.", "decode_"):
            if stem.startswith(prefix): stem = stem[len(prefix):]; break
        return "wrs_decode_" + stem.replace(".", "_")
    if stem.startswith("wrs.datasets."): stem = stem[len("wrs.datasets."):]
    return "wrs_datasets_" + stem.replace(".", "_")

def flatten_xml(element: ET.Element, result=None):
    result = result or {}
    tag = element.tag.split("}")[-1]
    if element.text and element.text.strip():
        value = element.text.strip()
        existing = next((k for k in result if k.lower() == tag.lower()), None)
        result[existing or tag] = value if existing is None else f"{result[existing]}; {value}"
    for child in element: flatten_xml(child, result)
    return result

def pans_table(root_tag: str):
    return {"VesselProfile":"pans_vespro","VoyageRegistration":"pans_calinf",
            "VesselCallNumber":"pans_calinv","BerthManagement":"pans_berman"}.get(root_tag)

def nsc_region(path: Path) -> str:
    """Resolve NSC EAST/WEST from the folder name or NSC_EAST/NSC_WEST filename."""
    for part in reversed(path.parts):
        token = re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_").upper()
        if token in {"EAST", "NSC_EAST"} or token.startswith("NSC_EAST_"):
            return "EAST"
        if token in {"WEST", "NSC_WEST"} or token.startswith("NSC_WEST_"):
            return "WEST"
    return "UNKNOWN"

def put_rows(store, namespace: str, rows: Iterable[dict[str, Any]], source_hash: str) -> int:
    batch, count = [], 0
    for index, row in enumerate(rows):
        batch.append((f"row:{source_hash}:{index}", dict(row)))
        if len(batch) >= 1000:
            store.put_many(namespace, batch); count += len(batch); batch.clear()
    if batch: store.put_many(namespace, batch); count += len(batch)
    return count

def fresh_target(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    return target.parent / f".{target.name}.build-{uuid.uuid4().hex}"

def write_manifest(target: Path, manifest: dict[str, Any]) -> None:
    (target / "REFERENCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

def swap_store(build: Path, target: Path) -> None:
    backup = target.parent / f".{target.name}.previous-{int(time.time())}"
    if target.exists(): os.replace(str(target), str(backup))
    try: os.replace(str(build), str(target))
    except Exception:
        if backup.exists() and not target.exists(): os.replace(str(backup), str(target))
        raise
    shutil.rmtree(backup, ignore_errors=True)

def _build_csv_store(name, db_name, source, target, files):
    build = fresh_target(target); store = RocksDBStore(build)
    manifest = {"database":name,"source_folder":str(source),"created_at":time.time(),"files":[],"tables":{},"rows":0}
    try:
        for path, is_decode in files:
            fh = file_hash(path); rows = csv_rows(path)
            table = wrs_table(path.name, is_decode) if name == "WRS" else "nsc_vessels"
            if name == "NSC":
                region = nsc_region(path)
                rows = (dict(row, SOURCE_REGION=region) for row in rows)
            loaded = put_rows(store, f"{db_name}/{table}", rows, fh)
            manifest["files"].append({"file":str(path),"sha256":fh,"rows":loaded,"table":table})
            manifest["tables"][table] = manifest["tables"].get(table,0) + loaded
            manifest["rows"] += loaded
        store.put("__reference__","manifest",manifest); store.close()
        write_manifest(build, manifest); swap_store(build, target); return manifest
    except Exception:
        try: store.close()
        except Exception: pass
        shutil.rmtree(build, ignore_errors=True); raise

def import_wrs(source: Path, target: Path):
    dirs = {p.name.casefold():p for p in source.iterdir() if p.is_dir()}
    datasets = dirs.get("datasets"); decode = dirs.get("decode") or dirs.get("decode files")
    if not datasets or not decode: raise ValueError("WRS source must contain Datasets and Decode/Decode files folders")
    files = [(p,False) for p in sorted(datasets.rglob("*.csv"))] + [(p,True) for p in sorted(decode.rglob("*.csv"))]
    if not files: raise ValueError("No WRS CSV files found under Datasets/Decode")
    return _build_csv_store("WRS","wrs",source,target,files)

def import_pans(source: Path, target: Path):
    files = sorted(source.rglob("*.xml"))
    if not files: raise ValueError("No PANS XML files found in the selected source folder")
    build = fresh_target(target); store = RocksDBStore(build)
    manifest = {"database":"PANS","source_folder":str(source),"created_at":time.time(),"files":[],"tables":{},"rows":0}
    try:
        for path in files:
            fh=file_hash(path); root=ET.parse(path).getroot(); table=pans_table(root.tag.split("}")[-1])
            if not table: continue
            row={str(k).replace("-","_").replace(" ","_"):str(v) for k,v in flatten_xml(root).items()}
            loaded=put_rows(store,f"pans/{table}",[row],fh)
            manifest["files"].append({"file":str(path),"sha256":fh,"rows":loaded,"table":table})
            manifest["tables"][table]=manifest["tables"].get(table,0)+loaded; manifest["rows"]+=loaded
        if not manifest["files"]: raise ValueError("No supported PANS XML root elements found")
        store.put("__reference__","manifest",manifest); store.close(); write_manifest(build,manifest); swap_store(build,target); return manifest
    except Exception:
        try: store.close()
        except Exception: pass
        shutil.rmtree(build,ignore_errors=True); raise

def import_nsc(source: Path, target: Path):
    files = sorted(source.rglob("*.csv"))
    if not files:
        raise ValueError("No NSC CSV files found in the selected source folder")

    # The operator source is expected to contain both regional NSC inputs.
    # Accept either files named NSC_EAST/NSC_WEST (with any CSV suffix) or
    # EAST/WEST subfolders. Unrelated CSVs are not imported as NSC data.
    regional = [(p, nsc_region(p)) for p in files]
    east = [p for p, region in regional if region == "EAST"]
    west = [p for p, region in regional if region == "WEST"]
    if not east or not west:
        raise ValueError(
            "NSC source must contain both NSC_EAST and NSC_WEST CSV data "
            "(or EAST/WEST folders)."
        )

    selected = [(p, False) for p in east + west]
    return _build_csv_store("NSC", "nsc", source, target, selected)

def import_reference(name: str, source_folder: str|Path, target: str|Path):
    name=str(name).upper().strip(); source=Path(source_folder).expanduser().resolve(); target=Path(target).expanduser().resolve()
    if not source.is_dir(): raise ValueError(f"Reference source folder does not exist: {source}")
    if name=="WRS": return import_wrs(source,target)
    if name=="PANS": return import_pans(source,target)
    if name=="NSC": return import_nsc(source,target)
    raise ValueError(f"Unsupported reference database: {name}")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser(description="Build a Validation RocksDB reference store")
    ap.add_argument("database",choices=["WRS","PANS","NSC"]); ap.add_argument("source"); ap.add_argument("target")
    args=ap.parse_args(); print(json.dumps(import_reference(args.database,args.source,args.target),indent=2,ensure_ascii=False))
