import os, json, logging, getpass, datetime
from logging.handlers import RotatingFileHandler
import psutil


def now_iso():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

def current_user():
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or "unknown"

def read_jsonl_tail(path: str, max_lines: int = 1000):
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    lines.append(line.rstrip("\n"))
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
    except FileNotFoundError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out

# ---------- logger (JSONL + rotation) ----------

def build_json_logger(log_dir: str, log_file: str, max_bytes: int = 10_485_760, backup_count: int = 5):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_file)
    logger = logging.getLogger("audit_json")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    # избегаем дублирования хендлеров при повторном создании
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', None) == handler.baseFilename
               for h in logger.handlers):
        logger.addHandler(handler)
    logger.propagate = False
    return logger

def emit_json(logger, payload: dict):
    logger.info(json.dumps(payload, ensure_ascii=False))

# ---------- collectors ----------
class FileCollector:
    def __init__(self, logger, watch_dirs):
        self.logger = logger
        self.watch_dirs = watch_dirs or []
        self.inotify = None
        self.wds = {}
        self._flags = None
        self._enabled = True

    def _add_watch_safe(self, path: str):
        try:
            wd = self.inotify.add_watch(path, self._flags)
            self.wds[wd] = path
        except Exception:
            pass  # игнорируем недоступные пути

    def start(self):
        try:
            from inotify_simple import INotify, flags
        except Exception:
            self._enabled = False
            return
        self.inotify = INotify()
        self._flags = (flags.CREATE | flags.DELETE | flags.MODIFY | flags.MOVED_FROM |
                       flags.MOVED_TO | flags.ATTRIB | flags.CLOSE_WRITE)
        for d in self.watch_dirs:
            if os.path.isdir(d):
                self._add_watch_safe(d)

    def poll(self):
        if not self._enabled or not self.inotify:
            return
        from inotify_simple import flags
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
