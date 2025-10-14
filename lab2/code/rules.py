from scapy.all import IP, TCP, UDP


state={"counts":{},"ports_common":{80,443,53,123,22,25,110,143,587,993,995}}


def rule_high_packet_rate(pkt, st):
    if IP not in pkt: return False, ""
    s=pkt[IP].src
    st["counts"].setdefault(s,0)
    st["counts"][s]+=1
    return st["counts"][s]%20==0, "high_rate"


def rule_unusual_port(pkt, st):
    if TCP in pkt: d=pkt[TCP].dport
    elif UDP in pkt: d=pkt[UDP].dport
    else: return False, ""
    return d not in st["ports_common"], f"port_{d}"