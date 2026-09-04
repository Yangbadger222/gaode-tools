#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from amap_tool.capture import capture_one
from amap_tool.region_grid import build_grid

def main():
 p=argparse.ArgumentParser();
 for n in ('west','south','east','north'): p.add_argument('--'+n,type=float,required=True)
 p.add_argument('--zoom',type=int,default=19); p.add_argument('--overlap',type=float,default=.15); p.add_argument('--region_id',required=True)
 p.add_argument('--out_dir',type=Path,required=True); p.add_argument('--width',type=int,default=1024); p.add_argument('--height',type=int,default=1024); p.add_argument('--resume',action='store_true'); p.add_argument('--retries',type=int,default=2)
 a=p.parse_args(); specs,rows,cols=build_grid(a.west,a.south,a.east,a.north,a.zoom,a.width,a.height,a.overlap); a.out_dir.mkdir(parents=True,exist_ok=True); allrows=[]; failed=[]
 if a.resume and (a.out_dir/'metadata.csv').exists():
  import csv
  with (a.out_dir/'metadata.csv').open(encoding='utf-8') as f: allrows=list(csv.DictReader(f))
 for s in specs:
  name=f'{a.region_id}_r{s.row:03d}_c{s.col:03d}_z{a.zoom}.png'; out=a.out_dir/name
  if a.resume and out.exists() and out.stat().st_size>0 and any(x.get('output_file')==str(out) or Path(x.get('output_file','')).name==name for x in allrows): print('skip',name); continue
  row=None
  for attempt in range(a.retries+1):
   try: row=capture_one(s.center_lat,s.center_lon,a.zoom,out,a.width,a.height,f'{a.region_id}_r{s.row:03d}_c{s.col:03d}_z{a.zoom}'); break
   except Exception as e:
    if attempt==a.retries: failed.append({'file':name,'error':str(e)}); print('FAILED',name,e)
    else: time.sleep(1.5*(attempt+1))
  if row:
   row.update(region_id=a.region_id,row=s.row,col=s.col,overlap=a.overlap,center_lat=s.center_lat,center_lon=s.center_lon,north=s.north,south=s.south,east=s.east,west=s.west,global_x=s.global_x,global_y=s.global_y,output_file=name); allrows.append(row); print('ok',name)
 fields=['image_id','region_id','row','col','source','map_type','center_lat','center_lon','lat','lon','zoom','width','height','overlap','global_x','global_y','capture_time','output_file','estimated_meters_per_pixel','estimated_ground_width_m','estimated_ground_height_m','north','south','east','west','api_mode','note']
 import csv
 with (a.out_dir/'metadata.csv').open('w',newline='',encoding='utf-8') as f: w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(allrows)
 region={'region_id':a.region_id,'source':'amap_js_api','map_type':'satellite','zoom':a.zoom,'tile_width':a.width,'tile_height':a.height,'overlap':a.overlap,'bbox':{'west':a.west,'south':a.south,'east':a.east,'north':a.north},'rows':rows,'cols':cols,'tiles':allrows,'failed_tiles':failed}
 (a.out_dir/'region.json').write_text(json.dumps(region,ensure_ascii=False,indent=2),encoding='utf-8')
 if failed: (a.out_dir/'failed_tiles.json').write_text(json.dumps(failed,indent=2),encoding='utf-8')
 print(f'completed: {len(allrows)}/{len(specs)} tiles; grid={rows}x{cols}')
 return 1 if failed else 0
if __name__=='__main__': raise SystemExit(main())
