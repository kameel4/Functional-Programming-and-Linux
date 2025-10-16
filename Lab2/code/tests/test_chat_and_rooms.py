# tests/test_chat_and_rooms.py
import asyncio
import pytest
from Lab2.code.protocol import loads_message, dumps_message

@pytest.mark.asyncio
async def test_broadcast_to_room_only(running_server):
    # Alice и Bob в одной комнате, Carol — в другой
    r1, w1 = await asyncio.open_connection(*running_server)
    w1.write(b'{"type":"join","nick":"Alice","room":"general"}\n'); await w1.drain()
    await r1.readline()

    r2, w2 = await asyncio.open_connection(*running_server)
    w2.write(b'{"type":"join","nick":"Bob","room":"general"}\n'); await w2.drain()
    await r2.readline()  # system Bob
    await r1.readline()  # system уведомление для Alice о Bob

    r3, w3 = await asyncio.open_connection(*running_server)
    w3.write(b'{"type":"join","nick":"Carol","room":"other"}\n'); await w3.drain()
    await r3.readline()  # system Carol

    # Bob говорит в general
    w2.write(b'{"type":"chat","text":"hi"}\n'); await w2.drain()

    msg_for_alice = loads_message(await r1.readline())
    assert msg_for_alice["type"] == "chat"
    assert msg_for_alice["from"] == "Bob"
    assert msg_for_alice["text"] == "hi"

    # Carol ничего не должна получить
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(r3.readline(), timeout=0.3)



@pytest.mark.asyncio
async def test_switch_room_moves_user_and_notifies(running_server):
    host, port = running_server

    # Клиент-слушатель в old room ("general")
    r_old, w_old = await asyncio.open_connection(host, port)
    w_old.write(b'{"type":"join","nick":"Listener","room":"general"}\n'); await w_old.drain()
    await asyncio.wait_for(r_old.readline(), timeout=1.0)  # system Listener joined

    # Переезжающий клиент
    r_move, w_move = await asyncio.open_connection(host, port)
    w_move.write(b'{"type":"join","nick":"Mover","room":"general"}\n'); await w_move.drain()
    await asyncio.wait_for(r_move.readline(), timeout=1.0)  # system Mover joined
    await asyncio.wait_for(r_old.readline(),  timeout=1.0)  # system for Listener about Mover

    # Переключаем комнату
    w_move.write(b'{"type":"switch_room","room":"r2"}\n'); await w_move.drain()

    # Слушатель в старой комнате должен увидеть "left room"
    left_msg = loads_message(await asyncio.wait_for(r_old.readline(), timeout=2.0))
    assert left_msg["type"] == "system"
    assert "left room" in left_msg["text"]

    # Переехавший клиент должен увидеть "joined room" (а НЕ "left room")
    joined_msg = loads_message(await asyncio.wait_for(r_move.readline(), timeout=2.0))
    assert joined_msg["type"] == "system"
    assert "joined room" in joined_msg["text"]

