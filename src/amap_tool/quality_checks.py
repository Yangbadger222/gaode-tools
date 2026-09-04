from __future__ import annotations
import math
from .geometry import segments_intersect

def check(data, region=None, near=20, short=10):
    warnings=[]; raw_nodes=data.get('nodes',[]); nodes={n.get('id'):n for n in raw_nodes}; edges=data.get('edges',[]); ignores=data.get('ignore_regions',[])
    for kind, objs in [('node',raw_nodes),('edge',edges),('ignore',ignores)]:
        seen=set()
        for obj in objs:
            ident=obj.get('id')
            if ident in seen: warnings.append(f'Duplicate {kind} ID: {ident}')
            seen.add(ident)
    degree={n.get('id'):0 for n in raw_nodes}
    for e in edges:
        start,end=e.get('start_node'),e.get('end_node')
        if start not in nodes: warnings.append(f'Missing start node reference: {e.get("id","")} -> {start}')
        if end not in nodes: warnings.append(f'Missing end node reference: {e.get("id","")} -> {end}')
        if start==end: warnings.append(f'Self-loop edge: {e.get("id","")}')
        poly=e.get('polyline',[])
        if len(poly)<2: warnings.append(f'Invalid polyline (<2 points): {e.get("id","")}'); continue
        length=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(poly,poly[1:]))
        if length<short: warnings.append('Short edge: '+e.get('id',''))
        if e.get('visibility')=='fully_occluded' and e.get('verification_source') in (None,'','none'): warnings.append('Fully occluded edge has no supporting verification source: '+e.get('id',''))
        for nid in (start,end):
            if nid in degree: degree[nid]+=1
        for nid, point in ((start,poly[0]),(end,poly[-1])):
            if nid in nodes and math.hypot(nodes[nid].get('x',0)-point[0],nodes[nid].get('y',0)-point[1])>1e-3: warnings.append(f'Endpoint/polyline mismatch: {e.get("id","")} {nid}')
        for point in poly:
            if not all(math.isfinite(float(v)) for v in point): warnings.append(f'Invalid coordinate: {e.get("id","")}')
    canvas_w=canvas_h=None
    if region:
        tiles=region.get('tiles',[])
        if tiles:
            canvas_w=max(float(t.get('global_x',0))+float(region.get('tile_width',0)) for t in tiles); canvas_h=max(float(t.get('global_y',0))+float(region.get('tile_height',0)) for t in tiles)
    for i,a in enumerate(edges):
        for b in edges[i+1:]:
            shared=set((a.get('start_node'),a.get('end_node'))) & set((b.get('start_node'),b.get('end_node')))
            found=False
            for pa,pb in zip(a.get('polyline',[]),a.get('polyline',[])[1:]):
                for pc,pd in zip(b.get('polyline',[]),b.get('polyline',[])[1:]):
                    if segments_intersect(pa,pb,pc,pd): found=True; break
                if found: break
            if found and not shared: warnings.append(f'Edge intersection without shared junction: {a.get("id")}, {b.get("id")}')
    ends=[n for n in raw_nodes if n.get('type')=='endpoint']
    for i,a in enumerate(ends):
        for b in ends[i+1:]:
            if math.hypot(a.get('x',0)-b.get('x',0),a.get('y',0)-b.get('y',0))<near: warnings.append(f'Nearby disconnected endpoints detected: {a.get("id")}, {b.get("id")}')
    for n in raw_nodes:
        x,y=n.get('x',0),n.get('y',0); typ=n.get('type'); d=degree.get(n.get('id'),0)
        if not all(math.isfinite(float(v)) for v in (x,y)): warnings.append(f'Invalid node coordinate: {n.get("id")}')
        if typ=='continuation' and d!=2: warnings.append(f'Continuation node degree is {d}: {n.get("id")}')
        if typ=='junction' and d<3: warnings.append(f'Junction node degree is {d}: {n.get("id")}')
        if typ in ('endpoint','boundary') and d!=1: warnings.append(f'{typ.title()} node degree is {d}: {n.get("id")}')
        if canvas_w is not None:
            margin=20
            near_boundary=min(x,y,canvas_w-x,canvas_h-y)<=margin
            if typ=='endpoint' and near_boundary: warnings.append(f'Endpoint near region boundary; consider boundary type: {n.get("id")}')
            if typ=='boundary' and not near_boundary: warnings.append(f'Boundary node far from region boundary: {n.get("id")}')
    return warnings
