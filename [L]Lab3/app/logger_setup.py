import os, json, logging
from logging.handlers import RotatingFileHandler

def build_json_logger(log_dir: str, log_file: str, max_bytes: int = 10_485_760, backup_count: int = 5):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_file)
    logger = logging.getLogger("audit_json")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backup_count)
    formatter = logging.Formatter('%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger

def emit_json(logger, payload: dict):
    logger.info(json.dumps(payload, ensure_ascii=False))
