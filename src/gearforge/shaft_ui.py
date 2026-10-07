"""Desktop editing and visualization of explicit shaft load paths."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QMessageBox,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,QTextBrowser,
    QTextEdit,QVBoxLayout,QWidget)

from .chart_style import ChartWidget, ReportBrowser, chart_color

from .desktop_ui import StudyDialog, StudyTabs

from .engineering_ui import StudyNumber
from .shafts import (ShaftStudy,ShaftSection,ShaftCase,ShaftLoad,calculate_shaft_study,
                     export_shaft_study,shaft_report_html)


class ShaftPlot(ChartWidget):
    QUANTITIES={
        'Deflection (mm)':('deflection_y_mm','deflection_z_mm'),
        'Bending moment magnitude (N·m)':('bending_moment_magnitude_nm',),
        'Shear force (N)':('shear_y_n','shear_z_n'),
        'Shaft slope (rad)':('slope_y_rad','slope_z_rad'),
        'Torque (N·m)':('torque_nm',),
        'Twist from X=0 (rad)':('twist_rad',),
        'Nominal surface stress (MPa)':('nominal_surface_von_mises_mpa',),
    }

    def __init__(self,parent=None):
        super().__init__(parent)
        self.result=None;self.case_index=0;self.quantity=next(iter(self.QUANTITIES));self.box=None
        self.setMinimumHeight(300);self.setMouseTracking(True)
        self.setAccessibleName('Shaft load and deflection diagram')
        self.setAccessibleDescription('Choose a case and quantity. Hover for sampled values. The report and JSON provide numerical results and section extrema.')

    def set_result(self,result,case_index=0,quantity=None):
        self.result=result;self.case_index=case_index
        if quantity:self.quantity=quantity
        self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),self.palette().base());painter.setPen(self.palette().text().color())
        if not self.result:
            painter.drawText(self.rect(),Qt.AlignCenter,'Calculate the current shaft study to view its load path.');return
        inputs=self.result['inputs'];case=self.result['cases'][self.case_index]
        length=inputs['length_mm'];left=82;right=self.width()-32;width=max(1,right-left)
        def xpos(x):return left+x/length*width
        painter.drawText(12,22,'Shaft X (mm), ideal supports and applied load positions')
        for section in inputs['sections']:
            painter.setPen(QPen(self.palette().text().color(),max(2,min(18,section['outer_diameter_mm']/2))))
            painter.drawLine(QPointF(xpos(section['start_mm']),50),QPointF(xpos(section['end_mm']),50))
        painter.setPen(QPen(chart_color(self,'#25846b'),2))
        for label,key in (('A','bearing_a_mm'),('B','bearing_b_mm')):
            x=xpos(inputs[key]);painter.drawPolyline(QPolygonF([QPointF(x-9,68),QPointF(x,53),QPointF(x+9,68),QPointF(x-9,68)]))
            painter.drawText(QRectF(x-25,71,50,18),Qt.AlignCenter,label)
        painter.setPen(QPen(chart_color(self,'#b85a15'),2))
        for load in inputs['cases'][self.case_index]['loads']:
            x=xpos(load['position_mm']);painter.drawLine(QPointF(x,30),QPointF(x,44))
        box=QRectF(left,130,width,max(1,self.height()-180));self.box=box
        fields=self.QUANTITIES[self.quantity]
        values=[p[key] for p in case['samples'] for key in fields]
        low=min(0,min(values));high=max(0,max(values));span=high-low or 1
        low-=.08*span;high+=.08*span
        def point(x,y):return QPointF(xpos(x),box.bottom()-(y-low)/(high-low)*box.height())
        painter.setPen(self.palette().text().color());painter.drawText(12,112,self.quantity)
        for i in range(5):
            x=length*i/4;y=low+(high-low)*i/4
            painter.setPen(QPen(self.palette().mid().color(),1))
            painter.drawLine(point(x,low),point(x,high));painter.drawLine(point(0,y),point(length,y))
            painter.setPen(self.palette().text().color())
            painter.drawText(QRectF(xpos(x)-32,box.bottom()+4,64,20),Qt.AlignCenter,f'{x:.5g}')
            painter.drawText(QRectF(1,point(0,y).y()-10,74,20),Qt.AlignRight,f'{y:.5g}')
        for index,key in enumerate(fields):
            painter.setPen(QPen(chart_color(self,('#3478db','#b85a15')[index]),2.2,Qt.SolidLine if index==0 else Qt.DashLine))
            painter.drawPolyline(QPolygonF([point(p['position_mm'],p[key]) for p in case['samples']]))
        painter.setPen(self.palette().text().color())
        painter.drawText(QRectF(0,self.height()-24,self.width(),20),Qt.AlignCenter,
                         'Solid: Y · Dashed: Z' if len(fields)==2 else 'Sampled curve; report extrema include interior stationary points')

    def mouseMoveEvent(self,event):
        if self.result and self.box and self.box.width()>0:
            x=max(0,min(self.result['inputs']['length_mm'],(event.position().x()-self.box.left())/self.box.width()*self.result['inputs']['length_mm']))
            point=min(self.result['cases'][self.case_index]['samples'],key=lambda p:abs(p['position_mm']-x))
            self.setToolTip(f"X = {point['position_mm']:.6g} mm\n"+'\n'.join(f"{key.replace('_',' ')} = {point[key]:.6g}" for key in self.QUANTITIES[self.quantity]))
        super().mouseMoveEvent(event)


class ShaftStudyDialog(StudyDialog):
    SECTION_FIELDS=('start_mm','end_mm','outer_diameter_mm','inner_diameter_mm','youngs_modulus_mpa','shear_modulus_mpa','material_basis')
    CASE_FIELDS=('name','rpm','duration_hours','ambient_c')
    LOAD_FIELDS=('name','position_mm','axial_n','force_y_n','force_z_n','torque_nm','moment_y_nm','moment_z_nm')

    def __init__(self,parent=None,study=None):
        super().__init__(parent)
        self.resize(1180,850);self.setWindowTitle('Shaft and bearing loads')
        self.path=None;self.result=None;self.dirty=False;self._loading=True;self.source_study=None
        layout=QVBoxLayout(self)
        note=QLabel('Resolve the actual load path through the shaft and its two bearings. Elastic motion and nominal stress do not establish fatigue life or bearing capacity.')
        note.setWordWrap(True);layout.addWidget(note)
        self.tabs=StudyTabs();layout.addWidget(self.tabs,1)
        page=QWidget();shaft_layout=QVBoxLayout(page);form=QFormLayout();shaft_layout.addLayout(form)
        self.name=QLineEdit();self.name.textEdited.connect(self.changed);form.addRow('Study name',self.name)
        self.numbers={}
        for key,label in (('length_mm','Shaft length'),('bearing_a_mm','Bearing A position'),('bearing_b_mm','Bearing B position')):
            widget=StudyNumber();widget.setDecimals(10);widget.setRange(0,10000);widget.setSuffix(' mm')
            widget.setKeyboardTracking(False);widget.valueChanged.connect(self.changed);widget.setAccessibleName(label)
            form.addRow(label,widget);self.numbers[key]=widget
        self.locator=QComboBox();self.locator.addItems(['A','B']);self.locator.currentIndexChanged.connect(self.changed)
        form.addRow('Axial locating bearing',self.locator)
        self.sections=self.make_table(['Start mm','End mm','OD mm','ID mm','E MPa','G MPa','Material/property basis'])
        self.sections.setAccessibleName('Contiguous shaft sections');shaft_layout.addWidget(self.sections,1)
        self.row_buttons(shaft_layout,'section',self.add_section,lambda:self.remove_row(self.sections))
        hint=QLabel('Sections must cover X=0 to the shaft length without gaps. Loads may be between or outside the two bearing supports. Enter actual elastic properties at operating temperature.')
        hint.setWordWrap(True);shaft_layout.addWidget(hint);self.tabs.addTab(page,'Shaft and sections')
        page=QWidget();case_layout=QVBoxLayout(page)
        self.cases=self.make_table(['Case','Shaft rpm','Hours','Ambient °C']);self.cases.itemChanged.connect(self.case_changed)
        self.cases.setAccessibleName('Shaft duty cases');case_layout.addWidget(self.cases,1)
        self.row_buttons(case_layout,'case',self.add_case,self.remove_case)
        self.tabs.addTab(page,'Operating cases')
        page=QWidget();load_layout=QVBoxLayout(page)
        note=QLabel('Right-handed axes: X along shaft; Y and Z transverse. Forces are N; torques/couples are N·m. Include a balancing drive/load torque—ideal bearings do not transmit torque.')
        note.setWordWrap(True);load_layout.addWidget(note)
        self.loads=self.make_table(['Case','Load','X mm','Fx N','Fy N','Fz N','Tx N·m','My N·m','Mz N·m'])
        self.loads.setAccessibleName('Applied shaft forces and couples');load_layout.addWidget(self.loads,1)
        self.row_buttons(load_layout,'load',self.add_load,lambda:self.remove_row(self.loads))
        self.tabs.addTab(page,'Applied loads')
        page=QWidget();context=QFormLayout(page)
        self.source_text=QTextEdit();self.source_text.setAcceptRichText(False);self.source_text.textChanged.connect(self.changed)
        self.notes=QTextEdit();self.notes.setAcceptRichText(False);self.notes.textChanged.connect(self.changed)
        context.addRow('Source description',self.source_text);context.addRow('Study notes',self.notes)
        self.tabs.addTab(page,'Sources and assumptions')
        page=QWidget();results_layout=QVBoxLayout(page);controls=QHBoxLayout();results_layout.addLayout(controls)
        self.case_choice=QComboBox();self.case_choice.currentIndexChanged.connect(self.update_plot)
        self.quantity=QComboBox();self.quantity.addItems(ShaftPlot.QUANTITIES);self.quantity.currentIndexChanged.connect(self.update_plot)
        controls.addWidget(QLabel('Case'));controls.addWidget(self.case_choice,1);controls.addWidget(self.quantity)
        self.plot=ShaftPlot();results_layout.addWidget(self.plot,1)
        self.summary=QLabel();self.summary.setWordWrap(True);results_layout.addWidget(self.summary)
        self.tabs.addTab(page,'Load path and motion');self.result_page=page
        self.report=ReportBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Calculation report')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in (('Open shaft study…',self.open_study),('Save shaft study…',self.save_study),
                               ('Calculate',self.calculate),('Assess bearings…',self.assess_bearings),('Assess fatigue…',self.assess_fatigue),('Export calculation…',self.export),('Close',self.reject)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        self.set_study(study or ShaftStudy())
        self.finish_ui()


    def make_table(self,headers):
        table=QTableWidget(0,len(headers));table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True);table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True);table.itemChanged.connect(self.changed)
        return table

    def row_buttons(self,layout,name,add,remove):
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for label,callback in ((f'Add {name}',add),(f'Remove selected {name}',remove)):
            button=QPushButton(label);button.clicked.connect(callback);buttons.addWidget(button)
        buttons.addStretch()

    def changed(self,*_):
        if self._loading:return
        self.dirty=True;self.result=None;self.plot.set_result(None);self.report.clear();self.summary.clear()
        self.status.setText('Inputs changed. Calculate again for current shaft and bearing loads.')

    def add_section(self,section=None):
        if not isinstance(section,ShaftSection):
            try:start=float(self.sections.item(self.sections.rowCount()-1,1).text()) if self.sections.rowCount() else 0
            except (ValueError,AttributeError):self.show_error('Correct the previous section end before adding a section.');return
            section=ShaftSection(start_mm=start,end_mm=start+20)
        row=self.sections.rowCount();self.sections.insertRow(row)
        for column,key in enumerate(self.SECTION_FIELDS):self.sections.setItem(row,column,QTableWidgetItem(str(getattr(section,key))))
        self.changed()

    def add_case(self,case=None):
        if not isinstance(case,ShaftCase):
            names={name for _,name in self.case_names()};number=1
            while f'Case {number}' in names:number+=1
            case=ShaftCase(name=f'Case {number}',duration_hours=1,loads=[])
        row=self.cases.rowCount();self.cases.insertRow(row);identity=uuid.uuid4().hex
        for column,key in enumerate(self.CASE_FIELDS):
            item=QTableWidgetItem(str(getattr(case,key)))
            if column==0:item.setData(Qt.UserRole,identity)
            self.cases.setItem(row,column,item)
        for load in case.loads:self.add_load(load,identity)
        self.case_changed();self.changed()

    def case_names(self):
        return [(self.cases.item(row,0).data(Qt.UserRole),self.cases.item(row,0).text())
                for row in range(self.cases.rowCount()) if self.cases.item(row,0)]

    def case_changed(self,*_):
        for row in range(self.loads.rowCount()) if hasattr(self,'loads') else []:
            combo=self.loads.cellWidget(row,0);identity=combo.currentData()
            combo.blockSignals(True);combo.clear()
            for key,name in self.case_names():combo.addItem(name,key)
            combo.setCurrentIndex(combo.findData(identity));combo.blockSignals(False)

    def add_load(self,load=None,identity=None):
        if not isinstance(load,ShaftLoad):load=ShaftLoad(name=f'Load {self.loads.rowCount()+1}')
        combo=QComboBox()
        for key,name in self.case_names():combo.addItem(name,key)
        if identity is not None:combo.setCurrentIndex(combo.findData(identity))
        combo.currentIndexChanged.connect(self.changed)
        row=self.loads.rowCount();self.loads.insertRow(row);self.loads.setCellWidget(row,0,combo)
        for column,key in enumerate(self.LOAD_FIELDS,1):self.loads.setItem(row,column,QTableWidgetItem(str(getattr(load,key))))
        self.changed()

    def remove_row(self,table):
        if table.currentRow()>=0:table.removeRow(table.currentRow());self.changed()

    def remove_case(self):
        row=self.cases.currentRow()
        if row<0:return
        identity=self.cases.item(row,0).data(Qt.UserRole)
        for load_row in reversed(range(self.loads.rowCount())):
            if self.loads.cellWidget(load_row,0).currentData()==identity:self.loads.removeRow(load_row)
        self.cases.removeRow(row);self.case_changed();self.changed()

    def set_study(self,study):
        study.validate();self._loading=True
        try:
            self.name.setText(study.name)
            for key,widget in self.numbers.items():widget.setValue(getattr(study,key))
            self.locator.setCurrentText(study.axial_locator.upper())
            self.sections.setRowCount(0);self.cases.setRowCount(0);self.loads.setRowCount(0)
            for section in study.sections:self.add_section(section)
            for case in study.cases:self.add_case(case)
            self.source_study=study.source_study;self.source_text.setPlainText(study.source_description);self.notes.setPlainText(study.notes)
            self.result=None;self.plot.set_result(None);self.report.clear();self.summary.clear();self.dirty=False
            self.status.setText('Ready to calculate the explicitly defined shaft load path.')
        finally:self._loading=False

    def read_table(self,table,row,fields,text_fields,offset=0):
        data={}
        for column,key in enumerate(fields,offset):
            item=table.item(row,column)
            if item is None:raise ValueError(f'Incomplete row {row+1}')
            data[key]=item.text().strip() if key in text_fields else float(item.text())
        return data

    def read_study(self):
        sections=[ShaftSection(**self.read_table(self.sections,row,self.SECTION_FIELDS,{'material_basis'})) for row in range(self.sections.rowCount())]
        cases=[];mapping={}
        for row in range(self.cases.rowCount()):
            case=ShaftCase(**self.read_table(self.cases,row,self.CASE_FIELDS,{'name'}),loads=[])
            mapping[self.cases.item(row,0).data(Qt.UserRole)]=case;cases.append(case)
        for row in range(self.loads.rowCount()):
            identity=self.loads.cellWidget(row,0).currentData()
            if identity not in mapping:raise ValueError(f'Choose a case for load row {row+1}')
            mapping[identity].loads.append(ShaftLoad(**self.read_table(self.loads,row,self.LOAD_FIELDS,{'name'},1)))
        study=ShaftStudy(name=self.name.text(),**{key:w.value() for key,w in self.numbers.items()},
            axial_locator=self.locator.currentText().lower(),sections=sections,cases=cases,source_study=self.source_study,
            source_description=self.source_text.toPlainText(),notes=self.notes.toPlainText())
        study.validate();return study

    def calculate(self):
        try:
            self.result=calculate_shaft_study(self.read_study());self.report.setHtml(shaft_report_html(self.result))
            self.case_choice.blockSignals(True);self.case_choice.clear();self.case_choice.addItems([c['name'] for c in self.result['cases']]);self.case_choice.blockSignals(False)
            self.update_plot();self.tabs.setCurrentWidget(self.result_page)
            self.status.setText('Shaft equilibrium, motion and nominal stress calculated. Bearing capacity and fatigue life remain unassessed.')
            return True
        except (ValueError,TypeError,RuntimeError,OverflowError) as exc:
            self.result=None;self.plot.set_result(None);self.report.clear();self.summary.clear();self.show_error(exc);return False

    def update_plot(self,*_):
        if not self.result:return
        index=max(0,self.case_choice.currentIndex());self.plot.set_result(self.result,index,self.quantity.currentText())
        case=self.result['cases'][index];a,b=case['bearings'];m=case['maxima']
        self.summary.setText(f"Bearing A: radial {a['radial_load_n']:.6g} N, axial {a['axial_load_n']:.6g} N. Bearing B: radial {b['radial_load_n']:.6g} N, axial {b['axial_load_n']:.6g} N. Maximum deflection {m['deflection_magnitude_mm']['value']:.6g} mm at X={m['deflection_magnitude_mm']['position_mm']:.6g} mm. Nominal surface stress {m['nominal_surface_von_mises_mpa']['value']:.6g} MPa.\n"+' '.join(case['findings']))

    def show_error(self,error):QMessageBox.warning(self,'Shaft study',str(error))

    def assess_bearings(self):
        from .bearings import bearings_from_shaft
        from .bearing_ui import BearingStudyDialog
        try:study=bearings_from_shaft(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=BearingStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def assess_fatigue(self):
        from .fatigue import fatigue_from_shaft
        from .fatigue_ui import FatigueStudyDialog
        try:study=fatigue_from_shaft(self.read_study())
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        dialog=FatigueStudyDialog(self,study);dialog.dirty=True;dialog.present();return True

    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=self.save_destination('Save shaft study',str(self.path or 'shaft.gearforge-shaft'),'Shaft study (*.gearforge-shaft)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True

    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved shaft study','Save the shaft study before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard

    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open shaft study','','Shaft study (*.gearforge-shaft)')
        if not path:return False
        try:study=ShaftStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True

    def export(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose a new shaft calculation folder','shaft-calculation','Folder name (*)')
        if not path:return False
        try:export_shaft_study(study,Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.status.setText('Exported inputs, calculations, readable report and integrity manifest.');return True

    def reject(self):
        if self.confirm_discard():super().reject()

    def closeEvent(self,event):
        if self.confirm_discard():self.dirty=False;super().closeEvent(event)
        else:event.ignore()
