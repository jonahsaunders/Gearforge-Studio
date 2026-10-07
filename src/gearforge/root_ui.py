"""Cancellable desktop tooth-root elastic studies with retained evidence."""
from dataclasses import asdict
import json
import math
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QPointF, QProcess, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox,QDialog,QFileDialog,QFormLayout,QHBoxLayout,QHeaderView,
    QLabel,QLineEdit,QMessageBox,QPushButton,QTabWidget,QTableWidget,QTableWidgetItem,
    QTextBrowser,QTextEdit,QVBoxLayout,QWidget)

from .models import atomic_text,read_text_limited,strict_json
from .root_stress import RootStressStudy,root_from_profile,synthetic_root_example,root_report_html
from .tooth_profile import ToothProfileStudy


class ProbePlot(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setMinimumSize(520,260)
        self.result=None;self.case_index=0;self.probe_index=0;self.rendered_items=0
        self.setAccessibleName('Signed normal and shear stress at one fixed material point')

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#f8fafc'))
        p.setPen(QColor('#263449'));self.rendered_items=0
        if not self.result or not 0<=self.case_index<len(self.result['cases']) or not 0<=self.probe_index<len(self.result['inputs']['probes']):
            p.drawText(self.rect(),Qt.AlignCenter,'Define fixed points and calculate to view signed stress.');return
        case=self.result['cases'][self.case_index];probe=self.result['inputs']['probes'][self.probe_index];groups={}
        for position in case['positions']:
            for value in position['point_probes'][self.probe_index]['values']:
                groups.setdefault(value['element_index'],[]).append((position['position_fraction'],value['resolved_mpa']['normal_mpa'],value['resolved_mpa']['shear_mpa']))
        if not groups:
            p.drawText(self.rect(),Qt.AlignCenter,'Point outside the fine mesh, or operating case unassessed. No substituted stress.');return
        values=[value for group in groups.values() for value in group]
        low=min(0.,min(min(v[1:]) for v in values));high=max(0.,max(max(v[1:]) for v in values))
        margin=max(1e-10,(high-low)*.08);low-=margin;high+=margin
        def point(value,index):
            return QPointF(82+value[0]*(self.width()-120),self.height()-65-(value[index]-low)/(high-low)*(self.height()-140))
        p.drawText(20,24,f"{probe['name'][:50]} · {case['name'][:45]} · {case['flank']} flank")
        p.drawText(20,46,f"Fixed X {probe['x_mm']:.6g}, Y {probe['y_mm']:.6g} mm · normal {probe['normal_direction_deg']:g}° from +X")
        p.drawLine(82,75,82,self.height()-65);p.drawLine(82,self.height()-65,self.width()-38,self.height()-65)
        p.drawText(5,80,f'{high:.4g}');p.drawText(5,self.height()-64,f'{low:.4g}')
        p.setPen(QPen(QColor('#94a3b8'),1,Qt.DashLine));p.drawLine(point((0,0),1),point((1,0),1))
        for values in groups.values():
            for index,color in ((1,'#2563eb'),(2,'#b44418')):
                p.setPen(QPen(QColor(color),1.5));p.setBrush(QColor(color))
                p.drawPolyline(QPolygonF([point(value,index) for value in values]))
                for value in values:p.drawEllipse(point(value,index),2.5,2.5);self.rendered_items+=1
        p.setPen(QColor('#263449'));p.drawText(82,self.height()-44,'0');p.drawText(self.width()-42,self.height()-44,'1')
        p.drawText(20,self.height()-25,'Path fraction · Blue: normal MPa · Orange: shear MPa · separate element sides')
        p.drawText(20,self.height()-7,'Sampled positions only; no chronology or full loading cycle. Not a fatigue history.')


class RootPlot(QWidget):
    def __init__(self,curves=False,parent=None):
        super().__init__(parent);self.setMinimumSize(520,360);self.result=None;self.case_index=0;self.position_index=0
        self.curves=curves;self.zoom=False;self.deformation=0.;self.rendered_items=0
        self.setAccessibleName('Sampled tooth-root stress curves' if curves else 'Elastic sector mesh and calculated stress')

    def selection(self):
        if not self.result or not self.result['calculation_available']:return None,None,None
        cases=self.result['cases']
        if self.case_index>=len(cases):return None,None,None
        case=cases[self.case_index];positions=case['positions']
        if self.position_index>=len(positions):return case,None,None
        position=positions[self.position_index]
        return case,position,self.result['mesh_levels'][-1]['responses'][position['unit_response_index']]

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#f8fafc'))
        p.setPen(QColor('#263449'));self.rendered_items=0
        if not self.result or not self.result['calculation_available']:
            p.drawText(self.rect(),Qt.AlignCenter,'Calculate a supported elastic study to view results.');return
        case,position,response=self.selection();scale=case['ideal_applied_member_torque_n_mm'] if response else None
        if self.curves:
            if response is None:p.drawText(self.rect(),Qt.AlignCenter,'This case has no assessed operating stress.');return
            rows=response['root_curve'];groups={};pitch=2*math.pi/self.result['inputs']['source']['source']['pair'][self.result['inputs']['source']['role']+'_teeth']
            for row in rows:
                angle=math.atan2(row['x_mm'],row['y_mm']);key=(row['tooth_index'],angle-row['tooth_index']*pitch>0)
                groups.setdefault(key,[]).append((math.degrees(angle),row['von_mises_mpa_per_n_mm']*scale,row['tensile_mpa_per_n_mm']*scale))
            left=min(v[0] for values in groups.values() for v in values);right=max(v[0] for values in groups.values() for v in values)
            maximum=max(1e-12,max(max(v[1:]) for values in groups.values() for v in values))
            def point(v,index):return QPointF(75+(v[0]-left)/(right-left)*(self.width()-110),self.height()-75-v[index]/maximum*(self.height()-155))
            p.setPen(QColor('#263449'));p.drawText(24,26,'Root edge samples · unaveraged element values')
            p.drawText(24,49,f"{case['name'][:65]} · path fraction {position['position_fraction']:g}")
            p.drawText(24,74,f'{maximum:.5g} MPa');p.drawLine(75,80,75,self.height()-75);p.drawLine(75,self.height()-75,self.width()-35,self.height()-75)
            for values in groups.values():
                values.sort(key=lambda v:v[0])
                for index,color in [(1,'#b44418'),(2,'#2563eb')]:
                    p.setPen(QPen(QColor(color),1.5));p.drawPolyline(QPolygonF([point(v,index) for v in values]));self.rendered_items+=len(values)
            p.setPen(QColor('#263449'));p.drawText(75,self.height()-50,f'{left:.4g}°');p.drawText(self.width()-100,self.height()-50,f'{right:.4g}°')
            p.drawText(24,self.height()-26,'Angle from +Y · Orange: von Mises · Blue: tensile principal · sampled positions only')
            return
        fine=self.result['mesh_levels'][-1];mesh=fine['mesh'];nodes=mesh['nodes_mm']
        displacement=response['displacement_mm_per_n_mm'] if response and self.deformation else None
        points=[(x+self.deformation*scale*displacement[i][0],y+self.deformation*scale*displacement[i][1]) if displacement else (x,y) for i,(x,y) in enumerate(nodes)]
        if self.zoom:
            central=[(r['x_mm'],r['y_mm']) for r in fine['responses'][0]['root_curve'] if r['tooth_index']==0]
            left=min(x for x,y in central);right=max(x for x,y in central);bottom=min(y for x,y in central)
            span=right-left;left-=span*.15;right+=span*.15;bottom-=span*.15;top=max(y for x,y in nodes)+span*.1
        else:
            left=min(x for x,y in points);right=max(x for x,y in points);bottom=min(y for x,y in points);top=max(y for x,y in points)
        factor=min((self.width()-80)/max(right-left,1e-12),(self.height()-150)/max(top-bottom,1e-12))
        def transform(point):return QPointF(self.width()/2+(point[0]-(left+right)/2)*factor,65+(top-point[1])*factor)
        maximum=max(response['element_von_mises_mpa_per_n_mm'])*scale if response else 0.
        p.save();p.setClipRect(20,60,self.width()-40,self.height()-140)
        for index,cell in enumerate(mesh['elements']):
            polygon=[points[i] for i in cell[:4]]
            if max(v[0] for v in polygon)<left or min(v[0] for v in polygon)>right or max(v[1] for v in polygon)<bottom:continue
            value=response['element_von_mises_mpa_per_n_mm'][index]*scale if response else 0.
            color=QColor.fromHsvF(.65*(1-min(1,value/maximum)) if maximum>0 else .65,.68,.94)
            p.setBrush(color if response else QColor('#e2e8f0'));p.setPen(QPen(QColor('#475569'),.2));p.drawPolygon(QPolygonF([transform(v) for v in polygon]));self.rendered_items+=1
        p.setPen(QPen(QColor('#171717'),2))
        for node in mesh['fixed_node_indices']:p.drawPoint(transform(points[node]))
        p.restore();p.setPen(QColor('#263449'))
        p.drawText(24,26,'Central tooth detail' if self.zoom else f"{fine['sector_teeth']}-tooth sector · {fine['elements']:,} Q9 elements")
        p.drawText(24,49,f"{case['name'][:65]} · path fraction {position['position_fraction']:g}" if response else 'Geometry only — selected case stress is unassessed')
        p.drawText(24,self.height()-57,f'Cell Gauss von Mises: blue 0 → red {maximum:.5g} MPa · black: fixed support' if response else 'Unloaded mesh · black: fixed support')
        p.drawText(24,self.height()-34,f'Displacement drawn ×{self.deformation:g} · millimetres · ' + ('undeformed geometry' if not self.deformation else 'exaggerated shape, not actual geometry'))
        p.drawText(24,self.height()-12,'Elastic model only. Mesh checks and material evidence appear in Assessment.')


class RootStressDialog(QDialog):
    def __init__(self,parent=None,study=None):
        super().__init__(parent);self.resize(1160,850);self.setWindowTitle('Tooth-root elastic stress')
        self.path=None;self.result=None;self.dirty=False;self._loading=True;self.process=None;self.temporary=None
        self.error_output='';self.fields={};self.actions=[]
        layout=QVBoxLayout(self);note=QLabel('Calculate 2D elastic stress from a generated spur root. Material, support and loading are explicit inputs. Mesh checks do not establish fatigue life or a production rating.')
        note.setWordWrap(True);layout.addWidget(note);self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        material=QWidget();form=QFormLayout(material)
        self.name=QLineEdit();self.name.textChanged.connect(self.changed);form.addRow('Study name',self.name)
        self.material_status=QComboBox();self.material_status.addItems(['unverified','synthetic','declared']);self.material_status.currentIndexChanged.connect(self.changed)
        form.addRow('Material data status',self.material_status)
        for key,label in [('youngs_modulus_mpa','Young modulus (MPa)'),('poisson_ratio','Poisson ratio'),('effective_face_width_mm','Effective loaded face width (mm)'),
            ('maximum_elastic_stress_mpa','Maximum elastic stress (MPa)'),('minimum_temperature_c','Material minimum temperature (°C)'),('maximum_temperature_c','Material maximum temperature (°C)')]:self.add_field(form,key,label)
        for key,label in [('material_reference','Material source and revision'),('redistribution_basis','Basis for sharing material data')]:self.add_field(form,key,label,True)
        hint=QLabel('Blank material values remain unknown. A declared source records your evidence; it does not constitute an independent approval. Face width may not exceed the retained gear face width.');hint.setWordWrap(True);form.addRow(hint)
        self.tabs.addTab(material,'Material and face width')
        domain=QWidget();form=QFormLayout(domain);self.plane_mode=QComboBox();self.plane_mode.addItems(['plane_stress','plane_strain']);self.plane_mode.currentIndexChanged.connect(self.changed)
        form.addRow('Plane model',self.plane_mode)
        for key,label in [('support_radius_mm','Fully fixed inner radius (mm)'),('sector_teeth','Teeth in sector (odd, 3–9)'),('patch_half_width_mm','Pressure patch half arc length (mm)'),
            ('load_positions','Active-path fractions, comma separated'),('angular_divisions_per_tooth','Base angular divisions per tooth'),('radial_layers','Base radial layers'),
            ('convergence_tolerance_percent','Mesh and sector comparison tolerance (%)')]:self.add_field(form,key,label)
        for key,label in [('support_basis','Physical support and plane-model basis'),('notes','Study notes')]:self.add_field(form,key,label,True)
        hint=QLabel('The inner arc is clamped and cut faces are free. Three mesh levels (1×, 2×, 4×) and a wider sector assess numerical sensitivity. Each pressure patch must lie wholly on the involute.');hint.setWordWrap(True);form.addRow(hint)
        self.tabs.addTab(domain,'Support and numerical model')
        loads=QWidget();column=QVBoxLayout(loads);hint=QLabel('Every retained duty case needs explicit factors and temperature. Positive pinion input loads the left flank; reversals use the opposite flank. Factors scale the retained ideal member torque.');hint.setWordWrap(True);column.addWidget(hint)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['Retained case','Load multiplier','Load share','Temperature °C','Factor / distribution basis'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        self.table.itemChanged.connect(self.changed);column.addWidget(self.table);self.tabs.addTab(loads,'Load cases')
        page=QWidget();column=QVBoxLayout(page);row=QHBoxLayout()
        self.case_selector=QComboBox();self.position_selector=QComboBox();self.view=QComboBox();self.view.addItems(['Whole sector','Central tooth'])
        self.deformation=QComboBox();self.deformation.addItems(['Undeformed','Displacement ×1','Displacement ×1000','Displacement ×10000'])
        for label,widget in [('Case',self.case_selector),('Position',self.position_selector),('View',self.view),('Shape',self.deformation)]:row.addWidget(QLabel(label));row.addWidget(widget)
        self.case_selector.currentIndexChanged.connect(self.select_case);self.position_selector.currentIndexChanged.connect(self.refresh_plots)
        self.view.currentIndexChanged.connect(self.refresh_plots);self.deformation.currentIndexChanged.connect(self.refresh_plots)
        column.addLayout(row);self.plot=RootPlot();column.addWidget(self.plot,1);self.tabs.addTab(page,'Mesh and stress')
        page=QWidget();column=QVBoxLayout(page);hint=QLabel('Uses the case and path position selected in Mesh and stress. Curves retain separate element-side values at shared points.');hint.setWordWrap(True);column.addWidget(hint)
        self.curves=RootPlot(curves=True);column.addWidget(self.curves,1);self.tabs.addTab(page,'Root stress curves')
        self.report=QTextBrowser();self.report.setOpenExternalLinks(False);self.tabs.addTab(self.report,'Assessment')
        self.source_view=QTextBrowser();self.source_view.setOpenExternalLinks(False);self.tabs.addTab(self.source_view,'Retained cutter and duty')
        page=QWidget();column=QVBoxLayout(page)
        hint=QLabel('Track up to 16 fixed material points. X/Y are millimetres from the gear center in the undeformed body frame; the central tooth points along +Y. The normal direction is counterclockwise from +X. Points outside any mesh remain unavailable.');hint.setWordWrap(True);column.addWidget(hint)
        self.probe_table=QTableWidget(0,5);self.probe_table.setHorizontalHeaderLabels(['Point name','X mm','Y mm','Normal direction °','Location / direction basis'])
        self.probe_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);self.probe_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.Stretch)
        self.probe_table.itemChanged.connect(self.changed);column.addWidget(self.probe_table)
        row=QHBoxLayout();self.add_probe_button=QPushButton('Add point');self.remove_probe_button=QPushButton('Remove selected point')
        self.add_probe_button.clicked.connect(self.add_probe);self.remove_probe_button.clicked.connect(self.remove_probe)
        row.addWidget(self.add_probe_button);row.addWidget(self.remove_probe_button);row.addStretch();column.addLayout(row)
        row=QHBoxLayout();self.probe_case_selector=QComboBox();self.probe_selector=QComboBox()
        for label,widget in [('Case',self.probe_case_selector),('Point',self.probe_selector)]:row.addWidget(QLabel(label));row.addWidget(widget);widget.currentIndexChanged.connect(self.refresh_plots)
        column.addLayout(row);self.probe_plot=ProbePlot();column.addWidget(self.probe_plot,1);self.tabs.addTab(page,'Fixed material points')
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        for actions in [[('Open…',self.open_study),('Save…',self.save_study),('From tooth profile…',self.from_source),('Synthetic example',self.example)],
            [('Calculate',self.calculate),('Export assessment…',self.export)]]:
            row=QHBoxLayout()
            for label,callback in actions:
                button=QPushButton(label);button.clicked.connect(callback);row.addWidget(button);self.actions.append(button)
            row.addStretch();layout.addLayout(row)
        row=QHBoxLayout();self.cancel=QPushButton('Cancel calculation');self.cancel.clicked.connect(self.cancel_job);self.cancel.setEnabled(False);row.addWidget(self.cancel)
        close=QPushButton('Close');close.clicked.connect(self.reject);row.addWidget(close);row.addStretch();layout.addLayout(row)
        self.set_study(study or RootStressStudy())

    def add_field(self,form,key,label,multiline=False):
        widget=QTextEdit() if multiline else QLineEdit();widget.setAccessibleName(label)
        if multiline:widget.setAcceptRichText(False);widget.setMaximumHeight(82)
        widget.textChanged.connect(self.changed);form.addRow(label,widget);self.fields[key]=widget
        form.labelForField(widget).setBuddy(widget)

    def set_study(self,study):
        self.cancel_job();self.model=RootStressStudy.from_dict(asdict(study));self._loading=True
        self.name.setText(study.name);self.material_status.setCurrentText(study.material_status);self.plane_mode.setCurrentText(study.plane_mode)
        for key,widget in self.fields.items():
            value=getattr(study,key)
            if isinstance(widget,QTextEdit):widget.setPlainText(value)
            else:widget.setText(', '.join(map(repr,value)) if key=='load_positions' else '' if value is None else repr(value))
        self.table.setRowCount(len(study.cases))
        for row,case in enumerate(study.cases):
            for col,key in enumerate(('case_name','normal_load_multiplier','load_share','temperature_c','factor_basis')):
                value=getattr(case,key);item=QTableWidgetItem('' if value is None else value if isinstance(value,str) else repr(value))
                if col==0:item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row,col,item)
        self.probe_table.setRowCount(len(study.probes))
        for row,probe in enumerate(study.probes):
            for col,key in enumerate(('name','x_mm','y_mm','normal_direction_deg','basis')):
                value=getattr(probe,key);self.probe_table.setItem(row,col,QTableWidgetItem(value if isinstance(value,str) else repr(value)))
        self.source_view.setPlainText(json.dumps(asdict(study.source),indent=2));self.path=None;self.dirty=False;self._loading=False;self.clear_result()
        self.status.setText('Inputs loaded; calculate to assess the model.')

    def read_study(self):
        data=asdict(self.model);data.update(name=self.name.text(),material_status=self.material_status.currentText(),plane_mode=self.plane_mode.currentText())
        for key,widget in self.fields.items():
            if isinstance(widget,QTextEdit):data[key]=widget.toPlainText();continue
            value=widget.text().strip()
            if key=='load_positions':data[key]=[float(v.strip()) for v in value.split(',')]
            elif key in ('sector_teeth','angular_divisions_per_tooth','radial_layers'):data[key]=int(value)
            else:data[key]=float(value) if value else None
        for row,case in enumerate(data['cases']):
            for col,key in enumerate(('case_name','normal_load_multiplier','load_share','temperature_c','factor_basis')):
                value=self.table.item(row,col).text()
                case[key]=value if col in (0,4) else float(value.strip()) if value.strip() else None
        data['probes']=[]
        for row in range(self.probe_table.rowCount()):
            probe={}
            for col,key in enumerate(('name','x_mm','y_mm','normal_direction_deg','basis')):
                value=self.probe_table.item(row,col).text();probe[key]=value if col in (0,4) else float(value)
            data['probes'].append(probe)
        return RootStressStudy.from_dict(data)

    def add_probe(self):
        if self.probe_table.rowCount()>=16:return
        self._loading=True;row=self.probe_table.rowCount();self.probe_table.insertRow(row)
        names={self.probe_table.item(i,0).text() for i in range(row)};number=1
        while f'Material point {number}' in names:number+=1
        for col,value in enumerate((f'Material point {number}','0','0','0','')):self.probe_table.setItem(row,col,QTableWidgetItem(value))
        self.probe_table.setCurrentCell(row,0);self._loading=False;self.changed()

    def remove_probe(self):
        row=self.probe_table.currentRow()
        if row>=0:self.probe_table.removeRow(row);self.changed()

    def clear_result(self):
        self.result=None;self.report.clear();self.case_selector.clear();self.position_selector.clear()
        self.probe_case_selector.clear();self.probe_selector.clear()
        for plot in (self.plot,self.curves,self.probe_plot):plot.result=None;plot.update()

    def changed(self,*args):
        if self._loading:return
        self.cancel_job();self.dirty=True;self.clear_result();self.status.setText('Inputs changed; recalculate before interpreting stresses.')

    def select_case(self,*args):
        self.position_selector.clear()
        if self.result and 0<=self.case_selector.currentIndex()<len(self.result['cases']):
            self.position_selector.addItems([f"{p['position_fraction']:g}" for p in self.result['cases'][self.case_selector.currentIndex()]['positions']])
        self.refresh_plots()

    def refresh_plots(self,*args):
        for plot in (self.plot,self.curves):
            plot.case_index=max(0,self.case_selector.currentIndex());plot.position_index=max(0,self.position_selector.currentIndex())
            plot.zoom=self.view.currentIndex()==1;plot.deformation=(0.,1.,1000.,10000.)[self.deformation.currentIndex()];plot.update()
        self.probe_plot.case_index=self.probe_case_selector.currentIndex();self.probe_plot.probe_index=self.probe_selector.currentIndex();self.probe_plot.update()

    def set_busy(self,busy):
        for index in range(3):self.tabs.widget(index).setEnabled(not busy)
        self.probe_table.setEnabled(not busy);self.add_probe_button.setEnabled(not busy);self.remove_probe_button.setEnabled(not busy)
        for button in self.actions:button.setEnabled(not busy)
        self.cancel.setEnabled(busy)

    def start_job(self,task,study,destination=None):
        if self.process is not None:return False
        self.temporary=tempfile.TemporaryDirectory(prefix='gearforge-root-');folder=Path(self.temporary.name)
        self.result_path=folder/'result.json';request=dict(task=task,study=asdict(study),result_path=str(self.result_path))
        if destination is not None:request['destination']=str(destination)
        try:atomic_text(folder/'input.json',json.dumps(request,allow_nan=False))
        except OSError as exc:self.cleanup_job();self.show_error(exc);return False
        self.task=task;self.error_output='';self.process=QProcess(self);self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardError.connect(self.drain_error);self.process.readyReadStandardOutput.connect(self.drain_output)
        self.process.finished.connect(self.job_finished);self.process.errorOccurred.connect(self.job_error)
        self.set_busy(True);self.status.setText('Calculating three meshes and a wider sector… You can cancel this calculation.')
        command=['--worker-file',str(folder/'input.json')]
        if not getattr(sys,'frozen',False):command=['-m','gearforge.cli',*command]
        self.process.start(sys.executable,command);return True

    def drain_error(self):
        if self.process:self.error_output=(self.error_output+bytes(self.process.readAllStandardError()).decode('utf-8',errors='replace'))[-4000:]
    def drain_output(self):
        if self.process:self.process.readAllStandardOutput()
    def job_error(self,error):
        if error==QProcess.FailedToStart:
            detail=self.process.errorString();self.cleanup_job();self.status.setText('Calculation could not start.');self.show_error(detail)
    def job_finished(self,*args):
        try:
            response=strict_json(read_text_limited(self.result_path,128_000_000,'Elastic worker result'))
            if not response['ok']:raise ValueError(response['error'])
            result=response['result'];task=self.task
        except (OSError,ValueError,KeyError,TypeError) as exc:
            detail=str(exc)+(' '+self.error_output if self.error_output else '');self.cleanup_job();self.status.setText('Calculation failed; inputs are retained.');self.show_error(detail);return
        self.cleanup_job()
        if task=='root-export':
            self.status.setText(f"Exported {result['files']} files to {result['destination']}; production rating remains unavailable.");return
        self.result=result;self.report.setHtml(root_report_html(result))
        for plot in (self.plot,self.curves,self.probe_plot):plot.result=result
        self.probe_case_selector.addItems([c['name'] for c in result['cases']]);self.probe_selector.addItems([p['name'] for p in result['inputs']['probes']])
        self.case_selector.addItems([c['name'] for c in result['cases']]);self.select_case()
        self.tabs.setCurrentIndex(3 if result['calculation_available'] else 5)
        checks=result['mesh_convergence_passed'] is True and result['domain_sensitivity_passed'] is True
        checks=checks and all(c['mesh_convergence_passed'] is True and c['domain_sensitivity_passed'] is True for c in result['probe_checks'])
        self.status.setText(('Elastic fields available; numerical comparisons '+('meet the entered threshold.' if checks else 'remain unresolved.')+' Review material evidence and assumptions in Assessment.')
            if result['calculation_available'] else 'Calculation unavailable: '+'; '.join(result['findings']))

    def cleanup_job(self):
        if self.process:
            self.process.deleteLater();self.process=None
        if self.temporary:self.temporary.cleanup();self.temporary=None
        self.set_busy(False)
    def cancel_job(self):
        if self.process:
            self.process.finished.disconnect(self.job_finished);self.process.errorOccurred.disconnect(self.job_error)
            self.process.kill();self.process.waitForFinished(3000);self.cleanup_job();self.status.setText('Calculation cancelled; inputs are retained.')

    def calculate(self):
        if self.process:return False
        self.clear_result()
        try:study=self.read_study()
        except (ValueError,TypeError,OverflowError) as exc:self.show_error(exc);return False
        return self.start_job('root-calculate',study)

    def show_error(self,error):QMessageBox.warning(self,'Tooth-root stress',str(error))
    def confirm_discard(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved root study','Save the root study before continuing?',QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel,QMessageBox.Save)
        return self.save_study() if answer==QMessageBox.Save else answer==QMessageBox.Discard
    def save_study(self):
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Save root study',str(self.path or 'gearbox.gearforge-root'),'Root study (*.gearforge-root)')
        if not path:return False
        try:study.save(Path(path))
        except (ValueError,OSError) as exc:self.show_error(exc);return False
        self.path=Path(path);self.dirty=False;self.status.setText(f'Saved {self.path.name}');return True
    def open_study(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Open root study','','Root study (*.gearforge-root)')
        if not path:return False
        try:study=RootStressStudy.load(Path(path))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.path=Path(path);return True
    def from_source(self):
        if not self.confirm_discard():return False
        path,_=QFileDialog.getOpenFileName(self,'Retain cutter profile','','Tooth profile (*.gearforge-tooth)')
        if not path:return False
        try:study=root_from_profile(ToothProfileStudy.load(Path(path)))
        except (ValueError,TypeError,OSError) as exc:self.show_error(exc);return False
        self.set_study(study);self.dirty=True;return True
    def example(self):
        if not self.confirm_discard():return False
        self.set_study(synthetic_root_example());self.dirty=True;return True
    def export(self):
        if self.process:return False
        try:study=self.read_study()
        except (ValueError,TypeError) as exc:self.show_error(exc);return False
        path,_=QFileDialog.getSaveFileName(self,'Choose new assessment folder','root-assessment','Folder name (*)')
        if not path:return False
        destination=Path(path)
        if destination.exists() or destination.is_symlink():self.show_error('Choose a new assessment folder');return False
        return self.start_job('root-export',study,destination)
    def reject(self):
        if self.confirm_discard():self.cancel_job();super().reject()
    def closeEvent(self,event):
        if self.confirm_discard():self.cancel_job();event.accept()
        else:event.ignore()
