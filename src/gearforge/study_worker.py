"""Bounded file-based subprocess jobs for editable engineering studies."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile

from PySide6.QtCore import QObject, QProcess, Signal

from .models import atomic_text, read_text_limited, strict_json


class StudyWorker(QObject):
    completed = Signal(str, object)
    failed = Signal(str)
    busy = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.temporary = None
        self.error_output = ''

    def start(self, task, study, destination=None):
        if self.process is not None:
            return False
        try:
            self.temporary = tempfile.TemporaryDirectory(prefix='gearforge-study-')
            folder = Path(self.temporary.name)
            self.result_path = folder/'result.json'
            request = dict(task=task, study=asdict(study), result_path=str(self.result_path))
            if destination is not None:
                request['destination'] = str(destination)
            atomic_text(folder/'input.json', json.dumps(request, allow_nan=False))
        except (OSError, ValueError) as exc:
            self.cleanup()
            self.failed.emit(str(exc))
            return False
        self.task = task
        self.error_output = ''
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardError.connect(self.drain_error)
        self.process.readyReadStandardOutput.connect(self.drain_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.error)
        self.busy.emit(True)
        command = ['--worker-file', str(folder/'input.json')]
        if not getattr(sys, 'frozen', False):
            command = ['-m', 'gearforge.cli', *command]
        self.process.start(sys.executable, command)
        return True

    def drain_error(self):
        if self.process:
            self.error_output = (self.error_output + bytes(self.process.readAllStandardError()).decode('utf-8', errors='replace'))[-4000:]

    def drain_output(self):
        if self.process:
            self.process.readAllStandardOutput()

    def error(self, error):
        if error == QProcess.FailedToStart:
            message = self.process.errorString()
            self.cleanup()
            self.failed.emit(message)

    def finished(self, exit_code, exit_status):
        try:
            response = strict_json(read_text_limited(self.result_path, 128_000_000, 'Study worker result'))
            if not isinstance(response, dict) or response.get('ok') is not True:
                raise ValueError(response.get('error', 'Invalid worker response') if isinstance(response, dict) else 'Invalid worker response')
            if exit_code != 0 or exit_status != QProcess.NormalExit:
                raise ValueError('Worker exited unexpectedly')
            result, task = response['result'], self.task
        except (OSError, ValueError, KeyError, TypeError) as exc:
            message = str(exc) + (' '+self.error_output if self.error_output else '')
            self.cleanup()
            self.failed.emit(message)
            return
        self.cleanup()
        self.completed.emit(task, result)

    def cleanup(self):
        if self.process:
            self.process.deleteLater()
            self.process = None
        if self.temporary:
            self.temporary.cleanup()
            self.temporary = None
        self.busy.emit(False)

    def cancel(self):
        if self.process:
            self.process.finished.disconnect(self.finished)
            self.process.errorOccurred.disconnect(self.error)
            self.process.kill()
            self.process.waitForFinished(3000)
            self.cleanup()
