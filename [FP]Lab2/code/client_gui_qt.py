from __future__ import annotations
import sys
import asyncio
import base64
from typing import Optional

from PyQt5 import QtWidgets, QtCore
from qasync import QEventLoop, asyncSlot, run

from protocol import dumps_message, loads_message

# asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

class AsyncClient(QtCore.QObject):
    message_received = QtCore.pyqtSignal(dict)
    system_message = QtCore.pyqtSignal(str)
    disconnected = QtCore.pyqtSignal()

    def __init__(self):
        super().__init__()
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._connected = False

    async def connect(self, host: str, port: int, nick: str, room: str):
        try:
            self.reader, self.writer = await asyncio.open_connection(host, port)
            self.writer.write(dumps_message({"type":"join","nick":nick,"room":room}))
            await self.writer.drain()
            self._connected = True
            asyncio.create_task(self._reader_loop())
            QtCore.QTimer.singleShot(
                0,
                lambda: self.system_message.emit(f"Connected to {host}:{port} as {nick} in #{room}")
            )
        except Exception as e:
            self.system_message.emit(f"Connection failed: {e}")
            self._connected = False

    async def _reader_loop(self):
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    self.system_message.emit("Disconnected")
                    self.disconnected.emit()
                    return
                try:
                    msg = loads_message(line)
                except Exception as e:
                    self.system_message.emit(f"Bad message: {e}")
                    continue
                QtCore.QTimer.singleShot(
                    0,
                    lambda m=msg: self.message_received.emit(m)
                )
        except Exception:
            self.disconnected.emit()

    async def send(self, msg: dict):
        if not self.writer:
            return
        self.writer.write(dumps_message(msg))
        await self.writer.drain()

    async def close(self):
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        finally:
            self._connected = False

class ConnectDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect")
        form = QtWidgets.QFormLayout(self)
        self.e_host = QtWidgets.QLineEdit("127.0.0.1")
        self.e_port = QtWidgets.QSpinBox(); self.e_port.setRange(1, 65535); self.e_port.setValue(50001)
        self.e_nick = QtWidgets.QLineEdit("user")
        self.e_room = QtWidgets.QLineEdit("general")
        form.addRow("Host", self.e_host)
        form.addRow("Port", self.e_port)
        form.addRow("Nick", self.e_nick)
        form.addRow("Room", self.e_room)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

class ChatWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Async Chat (PyQt5)")
        self.resize(800, 560)

        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)

        self.view = QtWidgets.QTextEdit(); self.view.setReadOnly(True)
        v.addWidget(self.view)

        h = QtWidgets.QHBoxLayout(); v.addLayout(h)
        self.entry = QtWidgets.QLineEdit(); self.entry.returnPressed.connect(self.on_send_clicked)
        self.btn_send = QtWidgets.QPushButton("Send"); self.btn_send.clicked.connect(self.on_send_clicked)
        self.btn_file = QtWidgets.QPushButton("File"); self.btn_file.clicked.connect(self.on_file_clicked)
        h.addWidget(self.entry, 1); h.addWidget(self.btn_send); h.addWidget(self.btn_file)

        self.client = AsyncClient()
        self.client.message_received.connect(self.on_message)
        self.client.system_message.connect(self.on_system)
        self.client.disconnected.connect(self.on_disconnected)

        # сразу показываем диалог подключения
        QtCore.QTimer.singleShot(0, self.open_connect_dialog)

    def open_connect_dialog(self):
        dlg = ConnectDialog(self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            host = dlg.e_host.text(); port = dlg.e_port.value(); nick = dlg.e_nick.text(); room = dlg.e_room.text()
            asyncio.create_task(self.client.connect(host, port, nick, room))

    def append_line(self, text: str):
        self.view.append(text)

    @QtCore.pyqtSlot(dict)
    def on_message(self, msg: dict):
        t = msg.get("type")
        if t == "chat":
            self.append_line(f"[{msg.get('room')}] {msg.get('from')}: {msg.get('text')}")
        elif t == "system":
            self.append_line(f"[*] {msg.get('text')}")
        elif t == "pm":
            self.append_line(f"[pm from {msg.get('from')}] {msg.get('text')}")
        elif t == "file":
            self.append_line(f"[file {msg.get('filename')} from {msg.get('from')} size={msg.get('size')}]")
        elif t == "error":
            self.append_line(f"[error] {msg.get('error')}")
        else:
            self.append_line(str(msg))

    @QtCore.pyqtSlot(str)
    def on_system(self, text: str):
        self.append_line(f"[*] {text}")

    @QtCore.pyqtSlot()
    def on_disconnected(self):
        self.append_line("[*] Disconnected")

    @asyncSlot()
    async def on_send_clicked(self):
        text = self.entry.text().strip()
        if not text:
            return
        if text.startswith("/room "):
            name = text.split(maxsplit=1)[1]
            await self.client.send({"type":"switch_room","room":name})
        elif text.startswith("/pm "):
            try:
                _, to, pm_text = text.split(" ", 2)
            except ValueError:
                self.append_line("Usage: /pm <nick> <text>")
                self.entry.clear(); return
            await self.client.send({"type":"pm","to":to,"text":pm_text})
        else:
            await self.client.send({"type":"chat","text":text})
        self.entry.clear()

    @asyncSlot()
    async def on_file_clicked(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Choose file")
        if not path:
            return
        try:
            data = open(path, 'rb').read()
        except Exception as e:
            self.append_line(f"[file error] {e}")
            return
        if len(data) > 5 * 1024 * 1024:
            self.append_line("[file error] File too large (max 5MB)")
            return
        import os
        b64 = base64.b64encode(data).decode('ascii')
        await self.client.send({"type":"file","filename":os.path.basename(path),"data":b64})

    async def shutdown(self):
        await self.client.close()

async def main():
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    win = ChatWindow(); win.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            await win.shutdown()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    win = ChatWindow()
    win.show()

    # чтобы корректно выйти из цикла при закрытии окна
    app.aboutToQuit.connect(loop.stop)

    try:
        with loop:
            loop.run_forever()
    finally:
        # аккуратно закрываем сетевое соединение клиента
        loop.run_until_complete(win.shutdown())