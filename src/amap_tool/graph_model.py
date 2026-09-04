from __future__ import annotations
import copy, math, re
from .geometry import nearest_polyline_segment
from .quality_checks import check

class GraphModel:
    def __init__(self, data):
        self.data = copy.deepcopy(data); self.data.setdefault('ignore_regions', []); self.undo=[]; self.redo=[]
    def snapshot(self): return copy.deepcopy(self.data)
    def _commit(self, before): self.undo.append(before); self.redo.clear()
    def restore(self, snapshot): self.data=copy.deepcopy(snapshot)
    def undo_once(self):
        if not self.undo: return False
        self.redo.append(self.snapshot()); self.restore(self.undo.pop()); return True
    def redo_once(self):
        if not self.redo: return False
        self.undo.append(self.snapshot()); self.restore(self.redo.pop()); return True
    def allocate_id(self, prefix):
        collection={'n':'nodes','e':'edges','i':'ignore_regions'}[prefix]
        nums=[int(m.group(1)) for o in self.data.get(collection,[]) if (m:=re.fullmatch(rf'{re.escape(prefix)}(\d+)', str(o.get('id',''))))]
        return f'{prefix}{max(nums, default=0)+1:06d}'
    def next_node_id(self): return self.allocate_id('n')
    def next_edge_id(self): return self.allocate_id('e')
    def next_ignore_id(self): return self.allocate_id('i')
    def move_node(self,nid,x,y):
        b=self.snapshot(); n=next(n for n in self.data['nodes'] if n['id']==nid); n.update(x=float(x),y=float(y))
        for e in self.data['edges']:
            if e['start_node']==nid:e['polyline'][0]=[float(x),float(y)]
            if e['end_node']==nid:e['polyline'][-1]=[float(x),float(y)]
        self._commit(b)
    def insert_point(self,eid,index,point):
        b=self.snapshot(); self.edge(eid)['polyline'].insert(index,[float(point[0]),float(point[1])]); self._commit(b)
    def delete_point(self,eid,index):
        e=self.edge(eid)
        if index<=0 or index>=len(e['polyline'])-1:return False
        b=self.snapshot(); e['polyline'].pop(index); self._commit(b); return True
    def edge(self,eid): return next(e for e in self.data['edges'] if e['id']==eid)
    def set_attr(self,kind,ident,key,value):
        b=self.snapshot(); obj=self.edge(ident) if kind=='edge' else next(n for n in self.data['nodes'] if n['id']==ident) if kind=='node' else next(r for r in self.data['ignore_regions'] if r['id']==ident); obj[key]=value; self._commit(b)
    def delete_edge(self,eid): b=self.snapshot(); self.data['edges']=[e for e in self.data['edges'] if e['id']!=eid]; self._commit(b)
    def add_ignore(self,polygon):
        b=self.snapshot(); iid=self.next_ignore_id(); self.data['ignore_regions'].append({'id':iid,'polygon':copy.deepcopy(polygon),'reason':'cannot_determine'}); self._commit(b); return iid
    def delete_ignore(self,iid): b=self.snapshot(); self.data['ignore_regions']=[r for r in self.data['ignore_regions'] if r['id']!=iid]; self._commit(b)
    def split_edge(self,eid,index=None,point=None):
        before=self.snapshot(); e=self.edge(eid); poly=e['polyline']
        if point is None:
            if index is None or index<=0 or index>=len(poly)-1: raise ValueError('Split requires an interior point')
            split_index=index; split_point=list(poly[index])
        else:
            hit=nearest_polyline_segment(point,poly)
            if hit is None: raise ValueError('Edge has no splittable segment')
            i=hit['segment_index']; split_point=hit['projected_point']
            if hit['t']<=1e-6: split_index=i; split_point=list(poly[i])
            elif hit['t']>=1-1e-6: split_index=i+1; split_point=list(poly[i+1])
            else: split_index=i+1; poly.insert(split_index,split_point)
        if split_index<=0 or split_index>=len(poly)-1: raise ValueError('Split cannot occur at an edge endpoint')
        nid=self.next_node_id(); self.data['nodes'].append({'id':nid,'x':split_point[0],'y':split_point[1],'type':'continuation'})
        pos=self.data['edges'].index(e); left=copy.deepcopy(e); right=copy.deepcopy(e)
        edge_nums=[int(m.group(1)) for item in self.data['edges'] if (m:=re.fullmatch(r'e(\d+)', str(item.get('id',''))))]
        next_num=max(edge_nums, default=0)+1; left['id']=f'e{next_num:06d}'; right['id']=f'e{next_num+1:06d}'
        left['end_node']=nid; right['start_node']=nid; left['polyline']=poly[:split_index+1]; right['polyline']=poly[split_index:]; self.data['edges'][pos:pos+1]=[left,right]; self._commit(before); return nid
    def merge_nodes(self,a,b):
        if a==b:return False
        if any((e['start_node']==a and e['end_node']==b) or (e['start_node']==b and e['end_node']==a) for e in self.data['edges']): raise ValueError('Merge would create a self-loop edge.')
        before=self.snapshot(); keep=next(n for n in self.data['nodes'] if n['id']==a)
        for e in self.data['edges']:
            if e['start_node']==b:e['start_node']=a;e['polyline'][0]=[keep['x'],keep['y']]
            if e['end_node']==b:e['end_node']=a;e['polyline'][-1]=[keep['x'],keep['y']]
        self.data['nodes']=[n for n in self.data['nodes'] if n['id']!=b]; self._commit(before); return True
    def stats(self):
        d=self.data; out={'region_id':d['region']['region_id'],'node_count':len(d['nodes']),'edge_count':len(d['edges']),'total_path_length_px':0.0,'path_type_length_px':{},'visibility_length_px':{},'confidence_length_px':{},'ignore_region_count':len(d.get('ignore_regions',[]))}
        for e in d['edges']:
            L=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(e['polyline'],e['polyline'][1:])); out['total_path_length_px']+=L
            for k,f in [('path_type','path_type_length_px'),('visibility','visibility_length_px'),('confidence','confidence_length_px')]:out[f][e.get(k,'unknown')]=out[f].get(e.get(k,'unknown'),0)+L
        out['warnings']=check(d); out['warning_count']=len(out['warnings']); return out
