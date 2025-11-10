# -*- coding: utf-8 -*-
# Скачивает 30 обложек книг по фиксированным URL и упаковывает их в ZIP.
# Результат: папка covers_30/ и архив book_covers_30.zip

import os
import re
import zipfile
import requests

COVERS = [
    # фантастика
    ("Дюна","Фрэнк Герберт","https://covers.openlibrary.org/b/olid/OL30105510M-L.jpg"),
    ("Фонд","Айзек Азимов","https://covers.openlibrary.org/b/olid/OL26774598M-L.jpg"),
    ("Нейромант","Уильям Гибсон","https://covers.openlibrary.org/b/olid/OL1627167M-L.jpg"),
    ("Игра Эндера","Орсон Скотт Кард","https://covers.openlibrary.org/b/olid/OL27900720M-L.jpg"),
    ("Цветы для Элджернона","Дэниел Киз","https://covers.openlibrary.org/b/olid/OL28677690M-L.jpg"),
    ("Марсианин","Энди Вейер","https://covers.openlibrary.org/b/olid/OL26420821M-L.jpg"),
    ("Гиперион","Дэн Симмонс","https://covers.openlibrary.org/b/olid/OL2055137M-L.jpg"),
    ("451° по Фаренгейту","Рэй Брэдбери","https://covers.openlibrary.org/b/olid/OL15228105M-L.jpg"),
    # фэнтези
    ("Властелин колец","Дж. Р. Р. Толкин","https://covers.openlibrary.org/b/olid/OL3404981M-L.jpg"),
    ("Хоббит, или Туда и обратно","Дж. Р. Р. Толкин","https://covers.openlibrary.org/b/olid/OL8151617M-L.jpg"),
    ("Игра престолов","Джордж Р. Р. Мартин","https://covers.openlibrary.org/b/olid/OL32664646M-L.jpg"),
    ("Последнее желание","Анджей Сапковский","https://covers.openlibrary.org/b/olid/OL26803794M-L.jpg"),
    ("Волшебник Земноморья","Урсула Ле Гуин","https://covers.openlibrary.org/b/olid/OL24224271M-L.jpg"),
    ("Путь королей","Брэндон Сандерсон","https://covers.openlibrary.org/b/olid/OL24383834M-L.jpg"),
    ("Имя ветра","Патрик Ротфусс","https://covers.openlibrary.org/b/olid/OL16159793M-L.jpg"),
    ("Американские боги","Нил Гейман","https://covers.openlibrary.org/b/olid/OL3945760M-L.jpg"),
    # детектив
    ("Убийство в «Восточном экспрессе»","Агата Кристи","https://covers.openlibrary.org/b/olid/OL3548297M-L.jpg"),
    ("И никого не стало","Агата Кристи","https://covers.openlibrary.org/b/olid/OL3301827M-L.jpg"),
    ("Этюд в багровых тонах","Артур Конан Дойл","https://covers.openlibrary.org/b/olid/OL27891215M-L.jpg"),
    ("Собака Баскервилей","Артур Конан Дойл","https://covers.openlibrary.org/b/olid/OL1101202M-L.jpg"),
    ("Большой сон","Реймонд Чандлер","https://covers.openlibrary.org/b/olid/OL4882720M-L.jpg"),
    ("Девушка с татуировкой дракона","Стиг Ларссон","https://covers.openlibrary.org/b/olid/OL23726164M-L.jpg"),
    ("Имя розы","Умберто Эко","https://covers.openlibrary.org/b/olid/OL3501018M-L.jpg"),
    # научпоп
    ("Sapiens. Краткая история человечества","Юваль Ной Харари","https://covers.openlibrary.org/b/olid/OL26234146M-L.jpg"),
    ("Чёрный лебедь","Нассим Николас Талеб","https://covers.openlibrary.org/b/olid/OL17969527M-L.jpg"),
    ("Краткая история времени","Стивен Хокинг","https://covers.openlibrary.org/b/olid/OL2402980M-L.jpg"),
    ("Эгоистичный ген","Ричард Докинз","https://covers.openlibrary.org/b/olid/OL4554174M-L.jpg"),
    ("Ружья, микробы и сталь","Джаред Даймонд","https://covers.openlibrary.org/b/olid/OL998315M-L.jpg"),
    ("Думай медленно… решай быстро","Даниэль Канеман","https://covers.openlibrary.org/b/olid/OL25416865M-L.jpg"),
    ("Почему мы спим","Мэттью Уокер","https://covers.openlibrary.org/b/olid/OL28416821M-L.jpg"),
]

OUT_DIR = "covers_30"
ZIP_NAME = "book_covers_30.zip"

def safe_name(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]+', "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0"}
    for i, (title, author, url) in enumerate(COVERS, 1):
        fn = f"{i:02d} - {safe_name(title)} - {safe_name(author)}.jpg"
        path = os.path.join(OUT_DIR, fn)
        print(f"[{i:02d}/30] {title} — {author}")
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)

    # zip
    with zipfile.ZipFile(ZIP_NAME, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(OUT_DIR)):
            z.write(os.path.join(OUT_DIR, fn), arcname=fn)
    print(f"\nГотово: {ZIP_NAME}")

if __name__ == "__main__":
    main()
