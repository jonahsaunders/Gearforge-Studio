"""Native Qt CAD mesh viewer; no GPU, embedded browser or network dependency."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .geometry import involute_outline
from .simulation import SimulationClock, part_motion, shaft_rates


class AssemblyViewer(QWidget):
    timeChanged = Signal(float)
    playbackChanged = Signal(bool)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(380,220)
        self.candidate = None
        self.meshes = []
        self.yaw, self.pitch, self.zoom = -.65, .95, 1.
        self.explode = 0.
        self.show_housing = False
        self.phase = 0.
        self.clock = SimulationClock()
        self.reduced_motion = False
        self.backlash_mm = .2
        self._mesh_cache = []
        self.last_pos = None
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName("Gearbox assembly viewer")
        self.setAccessibleDescription("Rigid-body kinematic preview. Arrow keys orbit, plus and minus zoom, R resets, Space toggles playback. No elastic contact simulation.")
        self.setToolTip(self.accessibleDescription()+" Drag to orbit; scroll to zoom.")

    def set_candidate(self,c):
        self.animate(False)
        self.candidate,self.meshes,self.phase = c,[],0
        self._mesh_cache = []
        self.clock = SimulationClock(c.stages[0].input_rpm if c else 1200.)
        self.timeChanged.emit(0.)
        self.update()

    def set_meshes(self,meshes):
        import numpy as np
        self.meshes = meshes
        self._mesh_cache = [(m,np.asarray(m["vertices"],dtype=float),np.asarray(m["triangles"],dtype=int)) for m in meshes]
        self.update()

    def reset_view(self):
        self.yaw,self.pitch,self.zoom = -.65,.95,1.
        self.update()

    def _tick(self):
        now = time.monotonic()
        self.clock.advance(max(0.,now-self._last_tick))
        self._last_tick = now
        self.phase = self.clock.input_angle
        self.timeChanged.emit(self.clock.time_s)
        self.update()

    def animate(self,active):
        if active and self.candidate and self.candidate.export_level != "concept" and not self.reduced_motion:
            self._last_tick = time.monotonic()
            self.timer.start()
        else:
            self.timer.stop()
        self.playbackChanged.emit(self.timer.isActive())

    def seek(self,seconds):
        self.animate(False)
        self.clock.seek(seconds);self.phase=self.clock.input_angle
        self.timeChanged.emit(self.clock.time_s);self.update()

    def step(self):
        self.animate(False)
        if self.candidate and self.candidate.export_level != "concept":
            self.clock.step_angle(2*math.pi/self.candidate.stages[0].driver.teeth * (1 if self.clock.speed_factor >= 0 else -1))
            self.phase=self.clock.input_angle;self.timeChanged.emit(self.clock.time_s);self.update()

    def keyPressEvent(self,event):
        key=event.key()
        if key==Qt.Key_Space:self.animate(not self.timer.isActive())
        elif key==Qt.Key_R:self.reset_view()
        elif key in (Qt.Key_Plus,Qt.Key_Equal):self.zoom=min(3,self.zoom*1.12)
        elif key==Qt.Key_Minus:self.zoom=max(.4,self.zoom/1.12)
        elif key in (Qt.Key_Left,Qt.Key_Right):self.yaw+=.1 if key==Qt.Key_Right else -.1
        elif key in (Qt.Key_Up,Qt.Key_Down):self.pitch=max(.1,min(1.5,self.pitch+(.08 if key==Qt.Key_Up else -.08)))
        else:super().keyPressEvent(event);return
        self.update();event.accept()

    def mousePressEvent(self,event):
        self.last_pos=event.position()

    def mouseMoveEvent(self,event):
        if self.last_pos is not None:
            delta=event.position()-self.last_pos
            self.yaw += delta.x()*.01
            self.pitch = max(.1,min(1.5,self.pitch+delta.y()*.008))
            self.last_pos=event.position()
            self.update()

    def mouseReleaseEvent(self,event):
        self.last_pos=None

    def wheelEvent(self,event):
        self.zoom=max(.4,min(3,self.zoom*(1.12 if event.angleDelta().y()>0 else 1/1.12)))
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor("#111a27"))
        painter.setPen(QPen(QColor("#1b2a3b"),1))
        for x in range(0,self.width(),30):painter.drawLine(x,0,x,self.height())
        for y in range(0,self.height(),30):painter.drawLine(0,y,self.width(),y)
        if self.candidate is None:
            painter.setPen(QColor("#8394ac"))
            painter.drawText(self.rect(),Qt.AlignCenter,"Your next transmission starts here\nSet requirements and generate designs")
            return
        if self.meshes:
            self._draw_mesh(painter)
        else:
            painter.setRenderHint(QPainter.Antialiasing)
            self._draw_layout(painter)
        painter.setPen(QColor("#a4b3c8"))
        text=("RIGID-BODY CAD" if self.meshes else "KINEMATIC LAYOUT")+" · contact unvalidated"
        painter.drawText(16,self.height()-17,text)
        painter.setPen(QColor("#e4ac55"))
        painter.drawText(16,24,"CONCEPT" if self.candidate.export_level=="concept" else "PROTOTYPE")

    def _draw_layout(self,p):
        c=self.candidate
        sx,sy,_=c.size_mm
        scale=min((self.width()-80)/sx,(self.height()-70)/sy)*self.zoom
        ox,oy=(self.width()-sx*scale)/2,(self.height()-sy*scale)/2
        p.setPen(QPen(QColor("#394a61"),2))
        p.setBrush(QColor("#162231"))
        p.drawRoundedRect(QRectF(ox,oy,sx*scale,sy*scale),12,12)
        if c.export_level=="concept":
            p.setPen(QColor("#83a2c2"))
            p.drawText(QRectF(ox+10,oy+10,sx*scale-20,sy*scale-20),Qt.AlignCenter,
                       f"{c.family.title()} packaging concept\n{c.ratio:.3g}:1 reduction\nDetailed tooth geometry required")
            return
        for item in c.layout:
            s=c.stages[item["stage"]]
            g=s.planet if item["role"]=="planet" else (s.driver if item["role"]=="driver" else s.driven)
            angle=math.radians(item["rotation_deg"])
            cx,cy=item["x"],item["y"]
            spin,(dx,dy)=part_motion(c,item["name"],item["shaft"],(cx,cy,0),self.phase)
            angle+=spin;cx+=dx;cy+=dy
            points=involute_outline(g.teeth,g.module_mm,g.pressure_deg,self.backlash_mm if g.source=="print" else .1,g.helix_deg,g.internal,samples=6)
            polygon=QPolygonF([QPointF(ox+(x*math.cos(angle)-y*math.sin(angle)+cx)*scale,
                                          oy+(x*math.sin(angle)+y*math.cos(angle)+cy)*scale) for x,y in points])
            color=QColor("#4284df" if item["role"]=="driven" else "#20bfa3")
            p.setPen(QPen(color,1.3))
            fill=QColor(color);fill.setAlpha(45)
            p.setBrush(fill)
            if g.internal:
                p.drawEllipse(QPointF(ox+cx*scale,oy+cy*scale),g.outer_mm*scale/2,g.outer_mm*scale/2)
                p.setBrush(QColor("#162231"))
            p.drawPolygon(polygon)
            p.setBrush(QColor("#111a27"))
            if g.bore_mm:
                p.drawEllipse(QPointF(ox+cx*scale,oy+cy*scale),g.bore_mm*scale/2,g.bore_mm*scale/2)
            if item["role"]!="driven" or not g.internal:
                p.setPen(QColor("#ccdae9"))
                p.drawText(QPointF(ox+cx*scale+7,oy+cy*scale-7),str(g.teeth)+"T")

    def _draw_mesh(self,p):
        import numpy as np
        sx,sy,sz=self.candidate.size_mm
        center=np.array([sx/2,sy/2,sz/2])
        cy,syaw,cp,sp=math.cos(self.yaw),math.sin(self.yaw),math.cos(self.pitch),math.sin(self.pitch)
        rz=np.array([[cy,-syaw,0],[syaw,cy,0],[0,0,1]])
        rx=np.array([[1,0,0],[0,cp,-sp],[0,sp,cp]])
        matrix=rx@rz
        scale=min((self.width()-80)/(sx+sz*.4),(self.height()-70)/(sy+sz*.7))*self.zoom
        faces=[]
        for mesh,vertices,tri in self._mesh_cache:
            if mesh["name"] in ("housing","lid") and not self.show_housing:continue
            spin,(dx,dy)=part_motion(self.candidate,mesh["name"],mesh["shaft"],mesh["center"],self.phase)
            pivot=np.asarray(mesh["center"])
            rotation=np.array([[math.cos(spin),-math.sin(spin),0],[math.sin(spin),math.cos(spin),0],[0,0,1]])
            vs=(vertices-pivot)@rotation.T+pivot+np.array([dx,dy,0])-center
            if self.explode:
                offset=np.array(mesh["center"])-center
                vs+=offset*self.explode*.35
            vs=vs@matrix.T
            if not len(tri):continue
            tv=vs[tri]
            normals=np.cross(tv[:,1]-tv[:,0],tv[:,2]-tv[:,0])
            lengths=np.linalg.norm(normals,axis=1)
            lengths[lengths==0]=1
            normals/=lengths[:,None]
            color=np.array(mesh["color"])
            light=np.array([-.25,-.45,1.]);light/=np.linalg.norm(light)
            shade=.42+.58*np.maximum(0,normals@light)
            alpha=85 if mesh["name"] in ("housing","lid") else 255
            for i in range(len(tri)):
                # View from +Z; drop backfaces on opaque parts.
                if normals[i,2]<=0 and alpha==255:continue
                rgb=np.clip(color*shade[i]*255,0,255).astype(int)
                pts=[QPointF(self.width()/2+x*scale,self.height()/2-y*scale) for x,y,_ in tv[i]]
                faces.append((float(tv[i,:,2].mean()),pts,QColor(int(rgb[0]),int(rgb[1]),int(rgb[2]),alpha)))
        p.setPen(Qt.NoPen)
        for _,points,color in sorted(faces,key=lambda f:f[0]):
            p.setBrush(color)
            p.drawPolygon(QPolygonF(points))
