import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from amap_tool.geometry import closest_point_on_segment,distance_point_to_segment,nearest_polyline_segment,segments_intersect,point_in_polygon

def test_segment_projection_and_distance():
 p,t=closest_point_on_segment((5,3),(0,0),(10,0));assert p==[5.0,0.0] and t==0.5;assert distance_point_to_segment((5,3),(0,0),(10,0))==3
def test_projection_clamps_endpoints():
 assert closest_point_on_segment((-2,1),(0,0),(10,0))[0]==[0.0,0.0];assert closest_point_on_segment((12,1),(0,0),(10,0))[0]==[10.0,0.0]
def test_nearest_polyline_segment():
 h=nearest_polyline_segment((8,2),[[0,0],[10,0],[10,10]]);assert h['segment_index']==0 and h['projected_point']==[8.0,0.0]
def test_intersections():
 assert segments_intersect((0,0),(10,10),(0,10),(10,0));assert not segments_intersect((0,0),(1,0),(0,2),(1,2));assert segments_intersect((0,0),(1,0),(1,0),(1,1))
def test_point_in_polygon():
 poly=[[0,0],[10,0],[10,10],[0,10]];assert point_in_polygon((5,5),poly);assert not point_in_polygon((15,5),poly);assert point_in_polygon((0,5),poly)
