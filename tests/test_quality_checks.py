import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from amap_tool.quality_checks import check

def base(edges,nodes):return {'region':{'region_id':'r'},'nodes':nodes,'edges':edges,'ignore_regions':[]}
def node(i,x,y,t='endpoint'):return {'id':i,'x':x,'y':y,'type':t}
def edge(i,a,b,p,**kw):return {'id':i,'start_node':a,'end_node':b,'polyline':p,'visibility':'visible','verification_source':'rgb_context',**kw}
def test_crossing_and_occluded():
 d=base([edge('e1','a','b',[[0,0],[10,10]]),edge('e2','c','d',[[0,10],[10,0]]),edge('e3','a','b',[[0,0],[10,0]],visibility='fully_occluded',verification_source='none')],[node('a',0,0),node('b',10,10),node('c',0,10),node('d',10,0)])
 w=check(d);assert any('intersection' in x for x in w);assert any('verification' in x for x in w)
def test_shared_crossing_and_boundary():
 d=base([edge('e1','a','j',[[0,0],[10,10]]),edge('e2','j','b',[[10,10],[10,0]])],[node('a',0,0),node('j',10,10,'junction'),node('b',10,0)])
 assert not any('intersection without' in x for x in check(d));region={'tiles':[{'global_x':0,'global_y':0}],'tile_width':100,'tile_height':100};assert any('boundary' in x.lower() for x in check(base([edge('e','a','b',[[0,0],[10,0]])],[node('a',0,0),node('b',10,0)]),region))
def test_invalid_and_duplicate_ids():
 d=base([edge('e1','missing','a',[[0,0],[1,0]]),edge('e1','a','a',[[1,0],[2,0]])],[node('a',1,0),node('a',1,0)])
 w=check(d);assert any('Duplicate node ID' in x for x in w);assert any('Duplicate edge ID' in x for x in w);assert any('Missing start' in x for x in w);assert any('Self-loop' in x for x in w)
