import psutil
from .util import now_iso, current_user
from .logger_setup import emit_json

class ProcessCollector:
    def __init__(self, logger, interval=2):
        self.logger = logger
        self.interval = interval
        self._known = set()

    def snapshot_pids(self):
        return set(p.pid for p in psutil.process_iter(attrs=[]))

    def start(self):
        self._known = self.snapshot_pids()

    def poll(self):
        now = now_iso()
        curr = self.snapshot_pids()
        started = curr - self._known
        ended = self._known - curr
        self._known = curr

        for pid in started:
            try:
                p = psutil.Process(pid)
                info = p.as_dict(attrs=["pid", "ppid", "name", "username"])
            except Exception:
                info = {"pid": pid, "ppid": None, "name": None, "username": None}
            event = {
                "ts": now,
                "type": "process",
                "user": info.get("username") or current_user(),
                "pid": info.get("pid"),
                "ppid": info.get("ppid"),
                "proc": info.get("name"),
                "file": None,
                "action": "START",
                "net_laddr": None,
                "net_raddr": None,
                "data": {},
            }
            emit_json(self.logger, event)

        for pid in ended:
            event = {
                "ts": now,
                "type": "process",
                "user": current_user(),
                "pid": pid,
                "ppid": None,
                "proc": None,
                "file": None,
                "action": "EXIT",
                "net_laddr": None,
                "net_raddr": None,
                "data": {},
            }
            emit_json(self.logger, event)
