# tests/test_files_and_timeouts.py
import asyncio
import base64
import os
import pytest
from Lab2.code.protocol import loads_message

@pytest.mark.asyncio
async def test_file_broadcast_ok(running_server, tmp_path):
    # Два клиента в одной комнате
    r1, w1 = await asyncio.open_connection(*running_server)
    w1.write(b'{"type":"join","nick":"A","room":"general"}\n'); await w1.drain()
    await r1.readline()

    r2, w2 = await asyncio.open_connection(*running_server)
    w2.write(b'{"type":"join","nick":"B","room":"general"}\n'); await w2.drain()
    await r2.readline(); await r1.readline()

    # Подготовим <= 5MB файл
    data = b'x' * (1024 * 10)
    b64 = base64.b64encode(data).decode("ascii")
    w1.write(('{"type":"file","filename":"t.bin","data":"%s"}\n' % b64).encode()); await w1.drain()

    msg_for_b = loads_message(await r2.readline())
    assert msg_for_b["type"] == "file"
    assert msg_for_b["filename"] == "t.bin"
    assert msg_for_b["size"] == len(data)

@pytest.mark.asyncio
async def test_file_too_large_rejected(running_server):
    r, w = await asyncio.open_connection(*running_server)
    w.write(b'{"type":"join","nick":"A","room":"general"}\n'); await w.drain()
    await r.readline()

    # 5MB + 1 байт
    data = b'x' * (5 * 1024 * 1024 + 1)
    b64 = base64.b64encode(data).decode("ascii")
    w.write(('{"type":"file","filename":"big.bin","data":"%s"}\n' % b64).encode()); await w.drain()

    err = loads_message(await r.readline())
    assert err["type"] == "error"
    assert "file too large" in err["error"]

@pytest.mark.asyncio
async def test_idle_timeout_disconnects(running_server):
    r, w = await asyncio.open_connection(*running_server)
    w.write(b'{"type":"join","nick":"Idle","room":"general"}\n'); await w.drain()
    await r.readline()

    # Ничего не отправляем и ждём, что соединение закроется
    with pytest.raises(asyncio.TimeoutError):
        # Сервер закроет сокет, readline вернёт b''; дадим чуть больше времени
        line = await asyncio.wait_for(r.readline(), timeout=2.0)
        assert line == b""
