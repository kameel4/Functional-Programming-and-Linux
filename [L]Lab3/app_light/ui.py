"""
ui.py — простой просмотрщик JSONL-лога с фильтрами.
"""
import json, os
from PyQt6 import QtWidgets, QtCore
from audit_core import read_jsonl_tail

class EventTableModel(QtCore.QAbstractTableModel):
    HEADERS = ["ts","type","user","pid","ppid","proc","file","action","net_laddr","net_raddr","data"]

    def __init__(self, rows):
        super().__init__()
        self.rows = rows  # list[dict]

    def rowCount(self, parent=None): return len(self.rows)
    def columnCount(self, parent=None): return len(self.HEADERS)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            key = self.HEADERS[index.column()]
            val = self.rows[index.row()].get(key)
            if key == "data" and isinstance(val, dict):
                try: return json.dumps(val, ensure_ascii=False)
                except Exception: return str(val)
            return "" if val is None else str(val)
        return None

    def headerData(self, section, orientation, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

class GUI(QtWidgets.QWidget):
    def __init__(self, log_path: str, refresh_interval: int = 2):
        super().__init__()
        self.log_path = log_path
        self.refresh_interval = refresh_interval
        self.setWindowTitle("Linux Audit Tool (No-DB)")
        self.resize(1200, 600)

        layout = QtWidgets.QVBoxLayout(self)

        # Фильтры
        filter_layout = QtWidgets.QHBoxLayout()
        self.type_edit = QtWidgets.QLineEdit()
        self.type_edit.setPlaceholderText("file | process (можно: type=file, file, file|process)")
        self.user_edit = QtWidgets.QLineEdit();  self.user_edit.setPlaceholderText("user ...")
        self.search_edit = QtWidgets.QLineEdit(); self.search_edit.setPlaceholderText("подстрока: proc/file/action")
        self.refresh_btn = QtWidgets.QPushButton("Обновить"); self.refresh_btn.clicked.connect(self.refresh)

        for w in (self.type_edit, self.user_edit, self.search_edit, self.refresh_btn):
            filter_layout.addWidget(w)
        layout.addLayout(filter_layout)

        self.table = QtWidgets.QTableView(); layout.addWidget(self.table)

        self.timer = QtCore.QTimer(self); self.timer.timeout.connect(self.refresh)
        self.timer.start(self.refresh_interval * 1000)
        self.refresh()

    @staticmethod
    def _parse_types(text: str):
        t = (text or "").strip().lower()
        if not t: return []
        for ch in [",", "|", "/", "\\", ";"]:
            t = t.replace(ch, " ")
        t = t.replace("type", " ").replace("=", " ")
        types = [s for s in t.split() if s]
        return types

    def _apply_filters(self, rows):
        types = self._parse_types(self.type_edit.text())
        u = (self.user_edit.text() or "").strip()
        s = (self.search_edit.text() or "").strip()

        def ok(r):
            rtype = (r.get("type") or "").lower()
            if types and rtype not in types: return False
            if u and (u not in (r.get("user") or "")): return False
            if s:
                hay = " ".join([str(r.get("proc") or ""), str(r.get("file") or ""), str(r.get("action") or "")])
                if s not in hay: return False
            return True

        return [r for r in rows if ok(r)]

    def refresh(self):
        rows = read_jsonl_tail(self.log_path, max_lines=2000)
        rows = self._apply_filters(rows)[::-1]  # новые сверху
        self.table.setModel(EventTableModel(rows))
        self.table.resizeColumnsToContents()
