import os
from inotify_simple import INotify, flags
from .util import now_iso, current_user
from .logger_setup import emit_json

INOTIFY_MASK = flags.CREATE | flags.DELETE | flags.MODIFY | flags.MOVED_FROM | flags.MOVED_TO | flags.ATTRIB | flags.CLOSE_WRITE

class FileCollector:
    def __init__(self, logger, watch_dirs):
        self.logger = logger
        self.watch_dirs = watch_dirs
        self.inotify = None
        self.wds = {}

    def _add_watch_safe(self, path: str):
        try:
            wd = self.inotify.add_watch(path, INOTIFY_MASK)
            self.wds[wd] = path
        except Exception:
            pass

    def start(self):
        self.inotify = INotify()
        for d in self.watch_dirs:
            if os.path.isdir(d):
                self._add_watch_safe(d)

    def poll(self):
        if not self.inotify:
            return
        events = self.inotify.read(timeout=0)
        for e in events:
            base = self.wds.get(e.wd, "?")
            name = e.name or ""
            fpath = os.path.join(base, name) if name else base
            for flag in flags.from_mask(e.mask):
                if flag == flags.Q_OVERFLOW:
                    continue
                event = {
                    "ts": now_iso(),
                    "type": "file",
                    "user": current_user(),
                    "pid": None,
                    "ppid": None,
                    "proc": None,
                    "file": fpath,
                    "action": str(flag),
                    "net_laddr": None,
                    "net_raddr": None,
                    "data": {"watch": base},
                }
                emit_json(self.logger, event)
