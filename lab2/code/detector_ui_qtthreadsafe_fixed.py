
#!/usr/bin/env python3
"""Simple PyQt5 UI to control detector.py, view logs and currently blocked IPs.

Features:
- Start / Stop detector subprocess with configurable parameters (iface, bpf, auto-block, thresholds, duration)
- Live view of detector stdout/stderr in a text box
- View recent detections (from logs/detections.jsonl or logs/detections.log)
- View currently blocked IPs by parsing logs/blocked_ips.log (added by blocker.py)
- Refresh blocked IPs periodically

Save as detector_ui.py and run (may require sudo to sniff on interfaces).

Usage examples:
  pip install PyQt5
  sudo python3 /mnt/data/detector_ui.py
or run without sudo if you run detector with passwordless sudo separately:
  python3 /mnt/data/detector_ui.py

"""

import sys
import os
import json
import subprocess
import threading
import time
from pathlib import Path
from collections import defaultdict

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QCheckBox, QSpinBox, QFileDialog, QMessageBox, QGroupBox
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QTextCursor

BASE_DIR = Path.cwd()
DETECTOR_PATH = Path('/mnt/data/detector.py') if Path('/mnt/data/detector.py').exists() else Path('detector.py')
BLOCKER_LOG = Path('logs/blocked_ips.log')
DETECTIONS_JSONL = Path('logs/detections.jsonl')
DETECTIONS_LOG = Path('logs/detections.log')

class DetectorUI(QWidget):
    append_output_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.append_output_signal.connect(self._append_output_main)
        self.setWindowTitle('Detector UI')
        self.proc = None
        self.proc_thread = None
        self._stop_reader = False
        self.init_ui()
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_blocked_ips)
        self.refresh_timer.start(3000)  # every 3s

    def init_ui(self):
        layout = QVBoxLayout()

        # Parameters group
        params_box = QGroupBox("Detector parameters")
        params_layout = QHBoxLayout()

        self.iface_input = QLineEdit("lo")
        self.bpf_input = QLineEdit("ip")
        self.auto_block_cb = QCheckBox("Auto-block")
        self.block_threshold_spin = QSpinBox(); self.block_threshold_spin.setRange(1, 100); self.block_threshold_spin.setValue(3)
        self.block_window_spin = QSpinBox(); self.block_window_spin.setRange(1, 3600); self.block_window_spin.setValue(30)
        self.block_duration_spin = QSpinBox(); self.block_duration_spin.setRange(0, 86400); self.block_duration_spin.setValue(10)

        params_layout.addWidget(QLabel("iface:")); params_layout.addWidget(self.iface_input)
        params_layout.addWidget(QLabel("BPF:")); params_layout.addWidget(self.bpf_input)
        params_layout.addWidget(self.auto_block_cb)
        params_layout.addWidget(QLabel("threshold:")); params_layout.addWidget(self.block_threshold_spin)
        params_layout.addWidget(QLabel("window(s):")); params_layout.addWidget(self.block_window_spin)
        params_layout.addWidget(QLabel("duration(s,0=perm):")); params_layout.addWidget(self.block_duration_spin)

        params_box.setLayout(params_layout)
        layout.addWidget(params_box)

        # Buttons
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Detector")
        self.stop_btn = QPushButton("Stop Detector"); self.stop_btn.setEnabled(False)
        self.open_logs_btn = QPushButton("Open logs folder")
        btn_layout.addWidget(self.start_btn); btn_layout.addWidget(self.stop_btn); btn_layout.addWidget(self.open_logs_btn)
        layout.addLayout(btn_layout)

        self.start_btn.clicked.connect(self.start_detector)
        self.stop_btn.clicked.connect(self.stop_detector)
        self.open_logs_btn.clicked.connect(self.open_logs_folder)

        # Live output
        layout.addWidget(QLabel("Detector output:"))
        self.output_text = QTextEdit(); self.output_text.setReadOnly(True); self.output_text.setMinimumHeight(200)
        layout.addWidget(self.output_text)

        # Recent detections
        det_layout = QHBoxLayout()
        det_layout.addWidget(QLabel("Recent detections (jsonl):"))
        self.reload_detections_btn = QPushButton("Reload")
        det_layout.addWidget(self.reload_detections_btn)
        self.reload_detections_btn.clicked.connect(self.load_recent_detections)
        layout.addLayout(det_layout)
        self.detections_text = QTextEdit(); self.detections_text.setReadOnly(True); self.detections_text.setMinimumHeight(150)
        layout.addWidget(self.detections_text)

        # Blocked IPs
        layout.addWidget(QLabel("Currently blocked IPs:"))
        self.blocked_text = QTextEdit(); self.blocked_text.setReadOnly(True); self.blocked_text.setMinimumHeight(120)
        layout.addWidget(self.blocked_text)
        blocked_btn_layout = QHBoxLayout()
        self.unblock_ip_input = QLineEdit(); self.unblock_ip_input.setPlaceholderText("IP to manually unblock (e.g. 1.2.3.4)")
        self.unblock_btn = QPushButton("Unblock IP now")
        blocked_btn_layout.addWidget(self.unblock_ip_input); blocked_btn_layout.addWidget(self.unblock_btn)
        layout.addLayout(blocked_btn_layout)
        self.unblock_btn.clicked.connect(self.manual_unblock)

        self.setLayout(layout)

        # initial loads
        self.load_recent_detections()
        self.refresh_blocked_ips()

    def build_cmd(self):
        cmd = [sys.executable, str(DETECTOR_PATH), "--iface", self.iface_input.text().strip(), "--bpf", self.bpf_input.text().strip() or "ip", "--log", "logs/detector_ui_detections.log", "--jsonl", "logs/detections.jsonl"]
        if self.auto_block_cb.isChecked():
            cmd.append("--auto-block")
            cmd += ["--block-threshold", str(self.block_threshold_spin.value())]
            cmd += ["--block-window", str(self.block_window_spin.value())]
            cmd += ["--block-duration", str(self.block_duration_spin.value())]
        return cmd

    def start_detector(self):
        if self.proc is not None:
            QMessageBox.warning(self, "Already running", "Detector already running.")
            return
        if not DETECTOR_PATH.exists():
            QMessageBox.critical(self, "Not found", f"Detector not found at {DETECTOR_PATH}.")
            return
        cmd = self.build_cmd()
        self.output_text.append(f"Starting: {' '.join(cmd)}\n")
        try:
            # Start detector as subprocess. Note: sniffing typically needs root permissions.
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True)
        except Exception as e:
            QMessageBox.critical(self, "Failed to start", str(e))
            self.proc = None
            return
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._stop_reader = False
        self.proc_thread = threading.Thread(target=self._read_proc_output, daemon=True)
        self.proc_thread.start()

    def _read_proc_output(self):
        try:
            for line in self.proc.stdout:
                if self._stop_reader:
                    break
                self.append_output(line.rstrip())
            self.proc.wait()
            rc = self.proc.returncode
            self.append_output(f"\n[Process exited with code {rc}]\n")
        except Exception as e:
            self.append_output(f"[Reader error] {e}\n")
        finally:
            self.proc = None
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def append_output(self, text):
        self.append_output_signal.emit(text)

    def _append_output_main(self, text):
        self.output_text.moveCursor(QTextCursor.End)
        self.output_text.insertPlainText(text + ("\n" if not text.endswith("\n") else ""))
        self.output_text.moveCursor(QTextCursor.End)

    def stop_detector(self):
        if self.proc is None:
            return
        self._stop_reader = True
        try:
            self.proc.terminate()
            # give it a sec, then kill
            t0 = time.time()
            while self.proc.poll() is None and time.time() - t0 < 2:
                time.sleep(0.1)
            if self.proc.poll() is None:
                self.proc.kill()
        except Exception as e:
            self.append_output(f"[Stop error] {e}\n")
        finally:
            self.proc = None
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)

    def open_logs_folder(self):
        logs_dir = Path('logs').resolve()
        if not logs_dir.exists():
            QMessageBox.information(self, "Logs", f"No logs folder yet. It will be created when detector runs.\nPath: {logs_dir}")
            return
        # Try to open folder in file manager
        try:
            if sys.platform == 'win32':
                os.startfile(str(logs_dir))
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(logs_dir)])
            else:
                subprocess.Popen(['xdg-open', str(logs_dir)])
        except Exception as e:
            QMessageBox.information(self, "Logs folder", f"Logs here: {logs_dir}\n(Open failed: {e})")

    def load_recent_detections(self, limit=50):
        out_lines = []
        # prefer jsonl
        if DETECTIONS_JSONL.exists():
            try:
                with open(DETECTIONS_JSONL, 'r', encoding='utf-8') as f:
                    lines = f.read().strip().splitlines()
                    lines = lines[-limit:]
                    for ln in lines:
                        try:
                            j = json.loads(ln)
                            out_lines.append(f"{j.get('time')} {j.get('src')} -> {j.get('dst')} {j.get('reason')}")
                        except Exception:
                            out_lines.append(ln)
            except Exception as e:
                out_lines.append(f"[Error reading {DETECTIONS_JSONL}: {e}]")
        elif DETECTIONS_LOG.exists():
            try:
                with open(DETECTIONS_LOG, 'r', encoding='utf-8') as f:
                    lines = f.read().strip().splitlines()
                    out_lines += lines[-limit:]
            except Exception as e:
                out_lines.append(f"[Error reading {DETECTIONS_LOG}: {e}]")
        else:
            out_lines.append("[No detection logs found yet]")
        self.detections_text.setPlainText('\n'.join(out_lines))

    def refresh_blocked_ips(self):
        # Parse blocker log and compute current blocked set.
        if not BLOCKER_LOG.exists():
            self.blocked_text.setPlainText("[No blocker log found yet: logs/blocked_ips.log]")
            return
        try:
            status = {}  # ip -> last action 'blocked' or 'unblocked' and timestamp
            with open(BLOCKER_LOG, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    # expect lines containing "Blocked IP: x.x.x.x" or "Unblocked IP: x.x.x.x"
                    if 'Blocked IP:' in line:
                        parts = line.split('Blocked IP:')
                        if len(parts) >= 2:
                            ip = parts[1].strip()
                            status[ip] = ('blocked', line[:19] if len(line)>=19 else '')
                    elif 'Unblocked IP:' in line:
                        parts = line.split('Unblocked IP:')
                        if len(parts) >= 2:
                            ip = parts[1].strip()
                            status[ip] = ('unblocked', line[:19] if len(line)>=19 else '')
            blocked = [ip for ip, (act,_) in status.items() if act == 'blocked']
            if not blocked:
                self.blocked_text.setPlainText("[No IPs currently marked as blocked in blocker log]")
            else:
                self.blocked_text.setPlainText('\n'.join(blocked))
        except Exception as e:
            self.blocked_text.setPlainText(f"[Error reading blocker log: {e}]")

    def manual_unblock(self):
        ip = self.unblock_ip_input.text().strip()
        if not ip:
            return
        # call blocker.unblock_ip directly by launching python process to avoid importing blocker into UI
        try:
            cmd = [sys.executable, '-c', f"import blocker; print(blocker.unblock_ip('{ip}'))"]
            self.append_output(f"Running: {' '.join(cmd)}")
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.append_output(p.stdout.strip())
            if p.returncode == 0:
                self.refresh_blocked_ips()
        except Exception as e:
            self.append_output(f"[Manual unblock error] {e}")


def main():
    app = QApplication(sys.argv)
    win = DetectorUI()
    win.resize(1000, 800)
    win.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
