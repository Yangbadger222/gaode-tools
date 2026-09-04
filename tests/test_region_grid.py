import json, math, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from amap_tool.mercator import x_to_lon,y_to_lat
from amap_tool.region_grid import build_grid

class GridTests(unittest.TestCase):
 def bbox_for_pixels(self,w,h,z=19): return (x_to_lon(100000,z),y_to_lat(100000+h,z),x_to_lon(100000+w,z),y_to_lat(100000,z))
 def test_smaller_one_tile(self): self.assertEqual(build_grid(*self.bbox_for_pixels(900,900))[2],1)
 def test_exact_one_tile(self): self.assertEqual(build_grid(*self.bbox_for_pixels(1024,1024))[2],1)
 def test_slightly_larger(self): self.assertEqual(build_grid(*self.bbox_for_pixels(1025,1025))[2],2)
 def test_fixed_stride_and_coverage(self):
  west,south,east,north=self.bbox_for_pixels(2500,2500); tiles,rows,cols=build_grid(west,south,east,north); self.assertEqual((rows,cols),(3,3)); s=1024*.85
  self.assertEqual([t.global_x for t in tiles if t.row==0],[0,s,2*s]); self.assertTrue(max(t.east for t in tiles)>=east); self.assertTrue(min(t.south for t in tiles)<=south)
  self.assertTrue(all(abs((b.global_x-a.global_x)-s)<1e-9 for a,b in zip(tiles[:2],tiles[1:3])))
 def test_roundtrip_geometry(self):
  tiles,_,_=build_grid(*self.bbox_for_pixels(2500,2500)); raw=json.loads(json.dumps([t.__dict__ for t in tiles])); self.assertEqual(raw[2]['global_x'],tiles[2].global_x)

if __name__=='__main__': unittest.main()
