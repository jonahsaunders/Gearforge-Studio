"""Native, labeled motor/load envelope plot with a table alternative."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from .chart_style import ChartWidget, chart_color


class OperatingPlot(ChartWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.points=[];self.load=0.
        self.setMinimumHeight(160)
        self.setAccessibleName("Available output torque versus output speed")
        self.setAccessibleDescription("Solid curve is available torque, dashed line is requested load. The adjacent operating points table contains all values.")

    def set_data(self,points,load):
        self.points=[p for p in points if "available_output_nm" in p];self.load=load;self.update()

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),self.palette().base())
        if not self.points:return
        box=QRectF(66,30,self.width()-90,self.height()-72)
        xmax=max(row["output_rpm"] for row in self.points)*1.05
        ymax=max(self.load,max(row["available_output_nm"] for row in self.points))*1.15 or 1
        def point(x,y):return QPointF(box.left()+x/xmax*box.width(),box.bottom()-y/ymax*box.height())
        p.setPen(self.palette().text().color())
        p.drawText(12,20,"Output torque (N·m)")
        p.drawText(QRectF(0,self.height()-24,self.width(),20),Qt.AlignCenter,"Output speed (rpm)")
        for i in range(5):
            x=xmax*i/4;y=ymax*i/4
            p.setPen(QPen(self.palette().mid().color(),1))
            p.drawLine(point(x,0),point(x,ymax));p.drawLine(point(0,y),point(xmax,y))
            p.setPen(self.palette().text().color())
            p.drawText(QRectF(point(x,0).x()-28,box.bottom()+3,56,18),Qt.AlignCenter,f"{x:.0f}")
            p.drawText(QRectF(1,point(0,y).y()-9,60,18),Qt.AlignRight,f"{y:.3g}")
        p.setPen(QPen(chart_color(self,"#3478db"),2.5))
        p.drawPolyline(QPolygonF([point(row["output_rpm"],row["available_output_nm"]) for row in self.points]))
        p.setPen(QPen(chart_color(self,"#b85a15"),2,Qt.DashLine));p.drawLine(point(0,self.load),point(xmax,self.load))
        p.setPen(self.palette().text().color());p.drawText(int(box.right()-230),20,"Solid: available   Dashed: load")
