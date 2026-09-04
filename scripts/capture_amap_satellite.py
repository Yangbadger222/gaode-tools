#!/usr/bin/env python3
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from amap_tool.capture import capture_one, write_metadata

def main():
    p = argparse.ArgumentParser(description="Capture one AMap satellite image")
    p.add_argument("--lat", type=float, required=True); p.add_argument("--lon", type=float, required=True)
    p.add_argument("--zoom", type=int, required=True); p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024); p.add_argument("--out", required=True)
    p.add_argument("--image-id", default="image")
    a = p.parse_args()
    if a.width <= 0 or a.height <= 0 or not 1 <= a.zoom <= 22: p.error("invalid size or zoom")
    row = capture_one(a.lat, a.lon, a.zoom, a.out, a.width, a.height, a.image_id)
    print(f"Captured z{a.zoom}: {a.out}")
    write_metadata([row], str(Path(a.out).with_suffix(".csv")))

if __name__ == "__main__": main()
