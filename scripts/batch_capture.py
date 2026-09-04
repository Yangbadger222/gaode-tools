#!/usr/bin/env python3
import argparse, csv, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from amap_tool.capture import capture_one, write_metadata

def main():
    p=argparse.ArgumentParser(description="Capture one location at multiple zooms, or YAML/CSV locations")
    p.add_argument("--lat", type=float); p.add_argument("--lon", type=float); p.add_argument("--zooms", type=int, nargs="+")
    p.add_argument("--out_dir", default="outputs/zoom_compare"); p.add_argument("--locations", type=Path)
    a=p.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True); rows=[]
    jobs=[]
    if a.locations:
        if a.locations.suffix.lower() in (".yaml",".yml"):
            import yaml
            data=yaml.safe_load(a.locations.read_text(encoding="utf-8")) or {}
            for x in data.get("locations",[]): jobs.append((x["id"],float(x["lat"]),float(x["lon"]),x.get("zooms",[x.get("zoom",18)])))
        else:
            with a.locations.open(newline="",encoding="utf-8") as f:
                for x in csv.DictReader(f): jobs.append((x["id"],float(x["lat"]),float(x["lon"]),[int(z) for z in x.get("zooms",x.get("zoom","18")).replace(";",",").split(",")]))
    elif a.lat is not None and a.lon is not None and a.zooms:
        jobs=[("campus",a.lat,a.lon,a.zooms)]
    else: p.error("provide --lat/--lon/--zooms or --locations")
    for ident,lat,lon,zooms in jobs:
        for z in zooms:
            target=out/f"{ident}_z{z}.png"
            try: rows.append(capture_one(lat,lon,int(z),target, image_id=f"{ident}_z{z}")); print(f"Captured {target}")
            except Exception as e: print(f"FAILED {ident} z{z}: {e}",file=sys.stderr)
    write_metadata(rows,out/"metadata.csv")
    if not rows: raise SystemExit("No images captured")

if __name__ == "__main__": main()
