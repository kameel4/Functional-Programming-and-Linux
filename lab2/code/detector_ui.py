#!/usr/bin/env python3
import json, subprocess, sys, threading, pathlib, os, time
from typing import Set
from PyQt5.QtCore import Qt, QProcess
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QPlainTextEdit, QSpinBox, QSplitter, QWidget,
    QGridLayout, QFormLayout, QMessageBox, QHBoxLayout
)

class DetectorProcessManager:
    def __init__(self, parent, detector_path):
        self.parent = parent
        self.detector_path = detector_path
        self.process = None
        self._stdout_buffer = ""

    def is_running(self):
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def start(self, iface, bpf, jsonl_path, auto_block, block_threshold, block_window, block_duration, on_stdout_line, on_started, on_finished, on_error):
        if self.is_running(): return
        self.process = QProcess(self.parent)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        args = [
            str(self.detector_path),
            "-i", iface,
            "--bpf", bpf,
            "--jsonl", str(jsonl_path),
            "--block-threshold", str(block_threshold),
            "--block-window", str(block_window),
            "--block-duration", str(block_duration)
        ]
        if auto_block: args.append("--auto-block")
        self.process.readyReadStandardOutput.connect(lambda: self._read_stdout(on_stdout_line))
        self.process.started.connect(on_started)
        self.process.finished.connect(lambda _c, _s: on_finished())
        self.process.errorOccurred.connect(lambda _e: on_error(self.process.errorString()))
        python_exe = sys.executable
        self.process.start(python_exe, args)

    def stop(self):
        if not self.is_running(): return
        self.process.terminate()
        if not self.process.waitForFinished(1500):
            self.process.kill()
        self.process = None
        self._stdout_buffer = ""

    def _read_stdout(self, on_stdout_line):
        if not self.process: return
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        if not data: return
        self._stdout_buffer += data
        lines = self._stdout_buffer.splitlines(keepends=True)
        new_buf = ""
        for chunk in lines:
            if chunk.endswith("\n") or chunk.endswith("\r"):
                on_stdout_line(chunk.strip())
            else:
                new_buf += chunk
        self._stdout_buffer = new_buf

class IpListItem(QWidget):
    def __init__(self, ip: str, on_block, on_whitelist_toggle, initial_whitelisted=False):
        super().__init__()
        self.ip = ip
        self.on_block = on_block
        self.on_whitelist_toggle = on_whitelist_toggle
        h = QHBoxLayout(self); h.setContentsMargins(2,2,2,2)
        self.label = QLabel(ip); h.addWidget(self.label)
        h.addStretch()
        self.block_btn = QPushButton("Block"); self.block_btn.setFixedWidth(90)
        self.block_btn.clicked.connect(self._block_clicked)
        h.addWidget(self.block_btn)
        self.wl_btn = QPushButton("Whitelist" if not initial_whitelisted else "Unwhitelist"); self.wl_btn.setFixedWidth(110)
        self.wl_btn.clicked.connect(self._wl_clicked)
        h.addWidget(self.wl_btn)
        self.set_whitelisted_state(initial_whitelisted)

    def _block_clicked(self):
        # self.block_btn.setEnabled(False)
        self.on_block(self.ip)

    def _wl_clicked(self):
        # toggle
        currently = (self.wl_btn.text() == "Unwhitelist")
        self.wl_btn.setEnabled(False)
        self.on_whitelist_toggle(self.ip, not currently)

    def set_blocked_state(self, blocked: bool):
        # self.block_btn.setEnabled(not blocked)
        pass

    def set_whitelisted_state(self, whitelisted: bool):
        if whitelisted:
            self.label.setStyleSheet("color: gray;")
            self.block_btn.setEnabled(False)
            self.wl_btn.setText("Unwhitelist")
        else:
            self.label.setStyleSheet("")
            self.block_btn.setEnabled(True)
            self.wl_btn.setText("Whitelist")
        self.wl_btn.setEnabled(True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Detector UI (PyQt5)")
        self.resize(960,560)
        root = QWidget(self); self.setCentralWidget(root)

        self.app_dir = pathlib.Path(__file__).resolve().parent
        self.detector_path = self.app_dir / "detector.py"
        self.logs_dir = self.app_dir / "logs"; self.logs_dir.mkdir(exist_ok=True)
        self.jsonl_path = self.logs_dir / "detections.jsonl"
        self.cmds_path = self.logs_dir / "commands.jsonl"

        self.proc_mgr = DetectorProcessManager(self, self.detector_path)

        # Controls
        self.iface_edit = QLineEdit("enp0s3"); self.bpf_edit = QLineEdit("ip")
        self.auto_block_check = QCheckBox("Auto block")
        self.block_threshold_spin = QSpinBox(); self.block_threshold_spin.setRange(1,100000); self.block_threshold_spin.setValue(10)
        self.block_window_spin = QSpinBox(); self.block_window_spin.setRange(1,3600); self.block_window_spin.setValue(30)
        self.block_duration_spin = QSpinBox(); self.block_duration_spin.setRange(0,86400); self.block_duration_spin.setValue(60)
        self.start_btn = QPushButton("Start"); self.stop_btn = QPushButton("Stop"); self.stop_btn.setEnabled(False)

        # Observed list and logs
        self.observed_list = QListWidget()
        self.log_view = QPlainTextEdit(); self.log_view.setReadOnly(True)
        font = QFont("Menlo" if sys.platform=="darwin" else "Consolas", 10); self.log_view.setFont(font)

        # Layout
        grid = QGridLayout(root)
        grid.setContentsMargins(8,8,8,8); grid.setSpacing(8)
        grid.addWidget(QLabel("Interface"),0,0); grid.addWidget(self.iface_edit,0,1)
        grid.addWidget(QLabel("BPF"),0,2); grid.addWidget(self.bpf_edit,0,3)
        grid.addWidget(self.auto_block_check,0,4)
        grid.addWidget(QLabel("Threshold"),0,5); grid.addWidget(self.block_threshold_spin,0,6)
        grid.addWidget(QLabel("Window"),0,7); grid.addWidget(self.block_window_spin,0,8)
        grid.addWidget(QLabel("Duration"),0,9); grid.addWidget(self.block_duration_spin,0,10)
        grid.addWidget(self.start_btn,0,11); grid.addWidget(self.stop_btn,0,12)
        splitter = QSplitter(Qt.Horizontal); grid.addWidget(splitter,1,0,1,13)
        left_panel = QWidget(); left_layout = QFormLayout(left_panel); left_layout.addRow(QLabel("Observed source IPs")); left_layout.addRow(self.observed_list)
        right_panel = QWidget(); right_layout = QFormLayout(right_panel); right_layout.addRow(QLabel("Log output")); right_layout.addRow(self.log_view)
        splitter.addWidget(left_panel); splitter.addWidget(right_panel); splitter.setStretchFactor(0,1); splitter.setStretchFactor(1,2)

        self.seen_ips: Set[str] = set()
        self.item_map = {}  # ip -> (QListWidgetItem, IpListItem)

        self.start_btn.clicked.connect(self.start_detector)
        self.stop_btn.clicked.connect(self.stop_detector)

    def start_detector(self):
        if self.proc_mgr.is_running(): return
        if not self.detector_path.exists():
            QMessageBox.critical(self, "Error", f"detector.py not found at\n{self.detector_path}")
            return
        self.log_view.clear(); self.observed_list.clear(); self.seen_ips.clear(); self.item_map.clear()
        self.proc_mgr.start(
            iface=self.iface_edit.text().strip(),
            bpf=self.bpf_edit.text().strip() or "ip",
            jsonl_path=self.jsonl_path,
            auto_block=self.auto_block_check.isChecked(),
            block_threshold=self.block_threshold_spin.value(),
            block_window=self.block_window_spin.value(),
            block_duration=self.block_duration_spin.value(),
            on_stdout_line=self.on_stdout_line,
            on_started=self.on_started,
            on_finished=self.on_finished,
            on_error=self.on_error
        )

    def stop_detector(self):
        self.proc_mgr.stop()
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)

    def on_started(self): self._append_log("[started]\n"); self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
    def on_finished(self): self._append_log("[finished]\n"); self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
    def on_error(self, msg): self._append_log(f"[error] {msg}\n"); QMessageBox.warning(self, "Process error", msg)

    def on_stdout_line(self, line):
        self._append_log(line + "\n")
        try:
            obj = json.loads(line)
        except Exception:
            return
        ip = obj.get("src")
        if not ip: return
        if ip not in self.seen_ips:
            self.seen_ips.add(ip)
            widget = IpListItem(ip, self.block_ip_command, self.whitelist_command, initial_whitelisted=False)
            item = QListWidgetItem(self.observed_list)
            item.setSizeHint(widget.sizeHint())
            self.observed_list.addItem(item)
            self.observed_list.setItemWidget(item, widget)
            self.item_map[ip] = (item, widget)

    def block_ip_command(self, ip):
        dur = int(self.block_duration_spin.value())
        cmd = {"cmd":"block","ip":ip,"duration":dur,"time":int(time.time())}
        try:
            with open(self.cmds_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(cmd, ensure_ascii=False) + "\n")
            pair = self.item_map.get(ip)
            if pair:
                _, widget = pair
                widget.set_blocked_state(True)
            self._append_log(f"[ui] block command written for {ip} dur={dur}\n")
        except Exception as e:
            self._append_log(f"[ui] failed to write command: {e}\n")

    def whitelist_command(self, ip, add_whitelist: bool):
        cmd_name = "whitelist" if add_whitelist else "unwhitelist"
        cmd = {"cmd":cmd_name,"ip":ip,"time":int(time.time())}
        try:
            with open(self.cmds_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(cmd, ensure_ascii=False) + "\n")
            pair = self.item_map.get(ip)
            if pair:
                _, widget = pair
                widget.set_whitelisted_state(add_whitelist)
                if add_whitelist:
                    widget.set_blocked_state(True)
            self._append_log(f"[ui] {cmd_name} command written for {ip}\n")
        except Exception as e:
            self._append_log(f"[ui] failed to write whitelist command: {e}\n")

    def _append_log(self, text):
        self.log_view.moveCursor(self.log_view.textCursor().End)
        self.log_view.insertPlainText(text)
        self.log_view.moveCursor(self.log_view.textCursor().End)

def main():
    app = QApplication(sys.argv)
    win = MainWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
