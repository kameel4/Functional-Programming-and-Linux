# rules.py

from scapy.layers.inet import IP, TCP, UDP
from collections import defaultdict
import time

# глобальное состояние
state = {
    "packet_count": defaultdict(list)
}

# пример 1: слишком частые пакеты с одного IP
def rule_high_packet_rate(pkt, state):
    if IP not in pkt:
        return False, ""
    src = pkt[IP].src
    now = time.time()
    timestamps = state["packet_count"][src]
    timestamps.append(now)
    # храним последние 5 сек
    state["packet_count"][src] = [t for t in timestamps if now - t < 5]
    if len(state["packet_count"][src]) > 20:
        return True, "Высокая частота пакетов"
    return False, ""

# пример 2: нестандартные порты
def rule_unusual_port(pkt, state):
    if TCP in pkt:
        dport = pkt[TCP].dport
        if dport not in [80, 443, 22]:
            return True, f"Необычный порт TCP {dport}"
    if UDP in pkt:
        dport = pkt[UDP].dport
        if dport not in [53, 67, 68]:
            return True, f"Необычный порт UDP {dport}"
    return False, ""
