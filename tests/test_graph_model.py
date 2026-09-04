import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from amap_tool.graph_model import GraphModel
def g(): return {'region':{'region_id':'x'},'nodes':[{'id':'n1','x':0,'y':0,'type':'endpoint'},{'id':'n2','x':10,'y':0,'type':'endpoint'}],'edges':[{'id':'e1','start_node':'n1','end_node':'n2','polyline':[[0,0],[5,2],[10,0]],'path_type':'pedestrian_path','visibility':'visible','confidence':'high','verification_source':'rgb_context'}],'ignore_regions':[]}
def test_move_sync():
 m=GraphModel(g());m.move_node('n1',2,3);assert m.data['edges'][0]['polyline'][0]==[2,3]
def test_split_connected():
 m=GraphModel(g());n=m.split_edge('e1',1); assert len(m.data['edges'])==2; assert m.data['edges'][0]['end_node']==m.data['edges'][1]['start_node']==n
def test_insert_delete_undo():
 m=GraphModel(g());m.insert_point('e1',1,[3,1]);assert len(m.edge('e1')['polyline'])==4;m.delete_point('e1',1);m.undo_once();assert len(m.edge('e1')['polyline'])==4
def test_merge():
 m=GraphModel(g());m.merge_nodes('n1','n2'); assert len(m.data['nodes'])==1
