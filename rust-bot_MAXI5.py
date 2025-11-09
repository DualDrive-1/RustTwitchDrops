import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup
from telegram.ext import Application
from telegram.ext import CommandHandler
from telegram.ext import CallbackQueryHandler
from telegram.ext import JobQueue
from telegram.ext import CallbackContext
from telegram.ext import ConversationHandler
from telegram.ext import MessageHandler
from telegram.ext import filters
import json
import os
import logging
import time
from datetime import datetime, timedelta
from PIL import Image
import io

# Кастомный форматтер логов на русском
class RussianFormatter(logging.Formatter):
    LEVELS = {
        'DEBUG': 'ОТЛАДКА',
        'INFO': 'ИНФО',
        'WARNING': 'ПРЕДУПРЕЖДЕНИЕ',
        'ERROR': 'ОШИБКА',
        'CRITICAL': 'КРИТИЧЕСКАЯ'
    }

    def format(self, record):
        record.levelname = self.LEVELS.get(record.levelname, record.levelname)
        return super().format(record)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger()
for handler in logger.handlers:
    handler.setFormatter(RussianFormatter())

# Ваш токен Telegram-бота
TOKEN = "7951243658:AAG0L0k-_eMqd0FZMR4AmFrn-pk2bIDL_18"

# URL сайтов
SITE_URL = "https://twitch.facepunch.com/"
STEAM_URL = "https://store.steampowered.com/app/252490/Rust/"
TWITCH_STREAMERS_URL = "https://www.twitch.tv/directory/category/rust"
NEWS_URL = "https://rust.facepunch.com/news/"

# Заголовки для запросов
DEFAULT_TIMEOUT = 10

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Путь к файлам для хранения данных
USER_IDS_FILE = "user_ids.json"
PRICE_FILE = "price.json"
SETTINGS_FILE = "user_settings.json"
CACHE_FILE = "cache.json"
STATS_FILE = "stats.json"
TEMP_IMAGE_DIR = "temp_images"

# Создать директорию для временных изображений
if not os.path.exists(TEMP_IMAGE_DIR):
    os.makedirs(TEMP_IMAGE_DIR)

# Глобальные переменные
is_event_live = None
last_timer_status = None
last_days = None

# Состояния для ConversationHandler
DROP_CALC_HOURS = 0

# Функция для создания полной клавиатуры
def get_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Старт", callback_data='start'),
            InlineKeyboardButton("Проверить статус трансляции", callback_data='check')
        ],
        [
            InlineKeyboardButton("Увидеть предметы", callback_data='items'),
            InlineKeyboardButton("Узнать цену в Стим", callback_data='price')
        ],
        [
            InlineKeyboardButton("История цен", callback_data='price_history'),
            InlineKeyboardButton("Стримы", callback_data='streams')
        ],
        [
            InlineKeyboardButton("Новости", callback_data='news'),
            InlineKeyboardButton("Калькулятор дропов", callback_data='drop_calc')
        ],
        [
            InlineKeyboardButton("Настройки", callback_data='settings'),
            InlineKeyboardButton("Инструкция по Auto Twitch", callback_data='auto_twitch')
        ],
        [
            InlineKeyboardButton("Поддержка", callback_data='support'),
            InlineKeyboardButton("Вернуться", callback_data='menu')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция для создания кнопки "Вернуться"
def get_back_button():
    keyboard = [
        [InlineKeyboardButton("Вернуться", callback_data='menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Функция для создания главного меню
def get_main_menu():
    return get_keyboard()

# Функция для загрузки данных из JSON
def load_json(file_path, default):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as file:
                return json.load(file)
        except Exception as e:
            logging.error(f"Ошибка при загрузке файла {file_path}: {e}")
            return default
    return default

# Функция для сохранения данных в JSON
def save_json(file_path, data):
    try:
        with open(file_path, "w") as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        logging.error(f"Ошибка при сохранении файла {file_path}: {e}")

# Функция для загрузки chat_id
def load_user_ids():
    data = load_json(USER_IDS_FILE, [])
    try:
        return set(data)
    except Exception:
        return set()

# Функция для сохранения chat_id
def save_user_ids(user_ids):
    save_json(USER_IDS_FILE, list(user_ids))

# Функция для загрузки настроек пользователей
def load_user_settings():
    return load_json(SETTINGS_FILE, {})

# Функция для сохранения настроек пользователей
def save_user_settings(settings):
    save_json(SETTINGS_FILE, settings)

# Функция для загрузки кэша
def load_cache():
    return load_json(CACHE_FILE, {})

# Функция для сохранения кэша
def save_cache(cache):
    save_json(CACHE_FILE, cache)

# Функция для загрузки статистики
def load_stats():
    return load_json(STATS_FILE, {"users": 0, "commands": {}, "errors": 0})

# Функция для сохранения статистики
def save_stats(stats):
    save_json(STATS_FILE, stats)

# Функция для обновления статистики
def update_stats(command):
    stats = load_stats()
    stats["commands"][command] = stats["commands"].get(command, 0) + 1
    save_stats(stats)

# Функция для проверки кэша
def get_cached_data(key, fetch_func, cache_duration=300):
    cache = load_cache()
    if key in cache and (time.time() - cache[key]["timestamp"]) < cache_duration:
        logging.info(f"Используется кэшированный результат для {key}")
        return cache[key]["data"]
    try:
        data = fetch_func()
        if not data and key == "streams":
            logging.warning(f"Получен пустой результат для {key}, кэш не обновляется")
            return data
        cache[key] = {"data": data, "timestamp": time.time()}
        save_cache(cache)
        logging.info(f"Успешно обновлён кэш для {key}")
        return data
    except Exception as e:
        logging.error(f"Ошибка при получении данных для {key}: {e}")
        stats = load_stats()
        stats["errors"] += 1
        save_stats(stats)
        return cache.get(key, {}).get("data", None)

# Функция для добавления чёрного фона к изображению
def add_black_background(image_url):
    try:
        response = requests.get(image_url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        img = Image.open(io.BytesIO(response.content))
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        background = Image.new('RGBA', img.size, (0, 0, 0, 255))
        background.paste(img, (0, 0), img)
        output_path = os.path.join(TEMP_IMAGE_DIR, f"image_{int(time.time())}.png")
        background.save(output_path, 'PNG')
        logging.info(f"Изображение с чёрным фоном сохранено: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Ошибка при обработке изображения: {e}")
        return None

# Функция для получения актуального изображения
def get_current_image():
    def fetch():
        response = requests.get(SITE_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос изображения: статус {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        img_tag = soup.find('img', alt="Drops on Twitch")
        if img_tag and 'src' in img_tag.attrs:
            image_url = img_tag['src']
            processed_image = add_black_background(image_url)
            if processed_image:
                return processed_image
            logging.warning("Не удалось обработать изображение, возвращаем оригинальный URL")
            return image_url
        logging.warning("Изображение не найдено")
        return None
    return get_cached_data("current_image", fetch)

# Функция для получения статуса таймера
def get_timer_status():
    def fetch():
        response = requests.get(SITE_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос таймера: статус {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        timer_element = soup.find('div', class_='counter timer')
        if not timer_element:
            return None
        title = timer_element.find('span', class_='title').text.strip()
        days = timer_element.find('h1', class_='value day')
        hours = timer_element.find('h1', class_='value hour')
        minutes = timer_element.find('h1', class_='value minute')
        seconds = timer_element.find('h1', class_='value second')
        time_parts = []
        if days and int(days.text) > 0:
            time_parts.append(f"{days.text} дней")
        if hours and int(hours.text) > 0:
            time_parts.append(f"{hours.text} часов")
        if minutes and int(minutes.text) > 0:
            time_parts.append(f"{minutes.text} минут")
        if seconds and int(seconds.text) > 0:
            time_parts.append(f"{seconds.text} секунд")
        time_str = ", ".join(time_parts) if time_parts else "менее секунды"
        coarse_time = ", ".join(part for part in time_parts if "дней" in part or "часов" in part)
        days_value = int(days.text) if days else 0
        if "starts in" in title.lower():
            return {"status": "pending", "time": time_str, "coarse_time": coarse_time, "days": days_value}
        elif "ends in" in title.lower():
            return {"status": "live", "time": time_str, "coarse_time": coarse_time, "days": days_value}
        return None
    return get_cached_data("timer_status", fetch)

# Функция для проверки статуса трансляции
def check_event_status():
    def fetch():
        response = requests.get(SITE_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос статуса трансляции: статус {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        live_element = soup.find('span', class_='round-info-live')
        timer_status = get_timer_status()
        if live_element and "Event Live" in live_element.text:
            return {"status": "live", "timer": timer_status}
        elif timer_status and timer_status["status"] == "pending":
            return {"status": "pending", "timer": timer_status}
        else:
            return {"status": "none", "timer": None}
    return get_cached_data("event_status", fetch)

# Функция для получения списка дропов
def get_drops():
    def fetch():
        response = requests.get(SITE_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос дропов: статус {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        drops_section = soup.find('div', class_='section drops')
        if not drops_section:
            logging.warning("Секция дропов не найдена")
            return []
        drop_boxes = drops_section.find_all('a', class_='drop-box')
        drops = []
        for box in drop_boxes:
            item_name = box.find('span', class_='drop-type')
            video_tag = box.find('video')
            item_time = box.find('div', class_='drop-time')
            item_count = box.find('span', class_='drop-counter')
            if item_name and video_tag and video_tag.find('source'):
                video_url = video_tag.find('source')['src']
                drop = {
                    "name": item_name.text.strip(),
                    "video_url": video_url,
                    "time": item_time.find('span').text.strip() if item_time else "Не указано",
                    "count": int(item_count.text) if item_count else 0
                }
                drops.append(drop)
        logging.info(f"Успешно получено {len(drops)} дропов")
        return drops
    return get_cached_data("drops", fetch)

# Функция для получения списка стримов
def get_streams():
    def fetch():
        response = requests.get(TWITCH_STREAMERS_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос стримов: статус {response.status_code}")
        if response.status_code != 200:
            logging.error(f"Ошибка HTTP при запросе стримов: {response.status_code}")
            return []
        soup = BeautifulSoup(response.text, 'html.parser')
        streams = []
        
        # Проверяем наличие секций стримов
        stream_cards = soup.find_all("div", class_="tw-card")
        logging.info(f"Найдено {len(stream_cards)} карточек стримов")
        
        # Сначала собираем русскоязычные стримы
        for card in stream_cards:
            tags = card.find_all("button", class_="tw-tag")
            is_russian = any(tag.find("span") and tag.find("span").text.lower() == "русский" for tag in tags)
            if is_russian:
                stream_data = extract_stream_data(card)
                if stream_data:
                    streams.append(stream_data)
        
        # Дополняем другими стримами, если меньше 6
        if len(streams) < 6:
            for card in stream_cards:
                if len(streams) >= 6:
                    break
                stream_data = extract_stream_data(card)
                if stream_data and stream_data not in streams:
                    streams.append(stream_data)
        
        logging.info(f"Итоговое количество стримов: {len(streams)}")
        return streams[:6]
    return get_cached_data("streams", fetch, cache_duration=600)

# Функция для извлечения данных одного стрима
def extract_stream_data(card):
    try:
        link_elem = card.find("a", class_="tw-link")
        if not link_elem or not link_elem.get("href"):
            logging.warning("Ссылка на стрим не найдена")
            return None
        channel = link_elem["href"].lstrip("/")
        stream_url = f"https://www.twitch.tv/{channel}"
        
        title_elem = card.find("h3", class_="tw-ellipsis")
        title = title_elem.get("title", "Без названия") if title_elem else "Без названия"
        
        channel_elem = card.find("p", class_="tw-c-text-alt-2")
        channel_name = channel_elem.get("title", channel) if channel_elem else channel
        
        preview_elem = card.find("img", class_="tw-image")
        preview_url = preview_elem.get("src") if preview_elem else None
        
        viewers_elem = card.find("span", class_="tw-c-text-alt")
        viewers = viewers_elem.text.strip() if viewers_elem else "Неизвестно"
        
        tags = [tag.find("span").text for tag in card.find_all("button", class_="tw-tag") if tag.find("span")]
        
        logging.info(f"Успешно извлечены данные стрима: {channel}")
        return {
            "url": stream_url,
            "title": title,
            "channel": channel_name,
            "preview": preview_url,
            "viewers": viewers,
            "tags": tags
        }
    except Exception as e:
        logging.error(f"Ошибка при парсинге стрима: {e}")
        return None

# Функция для получения цены Rust в Steam
def get_steam_price():
    def fetch():
        response = requests.get(STEAM_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос цены в Steam: статус {response.status_code}, URL: {STEAM_URL}")
        if response.status_code != 200:
            logging.error(f"Ошибка HTTP при запросе цены: {response.status_code}")
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        price_element = soup.find('div', class_='game_purchase_price price')
        if not price_element:
            price_element = soup.find('div', class_='discount_final_price')
        discount_block = soup.find('div', class_='discount_block')
        if price_element:
            price = price_element.text.strip()
            logging.info(f"Успешно получена цена: {price}")
            if discount_block:
                original_price = discount_block.find('div', class_='discount_original_price')
                discount_pct = discount_block.find('div', class_='discount_pct')
                if original_price and discount_pct:
                    result = {
                        "final_price": price,
                        "original_price": original_price.text.strip(),
                        "discount": discount_pct.text.strip()
                    }
                    logging.info(f"Успешно получена скидка: {result['discount']}")
                    return result
            return {"final_price": price}
        logging.error("Элемент цены не найден на странице Steam")
        return None
    return get_cached_data("steam_price", fetch)

# Функция для загрузки истории цен
def load_price_history():
    return load_json(PRICE_FILE, [])

# Функция для сохранения истории цен
def save_price_history(price_info):
    history = load_price_history()
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price": price_info["final_price"],
        "discount": price_info.get("discount", None)
    })
    save_json(PRICE_FILE, history)

# Функция для получения новостей
def get_news():
    def fetch():
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        logging.info(f"Запрос новостей: статус {response.status_code}, URL: {NEWS_URL}")
        if response.status_code != 200:
            logging.error(f"Ошибка HTTP при запросе новостей: {response.status_code}")
            return None
        soup = BeautifulSoup(response.text, 'html.parser')
        news_container = soup.find('div', class_='blog-posts-container')
        if not news_container:
            logging.error("Контейнер новостей не найден")
            return None
        news_items = news_container.find_all('div', class_='blog-post')[:3]
        news = []
        for item in news_items:
            title = item.find('h1')
            link = item.find('a', href=True, class_='blog-post-image')
            date = item.find('div', class_='tag secondary')
            if title and link and date:
                news.append({
                    "title": title.text.strip(),
                    "url": f"https://rust.facepunch.com{link['href']}",
                    "date": date.text.strip()
                })
        if news:
            logging.info(f"Успешно получено {len(news)} новостей")
        else:
            logging.warning("Новости не найдены")
        return news
    return get_cached_data("news", fetch)

# Список для хранения chat_id всех пользователей
user_chat_ids = set(load_user_ids())

# Обработчик команды /start
async def start(update: Update, context: CallbackContext):
    update_stats("start")
    chat_id = update.effective_chat.id
    if chat_id not in user_chat_ids:
        user_chat_ids.add(chat_id)
        save_user_ids(user_chat_ids)
        stats = load_stats()
        stats["users"] = len(user_chat_ids)
        save_stats(stats)
    status = check_event_status()
    image_path = get_current_image()
    caption = "Привет! Я бот, который следит за трансляциями на twitch.facepunch.com.\n"
    if status["status"] == "live":
        if status["timer"]:
            caption += f"Трансляция идёт! Окончится через {status['timer']['time']}."
        else:
            caption += "Трансляция идёт!"
    elif status["status"] == "pending":
        caption += f"Трансляция начнётся через {status['timer']['time']}."
    else:
        caption += "Трансляций нет. Можете проверить сами: https://twitch.facepunch.com/#drops"
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=get_keyboard()
            )
    else:
        await update.effective_message.reply_text(
            text=caption,
            reply_markup=get_keyboard()
        )

# Обработчик команды /check
async def check_status_command(update: Update, context: CallbackContext):
    update_stats("check")
    status = check_event_status()
    image_path = get_current_image()
    if status["status"] == "live":
        if status["timer"]:
            caption = f"Трансляция идёт! Окончится через {status['timer']['time']}."
        else:
            caption = "Трансляция идёт!"
    elif status["status"] == "pending":
        caption = f"Трансляция начнётся через {status['timer']['time']}."
    else:
        caption = "Трансляций нет. Можете проверить сами: https://twitch.facepunch.com/#drops"
    if image_path and os.path.exists(image_path):
        with open(image_path, 'rb') as photo:
            await update.effective_message.reply_photo(
                photo=photo,
                caption=caption,
                reply_markup=get_back_button()
            )
    else:
        await update.effective_message.reply_text(
            text=caption,
            reply_markup=get_back_button()
        )

# Обработчик команды /items
async def items(update: Update, context: CallbackContext):
    update_stats("items")
    drops = get_drops()
    if not drops:
        await update.effective_message.reply_text(
            text="Не удалось загрузить предметы дропов. Попробуйте позже.",
            reply_markup=get_back_button()
        )
        return
    for drop in drops:
        try:
            caption = f"Предмет: {drop['name']}\nВремя для получения: {drop['time']}\nПолучено: {drop['count']}"
            try:
                await update.effective_message.reply_animation(
                    animation=drop["video_url"],
                    caption=caption,
                    reply_markup=get_back_button()
                )
            except Exception as e:
                logging.error(f"Ошибка при отправке анимации для {drop['name']}: {e}")
                await update.effective_message.reply_text(
                    text=f"{caption}\nВидео: {drop['video_url']}",
                    reply_markup=get_back_button()
                )
        except Exception as e:
            logging.error(f"Ошибка при обработке предмета {drop['name']}: {e}")
            stats = load_stats()
            stats["errors"] += 1
            save_stats(stats)
            await update.effective_message.reply_text(
                text=f"Предмет: {drop['name']} (не удалось загрузить видео)\nВремя: {drop['time']}\nПолучено: {drop['count']}",
                reply_markup=get_back_button()
            )

# Обработчик команды /price
async def price(update: Update, context: CallbackContext):
    update_stats("price")
    steam_price = get_steam_price()
    if steam_price:
        caption = f"Текущая цена Rust в Steam: {steam_price['final_price']}"
        if "discount" in steam_price:
            caption += f"\nСкидка: {steam_price['discount']}\nОригинальная цена: {steam_price['original_price']}"
        caption += "\nСтраница в магазине: https://store.steampowered.com/app/252490/Rust/"
    else:
        caption = "Не удалось загрузить цену Rust в Steam. Попробуйте позже.\nСтраница в магазине: https://store.steampowered.com/app/252490/Rust/"
    await update.effective_message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик команды /price_history
async def price_history(update: Update, context: CallbackContext):
    update_stats("price_history")
    history = load_price_history()
    if not history:
        await update.effective_message.reply_text(
            text="История цен отсутствует.",
            reply_markup=get_back_button()
        )
        return
    caption = "История цен Rust:\n"
    for entry in history[-10:]:
        caption += f"{entry['date']}: {entry['price']}"
        if entry['discount']:
            caption += f" (скидка {entry['discount']})"
        caption += "\n"
    await update.effective_message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик команды /streams
async def streams(update: Update, context: CallbackContext):
    update_stats("streams")
    streams_list = get_streams()
    if not streams_list:
        await update.effective_message.reply_text(
            text="Сейчас нет активных стримов по Rust. Проверьте позже или посетите: https://www.twitch.tv/directory/category/rust",
            reply_markup=get_back_button()
        )
        return
    for stream in streams_list:
        caption = (
            f"🔴 {stream['title']}\n"
            f"Канал: {stream['channel']}\n"
            f"Зрители: {stream['viewers']}\n"
            f"Теги: {', '.join(stream['tags']) if stream['tags'] else 'Нет тегов'}\n"
            f"{stream['url']}"
        )
        try:
            if stream['preview']:
                processed_image = add_black_background(stream['preview'])
                if processed_image and os.path.exists(processed_image):
                    with open(processed_image, 'rb') as photo:
                        await update.effective_message.reply_photo(
                            photo=photo,
                            caption=caption,
                            reply_markup=get_back_button()
                        )
                    os.remove(processed_image)
                else:
                    await update.effective_message.reply_text(
                        text=caption,
                        reply_markup=get_back_button()
                    )
            else:
                await update.effective_message.reply_text(
                    text=caption,
                    reply_markup=get_back_button()
                )
        except Exception as e:
            logging.error(f"Ошибка при отправке стрима {stream['channel']}: {e}")
            await update.effective_message.reply_text(
                text=caption,
                reply_markup=get_back_button()
            )
    await update.effective_message.reply_text(
        text="Вы можете кликнуть на любую ссылку, если же вы хотите увидеть больше, https://www.twitch.tv/directory/category/rust",
        reply_markup=get_back_button()
    )

# Обработчик команды /news
async def news(update: Update, context: CallbackContext):
    update_stats("news")
    news_list = get_news()
    if not news_list:
        await update.effective_message.reply_text(
            text="Не удалось загрузить новости. Попробуйте позже.",
            reply_markup=get_back_button()
        )
        return
    caption = "Последние новости Rust:\n"
    for i, news_item in enumerate(news_list, 1):
        caption += f"{i}. {news_item['title']} ({news_item['date']})\nЧитать: {news_item['url']}\n\n"
    await update.effective_message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик команды /settings
async def settings(update: Update, context: CallbackContext):
    update_stats("settings")
    if isinstance(update, Update):
        chat_id = update.effective_chat.id
    else:
        chat_id = update.effective_message.chat.id
    user_settings = load_user_settings()
    if str(chat_id) not in user_settings:
        user_settings[str(chat_id)] = {
            "notify_streams": True,
            "notify_price": True,
            "notify_news": True
        }
        save_user_settings(user_settings)
    current = user_settings[str(chat_id)]
    caption = "Настройки уведомлений:\n"
    caption += f"1. Трансляции: {'Вкл' if current['notify_streams'] else 'Выкл'}\n"
    caption += f"2. Цена Rust: {'Вкл' if current['notify_price'] else 'Выкл'}\n"
    caption += f"3. Новости: {'Вкл' if current['notify_news'] else 'Выкл'}\n"
    caption += "Используйте /set_streams, /set_price, /set_news для изменения."
    if isinstance(update, Update):
        await update.effective_message.reply_text(
            text=caption,
            reply_markup=get_back_button()
        )
    else:
        await update.effective_message.reply_text(
            text=caption,
            reply_markup=get_back_button()
        )

# Обработчики для изменения настроек
async def set_streams(update: Update, context: CallbackContext):
    update_stats("set_streams")
    chat_id = update.effective_chat.id
    user_settings = load_user_settings()
    if str(chat_id) not in user_settings:
        user_settings[str(chat_id)] = {
            "notify_streams": True,
            "notify_price": True,
            "notify_news": True
        }
    user_settings[str(chat_id)]["notify_streams"] = not user_settings[str(chat_id)]["notify_streams"]
    save_user_settings(user_settings)
    status = "включены" if user_settings[str(chat_id)]["notify_streams"] else "выключены"
    await update.effective_message.reply_text(
        text=f"Уведомления о трансляциях {status}.",
        reply_markup=get_back_button()
    )

async def set_price(update: Update, context: CallbackContext):
    update_stats("set_price")
    chat_id = update.effective_chat.id
    user_settings = load_user_settings()
    if str(chat_id) not in user_settings:
        user_settings[str(chat_id)] = {
            "notify_streams": True,
            "notify_price": True,
            "notify_news": True
        }
    user_settings[str(chat_id)]["notify_price"] = not user_settings[str(chat_id)]["notify_price"]
    save_user_settings(user_settings)
    status = "включены" if user_settings[str(chat_id)]["notify_price"] else "выключены"
    await update.effective_message.reply_text(
        text=f"Уведомления о цене {status}.",
        reply_markup=get_back_button()
    )

async def set_news(update: Update, context: CallbackContext):
    update_stats("set_news")
    chat_id = update.effective_chat.id
    user_settings = load_user_settings()
    if str(chat_id) not in user_settings:
        user_settings[str(chat_id)] = {
            "notify_streams": True,
            "notify_price": True,
            "notify_news": True
        }
    user_settings[str(chat_id)]["notify_news"] = not user_settings[str(chat_id)]["notify_news"]
    save_user_settings(user_settings)
    status = "включены" if user_settings[str(chat_id)]["notify_news"] else "выключены"
    await update.effective_message.reply_text(
        text=f"Уведомления о новостях {status}.",
        reply_markup=get_back_button()
    )

# Обработчик команды /stats
async def stats(update: Update, context: CallbackContext):
    update_stats("stats")
    stats = load_stats()
    caption = f"Статистика бота:\n"
    caption += f"Пользователей: {stats['users']}\n"
    caption += f"Ошибок: {stats['errors']}\n"
    caption += "Команды:\n"
    for cmd, count in stats["commands"].items():
        caption += f"- {cmd}: {count} раз\n"
    await update.effective_message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик команды /menu
async def menu(update: Update, context: CallbackContext):
    update_stats("menu")
    await update.effective_message.reply_text(
        text="Выберите действие:",
        reply_markup=get_main_menu()
    )

# Обработчик для инструкции по Auto Twitch
async def auto_twitch(update: Update, context: CallbackContext):
    update_stats("auto_twitch")
    query = update.callback_query
    await query.answer()
    caption = (
        "Для автоматического получения дропов используйте расширение 'Auto Twitch: Drops, Моменты и Баллы Канала'.\n"
        "Оно автоматически собирает дропы, баллы и моменты на Twitch, не требуя просмотра стримов.\n"
        "Скачать: https://chromewebstore.google.com/detail/авто-twitch-drops-моменты/kfhgpagdjjoieckminnmigmpeclkdmjm?hl=ru\n"
        "Установите расширение, войдите в свой Twitch-аккаунт и включите автоматический сбор."
    )
    await query.message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик для поддержки
async def support(update: Update, context: CallbackContext):
    update_stats("support")
    query = update.callback_query
    await query.answer()
    caption = "Если вы хотите сообщить об ошибке в работе бота, или вы намерены предложить идею для улучшения функционала, вам сюда -> https://t.me/jurywolw"
    await query.message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )

# Обработчик для калькулятора дропов
async def drop_calc_start(update: Update, context: CallbackContext):
    update_stats("drop_calc")
    logging.info("Начало расчёта дропов")
    try:
        if update.callback_query:
            logging.info("Вызов калькулятора через кнопку")
            query = update.callback_query
            await query.answer()
            message = query.message
        else:
            logging.info("Вызов калькулятора через команду /drop_calc")
            message = update.message
        await message.reply_text(
            text="Введите число часов для расчёта дропов (например, 4):",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Отмена", callback_data='cancel')]
            ])
        )
        return DROP_CALC_HOURS
    except Exception as e:
        logging.error(f"Ошибка в drop_calc_start: {e}")
        stats = load_stats()
        stats["errors"] += 1
        save_stats(stats)
        return ConversationHandler.END

async def drop_calc_hours(update: Update, context: CallbackContext):
    logging.info(f"Получен ввод для калькулятора дропов: {update.effective_message.text}")
    try:
        hours = float(update.effective_message.text)
        if hours <= 0:
            raise ValueError("Число часов должно быть положительным")
    except ValueError as e:
        logging.error(f"Некорректный ввод часов: {update.effective_message.text}, ошибка: {e}")
        await update.effective_message.reply_text(
            text="Пожалуйста, укажите корректное число часов (например, 4).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Отмена", callback_data='cancel')]
            ])
        )
        return DROP_CALC_HOURS
    drops = get_drops()
    if not drops:
        logging.warning("Не удалось загрузить дропы для калькулятора")
        await update.effective_message.reply_text(
            text="Не удалось загрузить дропы. Попробуйте позже.",
            reply_markup=get_back_button()
        )
        return ConversationHandler.END
    caption = f"За {hours} часов вы можете получить:\n"
    found = False
    for drop in drops:
        try:
            drop_hours = float(drop['time'].split()[0]) if drop['time'] != "Не указано" else float('inf')
            if drop_hours <= hours:
                caption += f"- {drop['name']} ({drop['time']})\n"
                found = True
        except ValueError:
            logging.warning(f"Некорректное время дропа: {drop['time']}")
            continue
    if not found:
        caption += "Нет дропов, доступных за указанное время."
    logging.info(f"Расчёт дропов завершён: {caption}")
    await update.effective_message.reply_text(
        text=caption,
        reply_markup=get_back_button()
    )
    return ConversationHandler.END

async def drop_calc_cancel(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    logging.info("Расчёт дропов отменён")
    await query.message.reply_text(
        text="Расчёт дропов отменён.",
        reply_markup=get_back_button()
    )
    return ConversationHandler.END

# Обработчик нажатий на кнопки
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'start':
        await start(update, context)
    elif data == 'check':
        await check_status_command(update, context)
    elif data == 'items':
        await items(update, context)
    elif data == 'price':
        await price(update, context)
    elif data == 'price_history':
        await price_history(update, context)
    elif data == 'streams':
        await streams(update, context)
    elif data == 'news':
        await news(update, context)
    elif data == 'drop_calc':
        return await drop_calc_start(update, context)
    elif data == 'settings':
        await settings(update, context)
    elif data == 'auto_twitch':
        await auto_twitch(update, context)
    elif data == 'support':
        await support(update, context)
    elif data == 'menu':
        await menu(update, context)
    elif data == 'cancel':
        await drop_calc_cancel(update, context)

# Функция для отправки уведомлений

# Очистка временных изображений старше 24 часов
def cleanup_temp_images(context: CallbackContext):
    try:
        import time
        now = time.time()
        if not os.path.isdir(TEMP_IMAGE_DIR):
            return
        removed = 0
        for name in os.listdir(TEMP_IMAGE_DIR):
            path = os.path.join(TEMP_IMAGE_DIR, name)
            try:
                if os.path.isfile(path):
                    mtime = os.path.getmtime(path)
                    if now - mtime > 24*3600:
                        os.remove(path)
                        removed += 1
            except Exception as e:
                logging.error(f"Не удалось удалить временный файл {path}: {e}")
        if removed:
            logging.info(f"Очистка temp_images: удалено файлов: {removed}")
    except Exception as e:
        logging.error(f"Ошибка при очистке temp_images: {e}")

async def send_notification(context: CallbackContext):
    global is_event_live, last_timer_status, last_days
    user_settings = load_user_settings()
    
    # Проверка статуса трансляции
    current_status = check_event_status()
    current_is_live = current_status["status"] == "live"
    if current_is_live and is_event_live is not True:
        for chat_id in user_chat_ids:
            settings = user_settings.get(str(chat_id), {"notify_streams": True})
            if not settings["notify_streams"]:
                continue
            try:
                image_path = get_current_image()
                if current_status["timer"]:
                    caption = f"Началась новая трансляция! Окончится через {current_status['timer']['time']}."
                else:
                    caption = "Началась новая трансляция!"
                if image_path and os.path.exists(image_path):
                    with open(image_path, 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption,
                            reply_markup=get_back_button()
                        )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=get_back_button()
                    )
                logging.info(f"Отправлено уведомление о трансляции пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление пользователю {chat_id}: {e}")
                stats = load_stats()
                stats["errors"] += 1
                save_stats(stats)
        is_event_live = True
    elif not current_is_live and is_event_live is True:
        for chat_id in user_chat_ids:
            settings = user_settings.get(str(chat_id), {"notify_streams": True})
            if not settings["notify_streams"]:
                continue
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Трансляция завершилась.",
                    reply_markup=get_back_button()
                )
                logging.info(f"Отправлено уведомление о завершении трансляции пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление пользователю {chat_id}: {e}")
                stats = load_stats()
                stats["errors"] += 1
                save_stats(stats)
        is_event_live = False
    
    # Проверка таймера (уведомления только при смене дня)
    current_timer = current_status.get("timer")
    if current_timer and current_timer["status"] == "pending":
        current_days = current_timer.get("days", 0)
        if last_days is None or current_days < last_days:
            for chat_id in user_chat_ids:
                settings = user_settings.get(str(chat_id), {"notify_streams": True})
                if not settings["notify_streams"]:
                    continue
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"Новый виток! Трансляция начнётся через {current_timer['time']}.",
                        reply_markup=get_back_button()
                    )
                    logging.info(f"Отправлено уведомление о таймере пользователю {chat_id}")
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление пользователю {chat_id}: {e}")
                    stats = load_stats()
                    stats["errors"] += 1
                    save_stats(stats)
            last_days = current_days
    last_timer_status = current_timer
    
    # Проверка цены
    current_price = get_steam_price()
    last_price = load_price_history()[-1]["price"] if load_price_history() else None
    if current_price and current_price["final_price"] != last_price:
        for chat_id in user_chat_ids:
            settings = user_settings.get(str(chat_id), {"notify_price": True})
            if not settings["notify_price"]:
                continue
            try:
                caption = f"Цена Rust в Steam изменилась! Новая цена: {current_price['final_price']}"
                if "discount" in current_price:
                    caption += f"\nСкидка: {current_price['discount']}\nОригинальная цена: {current_price['original_price']}"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=get_back_button()
                )
                logging.info(f"Отправлено уведомление о цене пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление о цене пользователю {chat_id}: {e}")
                stats = load_stats()
                stats["errors"] += 1
                save_stats(stats)
        save_price_history(current_price)
    
    # Проверка новостей
    current_news = get_news()
    cache = load_cache()
    last_news = cache.get("news", {}).get("data", [])
    if current_news and last_news and current_news[0]["title"] != last_news[0]["title"]:
        for chat_id in user_chat_ids:
            settings = user_settings.get(str(chat_id), {"notify_news": True})
            if not settings["notify_news"]:
                continue
            try:
                caption = f"Новая новость Rust!\n{current_news[0]['title']} ({current_news[0]['date']})\nЧитать: {current_news[0]['url']}"
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=get_back_button()
                )
                logging.info(f"Отправлено уведомление о новости пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление о новости пользователю {chat_id}: {e}")
                stats = load_stats()
                stats["errors"] += 1
                save_stats(stats)

# Функция для отправки изображения при старте бота
async def notify_users_on_startup(application: Application):
    user_settings = load_user_settings()
    if user_chat_ids:
        status = check_event_status()
        image_path = get_current_image()
        for chat_id in user_chat_ids:
            settings = user_settings.get(str(chat_id), {"notify_streams": True})
            if not settings["notify_streams"]:
                continue
            try:
                if status["status"] == "live":
                    if status["timer"]:
                        caption = f"Перезапуск! Трансляция идёт, окончится через {status['timer']['time']}."
                    else:
                        caption = "Перезапуск! Трансляция идёт."
                elif status["status"] == "pending":
                    caption = f"Перезапуск! Трансляция начнётся через {status['timer']['time']}."
                else:
                    caption = "Перезапуск! Трансляций нет."
                if image_path and os.path.exists(image_path):
                    with open(image_path, 'rb') as photo:
                        await application.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption,
                            reply_markup=get_keyboard()
                        )
                else:
                    await application.bot.send_message(
                        chat_id=chat_id,
                        text=caption,
                        reply_markup=get_keyboard()
                    )
                logging.info(f"Отправлено стартовое уведомление пользователю {chat_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить стартовое уведомление пользователю {chat_id}: {e}")
                stats = load_stats()
                stats["errors"] += 1
                save_stats(stats)

# Основная функция запуска бота
def main():
    application = Application.builder().token(TOKEN).build()
    if not application.job_queue:
        raise RuntimeError("JobQueue не инициализирован. Убедитесь, что установлен python-telegram-bot[job-queue].")
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("drop_calc", drop_calc_start),
            CallbackQueryHandler(drop_calc_start, pattern='^drop_calc$')
        ],
        states={
            DROP_CALC_HOURS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, drop_calc_hours),
                CallbackQueryHandler(drop_calc_cancel, pattern='^cancel$')
            ]
        },
        fallbacks=[CallbackQueryHandler(drop_calc_cancel, pattern='^cancel$')]
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("check", check_status_command))
    application.add_handler(CommandHandler("items", items))
    application.add_handler(CommandHandler("price", price))
    application.add_handler(CommandHandler("price_history", price_history))
    application.add_handler(CommandHandler("streams", streams))
    application.add_handler(CommandHandler("news", news))
    application.add_handler(CommandHandler("settings", settings))
    application.add_handler(CommandHandler("set_streams", set_streams))
    application.add_handler(CommandHandler("set_price", set_price))
    application.add_handler(CommandHandler("set_news", set_news))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CallbackQueryHandler(button_callback))
    job_queue = application.job_queue
    job_queue.run_repeating(send_notification, interval=280, first=10)
    job_queue.run_repeating(cleanup_temp_images, interval=24*3600, first=60)
    application.post_init = notify_users_on_startup
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()