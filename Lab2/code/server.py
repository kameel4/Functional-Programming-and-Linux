from __future__ import annotations
import asyncio
import base64
import contextlib
import json
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any

from protocol import dumps_message, loads_message, ProtocolError

MAX_MESSAGE_BYTES = 64 * 1024  # ограничим размер входной строки
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB на файл
IDLE_TIMEOUT = 300  # секунд бездействия

@dataclass(eq=False)
class Client:
    nick: str
    writer: asyncio.StreamWriter
    room: Optional[str] = None

@dataclass
class Room:
    name: str
    clients: Set[Client] = field(default_factory=set)
    queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    dispatcher_task: Optional[asyncio.Task] = None

class ChatServer:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.clients_by_nick: Dict[str, Client] = {}
        self._lock = asyncio.Lock()

    def room_users(self, room_name: str) -> list[str]:
        room = self.rooms.get(room_name)
        if not room:
            return []
        return sorted(c.nick for c in room.clients)

    def get_room(self, name: str) -> Room:
        if name not in self.rooms:
            room = Room(name=name)
            room.dispatcher_task = asyncio.create_task(self.room_dispatcher(room))
            self.rooms[name] = room
        return self.rooms[name]

    async def room_dispatcher(self, room: Room):
        # Слушаем очередь и рассылаем всем участникам комнаты
        while True:
            msg = await room.queue.get()
            payload = dumps_message(msg)
            to_remove = []
            for c in list(room.clients):
                try:
                    c.writer.write(payload)
                    await c.writer.drain()
                except Exception:
                    to_remove.append(c)
            for c in to_remove:
                room.clients.discard(c)

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info('peername')
        client: Optional[Client] = None
        try:
            # Первое сообщение ожидаем join
            line = await asyncio.wait_for(reader.readline(), timeout=IDLE_TIMEOUT)
            if not line:
                return
            if len(line) > MAX_MESSAGE_BYTES:
                return
            msg = loads_message(line)
            if msg.get("type") != "join":
                await self.safe_send(writer, {"type":"error","error":"First message must be 'join'"})
                return
            nick = str(msg.get("nick", "")).strip()
            room_name = str(msg.get("room", "")).strip() or "general"
            if not nick:
                await self.safe_send(writer, {"type":"error","error":"Nick is required"})
                return

            async with self._lock:
                if nick in self.clients_by_nick:
                    await self.safe_send(writer, {"type":"error","error":"Nick is taken"})
                    return
                client = Client(nick=nick, writer=writer, room=room_name)
                self.clients_by_nick[nick] = client
                room = self.get_room(room_name)
                room.clients.add(client)

            await self.announce(room_name, {"type":"system","room":room_name,
                                            "text":f"{nick} joined", "users": self.room_users(room_name)})

            # Основной цикл приема
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=IDLE_TIMEOUT)
                if not line:
                    break
                if len(line) > MAX_MESSAGE_BYTES:
                    await self.safe_send(writer, {"type":"error","error":"Message too long"})
                    continue
                try:
                    msg = loads_message(line)
                except ProtocolError as e:
                    await self.safe_send(writer, {"type":"error","error":f"Bad JSON: {e}"})
                    continue
                await self.process_message(client, msg)
        except asyncio.TimeoutError:
            # неактивен — закрываем
            pass
        except Exception:
            # Логирование можно добавить здесь
            pass
        finally:
            # Уборка
            if client:
                async with self._lock:
                    self.clients_by_nick.pop(client.nick, None)
                    if client.room and client.room in self.rooms:
                        room = self.rooms[client.room]
                        room.clients.discard(client)
                if client.room:
                    await self.announce(client.room, {"type":"system","room":client.room,
                                                      "text":f"{client.nick} left", "users": self.room_users(client.room)})
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def process_message(self, client: Client, msg: Dict[str, Any]):
        t = msg.get("type")
        if t == "chat":
            text = str(msg.get("text", ""))
            if client.room:
                await self.announce(client.room, {"type":"chat","room":client.room,
                                                  "from":client.nick,"text":text})
        elif t == "switch_room":
            new_room = str(msg.get("room", "")).strip()
            if not new_room:
                await self.safe_send(client.writer, {"type":"error","error":"room required"})
                return
            await self.switch_room(client, new_room)
        elif t == "pm":
            to = str(msg.get("to", "")).strip()
            text = str(msg.get("text", ""))
            target = self.clients_by_nick.get(to)
            if not target:
                await self.safe_send(client.writer, {"type":"error","error":"user not found"})
                return
            await self.safe_send(target.writer, {"type":"pm","from":client.nick,"text":text})
        elif t == "file":
            if not client.room:
                return
            filename = str(msg.get("filename", ""))
            data_b64 = str(msg.get("data", ""))
            try:
                raw = base64.b64decode(data_b64, validate=True)
            except Exception:
                await self.safe_send(client.writer, {"type":"error","error":"bad base64"})
                return
            if len(raw) > MAX_FILE_BYTES:
                await self.safe_send(client.writer, {"type":"error","error":"file too large"})
                return
            await self.announce(client.room, {
                "type":"file","room":client.room,"from":client.nick,
                "filename": filename, "size": len(raw), "data": data_b64,
            })
        elif t == "who":
            if client.room:
                await self.safe_send(client.writer, {"type":"users","room":client.room,
                                                     "users": self.room_users(client.room)})
        else:
            await self.safe_send(client.writer, {"type":"error","error":"unknown type"})

    async def switch_room(self, client: Client, new_room: str):
        old_room = client.room
        if old_room == new_room:
            return
        if old_room and old_room in self.rooms:
            self.rooms[old_room].clients.discard(client)
            await self.announce(old_room, {"type":"system","room":old_room,
                                           "text":f"{client.nick} left room", "users": self.room_users(old_room)})
        room = self.get_room(new_room)
        room.clients.add(client)
        client.room = new_room
        await self.announce(new_room, {"type":"system","room":new_room,
                                       "text":f"{client.nick} joined room", "users": self.room_users(new_room)})

    async def announce(self, room_name: str, msg: Dict[str, Any]):
        room = self.get_room(room_name)
        await room.queue.put(msg)

    async def safe_send(self, writer: asyncio.StreamWriter, msg: Dict[str, Any]):
        try:
            writer.write(dumps_message(msg))
            await writer.drain()
        except Exception:
            pass

async def main(host: str = "0.0.0.0", port: int = 50001):
    srv = ChatServer()
    server = await asyncio.start_server(srv.handle_client, host, port)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
    print(f"Serving on {addrs}")
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass