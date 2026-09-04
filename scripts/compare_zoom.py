#!/usr/bin/env python3
import argparse,csv,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.capture import capture_one,write_metadata
def main():
 p=argparse.ArgumentParser(); p.add_argument('--locations',type=Path,required=True); p.add_argument('--out_dir',type=Path,required=True); p.add_argument('--zooms',nargs='+',type=int,default=[18,19]); a=p.parse_args(); rows=[]; a.out_dir.mkdir(parents=True,exist_ok=True)
 with a.locations.open() as f:
  data=list(csv.DictReader(f)) if a.locations.suffix.lower()=='.csv' else __import__('yaml').safe_load(f)['locations']
 for x in data:
  ident=x['id']
  for z in a.zooms:
   out=a.out_dir/ident/f'z{z}.png'; out.parent.mkdir(parents=True,exist_ok=True); rows.append(capture_one(float(x['lat']),float(x['lon']),z,out,1024,1024,f'{ident}_z{z}'))
 write_metadata(rows,a.out_dir/'metadata.csv')
if __name__=='__main__': main()
