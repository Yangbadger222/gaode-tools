#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from PIL import Image,ImageDraw
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from amap_tool.paths import resolve_data_path
def main():
 p=argparse.ArgumentParser();p.add_argument('--region',required=True);a=p.parse_args(); r=Path(a.region);d=json.loads(r.read_text()); scale=0.25; W=int((max((t.get('global_x',t['col']*d['tile_width']*(1-d['overlap']))+d['tile_width'] for t in d['tiles']),default=0))*scale);H=int((max((t.get('global_y',t['row']*d['tile_height']*(1-d['overlap']))+d['tile_height'] for t in d['tiles']),default=0))*scale); out=Image.new('RGB',(max(1,W),max(1,H)),'#ddd'); grid=Image.new('RGBA',out.size,(0,0,0,0)); dr=ImageDraw.Draw(grid)
 for t in d['tiles']:
  f=resolve_data_path(t.get('output_file',''),r,Path(__file__).resolve().parents[1]);
  if not f.exists(): continue
  im=Image.open(f).convert('RGB').resize((int(d['tile_width']*scale),int(d['tile_height']*scale))); x=int(t.get('global_x',t['col']*d['tile_width']*(1-d['overlap']))*scale); y=int(t.get('global_y',t['row']*d['tile_height']*(1-d['overlap']))*scale); out.paste(im,(x,y)); dr.rectangle((x,y,x+im.width,y+im.height),outline=(255,255,0,120),width=1); dr.text((x+3,y+3),f"r{t['row']:02d}c{t['col']:02d}",fill=(255,255,0,220))
 out.save(r.parent/'preview_mosaic.jpg',quality=90); Image.alpha_composite(out.convert('RGBA'),grid).convert('RGB').save(r.parent/'preview_grid.jpg',quality=90); print('wrote preview_mosaic.jpg and preview_grid.jpg')
if __name__=='__main__': main()
