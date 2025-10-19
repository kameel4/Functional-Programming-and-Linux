# Linux Audit Tool (No-DB MVP)

Минимальный инструмент аудита Linux: все события пишутся в **JSONL**-лог с ротацией. 
Есть GUI-просмотрщик (фильтры) и генератор отчёта.

## Быстрый старт

```bash
# 1) Подготовка окружения (Ubuntu/Debian)
sudo apt update
sudo apt install -y python3 python3-venv python3-pip libxcb-cursor0

# 2) Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 3) Установить зависимости
pip install -r requirements.txt

# 4а) Запуск с GUI
python -m app.main --gui

# 4б) Headless-сборщик (без GUI)
python -m app.main --headless
