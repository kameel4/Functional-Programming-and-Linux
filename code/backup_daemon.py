#!/usr/bin/env python3
import os
import time
import shutil
import syslog as sl
import configparser as cp
import datetime as dt

CONFIG_FILE = "/etc/backup.conf"

def load_config():
    config = cp.ConfigParser()
    config.read(CONFIG_FILE)

    source = config.get('settings', 'source')
    backup = config.get('settings', 'backup')
    interval = config.getint("settings", 'interval')
    
    return source, backup, interval

def copy_files(src_dir, dst_dir):
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = os.path.join(dst_dir, timestamp)
    try:
        shutil.copytree(src_dir, backup_dir)
        sl.syslog(sl.LOG_INFO, f'\nСоздана резервная копия {backup_dir}')
        
    except Exception as e:
        sl.syslog(sl.LOG_ERR, f'Не удалось копировать {src_dir} -> {dst_dir}')

def main():
    while True:
        src_dir, dst_dir, interval = load_config()
        copy_files(src_dir, dst_dir)
        time.sleep(interval)


if __name__ == "__main__":
    sl.openlog(ident="backup_daemon", logoption=sl.LOG_PID)
    main()






