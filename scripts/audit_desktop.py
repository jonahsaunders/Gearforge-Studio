"""Render every empty/input desktop surface in four appearance/text combinations.

Pair with capture_screenshots.py for calculated plots and reports from examples.
This is a reproducible Qt layout review, not a VoiceOver or native macOS audit.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build' / 'gui-audit')
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if sys.platform == 'win32':
        os.environ.setdefault('QT_QPA_FONTDIR', str(Path(os.environ['SystemRoot']) / 'Fonts'))
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from gearforge.appearance import apply_appearance
    from gearforge.app import MainWindow

    app = QApplication.instance() or QApplication([])
    family = next((name for name in ('Segoe UI', 'DejaVu Sans', 'Liberation Sans') if name in QFontDatabase.families()), app.font().family())
    app.setFont(QFont(family, 11))
    editors = [('engineering', 'EngineeringStudyDialog'), ('shaft', 'ShaftStudyDialog'),
               ('bearing', 'BearingStudyDialog'), ('fatigue', 'FatigueStudyDialog'),
               ('contact', 'ContactStudyDialog'), ('thermal', 'ThermalStudyDialog'),
               ('tooth', 'ToothProfileDialog'), ('root', 'RootStressDialog'),
               ('cyclic', 'HistoryStudyDialog')]
    args.out.mkdir(parents=True, exist_ok=True)
    captures = []

    def capture(window, name, section):
        for _ in range(5):
            app.processEvents()
        path = args.out / (name + '.png')
        image = window.grab()
        if image.isNull() or not image.save(str(path)):
            raise RuntimeError(f'Could not render {name}')
        captures.append({'file': path.name, 'section': section, 'width': image.width(),
                         'height': image.height(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})

    with tempfile.TemporaryDirectory(prefix='gearforge-gui-audit-') as directory:
        settings = QSettings(str(Path(directory) / 'settings.ini'), QSettings.IniFormat)
        for theme, scale in [('light', 1.), ('dark', 1.), ('light', 1.3), ('dark', 1.3)]:
            settings.setValue('appearance', theme)
            settings.setValue('text_scale', scale)
            settings.sync()
            apply_appearance(settings)
            for module, name in editors:
                window = getattr(importlib.import_module('gearforge.' + module + '_ui'), name)()
                try:
                    window.show()
                    window.resize(1024, 768)
                    for i in range(window.tabs.count()):
                        window.tabs.setCurrentIndex(i)
                        capture(window, f'{module}-{theme}-{scale:g}-{i}', window.tabs.tabText(i))
                finally:
                    window.dirty = False
                    window.close()
                    window.deleteLater()
                    app.processEvents()
            window = MainWindow(directory)
            try:
                window.show()
                window.resize(1024, 768)
                for i in range(window.pages.count()):
                    window.nav.setCurrentRow(i)
                    capture(window, f'main-{theme}-{scale:g}-{i}', window.nav.item(i).text())
            finally:
                window.dirty = False
                window.close()
                window.deleteLater()
                app.processEvents()
    manifest = {'platform': platform.system(), 'qt_platform': app.platformName(), 'font_family': family,
                'scope': 'All 5 main pages and 51 study sections; empty/input states; 1024×768; light/dark; 100%/130% text. Not native macOS or assistive-technology certification.',
                'captures': captures}
    (args.out / 'captures.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Rendered {len(captures)} surfaces: {args.out}')


if __name__ == '__main__':
    main()
