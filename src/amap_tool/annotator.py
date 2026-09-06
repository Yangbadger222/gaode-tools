from __future__ import annotations
import json, math, os, shutil, tempfile
from pathlib import Path
from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QPixmap, QPen, QBrush, QPainterPath, QAction
from PySide6.QtWidgets import QApplication,QMainWindow,QGraphicsView,QGraphicsScene,QDockWidget,QLabel,QComboBox,QFormLayout,QWidget,QTabWidget,QListWidget,QToolBar,QMessageBox
from .graph_model import GraphModel
from .quality_checks import check
from .geometry import nearest_polyline_segment, point_in_polygon
from .paths import resolve_data_path, portable_name

def atomic_save(data,path):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists(): shutil.copy2(path,str(path)+'.bak')
 fd,tmp=tempfile.mkstemp(prefix='.annotation-',suffix='.json',dir=path.parent);os.close(fd);Path(tmp).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');json.loads(Path(tmp).read_text(encoding='utf-8'));os.replace(tmp,path)

class View(QGraphicsView):
 def __init__(self,w):
  super().__init__();self.w=w;self.setScene(QGraphicsScene(self));self.setMouseTracking(True);self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse);self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse);self.setDragMode(QGraphicsView.DragMode.NoDrag);self.pan_origin=None
 def begin_pan(self,e):
  self.pan_origin=e.position().toPoint();self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
 def mousePressEvent(self,e):
  if e.button()==Qt.MouseButton.MiddleButton:
   self.begin_pan(e);e.accept();return
  self.w.click(self.mapToScene(e.position().toPoint()),e)
  # A selected node/control point starts a geometry edit. Every other left drag
  # in Select mode is a canvas pan, so users can inspect large tile mosaics.
  if e.button()==Qt.MouseButton.LeftButton and self.w.mode=='SELECT' and not self.w.drag:self.begin_pan(e)
 def mouseMoveEvent(self,e):
  if self.pan_origin is not None:
   current=e.position().toPoint();delta=current-self.pan_origin
   self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-delta.x())
   self.verticalScrollBar().setValue(self.verticalScrollBar().value()-delta.y())
   self.pan_origin=current;e.accept();return
  self.w.move(self.mapToScene(e.position().toPoint()),e)
 def mouseReleaseEvent(self,e):
  if self.pan_origin is not None:
   self.pan_origin=None;self.viewport().unsetCursor();e.accept();return
  self.w.release();self.w.drag=None
 def mouseDoubleClickEvent(self,e): self.w.finish(self.mapToScene(e.position().toPoint()))
 def wheelEvent(self,e):
  factor=1.18 if e.angleDelta().y()>0 else 1/1.18
  self.scale(factor,factor); self.w.statusBar().showMessage(f'Mode: {self.w.mode}  Zoom: {self.transform().m11():.2f}x')
class AnnotatorWindow(QMainWindow):
 def __init__(self,region_file,annotation_file=None):
  super().__init__();self.rpath=Path(region_file);self.region=json.loads(self.rpath.read_text());self.out=Path(annotation_file or self.rpath.parent.parent/'annotations'/f"{self.region['region_id']}.json");data=json.loads(self.out.read_text()) if self.out.exists() else {'schema_version':'1.1','region':{'region_id':self.region['region_id'],'source_region_file':portable_name(self.rpath)},'nodes':[],'edges':[],'ignore_regions':[]};self.m=GraphModel(data);self.mode='SELECT';self.sel=None;self.temp=[];self.drag=None;self.dirty=False
  self.view=View(self);self.setCentralWidget(self.view);tabs=QTabWidget();self.form=QFormLayout();pw=QWidget();pw.setLayout(self.form);tabs.addTab(pw,'Properties');self.warn=QListWidget();tabs.addTab(self.warn,'Warnings');self.stat=QLabel();tabs.addTab(self.stat,'Statistics');dock=QDockWidget('Inspector');dock.setWidget(tabs);self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dock);tb=QToolBar();self.addToolBar(tb)
  for name,mode in [('Select','SELECT'),('Draw Path','DRAW_PATH'),('Split','SPLIT'),('Merge','MERGE'),('Ignore','IGNORE')]: a=QAction(name,self);a.triggered.connect(lambda _,x=mode:self.set_mode(x));tb.addAction(a)
  for name,fn in [('Finish Path',self.finish_current),('Save',self.save),('Undo',self.undo),('Redo',self.redo),('Run Checks',self.refresh),('Help',self.help)]: a=QAction(name,self);a.triggered.connect(fn);tb.addAction(a)
  self.statusBar().showMessage('Mode: SELECT');self.render();self.refresh();QTimer.singleShot(30000,self.autosave)
 def set_mode(self,x):
  # Never discard a finished edge; only discard an unfinished draft explicitly.
  if self.mode in ('DRAW_PATH','IGNORE') and self.temp and x!=self.mode: self.temp=[]
  self.mode=x;self.statusBar().showMessage('Mode: '+x);self.render()
 def finish_current(self):
  if self.mode in ('DRAW_PATH','IGNORE'): self.finish(None)
 def help(self):
  QMessageBox.information(self,'Annotator 使用说明','选择：点击路线或节点\n画路线：D 或 Draw Path，左键逐点，双击或 Finish Path 完成\n缩放：鼠标滚轮（以光标为中心）\n平移：中键拖动；或 Select 模式下从空白处/路线拖动画布\n编辑节点：Select 模式下拖动蓝色节点或青色控制点\n插点：选中路线后按住 Option/Alt 点击\n删除：选中中间控制点、边或 Ignore 后按 Delete\n模式：Esc 返回 SELECT；S Split；M Merge；I Ignore\n保存：Cmd/Ctrl+S；撤销 Cmd/Ctrl+Z；重做 Cmd/Ctrl+Shift+Z')
 def keyPressEvent(self,e):
  k=e.key();mods=e.modifiers()
  if k==Qt.Key.Key_Escape:self.set_mode('SELECT')
  elif k==Qt.Key.Key_D:self.set_mode('DRAW_PATH')
  elif k==Qt.Key.Key_I:self.set_mode('IGNORE')
  elif k==Qt.Key.Key_S and not mods:self.set_mode('SPLIT')
  elif k==Qt.Key.Key_M:self.set_mode('MERGE')
  elif k==Qt.Key.Key_Delete:self.delete()
  elif k==Qt.Key.Key_Z and mods&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.MetaModifier):self.redo() if mods&Qt.KeyboardModifier.ShiftModifier else self.undo()
  elif k==Qt.Key.Key_S and mods&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.MetaModifier):self.save()
  elif self.sel and self.sel[0]=='edge' and k in (Qt.Key.Key_1,Qt.Key.Key_2,Qt.Key.Key_3,Qt.Key.Key_4,Qt.Key.Key_V,Qt.Key.Key_P,Qt.Key.Key_O):
   if k<=Qt.Key.Key_4:self.change('path_type',['vehicle_road','pedestrian_path','narrow_path','service_path'][k-Qt.Key.Key_1])
   else:self.change('visibility',{Qt.Key.Key_V:'visible',Qt.Key.Key_P:'partially_occluded',Qt.Key.Key_O:'fully_occluded'}[k])
  else:super().keyPressEvent(e)
 def p(self,q):return q.x(),q.y()
 def click(self,q,e):
  x,y=self.p(q)
  if self.mode in ('DRAW_PATH','IGNORE'):self.temp.append([x,y]);self.render();return
  if self.sel and self.sel[0]=='edge' and e.modifiers() & Qt.KeyboardModifier.AltModifier:
   h=self.nearest_edge(x,y)
   if h and h[0]==self.sel[1] and h[3] <= self.hit_tolerance(): self.m.insert_point(h[0],h[1]+1,h[2]); self.changed(); return
  if self.mode=='SPLIT':
   h=self.nearest_edge(x,y)
   if h and h[3] <= self.hit_tolerance():
    try:self.m.split_edge(h[0],point=h[2]);self.changed();self.set_mode('SELECT')
    except ValueError as exc:QMessageBox.warning(self,'Split',str(exc))
   return
  n=self.nearest_node(x,y)
  if n:
   if self.mode=='MERGE' and self.sel and self.sel[0]=='node':
    try:self.m.merge_nodes(self.sel[1],n);self.changed();self.set_mode('SELECT')
    except ValueError as exc:QMessageBox.warning(self,'Merge',str(exc))
   else:self.sel=('node',n);self.drag=('node',n);self.drag_before=self.m.snapshot()
  else:
   h=self.nearest_edge(x,y)
   if h and h[3] <= self.hit_tolerance():
    eid, index = h[0], h[1]
    poly=self.m.edge(eid)['polyline']; point_index=min(range(len(poly)),key=lambda i:math.hypot(poly[i][0]-x,poly[i][1]-y))
    if 0<point_index<len(poly)-1 and math.hypot(poly[point_index][0]-x,poly[point_index][1]-y)<=self.point_tolerance(): self.sel=('point',eid,point_index); self.drag=('point',eid,point_index)
    else:self.sel=('edge',eid); self.drag=None
    self.drag_before=self.m.snapshot()
   else:
    self.sel=None; self.drag=None
    for r in self.m.data.get('ignore_regions',[]):
     if point_in_polygon((x,y),r.get('polygon',[])): self.sel=('ignore',r['id']); break
  self.render();self.properties()
 def move(self,q,e):
  if not self.drag:return
  x,y=self.p(q)
  if self.drag[0]=='node':
   n=next(n for n in self.m.data['nodes'] if n['id']==self.drag[1]);n.update(x=x,y=y)
   for ed in self.m.data['edges']:
    if ed['start_node']==n['id']:ed['polyline'][0]=[x,y]
    if ed['end_node']==n['id']:ed['polyline'][-1]=[x,y]
  else:
   ed=self.m.edge(self.drag[1]);i=self.drag[2]
   if i==0:
    n=next(n for n in self.m.data['nodes'] if n['id']==ed['start_node']);n.update(x=x,y=y);ed['polyline'][0]=[x,y]
   elif i==len(ed['polyline'])-1:
    n=next(n for n in self.m.data['nodes'] if n['id']==ed['end_node']);n.update(x=x,y=y);ed['polyline'][-1]=[x,y]
   else:ed['polyline'][i]=[x,y]
  self.dirty=True;self.render();self.properties()
 def release(self):
  if self.drag and getattr(self,'drag_before',None) is not None:
   self.m._commit(self.drag_before);self.drag_before=None;self.dirty=True;self.autosave()
 def finish(self,q):
  if self.mode=='DRAW_PATH' and len(self.temp)>=2:
   before=self.m.snapshot();a,b=self.m.next_node_id(),None;self.m.data['nodes'].append({'id':a,'x':self.temp[0][0],'y':self.temp[0][1],'type':'endpoint'});b=self.m.next_node_id();self.m.data['nodes'].append({'id':b,'x':self.temp[-1][0],'y':self.temp[-1][1],'type':'endpoint'});self.m.data['edges'].append({'id':self.m.next_edge_id(),'start_node':a,'end_node':b,'polyline':self.temp,'path_type':'pedestrian_path','visibility':'visible','confidence':'high','verification_source':'rgb_context'});self.m._commit(before);self.changed();self.set_mode('SELECT')
  elif self.mode=='IGNORE' and len(self.temp)>=3:self.m.add_ignore(self.temp);self.changed();self.set_mode('SELECT')
 def nearest_node(self,x,y):
  a=[(math.hypot(n['x']-x,n['y']-y),n['id']) for n in self.m.data['nodes']];return min(a)[1] if a and min(a)[0]<18 else None
 def hit_tolerance(self): return 22.0 / max(self.view.transform().m11(),1e-6)
 def point_tolerance(self): return 12.0 / max(self.view.transform().m11(),1e-6)
 def nearest_edge(self,x,y):
  hits=[]
  for e in self.m.data['edges']:
   h=nearest_polyline_segment((x,y),e['polyline'])
   if h:hits.append((h['distance'],e['id'],h['segment_index'],h['projected_point']))
  if not hits:return None
  d,eid,index,projected=min(hits,key=lambda z:z[0]);return (eid,index,projected,d)
 def render(self):
  s=self.view.scene();s.clear()
  for t in self.region.get('tiles',[]):
   f=resolve_data_path(t.get('output_file',''),self.rpath,Path(__file__).resolve().parents[2])
   if f.exists():s.addPixmap(QPixmap(str(f))).setPos(float(t.get('global_x',t['col']*self.region['tile_width']*(1-self.region['overlap']))),float(t.get('global_y',t['row']*self.region['tile_height']*(1-self.region['overlap']))))
  for e in self.m.data['edges']:
   p=e['polyline'];path=QPainterPath(QPointF(*p[0]));[path.lineTo(QPointF(*z)) for z in p[1:]]; active=self.sel and self.sel[0] in ('edge','point') and self.sel[1]==e['id'];s.addPath(path,QPen(Qt.GlobalColor.yellow if active else Qt.GlobalColor.red,5 if active else 3))
   if active:
    for j,z in enumerate(p):s.addEllipse(z[0]-6,z[1]-6,12,12,QPen(Qt.GlobalColor.magenta if self.sel==('point',e['id'],j) else Qt.GlobalColor.cyan),QBrush(Qt.GlobalColor.magenta if self.sel==('point',e['id'],j) else Qt.GlobalColor.cyan))
  for r in self.m.data.get('ignore_regions',[]):
   poly=r.get('polygon',[])
   if len(poly)>=3:
    path=QPainterPath(QPointF(*poly[0]));[path.lineTo(QPointF(*z)) for z in poly[1:]];path.closeSubpath();active=self.sel==('ignore',r['id']);s.addPath(path,QPen(Qt.GlobalColor.magenta if active else Qt.GlobalColor.darkGray,4 if active else 2),QBrush(Qt.GlobalColor.red if active else Qt.GlobalColor.gray))
  for n in self.m.data['nodes']:s.addEllipse(n['x']-7,n['y']-7,14,14,QPen(Qt.GlobalColor.blue),QBrush(Qt.GlobalColor.blue))
  if len(self.temp)>1:
   path=QPainterPath(QPointF(*self.temp[0]));[path.lineTo(QPointF(*z)) for z in self.temp[1:]];s.addPath(path,QPen(Qt.GlobalColor.green,3))
 def change(self,k,v):self.m.set_attr('edge',self.sel[1],k,v);self.changed();self.properties()
 def changed(self):self.dirty=True;self.autosave();self.render();self.refresh()
 def delete(self):
  if not self.sel:return
  if self.sel[0]=='edge':self.m.delete_edge(self.sel[1])
  elif self.sel[0]=='point':self.m.delete_point(self.sel[1],self.sel[2])
  elif self.sel[0]=='ignore':self.m.delete_ignore(self.sel[1])
  elif any(self.sel[1] in (e['start_node'],e['end_node']) for e in self.m.data['edges']):QMessageBox.warning(self,'Node','Connected node cannot be deleted.')
  else:
   before=self.m.snapshot();self.m.data['nodes']=[n for n in self.m.data['nodes'] if n['id']!=self.sel[1]];self.m._commit(before)
  self.sel=None;self.changed()
 def properties(self):
  while self.form.count():self.form.takeAt(0).widget().deleteLater()
  if not self.sel:return
  if self.sel[0]=='edge':
   e=self.m.edge(self.sel[1]);self.form.addRow('Edge ID',QLabel(self.sel[1]))
   for k,vals in [('path_type',['vehicle_road','pedestrian_path','narrow_path','service_path']),('visibility',['visible','partially_occluded','fully_occluded']),('confidence',['high','medium','low']),('verification_source',['rgb_context','field_check','ground_photo','RTK','campus_map','secondary_image','none'])]:c=QComboBox();c.addItems(vals);c.setCurrentText(e.get(k,vals[0]));c.currentTextChanged.connect(lambda v,k=k:self.change(k,v));self.form.addRow(k,c)
   self.form.addRow('Polyline points',QLabel(str(len(e['polyline']))))
  elif self.sel[0]=='point':
   e=self.m.edge(self.sel[1]);i=self.sel[2];p=e['polyline'][i];self.form.addRow('Edge ID',QLabel(e['id']));self.form.addRow('Control Point Index',QLabel(str(i)));self.form.addRow('Global X/Y',QLabel(f'{p[0]:.1f}, {p[1]:.1f}'))
  elif self.sel[0]=='ignore':
   r=next(r for r in self.m.data.get('ignore_regions',[]) if r['id']==self.sel[1]);self.form.addRow('Ignore ID',QLabel(r['id']));self.form.addRow('Reason',QLabel(r.get('reason','cannot_determine')));self.form.addRow('Point count',QLabel(str(len(r.get('polygon',[])))))
  else:
   n=next(n for n in self.m.data['nodes'] if n['id']==self.sel[1]);self.form.addRow('Node ID',QLabel(n['id']));c=QComboBox();c.addItems(['junction','endpoint','boundary','continuation']);c.setCurrentText(n.get('type','endpoint'));c.currentTextChanged.connect(lambda v:self.m.set_attr('node',n['id'],'type',v) or self.changed());self.form.addRow('Node Type',c);self.form.addRow('Global X/Y',QLabel(f"{n['x']:.1f}, {n['y']:.1f}"))
 def refresh(self):self.warn.clear();self.warn.addItems(check(self.m.data,self.region));s=self.m.stats();self.stat.setText(json.dumps(s,ensure_ascii=False,indent=2));self.properties()
 def save(self):atomic_save(self.m.data,self.out);self.dirty=False;self.statusBar().showMessage('Saved '+str(self.out))
 def autosave(self):
  if self.dirty:atomic_save(self.m.data,self.out)
 def undo(self):
  if self.m.undo_once():self.render();self.refresh()
 def redo(self):
  if self.m.redo_once():self.render();self.refresh()
def launch(region_file,annotation_file=None):
 app=QApplication.instance() or QApplication([]);w=AnnotatorWindow(region_file,annotation_file);w.resize(1400,900);w.show();app.exec()
