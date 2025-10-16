from __future__ import annotations
import asyncio
import base64
import sys
from typing import Optional

from protocol import dumps_message, loads_message

async def ainput(prompt: str = "") -> str:
    return await asyncio.get_running_loop().run_in_executor(None, lambda: input(prompt))

async def reader_task(reader: asyncio.StreamReader):
    while True:
        line = await reader.readline()
        if not line:
            print("\n[disconnected]")
            return
        try:
            msg = loads_message(line)
        except Exception as e:
            print("[bad message]", e)
            continue
        t = msg.get("type")
        if t == "chat":
            print(f"[{msg.get('room')}] {msg.get('from')}: {msg.get('text')}")
        elif t == "system":
            print(f"[*] {msg.get('text')} | users: {', '.join(msg.get('users', []))}")
        elif t == "pm":
            print(f"[pm from {msg.get('from')}] {msg.get('text')}")
        elif t == "file":
            print(f"[file {msg.get('filename')} from {msg.get('from')} size={msg.get('size')} bytes]")
        elif t == "error":
            print(f"[error] {msg.get('error')}")

async def writer_task(writer: asyncio.StreamWriter, nick: str, room: str):
    # Отправляем join
    writer.write(dumps_message({"type":"join","nick":nick,"room":room}))
    await writer.drain()

    help_text = (
        "/help — показать команды\n"
        "/room <name> — перейти в комнату\n"
        "/pm <nick> <text> — личное сообщение\n"
        "/file <path> — отправить файл (<=5MB)\n"
        "просто текст — отправить сообщение в комнату\n"
    )
    print(help_text)

    while True:
        text = await ainput("")
        if not text:
            continue
        if text.startswith("/help"):
            print(help_text)
            continue
        if text.startswith("/room "):
            name = text.split(maxsplit=1)[1]
            writer.write(dumps_message({"type":"switch_room","room":name}))
            await writer.drain()
            continue
        if text.startswith("/pm "):
            try:
                _, to, pm_text = text.split(" ", 2)
            except ValueError:
                print("Usage: /pm <nick> <text>")
                continue
            writer.write(dumps_message({"type":"pm","to":to,"text":pm_text}))
            await writer.drain()
            continue
        if text.startswith("/file "):
            path = text.split(maxsplit=1)[1]
            try:
                data = open(path, 'rb').read()
            except Exception as e:
                print("File error:", e)
                continue
            import os
            if len(data) > 5 * 1024 * 1024:
                print("File too large")
                continue
            b64 = base64.b64encode(data).decode('ascii')
            writer.write(dumps_message({"type":"file","filename":os.path.basename(path),"data":b64}))
            await writer.drain()
            continue
        # обычный чат
        writer.write(dumps_message({"type":"chat","text":text}))
        await writer.drain()

async def main(host: str = "127.0.0.1", port: int = 8888, nick: str = "user", room: str = "general"):
    reader, writer = await asyncio.open_connection(host, port)
    await asyncio.gather(reader_task(reader), writer_task(writer, nick, room))

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=50001)
    p.add_argument("--nick", default="user")
    p.add_argument("--room", default="general")
    args = p.parse_args()
    try:
        asyncio.run(main(args.host, args.port, args.nick, args.room))
    except KeyboardInterrupt:
        pass