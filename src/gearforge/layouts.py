"""Wrapping native control rows for smaller windows and larger text."""
from PySide6.QtCore import QPoint,QRect,QSize
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self,parent=None):
        super().__init__(parent);self.items=[];self.setContentsMargins(0,0,0,0);self.setSpacing(6)

    def addItem(self,item):self.items.append(item)
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):
        from PySide6.QtCore import Qt
        return Qt.Orientations()
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self._arrange(QRect(0,0,width,0),True)
    def sizeHint(self):return self.minimumSize()
    def minimumSize(self):
        size=QSize()
        for item in self.items:size=size.expandedTo(item.minimumSize())
        return size
    def setGeometry(self,rect):super().setGeometry(rect);self._arrange(rect,False)
    def _arrange(self,rect,measure):
        x,y,line=rect.x(),rect.y(),0
        for item in self.items:
            size=item.sizeHint();widget=item.widget()
            if widget:size=size.boundedTo(widget.maximumSize())
            if x+size.width()>rect.right()+1 and line:
                x=rect.x();y+=line+self.spacing();line=0
            if not measure:item.setGeometry(QRect(QPoint(x,y),size))
            x+=size.width()+self.spacing();line=max(line,size.height())
        return y+line-rect.y()
