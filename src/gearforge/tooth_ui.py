"""Desktop manufacturing-profile editor and root detail view."""
from dataclasses import asdict
import json
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QLabel,
    QLineEdit,QMessageBox,QPushButton,QTabWidget,QTextBrowser,QTextEdit,QVBoxLayout,QWidget)

from .engineering import EngineeringStudy
from .tooth_profile import (ToothProfileStudy,calculate_profile_study,export_profile_study,
    profile_from_study,profile_report_html,synthetic_profile_example)


class ToothPlot(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.result=None;self.whole=False;self.setMinimumSize(520,360)
        self.setAccessibleName('Generated tooth root and involute profile')

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor('#f8fafc'));painter.setPen(QColor('#25324a'))
        if not self.result or not self.result['profile_available']:
            painter.drawText(self.rect(),Qt.AlignCenter,'Calculate a supported cutter profile to view geometry.');return
        colors=['#475569','#2563eb','#bc4a0b','#15803d']
        if self.whole:
            paths=[(self.result['outline_mm']+[self.result['outline_mm'][0]],'#166a5e')]
        else:
            paths=[]
            for segment,color in zip(self.result['segments'],colors):
                paths.extend([(segment['points_mm'],color),([(-x,y) for x,y in segment['points_mm']],color)])
        points=[p for path,_ in paths for p in path]
        left,right=min(p[0] for p in points),max(p[0] for p in points)
        bottom,top=min(p[1] for p in points),max(p[1] for p in points)
        scale=min((self.width()-100)/max(right-left,1e-9),(self.height()-120)/max(top-bottom,1e-9))
        def transform(p):return QPointF(self.width()/2+(p[0]-(left+right)/2)*scale,45+(top-p[1])*scale)
        for path,color in paths:
            painter.setPen(QPen(QColor(color),2));painter.drawPolyline(QPolygonF([transform(p) for p in path]))
        painter.setPen(QColor('#25324a'))
        painter.drawText(24,25,'Whole gear' if self.whole else 'Central tooth · +Y radial · millimetres')
        painter.drawText(24,self.height()-48,'Grey: tip   Blue: involute   Orange: generated root   Green: root land' if not self.whole else 'Closed outline · sampled representation of the analytic profile')
        painter.drawText(24,self.height()-24,'Geometry only. Cutter evidence and production strength remain to be established.')


class ToothProfileDialog(QDialog):
    def __init__(self,parent=None,study=None):
        super().__init__(parent);self.resize(1100,800);self.setWindowTitle('Rack-generated tooth roots')
        self.path=None;self.result=None;self.dirty=False;self._loading=True
        layout=QVBoxLayout(self)
        note=QLabel('Define the actual rack cutter before using root geometry for stress analysis. Synthetic inputs are examples; this study does not establish a production load rating.')
        note.setWordWrap(True);layout.addWidget(note)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        inputs=QWidget();form=QFormLayout(inputs);self.fields={}
        self.name=QLineEdit();form.addRow('Study name',self.name);self.name.textChanged.connect(self.changed)
        self.role=QComboBox();self.role.addItems(['pinion','wheel']);form.addRow('Gear member',self.role);self.role.currentIndexChanged.connect(self.changed)
        for key,label in [('cutter_depth_coefficient','Cutter depth / module'),('cutter_tip_radius_coefficient','Cutter tip radius / module (blank if unknown)'),
                          ('tooth_thickness_reduction_mm','Individual tooth thickness reduction (mm)'),('sampling_tolerance_mm','Requested sampling tolerance (mm)')]:
            widget=QLineEdit();widget.setAccessibleName(label);widget.textChanged.connect(self.changed)
            form.addRow(label,widget);self.fields[key]=widget
        self.data_status=QComboBox();self.data_status.addItems(['unverified','synthetic','declared']);self.data_status.currentIndexChanged.connect(self.changed)
        form.addRow('Cutter data status',self.data_status)
        for key,label in [('cutter_reference','Cutter source and revision'),('redistribution_basis','Basis for sharing cutter data'),('notes','Study notes')]:
            widget=QTextEdit();widget.setAcceptRichText(False);widget.setMaximumHeight(100);widget.setAccessibleName(label)
            widget.textChanged.connect(self.changed);form.addRow(label,widget);self.fields[key]=widget
        hint=QLabel('The retained pair sets module, pressure angle, teeth, profile shift and tip shortening. Cutter depth sets the actual root. Tooth thickness reduction is not assembled backlash. Helical cutters and trimmed undercut profiles are not yet supported.')
        hint.setWordWrap(True);form.addRow(hint);self.tabs.addTab(inputs,'Cutter and manufacturing')
        page=QWidget();plot_layout=QVBoxLayout(page);self.view=QComboBox();self.view.addItems(['Tooth and root detail','Whole gear'])
        self.view.currentIndexChanged.connect(self.change_view);plot_layout.addWidget(self.view)
        self.plot=ToothPlot();plot_layout.addWidget(self.plot,1);self.tabs.addTab(page,'Generated profile')
        self.source_view=QTextBrowser();self.source_view.setOpenExternalLinks(False);self.tabs.addTab(self.source_view,'Retained gear study')
        self.report=QTextBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Assessment')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        for actions in [[('Open…',self.open_study),('Save…',self.save_study),('From gear study…',self.from_source),('Synthetic example',self.example)],
                        [('Calculate',self.calculate),('Export profile package…',self.export),('Close',self.reject)]]:
            row=QHBoxLayout()
            for label,callback in actions:
                button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button)
            row.addStretch();layout.addLayout(row)
        for row in range(form.rowCount()):
            label=form.itemAt(row,QFormLayout.LabelRole);field=form.itemAt(row,QFormLayout.FieldRole)
            if label and field:label.widget().setBuddy(field.widget())
        self.set_study(study or ToothProfileStudy())

    def set_study(self,study):
        self.model=ToothProfileStudy.from_dict(asdict(study));self._loading=True
        self.name.setText(study.name);self.role.setCurrentText(study.role);self.data_status.setCurrentText(study.data_status)
        for key,widget in self.fields.items():
            value=getattr(study,key)
            if isinstance(widget,QTextEdit):widget.setPlainText(value)
            else:widget.setText('' if value is None else repr(value))
        self.source_view.setPlainText(json.dumps(asdict(study.source),indent=2))
        self._loading=False;self.path=None;self.dirty=False;self.clear_result();self.status.setText('Cutter inputs loaded; calculate to assess geometry.')

    def clear_result(self):
        self.result=None;self.report.clear();self.plot.result=None;self.plot.update()

    def changed(self,*args):
        if self._loading:return
        self.dirty=True;self.clear_result();self.status.setText('Inputs changed; recalculate before using the profile.')

    def read_study(self):
        data=asdict(self.model);data.update(name=self.name.text(),role=self.role.currentText(),data_status=self.data_status.currentText())
        for key,widget in self.fields.items():
            if isinstance(widget,QTextEdit):data[key]=widget.toPlainText()
            else:
                text=widget.text().strip()
                data[key]=None if key=='cutter_tip_radius_coefficient' and not text else float(text)
        return ToothProfileStudy.from_dict(data)

    def change_view(self,index):self.plot.whole=index==1;self.plot.update()

    def calculate(self):
        self.clear_result()
        try:self.result=calculate_profile_study(self.read_study())
        except (ValueError,TypeError,OverflowError) as exc:self.show_error(exc);return False
        self.report.setHtml(profile_report_html(self.result));self.plot.result=self.result;self.plot.update()
        available=self.result['profile_available'];self.tabs.setCurrentIndex(1 if available else 3)
        self.status.setText('Generated profile available; production rating remains unavailable.' if available else 'Profile unavailable: '+'; '.join(self.result['findings']))
        return True

    def show_error(self,error):QMessageBox.warning(self,'Tooth profile',str(error))
    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved tooth profile','Save the tooth profile before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        if answer==QMessageBox.Save:return self.save_study()
        return answer==QMessageBox.Discard
    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Save tooth profile',str(self.path or 'gearbox.gearforge-tooth'),'Tooth profile (*.gearforge-tooth)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True
    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open tooth profile','','Tooth profile (*.gearforge-tooth)')
        if not path:return False
        try:study=ToothProfileStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True
    def from_source(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Retain gear study','','Engineering study (*.gearforge-study)')
        if not path:return False
        try:study=profile_from_study(EngineeringStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.dirty=True;return True
    def example(self):
        if not self.confirm_discard():return False
        self.set_study(synthetic_profile_example());self.dirty=True;return True
    def export(self):
        try:study=self.read_study();calculate_profile_study(study)
        except (ValueError,TypeError,OverflowError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose new profile folder','tooth-profile','Folder name (*)')
        if not path:return False
        try:result=export_profile_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText(f"Exported {result['files']} files; "+('sampled DXF, SVG and coordinates included.' if result['profile_available'] else 'unsupported geometry recorded; no profile files created.'));return True
    def reject(self):
        if self.confirm_discard():super().reject()
    def closeEvent(self,event):
        if self.confirm_discard():event.accept()
        else:event.ignore()
