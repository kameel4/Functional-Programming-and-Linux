import getpass, datetime, os, json

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
