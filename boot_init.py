# boot_init.py
# Purpose: make sure runtime files and folders exist on Render's ephemeral FS
# We DO NOT touch your token or bot code.

import json, os, pathlib, sys, time

ROOT = pathlib.Path(__file__).parent.resolve()

RUNTIME_FILES = {
    "user_ids.json": "[]",         # set() in памяти -> в JSON как list
    "user_settings.json": "{}",    # словарь настроек пользователей
    "price.json": "{}",            # текущая цена/история по игре
    "cache.json": "{}",            # кэш сетевых ответов
    "stats.json": "{}",            # простая статистика
    "bot.log": "",                 # лог-файл (может перезаписываться)
}
RUNTIME_DIRS = [
    "temp_images",                 # временные картинки
]

def ensure_dirs():
    for d in RUNTIME_DIRS:
        (ROOT / d).mkdir(parents=True, exist_ok=True)

def ensure_files():
    for name, default_content in RUNTIME_FILES.items():
        f = ROOT / name
        if not f.exists():
            mode = "wb" if isinstance(default_content, bytes) else "w"
            with open(f, mode, encoding=None if mode == "wb" else "utf-8") as out:
                out.write(default_content)

if __name__ == "__main__":
    ensure_dirs()
    ensure_files()
    # Small stdout note for Render logs
    print("[boot_init] runtime folders/files are ready")
