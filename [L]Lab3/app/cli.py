import argparse, json, sys
from .util import read_jsonl_tail

def main():
    ap = argparse.ArgumentParser(description="Поиск по JSONL логу событий")
    ap.add_argument("--log", default="./logs/events.jsonl")
    ap.add_argument("--type", help="file|process|...", default=None)
    ap.add_argument("--user", help="имя пользователя содержит подстроку", default=None)
    ap.add_argument("--contains", help="подстрока в proc/file/action", default=None)
    ap.add_argument("--limit", type=int, default=2000, help="сколько последних строк читать")
    args = ap.parse_args()

    rows = read_jsonl_tail(args.log, max_lines=args.limit)

    def ok(r):
        if args.type and r.get("type") != args.type:
            return False
        if args.user and (args.user not in (r.get("user") or "")):
            return False
        if args.contains:
            hay = " ".join([str(r.get("proc") or ""), str(r.get("file") or ""), str(r.get("action") or "")])
            if args.contains not in hay:
                return False
        return True

    out = [r for r in rows if ok(r)]
    for r in out:
        sys.stdout.write(json.dumps(r, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    main()
