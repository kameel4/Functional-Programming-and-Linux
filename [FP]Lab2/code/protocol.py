from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict


NEWLINE = "\n"
ENCODING = "utf-8"


class ProtocolError(Exception):
    pass


# Базовый формат — строки JSON, разделенные "\n" (JSON Lines)
# Примеры исходящих от клиента:
# {"type":"join", "room":"general", "nick":"Alice"}
# {"type":"chat", "room":"general", "text":"Hello"}
# {"type":"pm", "to":"Bob", "text":"Hi"}
# {"type":"file", "room":"general", "filename":"img.png", "mime":"image/png", "data":"<base64>"}




def dumps_message(payload: Dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + NEWLINE).encode(ENCODING)




def loads_message(line: bytes) -> Dict[str, Any]:
    try:
        return json.loads(line.decode(ENCODING))
    except Exception as e:
        raise ProtocolError(str(e))