#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.region_grid import build_grid
from amap_tool.mercator import meters_per_pixel
def main():
 p=argparse.ArgumentParser(); p.add_argument('--west',type=float,required=True);p.add_argument('--south',type=float,required=True);p.add_argument('--east',type=float,required=True);p.add_argument('--north',type=float,required=True);p.add_argument('--zoom',type=int,default=19);p.add_argument('--width',type=int,default=1024);p.add_argument('--height',type=int,default=1024);p.add_argument('--overlap',type=float,default=.15);p.add_argument('--region_id',required=True);p.add_argument('--out_dir',type=Path,required=True);p.add_argument('--confirm_threshold',type=int,default=100);p.add_argument('--yes',action='store_true'); a=p.parse_args(); specs,rows,cols=build_grid(a.west,a.south,a.east,a.north,a.zoom,a.width,a.height,a.overlap); total=len(specs)
 actual={'west':min(s.west for s in specs),'south':min(s.south for s in specs),'east':max(s.east for s in specs),'north':max(s.north for s in specs)}
 mid=(a.north+a.south)/2; mpp=meters_per_pixel(mid,a.zoom)
 from amap_tool.mercator import lon_to_x,lat_to_y
 extra={'west_extra_m':max(0,lon_to_x(a.west,a.zoom)-lon_to_x(actual['west'],a.zoom))*mpp,'east_extra_m':max(0,lon_to_x(actual['east'],a.zoom)-lon_to_x(a.east,a.zoom))*mpp,'north_extra_m':max(0,lat_to_y(a.north,a.zoom)-lat_to_y(actual['north'],a.zoom))*mpp,'south_extra_m':max(0,lat_to_y(actual['south'],a.zoom)-lat_to_y(a.south,a.zoom))*mpp}
 print(f'Region Plan\nRegion ID: {a.region_id}\nZoom: {a.zoom}\nTile: {a.width} x {a.height}\nOverlap: {a.overlap:.0%}\nRows: {rows}\nCols: {cols}\nTotal tiles: {total}\nEstimated request count: {total}')
 print('Requested BBOX:',{'west':a.west,'south':a.south,'east':a.east,'north':a.north}); print('Actual Coverage BBOX:',actual); print('Extra coverage (m):',{k:round(v,3) for k,v in extra.items()})
 if total>a.confirm_threshold and not a.yes and input(f'This region will generate {total} tiles. Continue? [y/N] ').lower()!='y': return 2
 a.out_dir.mkdir(parents=True,exist_ok=True); tiles=[]
 for s in specs:
  name=f'{a.region_id}_r{s.row:03d}_c{s.col:03d}_z{a.zoom}.png';tiles.append({'image_id':name[:-4],'row':s.row,'col':s.col,'center_lat':s.center_lat,'center_lon':s.center_lon,'north':s.north,'south':s.south,'east':s.east,'west':s.west,'global_x':s.global_x,'global_y':s.global_y,'planned_output_file':name})
 (a.out_dir/'collection_plan.json').write_text(json.dumps({'region_id':a.region_id,'zoom':a.zoom,'tile_width':a.width,'tile_height':a.height,'overlap':a.overlap,'bbox':{'west':a.west,'south':a.south,'east':a.east,'north':a.north},'actual_coverage_bbox':actual,'extra_coverage_m':extra,'rows':rows,'cols':cols,'total_tiles':total,'tiles':tiles},ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': raise SystemExit(main())
