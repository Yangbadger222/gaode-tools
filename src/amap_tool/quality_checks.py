from __future__ import annotations
import math
def check(data, near=20, short=10):
 nodes={n['id']:n for n in data.get('nodes',[])}; warnings=[]
 ends=[n for n in nodes.values() if n.get('type')=='endpoint']
 for i,a in enumerate(ends):
  for b in ends[i+1:]:
   if math.hypot(a['x']-b['x'],a['y']-b['y'])<near: warnings.append('Nearby disconnected endpoints detected: %s, %s'%(a['id'],b['id']))
 for e in data.get('edges',[]):
  p=e.get('polyline',[]); length=sum(math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(p,p[1:]))
  if length<short: warnings.append('Short edge: '+e.get('id',''))
  if e.get('visibility')=='fully_occluded' and not e.get('verification_source'): warnings.append('Fully occluded edge missing verification_source: '+e.get('id',''))
 for i,a in enumerate(data.get('edges',[])):
  for b in data.get('edges',[])[i+1:]:
   for p in a.get('polyline',[]):
    for q in b.get('polyline',[]):
     if math.hypot(p[0]-q[0],p[1]-q[1])<3 and not ({a.get('start_node'),a.get('end_node')}&{b.get('start_node'),b.get('end_node')}): warnings.append('Edge intersection without shared junction: %s, %s'%(a.get('id'),b.get('id'))); break
 for n in data.get('nodes',[]):
  if n.get('type') in ('endpoint','boundary') and (n.get('x',0)<20 or n.get('y',0)<20): warnings.append('Possible boundary node: '+n.get('id',''))
 return warnings
