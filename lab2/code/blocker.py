# blocker.py
import subprocess
import threading
import time
import logging
import os

LOG_PATH = "logs/blocked_ips.log"
os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)

logger = logging.getLogger("blocker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LOG_PATH)
    fmt = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

def _iptables_check_rule(ip):
    try:
        subprocess.run(["sudo", "iptables", "-C", "INPUT", "-s", ip, "-j", "DROP"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False

def block_ip(ip, duration=None):
    try:
        if _iptables_check_rule(ip):
            logger.info(f"Attempted to block {ip}, but rule already present.")
        else:
            subprocess.run(["sudo", "iptables", "-I", "INPUT", "-s", ip, "-j", "DROP"],
                           check=True)
            logger.info(f"Blocked IP: {ip}")
        if duration and duration > 0:
            t = threading.Timer(duration, unblock_ip, args=(ip,))
            t.daemon = True
            t.start()
            logger.info(f"Scheduled unblock for {ip} in {duration} seconds")
        return True
    except Exception as e:
        logger.exception(f"Failed to block {ip}: {e}")
        return False

def unblock_ip(ip):
    try:
        removed = False
        while _iptables_check_rule(ip):
            subprocess.run(["sudo", "iptables", "-D", "INPUT", "-s", ip, "-j", "DROP"],
                           check=True)
            removed = True
        if removed:
            logger.info(f"Unblocked IP: {ip}")
        else:
            logger.info(f"Tried to unblock {ip} but no rule found")
        return True
    except Exception as e:
        logger.exception(f"Failed to unblock {ip}: {e}")
        return False
