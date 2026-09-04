from __future__ import annotations
import copy, math
from .quality_checks import check

class GraphModel:
 def __init__(self,data): self.data=copy.deepcopy(data); self.undo=[]; self.redo=[]
 def snapshot(self): return copy.deepcopy(self.data)
 def _commit(self,before): self.undo.append(before); self.redo.clear()
 def restore(self,s): self.data=copy.deepcopy(s)
 def undo_once(self):
  if self.undo: self.redo.append(self.snapshot()); self.restore(self.undo.pop()); return True
  return False
 def redo_once(self):
  if self.redo: self.undo.append(self.snapshot()); self.restore(self.redo.pop()); return True
  return False
 def move_node(self,nid,x,y):
  b=self.snapshot(); n=next(n for n in self.data['nodes'] if n['id']==nid); n.update(x=x,y=y)
  for e in self.data['edges']:
   if e['start_node']==nid: e['polyline'][0]=[x,y]
   if e['end_node']==nid: e['polyline'][-1]=[x,y]
  self._commit(b)
 def insert_point(self,eid,index,point): b=self.snapshot(); e=self.edge(eid); e['polyline'].insert(index,list(point)); self._commit(b)
 def delete_point(self,eid,index):
  e=self.edge(eid)
  if index<=0 or index>=len(e['polyline'])-1: return False
  b=self.snapshot(); e['polyline'].pop(index); self._commit(b); return True
 def edge(self,eid): return next(e for e in self.data['edges'] if e['id']==eid)
 def set_attr(self, kind, ident, key, value):
  b=self.snapshot(); obj=self.edge(ident) if kind=='edge' else next(n for n in self.data['nodes'] if n['id']==ident); obj[key]=value; self._commit(b)
 def delete_edge(self,eid): b=self.snapshot(); self.data['edges']=[e for e in self.data['edges'] if e['id']!=eid]; self._commit(b)
 def add_ignore(self, polygon): b=self.snapshot(); iid=f"i{len(self.data.get('ignore_regions',[]))+1:06d}"; self.data.setdefault('ignore_regions',[]).append({'id':iid,'polygon':polygon,'reason':'cannot_determine'}); self._commit(b); return iid
 def delete_ignore(self,iid): b=self.snapshot();self.data['ignore_regions']=[x for x in self.data.get('ignore_regions',[]) if x['id']!=iid];self._commit(b)
 def split_edge(self,eid,index):
  b=self.snapshot(); e=self.edge(eid); p=e['polyline'][index]; nid=f"n{len(self.data['nodes'])+1:06d}"; self.data['nodes'].append({'id':nid,'x':p[0],'y':p[1],'type':'junction'}); i=self.data['edges'].index(e); base=copy.deepcopy(e); a,bx=copy.deepcopy(base),copy.deepcopy(base); a['id']=f"{eid}_a"; bx['id']=f"{eid}_b"; a['end_node']=nid; bx['start_node']=nid; a['polyline']=base['polyline'][:index+1]; bx['polyline']=base['polyline'][index:]; self.data['edges'][i:i+1]=[a,bx]; self._commit(b); return nid
 def merge_nodes(self,a,b):
  if a==b:return False
  before=self.snapshot(); keep=a; n1=next(n for n in self.data['nodes'] if n['id']==a); self.data['nodes']=[n for n in self.data['nodes'] if n['id']!=b]
  for e in self.data['edges']:
   if e['start_node']==b:e['start_node']=keep;e['polyline'][0]=[n1['x'],n1['y']]
   if e['end_node']==b:e['end_node']=keep;e['polyline'][-1]=[n1['x'],n1['y']]
  self._commit(before); return True
 def stats(self):
  d=self.data; out={'region_id':d['region']['region_id'],'node_count':len(d['nodes']),'edge_count':len(d['edges']),'total_path_length_px':0.0,'path_type_length_px':{},'visibility_length_px':{},'confidence_length_px':{},'ignore_region_count':len(d.get('ignore_regions',[]))}
  for e in d['edges']:
   L=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(e['polyline'],e['polyline'][1:])); out['total_path_length_px']+=L
   for k,field in [('path_type','path_type_length_px'),('visibility','visibility_length_px'),('confidence','confidence_length_px')]: out[field][e.get(k,'unknown')]=out[field].get(e.get(k,'unknown'),0)+L
  out['warnings']=check(d); out['warning_count']=len(out['warnings']); return out
