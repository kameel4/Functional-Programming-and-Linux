"""
app.py — CLI:
- run [--gui|--headless]  запуск сборщиков, опционально GUI
- search                 поиск по JSONL (как раньше cli.py)
- report                 отчёт по JSONL (PNG, либо CSV если нет matplotlib)
"""

import argparse, time, threading, os
from audit_core import build_json_logger, FileCollector, ProcessCollector, read_jsonl_tail
# GUI импортируем лениво, только при --gui

# ---- конфиг ----
DEFAULT_CFG = {
    "log_dir": "./logs",
    "log_file": "events.jsonl",
    "log_max_bytes": 10_485_760,
    "log_backup_count": 5,
    "watch_dirs": ["/etc", "/var/log", "./"],
    "process_poll_interval": 2,
    "gui_refresh_interval": 2,
}

def load_config(path: str | None):
    cfg = dict(DEFAULT_CFG)
    if not path: return cfg
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        cfg.update(user)
    except FileNotFoundError:
        pass
    except Exception:
        # если PyYAML не установлен или файл битый — остаёмся на дефолтах
        pass
    return cfg

# ---- запуск сборщиков ----
def run_collectors(logger, cfg):
    fcol = FileCollector(logger, cfg.get("watch_dirs", []))
    pcol = ProcessCollector(logger, cfg.get("process_poll_interval", 2))
    fcol.start(); pcol.start()
    while True:
        fcol.poll(); pcol.poll()
        time.sleep(max(1, int(cfg.get("process_poll_interval", 2))))

# ---- search (бывш. cli.py) ----
def cmd_search(args):
    rows = read_jsonl_tail(args.log, max_lines=args.limit)
    def ok(r):
        if args.type and r.get("type") != args.type: return False
        if args.user and (args.user not in (r.get("user") or "")): return False
        if args.contains:
            hay = " ".join([str(r.get("proc") or ""), str(r.get("file") or ""), str(r.get("action") or "")])
            if args.contains not in hay: return False
        return True
    import json, sys
    for r in (r for r in rows if ok(r)):
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---- report (бывш. report.py с мягким импортом matplotlib) ----
def cmd_report(args):
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)
    rows = read_jsonl_tail(args.log, max_lines=50_000)
    counts = {}
    for r in rows:
        t = r.get("type") or "unknown"
        counts[t] = counts.get(t, 0) + 1

    try:
        import matplotlib.pyplot as plt
        labels = list(counts.keys()); values = [counts[k] for k in labels]
        plt.figure(); plt.bar(labels, values)
        plt.title("События по типам"); plt.xlabel("Тип события"); plt.ylabel("Количество")
        out_path = os.path.join(out_dir, "events_by_type.png")
        plt.savefig(out_path, bbox_inches="tight")
        print(out_path)
    except Exception:
        # фоллбэк без matplotlib — пишем CSV
        csv = os.path.join(out_dir, "events_by_type.csv")
        with open(csv, "w", encoding="utf-8") as f:
            f.write("type,count\n")
            for k, v in counts.items():
                f.write(f"{k},{v}\n")
        print(csv)

# ---- run (сборщики + опционально GUI) ----
def cmd_run(args):
    cfg = load_config(args.config)
    logger = build_json_logger(cfg["log_dir"], cfg["log_file"], cfg["log_max_bytes"], cfg["log_backup_count"])
    t = threading.Thread(target=run_collectors, args=(logger, cfg), daemon=True); t.start()

    if args.gui:
        from ui import GUI
        from PyQt6 import QtWidgets
        app = QtWidgets.QApplication([])
        log_path = os.path.join(cfg["log_dir"], cfg["log_file"])
        gui = GUI(log_path, cfg["gui_refresh_interval"]); gui.show()
        app.exec()
    else:
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: pass

# ---- argparse ----
def main():
    ap = argparse.ArgumentParser(description="Linux Audit Tool (No-DB) — compact 3 files")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_run = sub.add_parser("run", help="запуск сборщиков (по умолчанию headless или с GUI)")
    sp_run.add_argument("--config", default=None, help="путь к YAML; при отсутствии используются дефолты")
    mode = sp_run.add_mutually_exclusive_group()
    mode.add_argument("--gui", action="store_true", help="запуск GUI")
    mode.add_argument("--headless", action="store_true", help="без GUI (по умолчанию)")
    sp_run.set_defaults(func=cmd_run)

    sp_search = sub.add_parser("search", help="поиск по JSONL (как раньше cli.py)")
    sp_search.add_argument("--log", default="./logs/events.jsonl")
    sp_search.add_argument("--type", default=None)
    sp_search.add_argument("--user", default=None)
    sp_search.add_argument("--contains", default=None)
    sp_search.add_argument("--limit", type=int, default=2000)
    sp_search.set_defaults(func=cmd_search)

    sp_report = sub.add_parser("report", help="отчёт: PNG (если есть matplotlib) или CSV")
    sp_report.add_argument("--log", default="./logs/events.jsonl")
    sp_report.add_argument("--out", default="./reports")
    sp_report.set_defaults(func=cmd_report)

    args = ap.parse_args()
    if args.cmd == "run" and not (args.gui or args.headless):
        args.headless = True
    args.func(args)

if __name__ == "__main__":
    main()
