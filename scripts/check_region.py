#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from PIL import Image
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.paths import resolve_data_path
def main():
 p=argparse.ArgumentParser();p.add_argument('--region',required=True);p.add_argument('--tolerance',type=float,default=1e-6);a=p.parse_args(); r=Path(a.region); d=json.loads(r.read_text()); base=r.parent; tiles=d.get('tiles',[]); missing=invalid=wrong=0; ids=[]; seen=set()
 for t in tiles:
  ids.append(t.get('image_id')); f=resolve_data_path(t.get('output_file',''),r,Path(__file__).resolve().parents[1])
  if not f.exists(): missing+=1; continue
  try:
   im=Image.open(f); im.verify(); im=Image.open(f)
   if im.size!=(d['tile_width'],d['tile_height']): wrong+=1
  except Exception: invalid+=1
 dup=len(ids)-len(set(ids)); geom=[]; expected=d['overlap']; by={(int(t['row']),int(t['col'])):t for t in tiles}
 print('Region Integrity Check'); print(f"Expected tiles: {d.get('rows',0)*d.get('cols',0)}");print(f'Found: {len(tiles)-missing}');print(f'Missing: {missing}');print(f'Invalid PNG: {invalid}');print(f'Wrong dimensions: {wrong}');print(f'Duplicate IDs: {dup}'); print(f'Expected overlap: {expected:.4f}')
 for rr in range(d['rows']):
  for cc in range(d['cols']-1):
   x1=float(by[(rr,cc)]['global_x']);x2=float(by[(rr,cc+1)]['global_x']);ov=1-(x2-x1)/d['tile_width'];ok=abs(ov-expected)<=a.tolerance;geom.append(ok);print(f'Horizontal r{rr}c{cc} <-> r{rr}c{cc+1}: {ov:.4f} '+('PASS' if ok else 'FAIL'))
 for rr in range(d['rows']-1):
  for cc in range(d['cols']):
   y1=float(by[(rr,cc)]['global_y']);y2=float(by[(rr+1,cc)]['global_y']);ov=1-(y2-y1)/d['tile_height'];ok=abs(ov-expected)<=a.tolerance;geom.append(ok);print(f'Vertical r{rr}c{cc} <-> r{rr+1}c{cc}: {ov:.4f} '+('PASS' if ok else 'FAIL'))
 bad=any((missing,invalid,wrong,dup)) or not all(geom); print('PASS' if not bad else 'FAIL'); return 1 if bad else 0
if __name__=='__main__': raise SystemExit(main())
