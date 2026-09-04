from __future__ import annotations
from dataclasses import dataclass, asdict
from .mercator import lon_to_x, lat_to_y, x_to_lon, y_to_lat

@dataclass
class TileSpec:
    row: int; col: int; center_lat: float; center_lon: float
    north: float; south: float; east: float; west: float; global_x: float=0; global_y: float=0

def build_grid(west, south, east, north, zoom=19, width=1024, height=1024, overlap=.15):
    if not (west < east and south < north): raise ValueError('bbox must satisfy west<east and south<north')
    if not (0 <= overlap < 1): raise ValueError('overlap must be in [0,1)')
    x0,x1=lon_to_x(west,zoom),lon_to_x(east,zoom); y0,y1=lat_to_y(north,zoom),lat_to_y(south,zoom)
    sx,sy=width*(1-overlap),height*(1-overlap)
    cols=max(1,int(__import__('math').ceil((x1-x0-width)/sx)+1)); rows=max(1,int(__import__('math').ceil((y1-y0-height)/sy)+1))
    specs=[]
    for r in range(rows):
      for c in range(cols):
        # Keep a strictly regular grid. The final row/column may extend beyond
        # the requested bbox; clamping its center would change the overlap.
        cx=x0+width/2+c*sx; cy=y0+height/2+r*sy
        specs.append(TileSpec(r,c,y_to_lat(cy,zoom),x_to_lon(cx,zoom),y_to_lat(cy-height/2,zoom),y_to_lat(cy+height/2,zoom),x_to_lon(cx+width/2,zoom),x_to_lon(cx-width/2,zoom),c*sx,r*sy))
    return specs, rows, cols
