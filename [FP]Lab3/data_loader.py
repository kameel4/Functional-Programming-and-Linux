import json
from typing import Dict, List

Book = Dict[str, object]


# { "title": ..., "author": ..., "genre": ..., "description": ..., "year": ... }
def read_books(path: str) -> List[Book]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)  # ожидается список словарей
        return list(data)