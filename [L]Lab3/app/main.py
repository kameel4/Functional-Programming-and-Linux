import argparse, time, threading, yaml, os
from .logger_setup import build_json_logger
from .collector_files import FileCollector
from .collector_processes import ProcessCollector

def run_collectors(logger, cfg):
    fcol = FileCollector(logger, cfg.get("watch_dirs", []))
    pcol = ProcessCollector(logger, cfg.get("process_poll_interval", 2))
    fcol.start()
    pcol.start()

    while True:
        fcol.poll()
        pcol.poll()
        time.sleep( max(1, int(cfg.get("process_poll_interval", 2))) )

def main():
    ap = argparse.ArgumentParser(description="Linux Audit Tool (No-DB)")
    ap.add_argument("--config", default="./configs/config.yaml")
    ap.add_argument("--gui", action="store_true", help="запуск GUI")
    ap.add_argument("--headless", action="store_true", help="без GUI (только сбор)")
    args = ap.parse_args()

    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)

    logger = build_json_logger(cfg.get("log_dir", "./logs"),
                               cfg.get("log_file", "events.jsonl"),
                               cfg.get("log_max_bytes", 10_485_760),
                               cfg.get("log_backup_count", 5))

    t = threading.Thread(target=run_collectors, args=(logger, cfg), daemon=True)
    t.start()

    if args.gui:
        from .gui import GUI
        from PyQt6 import QtWidgets
        app = QtWidgets.QApplication([])
        log_path = os.path.join(cfg.get("log_dir", "./logs"), cfg.get("log_file", "events.jsonl"))
        gui = GUI(log_path, cfg.get("gui_refresh_interval", 2))
        gui.show()
        app.exec()
    else:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
