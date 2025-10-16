# tests/conftest.py
import asyncio
import contextlib
import socket
import pytest_asyncio
import pytest

import Lab2.code.server as srv_mod
from Lab2.code.protocol import dumps_message, loads_message

# pytest_plugins = ("pytest_asyncio",)

@pytest.fixture
def any_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

@pytest_asyncio.fixture
async def running_server(any_free_port, monkeypatch):
    # Чтобы тесты отрабатывали быстрее, уменьшим таймауты:
    monkeypatch.setattr(srv_mod, "IDLE_TIMEOUT", 5)   
    monkeypatch.setattr(srv_mod, "MAX_MESSAGE_BYTES", 8 * 1024 * 1024)    # секунд
    # Можно при желании уменьшить лимиты сообщений/файлов аналогично.

    chat = srv_mod.ChatServer()
    server = await asyncio.start_server(chat.handle_client, "127.0.0.1", any_free_port,
                                        limit=10 * 1024 * 1024)
    async def _serve():
        async with server:
            await server.serve_forever()

    task = asyncio.create_task(_serve())
    try:
        yield ("127.0.0.1", any_free_port)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

async def open_client(addr):
    host, port = addr
    reader, writer = await asyncio.open_connection(host, port)
    return reader, writer

async def send_json(writer, payload: dict):
    writer.write(dumps_message(payload))
    await writer.drain()

async def recv_json(reader, *, timeout=1.0):
    line = await asyncio.wait_for(reader.readline(), timeout=timeout)
    if not line:
        return None
    return loads_message(line)
