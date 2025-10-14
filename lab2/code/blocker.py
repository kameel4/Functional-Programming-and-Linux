#!/usr/bin/env python3
import time, json
from pathlib import Path

blocked = {}          # ip -> expire_ts or None
whitelist = set()
global_lock_until = 0
_whitelist_file = None

def _now(): return time.time()

def load_whitelist(path: str):
    global _whitelist_file
    _whitelist_file = Path(path)
    if not _whitelist_file.exists(): return
    try:
        with _whitelist_file.open("r", encoding="utf-8") as fh:
            for line in fh:
                line=line.strip()
                if not line: continue
                try:
                    obj=json.loads(line)
                except Exception:
                    continue
                ip=obj.get("ip")
                if ip: whitelist.add(ip)
    except Exception:
        pass

def _append_whitelist_file(cmd: dict):
    if not _whitelist_file: return
    try:
        _whitelist_file.parent.mkdir(parents=True, exist_ok=True)
        with _whitelist_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(cmd, ensure_ascii=False) + "\n")
    except Exception:
        pass

def add_whitelist(ip: str) -> bool:
    if not ip: return False
    whitelist.add(ip)
    _append_whitelist_file({"cmd":"whitelist","ip":ip,"time":int(_now())})
    return True

def remove_whitelist(ip: str) -> bool:
    if not ip: return False
    whitelist.discard(ip)
    _append_whitelist_file({"cmd":"unwhitelist","ip":ip,"time":int(_now())})
    return True

def is_whitelisted(ip: str) -> bool:
    return ip in whitelist

def set_global_lockdown(duration: int):
    """Block everyone except whitelist for <duration> seconds."""
    global global_lock_until
    end = _now() + max(0, int(duration))
    if end > global_lock_until:
        global_lock_until = end

def is_global_locked() -> bool:
    global global_lock_until
    if global_lock_until <= 0: return False
    if _now() > global_lock_until:
        global_lock_until = 0
        return False
    return True

def block_ip(ip: str, duration: int = 60) -> bool:
    if not ip: return False
    if is_whitelisted(ip): return False
    expire = None if not duration or duration <= 0 else int(_now() + int(duration))
    blocked[ip] = expire
    return True

def is_blocked(ip: str) -> bool:
    if is_whitelisted(ip): return False
    if is_global_locked(): return True
    t = blocked.get(ip)
    if not t: return False
    if t is None: return True
    if _now() > t:
        try: del blocked[ip]
        except KeyError: pass
        return False
    return True
