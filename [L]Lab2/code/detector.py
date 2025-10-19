#!/usr/bin/env python3
import argparse, json, os, time, threading
from datetime import datetime
from pathlib import Path
from scapy.all import sniff, IP
import rules, blocker

# per-IP burst history for individual autoblock
arrival_history = {}
# last seen timestamp per src for unique-IP-in-window DDOS detection
last_seen_ts = {}

commands_seen = set()

def record_arrival(src: str):
    t = time.time()
    arrival_history.setdefault(src, []).append(t)
    last_seen_ts[src] = t

def count_recent(src: str, window: int) -> int:
    t = time.time()
    xs = [x for x in arrival_history.get(src, []) if t - x <= window]
    arrival_history[src] = xs
    return len(xs)

def unique_sources_in_window(window_sec: float) -> int:
    t = time.time()
    return sum(1 for ts in last_seen_ts.values() if t - ts <= window_sec)

def emit_event(pkt, reason: str, path: str, extra: dict | None = None):
    ip = pkt[IP]
    ev = {
        "time": datetime.utcnow().isoformat() + "Z",
        "src": ip.src,
        "dst": ip.dst,
        "proto": ip.proto,
        "length": len(pkt),
        "reason": reason
    }
    if extra: ev.update(extra)
    print(json.dumps(ev), flush=True)
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

def emit_meta(reason: str, path: str, extra: dict | None = None):
    ev = {"time": datetime.utcnow().isoformat() + "Z", "reason": reason}
    if extra: ev.update(extra)
    print(json.dumps(ev), flush=True)
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")

def handle_packet(pkt, jsonl_path, auto_block, ab_threshold, ab_window, ab_duration,
                  ddos_unique_threshold, ddos_window_sec, ddos_duration):
    if IP not in pkt: return
    src = pkt[IP].src
    
    if blocker.is_global_locked() and not blocker.is_whitelisted(src):
        print("LOCKDOWN BLOCK")
        return

    # global lock check (whitelist bypass happens inside blocker.is_blocked)
    if blocker.is_blocked(src): return

    # rules
    trig1, reason1 = rules.rule_high_packet_rate(pkt, rules.state)
    trig2, reason2 = rules.rule_unusual_port(pkt, rules.state)
    triggered = []
    if trig1: triggered.append(reason1)
    if trig2: triggered.append(reason2)

    # record and maybe emit
    if triggered:
        emit_event(pkt, "+".join(triggered), jsonl_path)
    record_arrival(src)

    # individual autoblock
    if auto_block and count_recent(src, ab_window) >= ab_threshold:
        try: blocker.block_ip(src, ab_duration)
        except Exception: pass

    # DDOS detection: too many unique sources within short window
    if unique_sources_in_window(ddos_window_sec) >= ddos_unique_threshold:
        # start/extend global lockdown
        blocker.set_global_lockdown(ddos_duration)
        emit_meta("ddos_lockdown", jsonl_path, {
            "unique_sources": ddos_unique_threshold,
            "window_sec": ddos_window_sec,
            "lockdown_sec": ddos_duration
        })

def poll_commands(cmd_path: str, whitelist_path: str):
    p = Path(cmd_path)
    while True:
        try:
            if p.exists():
                with p.open("r", encoding="utf-8") as fh:
                    for line in fh:
                        raw = line.strip()
                        if not raw or raw in commands_seen: continue
                        commands_seen.add(raw)
                        try: cmd = json.loads(raw)
                        except Exception: continue
                        c = cmd.get("cmd"); ip = cmd.get("ip")
                        if c == "block" and ip:
                            try: blocker.block_ip(ip, cmd.get("duration", 0))
                            except Exception: pass
                        elif c == "whitelist" and ip:
                            try: blocker.add_whitelist(ip)
                            except Exception: pass
                        elif c == "unwhitelist" and ip:
                            try: blocker.remove_whitelist(ip)
                            except Exception: pass
        except Exception:
            pass
        time.sleep(1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--iface", required=True)
    ap.add_argument("--bpf", default="ip")
    ap.add_argument("--jsonl", default="logs/detections.jsonl")

    # per-IP autoblock
    ap.add_argument("--auto-block", action="store_true")
    ap.add_argument("--block-threshold", type=int, default=10)
    ap.add_argument("--block-window", type=int, default=30)
    ap.add_argument("--block-duration", type=int, default=60)

    # DDOS detection (unique sources in short window)
    ap.add_argument("--ddos-unique-threshold", type=int, default=15,
                    help="trigger when >= this many unique src seen in window")
    ap.add_argument("--ddos-window-sec", type=float, default=5,
                    help="window in seconds for unique source counting")
    ap.add_argument("--ddos-duration", type=int, default=10,
                    help="global lockdown duration (seconds)")

    a = ap.parse_args()

    logs_dir = Path(a.jsonl).resolve().parent
    whitelist_file = logs_dir / "whitelist.jsonl"
    commands_file = logs_dir / "commands.jsonl"
    
    with open(whitelist_file, 'w', encoding='utf-8') as _:
        pass
    blocker.load_whitelist(str(whitelist_file))

    threading.Thread(target=poll_commands, args=(str(commands_file), str(whitelist_file)), daemon=True).start()

    sniff(
        iface=a.iface,
        filter=a.bpf,
        prn=lambda pkt: handle_packet(
            pkt, a.jsonl,
            a.auto_block, a.block_threshold, a.block_window, a.block_duration,
            a.ddos_unique_threshold, a.ddos_window_sec, a.ddos_duration
        ),
        store=False
    )

if __name__ == "__main__":
    main()
