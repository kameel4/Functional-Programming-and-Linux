import os, json
import matplotlib.pyplot as plt
from .util import read_jsonl_tail

def build_report(log_path: str, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    rows = read_jsonl_tail(log_path, max_lines=50000)  # читаем до 50k последних строк
    counts = {}
    for r in rows:
        t = r.get("type") or "unknown"
        counts[t] = counts.get(t, 0) + 1

    labels = list(counts.keys())
    values = [counts[k] for k in labels]

    plt.figure()
    plt.bar(labels, values)
    plt.title("События по типам")
    plt.xlabel("Тип события")
    plt.ylabel("Количество")
    out_path = os.path.join(out_dir, "events_by_type.png")
    plt.savefig(out_path, bbox_inches="tight")
    return out_path
