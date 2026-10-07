"""Editable signed stress histories, evidence, cycle plots and cancellable assessment."""
from dataclasses import asdict
import csv
import html
import io
import json
import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from .chart_style import ChartWidget, ReportBrowser, chart_color

from .desktop_ui import StudyDialog, StudyTabs

from .cyclic import (HistoryStudy, HistoryBlock, SNPoint, synthetic_history_example, history_from_study,
    parse_sample_csv, import_sample_csv, history_report_html)
from .engineering import EngineeringStudy
from .study_worker import StudyWorker


def sample_text(samples):
    return 'time_s,stress_mpa\n' + ''.join(f'{s.time_s!r},{s.stress_mpa!r}\n' for s in samples) if samples else ''


class HistoryPlot(ChartWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 340)
        self.setAccessibleName('Stress history, cycle distribution or fatigue curve; full data in assessment export')
        self.result = None
        self.mode = 0
        self.block_index = 0
        self.rendered_items = 0

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.palette().base())
        p.setPen(self.palette().text().color())
        self.rendered_items = 0
        if not self.result or not self.result['calculation_available']:
            p.drawText(self.rect(), Qt.AlignCenter, 'Calculate an entered history to view its plots.')
            return
        rows = self.result['cycles']
        if self.mode == 0:
            block = self.result['inputs']['blocks'][self.block_index]
            points = [(v['time_s'], v['stress_mpa']) for v in block['samples']]
            title, xlabel, ylabel = 'One template block · raw signed local normal stress', 'Time (s)', 'Stress (MPa)'
            subtitle = f"{block['name'][:65]} · {block['repetitions']:,} repetitions"
        elif self.mode == 1:
            points = [(c['mean_mpa'], c['range_mpa']) for c in rows]
            title, xlabel, ylabel = 'Cycle ranges and means · raw stresses', 'Mean stress (MPa)', 'Range (MPa)'
            subtitle = 'Bubble area increases with log cycle count. Full values are retained in CSV.'
        else:
            curve = self.result['inputs']['material']['sn_curve']
            points = [(math.log10(v['failure_cycles']), math.log10(v['amplitude_mpa'])) for v in curve]
            title, xlabel, ylabel = 'Entered fully reversed failure S-N curve', 'log10(failure cycles)', 'log10(amplitude MPa)'
            subtitle = 'Bounded interpolation only. No extrapolated endurance limit.'
        if not points:
            p.drawText(self.rect(), Qt.AlignCenter, 'No points are available for this view.')
            return
        left, right = min(v[0] for v in points), max(v[0] for v in points)
        low, high = min(v[1] for v in points), max(v[1] for v in points)
        if left == right:
            left -= .5
            right += .5
        if low == high:
            low -= .5
            high += .5
        margin = (high-low)*.08
        low -= margin
        high += margin
        box = QRectF(88, 92, self.width()-128, self.height()-172)
        def point(value):
            return QPointF(box.left()+(value[0]-left)/(right-left)*box.width(), box.bottom()-(value[1]-low)/(high-low)*box.height())
        p.drawText(24, 25, title)
        p.drawText(24, 48, subtitle)
        p.drawText(24, 73, ylabel)
        p.drawText(QRectF(0, self.height()-33, self.width(), 25), Qt.AlignCenter, xlabel)
        for index in range(5):
            x, y = left+(right-left)*index/4, low+(high-low)*index/4
            p.setPen(QPen(self.palette().mid().color(), 1))
            p.drawLine(point((x, low)), point((x, high)))
            p.drawLine(point((left, y)), point((right, y)))
            p.setPen(self.palette().text().color())
            p.drawText(QRectF(point((x, low)).x()-42, box.bottom()+5, 84, 20), Qt.AlignCenter, f'{x:.4g}')
            p.drawText(QRectF(4, point((left, y)).y()-10, 76, 20), Qt.AlignRight, f'{y:.4g}')
        if self.mode == 1:
            # Screen-pixel aggregation retains the population of every cycle bin.
            # It does not alter the exact arithmetic or exported cycle table.
            cells = {}
            for value, cycle in zip(points, rows):
                pos = point(value)
                key = (int(pos.x()/3)*3, int(pos.y()/3)*3)
                cells[key] = cells.get(key, 0)+cycle['count']
            maximum = max(math.log1p(count) for count in cells.values())
            p.setPen(chart_color(self,'#2563eb'))
            p.setBrush(chart_color(self,'#79a2ee'))
            for (x, y), count in cells.items():
                radius = 2+7*math.sqrt(math.log1p(count)/maximum)
                p.drawEllipse(QPointF(x, y), radius, radius)
            self.rendered_items = len(cells)
        else:
            if len(points) > 2000:
                # Keep each bucket's min/max in chronological order, including
                # the first/last endpoints. Axis limits above use every sample.
                selected = {0, len(points)-1}
                step = math.ceil(len(points)/900)
                for start in range(0, len(points), step):
                    group = range(start, min(start+step, len(points)))
                    selected.update((min(group, key=lambda i: points[i][1]), max(group, key=lambda i: points[i][1])))
                points = [points[i] for i in sorted(selected)]
                p.drawText(24, self.height()-8, 'Display reduced with per-bucket extrema retained; complete samples are exported.')
            p.setPen(QPen(chart_color(self,'#2563eb'), 2))
            p.drawPolyline(QPolygonF([point(v) for v in points]))
            self.rendered_items = len(points)


class HistoryStudyDialog(StudyDialog):
    BLOCK_KEYS = ('name', 'duty_case_name', 'repetitions', 'starts_per_repeat', 'data_status', 'source_reference', 'applicable_conditions', 'redistribution_basis')
    MATERIAL_TEXT = ('designation', 'source_reference', 'applicable_conditions', 'redistribution_basis', 'failure_definition')
    BASIS_TEXT = ('name', 'point_definition', 'history_basis', 'coverage_basis', 'stress_factor_basis', 'mean_stress_basis', 'damage_limit_basis', 'notes')

    def __init__(self, parent=None, study=None):
        super().__init__(parent)
        self.resize(1160, 850)
        self.setWindowTitle('Cyclic stress history and fatigue')
        self.path = None
        self.result = None
        self.dirty = False
        self._loading = True
        self.selected_block = -1
        self.basis_fields = {}
        self.material_fields = {}
        self.actions = []
        self.worker = StudyWorker(self)
        self.worker.completed.connect(self.job_finished)
        self.worker.failed.connect(self.job_failed)
        self.worker.busy.connect(self.set_busy)
        layout = QVBoxLayout(self)
        note = QLabel('Count changes in signed normal stress at one material point. Fatigue damage requires an elastic uniaxial history and applicable S-N data. No gearbox load or life rating is established.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs = StudyTabs()
        layout.addWidget(self.tabs, 1)
        basis = self.form_tab('Point and method')
        self.add_fields(basis, self.basis_fields, [
            ('name', 'Study name'), ('point_definition', 'Physical point and normal direction'),
            ('history_basis', 'History source / model and revision'), ('coverage_basis', 'Duty and transition coverage basis'),
            ('history_minimum_temperature_c', 'Lowest local temperature (°C)'), ('history_maximum_temperature_c', 'Highest local temperature (°C)'),
            ('stress_design_factor', 'Stress design factor (at least 1)'), ('stress_factor_basis', 'Stress factor basis'),
            ('mean_stress_basis', 'Mean stress model applicability'), ('damage_limit', 'Entered damage limit (blank = unknown)'),
            ('damage_limit_basis', 'Damage limit basis'), ('notes', 'Notes')])
        self.stress_state = QComboBox()
        self.stress_state.addItems(['unverified', 'uniaxial_normal', 'other'])
        self.mean_model = QComboBox()
        self.mean_model.addItems(['unverified', 'fully_reversed_only', 'goodman_tension_only'])
        basis.insertRow(2, 'Declared stress state', self.stress_state)
        basis.insertRow(9, 'Mean stress model', self.mean_model)
        self.stress_state.currentIndexChanged.connect(self.changed)
        self.mean_model.currentIndexChanged.connect(self.changed)
        material = self.form_tab('Material and S-N curve')
        self.material_status = QComboBox()
        self.material_status.addItems(['unverified', 'synthetic', 'declared'])
        self.material_status.currentIndexChanged.connect(self.changed)
        material.addRow('Data status', self.material_status)
        self.add_fields(material, self.material_fields, [
            ('designation', 'Material / process designation'), ('source_reference', 'Source and revision'),
            ('applicable_conditions', 'Surface, size, process and applicability'), ('redistribution_basis', 'Basis for sharing these data'),
            ('failure_definition', 'Failure endpoint (e.g. crack initiation)'), ('survival_probability', 'Survival probability (fraction)'),
            ('confidence_probability', 'Confidence probability (fraction)'), ('elastic_limit_mpa', 'Local elastic stress limit (MPa)'),
            ('ultimate_tensile_mpa', 'Ultimate tensile strength (MPa)'), ('minimum_temperature_c', 'Material minimum temperature (°C)'),
            ('maximum_temperature_c', 'Material maximum temperature (°C)')])
        hint = QLabel('Fully reversed LOCAL normal stress amplitude versus cycles to the stated failure endpoint. Use failure data, not runouts. Cycles increase; amplitudes decrease. No extrapolation or beneficial compressive mean credit.')
        hint.setWordWrap(True)
        material.addRow(hint)
        self.curve = QPlainTextEdit()
        self.curve.setMinimumHeight(130)
        self.curve.setPlaceholderText('failure_cycles,amplitude_mpa\n1000,220\n1000000000,120')
        self.curve.textChanged.connect(self.changed)
        material.addRow('S-N CSV', self.curve)
        blocks = QWidget()
        column = QVBoxLayout(blocks)
        hint = QLabel('Blocks run in row order. Repeated blocks must return to their starting stress; adjacent blocks must share their endpoint stress. Enter transitions explicitly. Start counts and durations are checked against retained duty.')
        hint.setWordWrap(True)
        column.addWidget(hint)
        self.table = QTableWidget(0, len(self.BLOCK_KEYS))
        self.table.setHorizontalHeaderLabels(['Block name', 'Retained duty case', 'Repetitions', 'Starts per repeat', 'Data status', 'Source / revision', 'Applicable conditions', 'Sharing basis'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for col in range(8):
            self.table.setColumnWidth(col, 150 if col != 2 else 100)
        self.table.cellChanged.connect(self.changed)
        self.table.currentCellChanged.connect(self.select_block)
        column.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        for title, callback in [('Add block', self.add_block), ('Remove block', self.remove_block), ('Move up', lambda: self.move_block(-1)), ('Move down', lambda: self.move_block(1))]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        column.addLayout(buttons)
        self.tabs.addTab(blocks, 'Ordered blocks')
        samples = QWidget()
        column = QVBoxLayout(samples)
        self.sample_label = QLabel()
        self.sample_label.setWordWrap(True)
        column.addWidget(self.sample_label)
        hint = QLabel('Select a block in Ordered blocks, then edit its samples here. CSV columns: time_s,stress_mpa. Time starts at zero and strictly increases. Blank samples mean unknown. All blocks refer to the same physical point and stress direction.')
        hint.setWordWrap(True)
        column.addWidget(hint)
        self.samples = QPlainTextEdit()
        self.samples.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.samples.textChanged.connect(self.changed)
        column.addWidget(self.samples, 1)
        button = QPushButton('Import UTF-8 sample CSV…')
        button.clicked.connect(self.import_csv)
        column.addWidget(button)
        self.tabs.addTab(samples, 'Selected block samples')
        plots = QWidget()
        column = QVBoxLayout(plots)
        row = QHBoxLayout()
        self.plot_mode = QComboBox()
        self.plot_mode.addItems(['Signed history', 'Cycle ranges and means', 'Entered S-N curve'])
        self.plot_block = QComboBox()
        row.addWidget(self.plot_mode)
        row.addWidget(self.plot_block, 1)
        column.addLayout(row)
        self.plot = HistoryPlot()
        column.addWidget(self.plot, 1)
        self.plot_mode.currentIndexChanged.connect(self.refresh_plot)
        self.plot_block.currentIndexChanged.connect(self.refresh_plot)
        self.tabs.addTab(plots, 'Plots')
        self.report = ReportBrowser()
        self.tabs.addTab(self.report, 'Assessment')
        self.source_view = ReportBrowser()
        self.tabs.addTab(self.source_view, 'Retained gear duty')
        self.status = QLabel('Enter traceable local stress samples and applicable material data.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        for title, callback in [('Open…', self.open_study), ('Save…', self.save_study), ('From gear study…', self.from_source),
                                ('Synthetic example', self.example), ('Calculate', self.calculate), ('Export…', self.export)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
            self.actions.append(button)
        self.cancel = QPushButton('Cancel calculation')
        self.cancel.clicked.connect(self.cancel_job)
        self.cancel.setEnabled(False)
        row.addWidget(self.cancel)
        layout.addLayout(row)
        self.set_study(study or HistoryStudy())
        self.finish_ui()


    @property
    def process(self):
        return self.worker.process

    def form_tab(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        form = QFormLayout(widget)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, title)
        return form

    def add_fields(self, form, fields, entries):
        for key, title in entries:
            editor = QLineEdit()
            editor.textChanged.connect(self.changed)
            editor.setAccessibleName(title)
            fields[key] = editor
            form.addRow(title, editor)

    def set_study(self, study):
        study = HistoryStudy.from_dict(asdict(study))
        self.cancel_job()
        self._loading = True
        self.source = study.source
        self.path = None
        self.selected_block = -1
        for fields, obj in ((self.basis_fields, study), (self.material_fields, study.material)):
            for key, editor in fields.items():
                value = getattr(obj, key)
                editor.setText('' if value is None else str(value))
        self.stress_state.setCurrentText(study.stress_state)
        self.mean_model.setCurrentText(study.mean_stress_model)
        self.material_status.setCurrentText(study.material.data_status)
        self.curve.setPlainText('failure_cycles,amplitude_mpa\n'+''.join(f'{p.failure_cycles!r},{p.amplitude_mpa!r}\n' for p in study.material.sn_curve) if study.material.sn_curve else '')
        self.sample_texts = [sample_text(b.samples) for b in study.blocks]
        self.fingerprints = [(b.imported_file_sha256, b.imported_samples_sha256) for b in study.blocks]
        self.table.setRowCount(len(study.blocks))
        for row, block in enumerate(study.blocks):
            for col, key in enumerate(self.BLOCK_KEYS):
                value = getattr(block, key)
                self.table.setItem(row, col, QTableWidgetItem('' if value is None else str(value)))
        self.source_view.setHtml('<h2>Retained gear study</h2><p>Local histories are supplied separately. Gear duty alone does not determine local cyclic stress.</p><pre>'+html.escape(json.dumps(asdict(self.source), indent=2))+'</pre>')
        self.table.setCurrentCell(0, 0)
        self.selected_block = 0
        self.samples.setPlainText(self.sample_texts[0])
        self.sample_label.setText('Editing block: '+study.blocks[0].name)
        self._loading = False
        self.dirty = False
        self.clear_result()
        self.status.setText('Study loaded. Recalculate after reviewing the entered basis.')

    def flush_samples(self):
        if 0 <= self.selected_block < len(self.sample_texts):
            self.sample_texts[self.selected_block] = self.samples.toPlainText()

    def select_block(self, row, *args):
        if self._loading or row < 0:
            return
        self.flush_samples()
        self.selected_block = row
        self._loading = True
        self.samples.setPlainText(self.sample_texts[row])
        self.sample_label.setText('Editing block: '+self.table.item(row, 0).text())
        self._loading = False

    def block_data(self, row):
        data = {key: self.table.item(row, col).text() for col, key in enumerate(self.BLOCK_KEYS)}
        data['repetitions'] = int(data['repetitions'])
        data['starts_per_repeat'] = int(data['starts_per_repeat']) if data['starts_per_repeat'].strip() else None
        data['imported_file_sha256'], data['imported_samples_sha256'] = self.fingerprints[row]
        return data

    def read_study(self):
        self.flush_samples()
        basis = {key: editor.text() if key in self.BASIS_TEXT else float(editor.text()) if editor.text().strip() else None for key, editor in self.basis_fields.items()}
        material = {key: editor.text() if key in self.MATERIAL_TEXT else float(editor.text()) if editor.text().strip() else None for key, editor in self.material_fields.items()}
        curve = []
        if self.curve.toPlainText().strip():
            try:
                rows = csv.reader(io.StringIO(self.curve.toPlainText()), strict=True)
                if next(rows) != ['failure_cycles', 'amplitude_mpa']:
                    raise ValueError('S-N CSV header must be failure_cycles,amplitude_mpa')
                for row in rows:
                    if len(row) != 2 or len(curve) >= 50:
                        raise ValueError('S-N CSV needs two columns and at most 50 points')
                    curve.append(asdict(SNPoint(float(row[0]), float(row[1]))))
            except (csv.Error, StopIteration) as exc:
                raise ValueError('Invalid S-N CSV') from exc
        material.update(data_status=self.material_status.currentText(), sn_curve=curve)
        blocks = []
        for row, text in enumerate(self.sample_texts):
            data = self.block_data(row)
            data['samples'] = [asdict(s) for s in parse_sample_csv(text)] if text.strip() else []
            blocks.append(data)
        return HistoryStudy.from_dict(dict(**basis, source=asdict(self.source), stress_state=self.stress_state.currentText(),
            mean_stress_model=self.mean_model.currentText(), material=material, blocks=blocks, schema_version=1))

    def changed(self, *args):
        if self._loading:
            return
        self.cancel_job()
        self.dirty = True
        self.clear_result()
        self.status.setText('Inputs changed. Recalculate to assess this history.')

    def clear_result(self):
        self.result = None
        self.report.clear()
        self.plot.result = None
        self.plot_block.clear()
        self.plot.update()

    def add_block(self):
        if self.table.rowCount() >= 200:
            self.show_error('At most 200 blocks are supported.')
            return
        self.flush_samples()
        row = self.table.rowCount()
        block = HistoryBlock(name=f'Block {row+1}', duty_case_name=self.source.duty[0].name)
        used = {self.table.item(i, 0).text() for i in range(row)}
        while block.name in used:
            block.name += ' new'
        self._loading = True
        self.sample_texts.append('')
        self.fingerprints.append(('', ''))
        self.table.insertRow(row)
        for col, key in enumerate(self.BLOCK_KEYS):
            value = getattr(block, key)
            self.table.setItem(row, col, QTableWidgetItem('' if value is None else str(value)))
        self._loading = False
        self.table.setCurrentCell(row, 0)
        self.changed()

    def remove_block(self):
        row = self.selected_block
        if self.table.rowCount() <= 1 or row < 0:
            return
        self._loading = True
        self.sample_texts.pop(row)
        self.fingerprints.pop(row)
        self.table.removeRow(row)
        self.selected_block = -1
        self._loading = False
        target = min(row, self.table.rowCount()-1)
        self.table.setCurrentCell(target, 0)
        self.select_block(target)
        self.changed()

    def move_block(self, direction):
        row = self.selected_block
        target = row+direction
        if row < 0 or not 0 <= target < self.table.rowCount():
            return
        self.flush_samples()
        self._loading = True
        for col in range(self.table.columnCount()):
            a, b = self.table.takeItem(row, col), self.table.takeItem(target, col)
            self.table.setItem(row, col, b)
            self.table.setItem(target, col, a)
        self.sample_texts[row], self.sample_texts[target] = self.sample_texts[target], self.sample_texts[row]
        self.fingerprints[row], self.fingerprints[target] = self.fingerprints[target], self.fingerprints[row]
        self.selected_block = target
        self.table.setCurrentCell(target, 0)
        self._loading = False
        self.changed()

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import signed local stress samples', '', 'CSV (*.csv)')
        if not path:
            return False
        try:
            block = HistoryBlock(**self.block_data(self.selected_block))
            import_sample_csv(path, block)
        except (ValueError, TypeError, OSError) as exc:
            self.show_error(exc)
            return False
        self.fingerprints[self.selected_block] = block.imported_file_sha256, block.imported_samples_sha256
        self.samples.setPlainText(sample_text(block.samples))
        self.changed()
        return True

    def refresh_plot(self, *args):
        self.plot.mode = self.plot_mode.currentIndex()
        self.plot.block_index = max(0, self.plot_block.currentIndex())
        self.plot_block.setEnabled(self.plot.mode == 0)
        self.plot.update()

    def set_busy(self, busy):
        for index in range(4):
            self.tabs.widget(index).setEnabled(not busy)
        for action in self.actions:
            action.setEnabled(not busy)
        self.cancel.setEnabled(busy)

    def start_job(self, task, study, destination=None):
        self.status.setText('Processing the complete ordered history. You can cancel this calculation.')
        return self.worker.start(task, study, destination)

    def cancel_job(self):
        if self.process:
            self.worker.cancel()
            self.status.setText('Calculation cancelled; inputs retained.')

    def job_failed(self, error):
        self.status.setText('Calculation failed; inputs retained.')
        self.show_error(error)

    def job_finished(self, task, result):
        if task == 'history-export':
            self.status.setText(f"Exported {result['files']} files to {result['destination']}.")
            return
        self.result = result
        self.report.setHtml(history_report_html(result))
        self.plot.result = result
        self.plot_block.addItems([b['name'] for b in result['inputs']['blocks']])
        self.refresh_plot()
        self.tabs.setCurrentIndex(4 if result['calculation_available'] else 5)
        damage = result['damage']
        self.status.setText((f'Entered-history damage: {damage:.6g}. ' if damage is not None else 'Total fatigue damage unavailable. ')
            + ('Duty duration and starts match. ' if result['coverage_complete'] else 'Retained duty coverage is incomplete. ')
            + 'Review assessment and evidence; production rating remains unavailable.')

    def calculate(self):
        if self.process:
            return False
        self.clear_result()
        try:
            study = self.read_study()
        except (ValueError, TypeError, OverflowError) as exc:
            self.show_error(exc)
            return False
        return self.start_job('history-calculate', study)

    def show_error(self, error):
        QMessageBox.warning(self, 'Cyclic stress history', str(error))

    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, 'Unsaved history', 'Save the stress history before continuing?', QMessageBox.Save|QMessageBox.Discard|QMessageBox.Cancel, QMessageBox.Save)
        return self.save_study() if answer == QMessageBox.Save else answer == QMessageBox.Discard

    def save_study(self):
        try:
            study = self.read_study()
        except (ValueError, TypeError, OverflowError) as exc:
            self.show_error(exc)
            return False
        path, _ = self.save_destination('Save stress history', str(self.path or 'local.gearforge-history'), 'Stress history (*.gearforge-history)')
        if not path:
            return False
        try:
            study.save(path)
        except (ValueError, OSError) as exc:
            self.show_error(exc)
            return False
        self.path = Path(path)
        self.dirty = False
        self.status.setText(f'Saved {self.path.name}')
        return True

    def open_study(self):
        if not self.confirm_discard():
            return False
        path, _ = QFileDialog.getOpenFileName(self, 'Open stress history', '', 'Stress history (*.gearforge-history)')
        if not path:
            return False
        try:
            study = HistoryStudy.load(path)
        except (ValueError, TypeError, OSError) as exc:
            self.show_error(exc)
            return False
        self.set_study(study)
        self.path = Path(path)
        return True

    def from_source(self):
        if not self.confirm_discard():
            return False
        path, _ = QFileDialog.getOpenFileName(self, 'Retain gear duty', '', 'Gear study (*.gearforge-study)')
        if not path:
            return False
        try:
            study = history_from_study(EngineeringStudy.load(path))
        except (ValueError, TypeError, OSError) as exc:
            self.show_error(exc)
            return False
        self.set_study(study)
        self.dirty = True
        return True

    def example(self):
        if not self.confirm_discard():
            return False
        self.set_study(synthetic_history_example())
        self.dirty = True
        return True

    def export(self):
        if self.process:
            return False
        try:
            study = self.read_study()
        except (ValueError, TypeError, OverflowError) as exc:
            self.show_error(exc)
            return False
        path, _ = QFileDialog.getSaveFileName(self, 'Choose new assessment folder', 'history-assessment', 'Folder name (*)')
        if not path:
            return False
        if Path(path).exists() or Path(path).is_symlink():
            self.show_error('Choose a new assessment folder')
            return False
        return self.start_job('history-export', study, Path(path))

    def reject(self):
        if self.confirm_discard():
            self.cancel_job()
            super().reject()

    def closeEvent(self, event):
        if self.confirm_discard():
            self.cancel_job()
            event.accept()
        else:
            event.ignore()
