#!/usr/bin/env python3
# detector.py
import argparse
import logging
import sys
import json
import os
import time
from datetime import datetime
from scapy.all import sniff, IP
import rules
import blocker


logger = logging.getLogger("detector")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')

def setup_logging(log_path):
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    fh = logging.FileHandler(log_path)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

alert_history = {}
blocked_ips = set()

def record_alert(src, now=None):
    if now is None:
        now = time.time()
    lst = alert_history.get(src, [])
    lst.append(now)
    alert_history[src] = lst

def prune_alerts(src, window):
    now = time.time()
    if src not in alert_history:
        return 0
    alert_history[src] = [t for t in alert_history[src] if now - t <= window]
    return len(alert_history[src])


DEFAULT_LOGFILE = "logs/detections.log"
DEFAULT_JSONL = "logs/detections.jsonl"

def packet_summary(pkt):
    try:
        if IP in pkt:
            ip = pkt[IP]
            return f"{ip.src} -> {ip.dst} proto={ip.proto} len={len(pkt)}"
        return f"len={len(pkt)}"
    except Exception:
        return "summary-error"

def log_event(pkt, reason, jsonl_path):
    ip = pkt[IP]
    event = {
        "time": datetime.utcnow().isoformat() + "Z",
        "src": ip.src,
        "dst": ip.dst,
        "proto": ip.proto,
        "reason": reason,
        "length": len(pkt)
    }
    logger.info(f" ALERT: {event['src']} -> {event['dst']} ({reason})")
    try:
        with open(jsonl_path, "a") as jf:
            jf.write(json.dumps(event) + "\n")
    except Exception as e:
        logger.error(f"Ошибка записи jsonl: {e}")
    return event

def handle_packet(pkt, jsonl_path, auto_block=False, block_threshold=3, block_window=30, block_duration=None):
    if IP not in pkt:
        return
    src = pkt[IP].src

    # call your fixed rules (edit as needed)
    try:
        suspicious, reason = rules.rule_high_packet_rate(pkt, rules.state)
        if suspicious:
            ev = log_event(pkt, reason, jsonl_path)
            # record alert and possibly block
            record_alert(src)
            cnt = prune_alerts(src, block_window)
            logger.info(f"Alert count for {src} in last {block_window}s: {cnt}")
            if auto_block and cnt >= block_threshold and src not in blocked_ips:
                logger.info(f"Threshold reached for {src} ({cnt} >= {block_threshold}), blocking...")
                ok = blocker.block_ip(src, duration=block_duration)
                if ok:
                    blocked_ips.add(src)

        suspicious, reason = rules.rule_unusual_port(pkt, rules.state)
        if suspicious:
            ev = log_event(pkt, reason, jsonl_path)
            record_alert(src)
            cnt = prune_alerts(src, block_window)
            logger.info(f"Alert count for {src} in last {block_window}s: {cnt}")
            if auto_block and cnt >= block_threshold and src not in blocked_ips:
                logger.info(f"Threshold reached for {src} ({cnt} >= {block_threshold}), blocking...")
                ok = blocker.block_ip(src, duration=block_duration)
                if ok:
                    blocked_ips.add(src)

    except Exception as e:
        logger.exception(f"Ошибка при проверке правил: {e}")

def main():
    parser = argparse.ArgumentParser(description="Simple IDS detector with optional auto-block")
    parser.add_argument("--iface", "-i", required=True, help="Interface to sniff (e.g., eth0 or lo)")
    parser.add_argument("--bpf", default="ip", help="BPF filter (default: ip)")
    parser.add_argument("--log", "-l", default=DEFAULT_LOGFILE, help="Log path")
    parser.add_argument("--jsonl", default=DEFAULT_JSONL, help="JSONL output path")
    parser.add_argument("--auto-block", action="store_true", help="Enable automatic blocking via blocker.py")
    parser.add_argument("--block-threshold", type=int, default=3, help="Number of alerts required to block (default 3)")
    parser.add_argument("--block-window", type=int, default=10, help="Window in seconds to count alerts (default 30s)")
    parser.add_argument("--block-duration", type=int, default=10, help="Auto-unblock after seconds (0 or omitted = permanent until manual unblock)")

    args = parser.parse_args()

    setup_logging(args.log)
    os.makedirs("logs", exist_ok=True)
    logger.info(f"Starting detector on iface={args.iface} bpf='{args.bpf}' auto_block={args.auto_block}")

    # sniff
    try:
        sniff(
            iface=args.iface,
            filter=args.bpf,
            prn=lambda pkt: handle_packet(
                pkt,
                args.jsonl,
                auto_block=args.auto_block,
                block_threshold=args.block_threshold,
                block_window=args.block_window,
                block_duration=(args.block_duration if args.block_duration > 0 else None)
            ),
            store=False
        )
    except PermissionError:
        logger.error("Permission denied: run with sudo.")
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except Exception as e:
        logger.exception(f"sniff error: {e}")

if __name__ == "__main__":
    main()
