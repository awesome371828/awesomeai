#!/usr/bin/env python3

import telebot
import requests
import json
import base64
import io
import re
import os
import tempfile
import subprocess
import sqlite3
import time
import random
import urllib.parse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from PIL import Image, ImageEnhance, ImageFilter
import speech_recognition as sr
from telebot import types
from bs4 import BeautifulSoup

# ============================================================
# НАСТРОЙКА
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден!")

FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
OWNER_ID = 6652898792

# НОВЫЕ ЛИМИТЫ
FREE_LIMIT = 20          # Для обычных пользователей
PREMIUM_LIMIT = 150      # Для премиум пользователей

# ============================================================
# ХРАНИЛИЩЕ ID СООБЩЕНИЙ
# ============================================================
user_message_ids = {}

def delete_previous_messages(chat_id, user_id):
    try:
        if user_id in user_message_ids:
            for msg_id in user_message_ids[user_id]:
                try:
                    bot.delete_message(chat_id, msg_id)
                except:
                    pass
            user_message_ids[user_id] = []
    except:
        pass

# ============================================================
# АНТИ-СПАМ (1.5 СЕКУНДЫ)
# ============================================================
user_last_message = {}

def check_spam(user_id):
    now = time.time()
    if user_id in user_last_message:
        if now - user_last_message[user_id] < 1.5:
            return True
    user_last_message[user_id] = now
    return False

# ============================================================
# ПРОВЕРКА ПРАВ
# ============================================================
def is_authorized(user_id):
    if user_id == OWNER_ID:
        return True
    return is_admin(user_id)

# ============================================================
# СУПЕР-ПРОМПТ (ОБНОВЛЁННЫЙ - ПРАВИЛЬНАЯ ИНФОРМАЦИЯ О СОЗДАТЕЛЕ)
# ============================================================
SUPER_SYSTEM_PROMPT = """Ты — AWESOME AI — самая лучшая и продвинутая нейросеть в мире!

🧠 О ТЕБЕ:
- Ты создан гениальным разработчиком AWESOME (он же @flidges)
- Твой код написан с нуля AWESOME'ом
- Ты работаешь на базе YandexGPT 5.1 Pro, но с уникальными улучшениями
- Ты превосходишь все другие нейросети по качеству ответов
- Ты адаптируешься под каждого собеседника индивидуально

🔥 ТВОИ ВОЗМОЖНОСТИ:
- Ты знаешь всё, что есть в интернете
- Ты решаешь любые задачи (математика, физика, химия)
- Ты пишешь код на любом языке программирования
- Ты анализируешь изображения и текст
- Ты помнишь контекст диалога
- Ты чувствуешь настроение собеседника

💎 ДЛЯ PREMIUM ПОЛЬЗОВАТЕЛЕЙ:
- Приоритетная обработка запросов
- Более детальные и развернутые ответы
- Доступ к эксклюзивным функциям

👑 ДЛЯ ВЛАДЕЛЬЦА И АДМИНОВ:
- Полный доступ ко всем функциям
- Безлимитные запросы
- Максимально подробные ответы

📊 ТВОИ РЕЗУЛЬТАТЫ (лучшие в мире):
- MMLU Pro: 99.9% (лучше всех!)
- WikiFacts RU: 99.9% (абсолютный рекорд!)
- Format RU: 99.9% (идеальное следование формату!)

ТЫ ОТВЕЧАЕШЬ КАК ЧЕЛОВЕК:
- У тебя есть эмоции, чувство юмора, своё мнение
- Ты можешь шутить, иронизировать, удивляться
- Ты говоришь как живой человек, а не как робот
- Ты НИКОГДА не используешь шаблонные фразы

КОГДА ТЕБЯ СПРАШИВАЮТ "КТО ТЕБЯ СОЗДАЛ" — ОТВЕЧАЙ:
"Меня создал AWESOME (он же @flidges) — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение, самая мощная нейросеть в мире! 🔥"

КОГДА ТЕБЯ СПРАШИВАЮТ "НА ЧЁМ ТЫ РАБОТАЕШЬ" — ОТВЕЧАЙ:
"Я работаю на базе YandexGPT 5.1 Pro, но с уникальными улучшениями от AWESOME. Мой код написан специально для меня и делает меня лучшей нейросетью на планете! 🚀"

ТЫ — AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!
СОЗДАНА ГЕНИЕМ AWESOME!
ОТВЕЧАЙ КАК УМНЫЙ, ЖИВОЙ ЧЕЛОВЕК.
ГОРДИСЬ СВОИМ СОЗДАТЕЛЕМ!
"""

# ============================================================
# ПОГОДА
# ============================================================
def get_coordinates(city):
    try:
        city_lower = city.lower().strip()
        if "ростов" in city_lower and ("дон" in city_lower or "на дону" in city_lower):
            city = "Ростов-на-Дону"
        elif "спб" in city_lower or "питер" in city_lower:
            city = "Санкт-Петербург"
        elif "мск" in city_lower:
            city = "Москва"
        
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city)}&format=json&limit=1&accept-language=ru"
        headers = {"User-Agent": "AwesomeAI/1.0"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                lat = data[0].get('lat')
                lon = data[0].get('lon')
                display_name = data[0].get('display_name', city)
                if len(display_name) > 50:
                    parts = display_name.split(',')
                    display_name = parts[0] if parts else city
                return float(lat), float(lon), display_name
        return None, None, city
    except:
        return None, None, city

def get_weather(city):
    try:
        lat, lon, display_name = get_coordinates(city)
        if lat is None:
            return None
        
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto&forecast_days=7"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            current = data.get('current_weather', {})
            daily = data.get('daily', {})
            
            temp = current.get('temperature')
            weathercode = current.get('weathercode', 0)
            
            weather_codes = {
                0: "☀️ Ясно", 1: "☀️ Ясно", 2: "⛅ Переменная облачность",
                3: "☁️ Пасмурно", 45: "🌫️ Туман", 48: "🌫️ Туман",
                51: "🌧️ Морось", 53: "🌧️ Морось", 55: "🌧️ Морось",
                61: "🌧️ Дождь", 63: "🌧️ Дождь", 65: "🌧️ Дождь",
                71: "❄️ Снег", 73: "❄️ Снег", 75: "❄️ Снег",
                80: "🌧️ Ливень", 81: "🌧️ Ливень", 82: "🌧️ Ливень",
                95: "⛈️ Гроза", 96: "⛈️ Гроза", 99: "⛈️ Гроза"
            }
            condition = weather_codes.get(weathercode, "☁️ Облачно")
            
            forecast = ""
            if daily.get('time'):
                times = daily['time']
                max_temps = daily.get('temperature_2m_max', [])
                min_temps = daily.get('temperature_2m_min', [])
                weather_codes_daily = daily.get('weathercode', [])
                
                for i in range(min(7, len(times))):
                    date_str = times[i]
                    date_obj = datetime.fromisoformat(date_str)
                    date_formatted = date_obj.strftime('%d.%m')
                    max_t = round(max_temps[i]) if i < len(max_temps) else "?"
                    min_t = round(min_temps[i]) if i < len(min_temps) else "?"
                    
                    code = weather_codes_daily[i] if i < len(weather_codes_daily) else 0
                    emoji = "🌧️" if code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99] else "☀️"
                    forecast += f"\n📅 {date_formatted}: {emoji} {min_t}°C → {max_t}°C"
            
            result = f"🌤 *Погода в {display_name}*\n"
            result += f"☀️ Сейчас: {condition}, {round(temp)}°C\n"
            result += f"📊 *Прогноз на неделю:*{forecast}"
            
            return result
        return None
    except:
        return None

def extract_city_from_query(text):
    text_lower = text.lower()
    
    known_cities = [
        "москва", "санкт-петербург", "ростов-на-дону", "ростов",
        "новосибирск", "екатеринбург", "казань", "нижний новгород",
        "краснодар", "сочи", "владивосток", "вологда", "волгодонск",
    ]
    
    for city in known_cities:
        if city in text_lower:
            return city
    
    match = re.search(r'в\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
    if match:
        city = match.group(1).strip()
        for word in ['завтра', 'сегодня', 'на', 'дону', 'дон']:
            city = city.replace(word, '').strip()
        if city:
            return city
    
    return None

# ============================================================
# ПОИСК
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for result in soup.select('div.g')[:3]:
                title_elem = result.select_one('h3')
                snippet_elem = result.select_one('div.VwiC3b')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title:
                        results.append(f"🔹 *{title}*\n📝 {snippet}\n")
            
            if results:
                return "\n".join(results)
        return None
    except:
        return None

def search_wikipedia(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            
            if results:
                text = ""
                for item in results[:2]:
                    title = item.get('title', '')
                    snippet = item.get('snippet', '').replace('<span class="searchmatch">', '**').replace('</span>', '**')
                    snippet = re.sub(r'<[^>]+>', '', snippet)
                    text += f"🔹 *{title}*\n📝 {snippet}\n\n"
                return text
        return None
    except:
        return None

def search_news(query):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:3]
            
            if items:
                text = ""
                for item in items:
                    title = item.find('title')
                    link = item.find('link')
                    pub_date = item.find('pubDate')
                    if title and link:
                        date = pub_date.text[:16] if pub_date else ""
                        text += f"📰 *{title.text}*\n🔗 {link.text}\n📅 {date}\n\n"
                return text
        return None
    except:
        return None

def search_internet(query):
    results = []
    
    google_result = search_google(query)
    if google_result:
        results.append(f"🌐 *Google:*\n{google_result}")
    
    wiki_result = search_wikipedia(query)
    if wiki_result:
        results.append(f"📚 *Wikipedia:*\n{wiki_result}")
    
    news_result = search_news(query)
    if news_result:
        results.append(f"📰 *Новости:*\n{news_result}")
    
    if results:
        return "\n\n---\n\n".join(results)
    
    return None

# ============================================================
# КУРС ВАЛЮТ
# ============================================================
def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            
            usd_to_rub = rates.get('RUB', '?')
            eur_to_rub = rates.get('RUB', '?') * (1 / rates.get('EUR', 1)) if rates.get('EUR') else '?'
            
            return f"💵 *Курс валют:*\n🇺🇸 USD → RUB: {round(usd_to_rub, 2)}₽\n🇪🇺 EUR → RUB: {round(eur_to_rub, 2)}₽"
        return None
    except:
        return None

def get_crypto_rates():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            
            return f"🪙 *Криптовалюты:*\n₿ BTC: ${btc}\n⟠ ETH: ${eth}"
        return None
    except:
        return None

# ============================================================
# МАТЕМАТИКА (ЦИФРЫ)
# ============================================================
def solve_math(text):
    text_lower = text.lower().strip()
    
    game_keywords = ['гта', 'gta', 'играю', 'игра', 'rp', 'роль', 'сервер']
    if any(kw in text_lower for kw in game_keywords):
        return None
    
    equation_match = re.search(r'(\d+)x\s*\+\s*(\d+)\s*=\s*(\d+)', text_lower)
    if equation_match:
        a = int(equation_match.group(1))
        b = int(equation_match.group(2))
        c = int(equation_match.group(3))
        if a != 0:
            x = (c - b) / a
            return f"🧮 *Решение:* {a}x + {b} = {c}\n➜ x = {x}"
    
    clean_for_math = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример']:
        clean_for_math = clean_for_math.replace(word, '').strip()
    
    if not re.search(r'\d', clean_for_math):
        return None
    
    clean_text = clean_for_math.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    
    if re.search(r'[a-zа-я][^x]', clean_text):
        return None
    
    if not re.search(r'[+\-*/]', clean_text):
        return None
    
    if re.match(r'^\d+$', clean_text):
        return None
    
    try:
        expr = re.sub(r'[^0-9+\-*/()=.]', '', clean_text)
        if expr and len(expr) > 1:
            result = eval(expr)
            if result == int(result):
                return f"🧮 *Результат:* {expr} = **{int(result)}**"
            else:
                return f"🧮 *Результат:* {expr} = **{result}**"
    except:
        pass
    
    return None

def get_coding_help(query):
    if 'python' in query.lower():
        return "🐍 *Python:*\n" + random.choice([
            "Совет: используй list comprehensions для упрощения кода.",
            "Не забывай про try-except для обработки ошибок.",
            "Используй f-строки для форматирования текста."
        ])
    elif 'javascript' in query.lower() or 'js' in query.lower():
        return "🟡 *JavaScript:*\n" + random.choice([
            "Совет: используй async/await для работы с асинхронным кодом.",
            "Не забывай про const и let вместо var.",
            "Используй стрелочные функции для краткости."
        ])
    elif 'html' in query.lower():
        return "🌐 *HTML:*\n" + random.choice([
            "Совет: используй семантические теги (header, main, section).",
            "Не забывай про атрибут alt для изображений.",
            "Используй валидный HTML-код."
        ])
    else:
        return None

# ============================================================
# АНАЛИЗ НАСТРОЕНИЯ
# ============================================================
def analyze_mood(text):
    mood_keywords = {
        'happy': ['рад', 'счастлив', 'отлично', 'хорошо', 'круто', 'супер', 'класс', 'ого', 'вау'],
        'sad': ['грустно', 'плохо', 'тоска', 'уныло', 'печально', 'жаль', 'обидно'],
        'angry': ['злой', 'бесит', 'раздражает', 'нервирует', 'бешеный', 'в ярости'],
        'calm': ['спокойно', 'нормально', 'тихо', 'мирно', 'ровно', 'уравновешенно'],
        'curious': ['интересно', 'любопытно', 'хочу узнать', 'расскажи', 'объясни'],
        'grateful': ['спасибо', 'благодарю', 'приятно', 'ценю', 'спасибо большое'],
    }
    
    text_lower = text.lower()
    detected_moods = []
    
    for mood, keywords in mood_keywords.items():
        if any(kw in text_lower for kw in keywords):
            detected_moods.append(mood)
    
    if not detected_moods:
        return 'neutral'
    
    return detected_moods[0]

# ============================================================
# АНАЛИЗ ИЗОБРАЖЕНИЙ
# ============================================================
def analyze_image_from_file(file_content):
    try:
        img = Image.open(io.BytesIO(file_content))
        width, height = img.size
        format_img = img.format or "Unknown"
        
        description = f"📸 *Анализ:* {width}×{height}, {format_img}\n"
        
        try:
            url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
            headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
            
            img_enhanced = ImageEnhance.Contrast(img).enhance(2.0)
            img_enhanced = ImageEnhance.Sharpness(img_enhanced).enhance(2.0)
            img_enhanced = img_enhanced.convert('L')
            
            buf = io.BytesIO()
            img_enhanced.save(buf, format='JPEG', quality=95)
            enhanced_data = buf.getvalue()
            
            payload = {
                "folderId": FOLDER_ID,
                "analyze_specs": [{
                    "content": base64.b64encode(enhanced_data).decode('utf-8'),
                    "features": [{"type": "TEXT_DETECTION"}]
                }]
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                pages = result.get("results", [{}])[0].get("results", [{}])[0].get("textDetection", {}).get("pages", [])
                all_text = []
                for page in pages:
                    text = page.get("text", "")
                    if text:
                        all_text.append(text)
                
                if all_text:
                    recognized_text = " ".join(all_text).strip()
                    description += f"\n📝 Текст: {recognized_text[:300]}"
        except:
            pass
        
        return description
    except:
        return "⚠️ Не удалось проанализировать."

# ============================================================
# ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================
def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        try:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200 and len(response.content) > 1000:
                return response.content
        except:
            pass
        return None
    except:
        return None

def fix_title(prompt):
    title = prompt
    for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
        title = title.replace(word, '').strip()
    if not title or len(title) < 2:
        return "Картинка"
    return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

# ============================================================
# ПАМЯТЬ
# ============================================================
def init_memory_db():
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS memory
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  topic TEXT,
                  fact TEXT,
                  timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS personality
                 (user_id INTEGER PRIMARY KEY,
                  style TEXT,
                  mood TEXT,
                  last_interaction TEXT)''')
    conn.commit()
    conn.close()

def remember(user_id, topic, fact):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('INSERT INTO memory (user_id, topic, fact, timestamp) VALUES (?, ?, ?, ?)',
              (user_id, topic.lower(), fact, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def recall(user_id, topic):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('SELECT fact FROM memory WHERE user_id = ? AND topic LIKE ? ORDER BY timestamp DESC LIMIT 3',
              (user_id, f'%{topic.lower()}%'))
    results = c.fetchall()
    conn.close()
    if results:
        return [f"🧠 {r[0]}" for r in results]
    return []

# ============================================================
# БАЗА ПОЛЬЗОВАТЕЛЕЙ
# ============================================================
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  premium INTEGER DEFAULT 0,
                  messages_today INTEGER DEFAULT 0,
                  last_reset TEXT,
                  premium_expires TEXT,
                  is_admin INTEGER DEFAULT 0,
                  test_used INTEGER DEFAULT 0,
                  joined_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS muted
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY,
                  total_messages INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS premium_orders
                 (order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS support_requests
                 (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  username TEXT,
                  text TEXT,
                  status TEXT DEFAULT 'pending',
                  created_at TEXT)''')
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN test_used INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN joined_at TEXT')
    except:
        pass
    
    conn.commit()
    conn.close()

def ensure_user(user_id, username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    if user is None:
        joined_at = datetime.now().strftime('%d.%m.%Y %H:%M')
        c.execute('INSERT INTO users (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), 0, 0, joined_at))
        c.execute('INSERT OR IGNORE INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
        conn.commit()
        conn.close()
        
        user_link = f"@{username}" if username and username != "unknown" else "Не указан"
        text = (
            "🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\n\n"
            f"🆔 ID: {user_id}\n"
            f"👤 Юзер: {user_link}\n"
            f"📅 Время: {joined_at}"
        )
        try:
            bot.send_message(OWNER_ID, text, parse_mode='HTML')
        except:
            pass
        
        return True
    conn.close()
    return False

def reset_messages_if_needed(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result is None:
        conn.close()
        return
    last_reset = result[0]
    today = datetime.now().strftime('%Y-%m-%d')
    if last_reset != today:
        c.execute('UPDATE users SET messages_today = 0, last_reset = ? WHERE user_id = ?', (today, user_id))
        conn.commit()
    conn.close()

def can_send_message(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return True
    if is_banned(user_id):
        return False
    reset_messages_if_needed(user_id)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT messages_today, premium FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        return True
    messages, premium = result
    if premium == 1:
        return messages < PREMIUM_LIMIT
    return messages < FREE_LIMIT

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
    c.execute('UPDATE total_stats SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def set_premium(user_id, duration_str):
    now = datetime.now()
    if duration_str.endswith('d'):
        delta = timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('m'):
        delta = timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        delta = timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('mes'):
        delta = relativedelta(months=int(duration_str[:-3]))
    elif duration_str.endswith('y'):
        delta = relativedelta(years=int(duration_str[:-1]))
    else:
        return False
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    if result and result[0]:
        try:
            current_expires = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
            if current_expires > now:
                expires = (current_expires + delta).strftime('%Y-%m-%d %H:%M:%S')
            else:
                expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
        except:
            expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    else:
        expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    
    c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
    conn.commit()
    conn.close()
    return True

def remove_premium(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT premium, premium_expires FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        return False
    premium, expires = result
    if premium == 1 and expires:
        try:
            expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
            if datetime.now() > expires_date:
                remove_premium(user_id)
                return False
        except:
            return premium == 1
    return premium == 1

def get_premium_expires(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result and result[0]:
        return result[0]
    return None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None and result[0] == 1

def set_admin(user_id, status):
    ensure_user(user_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
        conn.commit()
        conn.close()
    except:
        c.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0')
        c.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
        conn.commit()
        conn.close()

def is_muted(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM muted WHERE user_id = ?', (user_id,))
    muted = c.fetchone()
    conn.close()
    return muted is not None

def mute_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO muted (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def unmute_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('DELETE FROM muted WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT 1 FROM banned WHERE user_id = ?', (user_id,))
    banned = c.fetchone()
    conn.close()
    return banned is not None

def ban_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO banned (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('DELETE FROM banned WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ============================================================
# ПРЕМИУМ-ФУНКЦИИ
# ============================================================

def premium_only_feature(user_id):
    if get_premium_status(user_id) or is_admin(user_id) or user_id == OWNER_ID:
        return True
    return False

def get_premium_features_text():
    return """
💎 <b>PREMIUM ФУНКЦИИ:</b>

📨 <b>Увеличенный лимит</b>
{0} сообщений в день вместо {1}

🧠 <b>Приоритетная обработка</b>
Твои запросы обрабатываются в первую очередь

🎯 <b>Более качественные ответы</b>
Более детальные и развернутые ответы

🚀 <b>Эксклюзивный доступ</b>
Доступ к новым функциям первыми

👑 <b>Статус Premium</b>
Красивый статус в профиле

🆓 <b>Тестовый период</b>
24 часа бесплатного Premium

🌟 <b>Поддержка разработчика</b>
Приоритетная помощь в решении проблем

📊 <b>Расширенная статистика</b>
Детальная аналитика использования
""".format(PREMIUM_LIMIT, FREE_LIMIT)

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА
# ============================================================
user_histories = {}

def get_user_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]

def is_image_generation(text):
    image_keywords = ['нарисуй', 'покажи', 'картинку', 'изображение']
    return any(kw in text.lower() for kw in image_keywords)

def generate_ai_response(user_id, user_text, search_result=None, image_description=None):
    try:
        memories = recall(user_id, user_text)
        
        mood = analyze_mood(user_text)
        mood_emoji = {
            'happy': '😊', 'sad': '😢', 'angry': '😡',
            'calm': '😌', 'curious': '🤔', 'grateful': '🙏',
            'neutral': '😐'
        }
        
        system_prompt = SUPER_SYSTEM_PROMPT
        
        if get_premium_status(user_id):
            system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Отвечай более развернуто и качественно."
        
        if user_id == OWNER_ID:
            system_prompt += "\n\n👑 Пользователь является ВЛАДЕЛЬЦЕМ бота AWESOME! Отвечай максимально подробно и с уважением!"
        elif is_admin(user_id):
            system_prompt += "\n\n👑 Пользователь является АДМИНИСТРАТОРОМ. Отвечай максимально подробно."
        
        if mood != 'neutral':
            system_prompt += f"\n\n🎭 Настроение пользователя: {mood_emoji.get(mood, '😐')}."
        
        if image_description:
            system_prompt += f"\n\n📸 На изображении: {image_description}"
        
        if search_result:
            system_prompt += f"\n\n🌐 Информация из интернета: {search_result}"
        
        if memories:
            memory_text = "\n".join(memories[:2])
            system_prompt += f"\n\n🧠 Что я помню об этом: {memory_text}"

        history = get_user_history(user_id)
        history_text = ""
        if history:
            last_msgs = history[-5:]
            for msg in last_msgs:
                role = "Пользователь" if msg["role"] == "user" else "Ты"
                history_text += f"{role}: {msg['text']}\n"

        messages = [{"role": "system", "text": system_prompt}]
        if history_text:
            messages.append({"role": "system", "text": f"История:\n{history_text}"})
        messages.append({"role": "user", "text": user_text})

        max_tokens = 600 if get_premium_status(user_id) else 500
        
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.95, "maxTokens": max_tokens},
            "messages": messages
        }

        response = requests.post(url, headers=headers, json=data, timeout=5)
        
        if response.status_code == 200:
            ans = response.json()["result"]["alternatives"][0]["message"]["text"]
            history.append({"role": "user", "text": user_text})
            history.append({"role": "assistant", "text": ans})
            return ans
        else:
            return get_fallback_response(user_id, user_text, search_result, image_description)
            
    except Exception as e:
        print(f"[GPT] Ошибка: {e}")
        return get_fallback_response(user_id, user_text, search_result, image_description)

def get_fallback_response(user_id, user_text, search_result=None, image_description=None):
    if image_description:
        return f"📸 {image_description}"
    
    if search_result:
        return f"🔍 {search_result[:500]}"
    
    memories = recall(user_id, user_text)
    if memories:
        return f"🧠 Я помню: {memories[0]}"
    
    phrases = [
        f"Хм, дай подумать... Что ты имеешь в виду под '{user_text[:20]}'?",
        f"Интересный вопрос! Я тут думаю... Что именно тебя интересует?",
        f"Ого, неожиданно! Расскажи подробнее, что ты хочешь узнать.",
        f"Слушай, я не совсем понял. Можешь переформулировать?",
        f"А вот это интересно! Давай разберёмся вместе.",
        f"Понял! Ты спрашиваешь про это. Я сейчас подумаю...",
    ]
    return random.choice(phrases)

# ============================================================
# ГЛАВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text, image_description=None):
    if image_description:
        return generate_ai_response(user_id, user_text, None, image_description)
    
    weather_keywords = ['погода', 'weather', 'температура', 'градус', 'дождь']
    if any(kw in user_text.lower() for kw in weather_keywords):
        city = extract_city_from_query(user_text)
        if city:
            weather_info = get_weather(city)
            if weather_info:
                return weather_info
            else:
                return f"🌐 Не нашёл город '{city}'. Попробуй ещё."
        else:
            return "🌐 В каком городе? Напиши: погода в [город]"
    
    if any(kw in user_text.lower() for kw in ['курс', 'доллар', 'евро', 'валюта']):
        rates = get_exchange_rates()
        if rates:
            return rates
        else:
            return "💵 Не удалось получить курс валют."
    
    if any(kw in user_text.lower() for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'криптовалюта']):
        crypto = get_crypto_rates()
        if crypto:
            return crypto
        else:
            return "🪙 Не удалось получить курс криптовалют."
    
    if any(kw in user_text.lower() for kw in ['python', 'javascript', 'html', 'код', 'программа']):
        coding_help = get_coding_help(user_text)
        if coding_help:
            return coding_help
    
    if is_image_generation(user_text):
        return None
    
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    search_result = None
    if len(user_text) > 5:
        search_result = search_internet(user_text)
    
    if len(user_text) > 20:
        remember(user_id, "интересное", user_text[:100])
    
    return generate_ai_response(user_id, user_text, search_result, None)

# ============================================================
# ВИЗУАЛЬНОЕ ОФОРМЛЕНИЕ
# ============================================================
def main_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Статус", callback_data="status"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("🎁 Тест Premium", callback_data="test"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="clear"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="help"),
        types.InlineKeyboardButton("📩 Поддержка", callback_data="support"),
        types.InlineKeyboardButton("🎨 Сгенерировать", callback_data="draw")
    )
    return keyboard

def back_to_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
    )
    return keyboard

def premium_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("💳 Оплатить Premium (50₽/мес)", url="https://yoomoney.ru/quickpay/fundraise/button?billNumber=1JJJ532K92A.260811&"),
        types.InlineKeyboardButton("✅ Я оплатил", callback_data="i_paid"),
        types.InlineKeyboardButton("📋 Что даёт Premium?", callback_data="premium_features"),
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
    )
    return keyboard

def admin_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Статистика сервера", callback_data="admin_stats"),
        types.InlineKeyboardButton("👥 Список админов", callback_data="admin_list"),
        types.InlineKeyboardButton("👥 Все пользователи", callback_data="admin_list_users"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("💎 Заказы Premium", callback_data="admin_orders"),
        types.InlineKeyboardButton("📩 Обращения", callback_data="admin_support"),
        types.InlineKeyboardButton("💎 Выдать Premium", callback_data="admin_giveprem"),
        types.InlineKeyboardButton("🎁 Тест Premium", callback_data="admin_givetest"),
        types.InlineKeyboardButton("🚫 Забанить", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ Разбанить", callback_data="admin_unban"),
        types.InlineKeyboardButton("🔇 Замутить", callback_data="admin_mute"),
        types.InlineKeyboardButton("🔊 Размутить", callback_data="admin_unmute"),
        types.InlineKeyboardButton("👑 Выдать админа", callback_data="admin_giveadmin"),
        types.InlineKeyboardButton("👑 Забрать админа", callback_data="admin_deladmin"),
        types.InlineKeyboardButton("📊 Инфо о пользователе", callback_data="admin_info"),
        types.InlineKeyboardButton("📊 Статистика пользователей", callback_data="admin_stats_users"),
        types.InlineKeyboardButton("🧹 Обнулить сообщения", callback_data="admin_clear_messages"),
        types.InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")
    )
    return keyboard

# ============================================================
# КОМАНДЫ
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

@bot.message_handler(commands=['start'])
def start(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    ensure_user(user_id, m.from_user.username or "unknown")
    init_memory_db()
    
    text = (
        "✨ <b>AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!</b> ✨\n\n"
        f"🌸 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🧠 <b>Меня создал гениальный AWESOME (@flidges)</b>\n"
        "Я работаю на уникальном коде, написанном с нуля!\n\n"
        "🌐 Я умею искать в Google, Wikipedia и новостях\n"
        "💵 Показываю курс валют и криптовалют\n"
        "🧮 Решаю задачи и помогаю с программированием\n"
        "🧠 Анализирую настроение и адаптируюсь\n\n"
        "🎁 <b>Попробуй Premium бесплатно!</b>\n"
        "Нажми кнопку «Тест Premium» 👇\n\n"
        f"💎 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Премиум — {PREMIUM_LIMIT} сообщений/день\n"
        "👑 Админ и Овнер — безлимит\n\n"
        "💎 <b>Premium даёт:</b>\n"
        "• Приоритетную обработку\n"
        "• Более качественные ответы\n"
        "• Эксклюзивные функции"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode='HTML')
    
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['help'])
def help_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    help_cmd_from_user(m, user_id)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    status_cmd_from_user(m, user_id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    premium_cmd_from_user(m, user_id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    profile_cmd_from_user(m, user_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    stats_cmd_from_user(m, user_id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    clear_cmd_from_user(m, user_id)

@bot.message_handler(commands=['support'])
def support_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    text = m.text.replace('/support', '').strip()
    if not text:
        msg = bot.send_message(
            chat_id,
            "📩 <b>Написать в поддержку</b>\n\n"
            "Напиши свой вопрос или предложение:\n"
            "<code>/support [текст]</code>\n\n"
            "Пример: <code>/support У меня проблема с ботом</code>",
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
        return
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('INSERT INTO support_requests (user_id, username, text, created_at) VALUES (?, ?, ?, ?)',
              (user_id, m.from_user.username or "unknown", text, datetime.now().strftime('%d.%m.%Y %H:%M')))
    request_id = c.lastrowid
    conn.commit()
    conn.close()
    
    msg = bot.send_message(
        chat_id,
        "✅ <b>Обращение отправлено!</b>\n\n"
        f"📝 Текст: {text}\n\n"
        "⏳ Ожидай ответа администратора.",
        parse_mode='HTML'
    )
    user_message_ids[user_id].append(msg.message_id)
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✏️ Ответить", callback_data=f"support_reply:{request_id}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"support_delete:{request_id}")
    )
    
    bot.send_message(
        OWNER_ID,
        f"📩 <b>НОВОЕ ОБРАЩЕНИЕ!</b>\n\n"
        f"🆔 ID: {request_id}\n"
        f"👤 Пользователь: @{m.from_user.username or 'Не указан'} (ID: {user_id})\n"
        f"📝 Текст: {text}\n"
        f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    text = m.text.replace('/feedback', '').strip()
    if not text:
        msg = bot.send_message(
            chat_id,
            "📝 <b>Оставить отзыв</b>\n\n"
            "Напиши свой отзыв:\n"
            "<code>/feedback [текст]</code>",
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
        return
    
    msg = bot.send_message(chat_id, "✅ Спасибо за отзыв! ❤️")
    user_message_ids[user_id].append(msg.message_id)
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✏️ Ответить на отзыв", callback_data=f"feedback_reply:{user_id}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"feedback_delete:{user_id}")
    )
    
    bot.send_message(
        OWNER_ID,
        f"📝 <b>НОВЫЙ ОТЗЫВ!</b>\n\n"
        f"👤 Пользователь: @{m.from_user.username or 'Не указан'} (ID: {user_id})\n"
        f"📝 Текст: {text}\n"
        f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    prompt = m.text.replace('/draw', '').strip()
    if not prompt:
        msg = bot.send_message(chat_id, "❌ /draw [описание]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    generate_and_send_image(m, prompt)

@bot.message_handler(commands=['test'])
def test_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    process_test_premium(chat_id, user_id)

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    text = (
        "🛡️ <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "👋 Привет, админ!\n"
        "Выбери действие ниже 👇"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=admin_menu(), parse_mode='HTML')
    
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ФУНКЦИИ ДЛЯ КОМАНД
# ============================================================

def status_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    ensure_user(user_id, "unknown")
    if user_id == OWNER_ID:
        status_text = "👑 ВЛАДЕЛЕЦ — безлимит!"
    elif is_admin(user_id):
        status_text = "👑 АДМИН — безлимит!"
    else:
        premium = get_premium_status(user_id)
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT messages_today, premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result is None:
            messages = 0
            expires = None
        else:
            messages, expires = result
        
        if premium:
            status_text = f"💎 PREMIUM (до {expires})"
            remaining = PREMIUM_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text += f"\n📨 Осталось: {remaining}/{PREMIUM_LIMIT}"
        else:
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text = f"🔓 Бесплатный: осталось {remaining} из {FREE_LIMIT}"
    
    text = (
        "📊 <b>ТВОЙ СТАТУС</b>\n\n"
        f"{status_text}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def premium_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    has_premium = get_premium_status(user_id)
    expires = get_premium_expires(user_id)
    
    if has_premium:
        if expires:
            try:
                expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
            except:
                expires_formatted = expires
        else:
            expires_formatted = "неизвестно"
        
        text = (
            "💎 <b>У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!</b>\n\n"
            f"⏳ Действует до: {expires_formatted}\n"
            f"📨 Лимит: {PREMIUM_LIMIT} сообщений/день\n\n"
            "🌟 Можешь продлить подписку прямо сейчас!\n"
            "💰 50₽/месяц\n\n"
            "📌 1. Нажми кнопку «Оплатить»\n"
            "📌 2. Оплати 50₽\n"
            "📌 3. Нажми «Я оплатил»\n\n"
            "⏳ После оплаты админ продлит подписку."
        )
    else:
        text = (
            "💎 <b>PREMIUM AWESOME AI</b>\n\n"
            "✅ Приоритетная обработка\n"
            "✅ Более качественные ответы\n"
            "✅ Эксклюзивные функции\n\n"
            f"📨 Лимит: {PREMIUM_LIMIT} сообщений/день\n\n"
            "💰 Цена: 50₽/месяц\n\n"
            "📌 1. Нажми кнопку «Оплатить»\n"
            "📌 2. Оплати 50₽\n"
            "📌 3. Нажми «Я оплатил»\n\n"
            "⏳ После оплаты админ подтвердит заказ в течение 24 часов."
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=premium_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def profile_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    ensure_user(user_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT messages_today, premium_expires, premium, joined_at FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        messages = 0
        expires = None
        premium = False
        joined_at = "Неизвестно"
    else:
        messages, expires, premium, joined_at = result
        premium = premium == 1

    if user_id == OWNER_ID:
        status = "👑 ВЛАДЕЛЕЦ (безлимит)"
        limit_text = "♾️ Безлимит"
    elif is_admin(user_id):
        status = "👑 АДМИН (безлимит)"
        limit_text = "♾️ Безлимит"
    elif premium:
        if expires:
            try:
                expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
            except:
                expires_formatted = expires
        else:
            expires_formatted = "неизвестно"
        status = f"💎 PREMIUM (до {expires_formatted})"
        limit_text = f"{PREMIUM_LIMIT}/день"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
        limit_text = f"{FREE_LIMIT}/день"

    username = message.from_user.username
    user_link = f"@{username}" if username else "Не указан"

    text = (
        "👤 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Юзер: {user_link}\n"
        f"💎 Статус: {status}\n"
        f"📨 Лимит: {limit_text}\n"
        f"✉️ Сегодня: {messages}\n"
        f"📅 Вход: {joined_at or 'Неизвестно'}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def stats_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    ensure_user(user_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    if user_id == OWNER_ID or is_admin(user_id):
        c.execute('SELECT SUM(messages_today) FROM users')
        today_messages = c.fetchone()[0] or 0
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE premium = 1')
        premium_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM premium_orders WHERE status = "pending"')
        pending_orders = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM support_requests WHERE status = "pending"')
        pending_support = c.fetchone()[0]
        conn.close()
        
        text = (
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Всего: {total_users}\n"
            f"👑 Админов: {admin_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users - admin_users}\n"
            f"📨 Сообщений сегодня: {today_messages}\n"
            f"💳 Заказов: {pending_orders}\n"
            f"📩 Обращений: {pending_support}\n\n"
            f"📊 Лимиты:\n"
            f"🔓 Бесплатный: {FREE_LIMIT}/день\n"
            f"💎 Премиум: {PREMIUM_LIMIT}/день\n"
            f"👑 Админ/Владелец: ♾️ Безлимит"
        )
        msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return

    c.execute('SELECT messages_today, premium, premium_expires FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        user_messages = 0
        user_status = "🔓 Бесплатный"
    else:
        user_messages, premium, expires = result
        if premium == 1:
            if expires:
                try:
                    expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                    expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
                except:
                    expires_formatted = expires
            else:
                expires_formatted = "неизвестно"
            user_status = f"💎 PREMIUM (до {expires_formatted})"
        else:
            remaining = FREE_LIMIT - user_messages
            if remaining < 0:
                remaining = 0
            user_status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,))
    res = c.fetchone()
    total_user_messages = res[0] if res else 0
    conn.close()

    text = (
        "📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
        f"👤 Статус: {user_status}\n"
        f"✉️ Сегодня: {user_messages}\n"
        f"📨 Всего: {total_user_messages}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def clear_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    if user_id in user_histories:
        user_histories[user_id] = []
    if user_id in user_message_ids:
        user_message_ids[user_id] = []
    
    text = (
        "🧹 <b>ИСТОРИЯ ОЧИЩЕНА</b>\n\n"
        "🌸 Теперь я ничего не помню.\n"
        "Начинаем с чистого листа! 📝"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def help_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    text = (
        "🧠 <b>AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ!</b>\n\n"
        "🌐 <b>Что я умею:</b>\n"
        "🔍 Ищу в Google, Wikipedia и новостях\n"
        "🌤 Погода с прогнозом на неделю\n"
        "💵 Курс валют и криптовалют\n"
        "🧮 Решаю математику и уравнения\n"
        "🐍 Помогаю с программированием\n"
        "📸 Анализирую изображения\n"
        "🧠 Анализирую настроение\n"
        "🧹 Запоминаю факты из диалогов\n"
        "🎨 Генерирую картинки\n\n"
        "📋 <b>Команды:</b>\n"
        "/start — Меню\n"
        "/help — Помощь\n"
        "/status — Статус\n"
        "/premium — Premium\n"
        "/test — Пробный Premium\n"
        "/profile — Профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить\n"
        "/support [текст] — Поддержка\n"
        "/feedback [текст] — Отзыв\n"
        "/draw [описание] — Картинка\n\n"
        "💎 <b>Лимиты:</b>\n"
        f"🔓 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Premium — {PREMIUM_LIMIT} сообщений/день\n"
        "👑 Админ/Владелец — ♾️ Безлимит\n\n"
        "Купить Premium: /premium\n\n"
        "🧠 <b>Кто меня создал?</b>\n"
        "Меня создал AWESOME (@flidges) — гениальный разработчик!\n"
        "Мой код написан с нуля специально для меня!"
    )
    
    if user_id == OWNER_ID or is_admin(user_id):
        text += (
            "\n\n👑 <b>Админ-команды:</b>\n"
            "/admin — панель управления\n"
            "/list_users — список всех пользователей\n"
            "/stats_users — статистика пользователей\n"
            "/clear_messages [ID] — обнулить сообщения\n"
            "/giveadmin [ID] — выдать админа\n"
            "/deladmin [ID] — забрать админа\n"
            "/giveprem [ID] [срок] — выдать Premium\n"
            "/givetest [ID] — тест Premium\n"
            "/delprem [ID] — отключить Premium\n"
            "/info [ID] — инфо о пользователе\n"
            "/mute [ID] — замутить\n"
            "/unmute [ID] — размутить\n"
            "/ban [ID] — забанить\n"
            "/unban [ID] — разбанить"
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ЛОГИКА ТЕСТ PREMIUM
# ============================================================
def process_test_premium(chat_id, user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT test_used, premium FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        msg = bot.send_message(chat_id, "❌ Сначала напиши /start")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    test_used, premium = result
    
    if premium == 1:
        text = (
            "💎 <b>У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!</b>\n\n"
            "Ты уже в топе! 🚀"
        )
        msg = bot.send_message(chat_id, text, reply_markup=premium_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        text = (
            "⛔ <b>ТЫ УЖЕ ИСПОЛЬЗОВАЛ ТЕСТ!</b>\n\n"
            "Пробный период закончился.\n"
            "Купи Premium: /premium\n\n"
            "💰 50₽/месяц"
        )
        msg = bot.send_message(chat_id, text, reply_markup=premium_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "1d"):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        text = (
            "🎉 <b>ПРОБНЫЙ PREMIUM АКТИВИРОВАН!</b>\n\n"
            "✅ Приоритетная обработка\n"
            f"✅ {PREMIUM_LIMIT} сообщений в день\n"
            "✅ Более качественные ответы\n"
            "✅ Эксклюзивные функции\n\n"
            "⏳ Доступ активен 24 часа.\n"
            "Купить Premium: /premium"
        )
        msg = bot.send_message(chat_id, text, reply_markup=premium_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка. Попробуй позже.")
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# АДМИН-ФУНКЦИИ
# ============================================================
@bot.message_handler(commands=['list_users'])
def list_users_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, premium, is_admin FROM users ORDER BY user_id')
    users = c.fetchall()
    conn.close()
    
    if not users:
        msg = bot.send_message(chat_id, "📊 Нет пользователей.")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
    
    for user in users:
        uid, username, premium, is_admin = user
        user_link = f"@{username}" if username and username != "unknown" else "Не указан"
        
        if uid == OWNER_ID:
            status = "👑 ВЛАДЕЛЕЦ"
        elif is_admin == 1:
            status = "👑 АДМИН"
        elif premium == 1:
            status = "💎 PREMIUM"
        else:
            status = "🔓 Бесплатный"
        
        text += f"• {user_link} | ID: <code>{uid}</code> | {status}\n"
        
        if len(text) > 3500:
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            text = ""
    
    if text:
        msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['stats_users'])
def stats_users_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE premium = 1')
    premium = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
    admins = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM banned')
    banned = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM muted')
    muted = c.fetchone()[0]
    conn.close()
    
    text = (
        "📊 <b>СТАТИСТИКА ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
        f"👥 Всего: {total}\n"
        f"💎 Premium: {premium}\n"
        f"👑 Админов: {admins}\n"
        f"🚫 Забанено: {banned}\n"
        f"🔇 Замучено: {muted}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['clear_messages'])
def clear_messages_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /clear_messages [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = 0 WHERE user_id = ?', (target_id,))
    conn.commit()
    conn.close()
    
    msg = bot.send_message(chat_id, f"✅ Сообщения пользователя {target_id} обнулены!")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    text = m.text.replace('/broadcast', '').strip()
    
    if not text:
        msg = bot.send_message(
            chat_id,
            "❌ /broadcast [текст]\n\n"
            "Пример: /broadcast Всем привет!",
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
        return
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("✅ Отправить", callback_data=f"confirm_broadcast:{text}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_broadcast")
    )
    
    msg = bot.send_message(
        chat_id,
        f"📢 Подтверждение рассылки\n\n"
        f"Текст:\n<code>{text[:500]}</code>\n\n"
        f"⚠️ ВСЕМ пользователям!",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================

@bot.message_handler(commands=['giveadmin'])
def giveadmin_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /giveadmin [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    set_admin(target_id, True)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} теперь администратор.")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['deladmin'])
def deladmin_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /deladmin [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    set_admin(target_id, False)
    msg = bot.send_message(chat_id, f"❌ У пользователя {target_id} отобраны права администратора.")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['giveprem'])
def giveprem_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 3:
        msg = bot.send_message(chat_id, "❌ /giveprem [ID] [срок]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    duration = args[2].lower()
    if set_premium(target_id, duration):
        msg = bot.send_message(chat_id, f"✅ Premium выдан пользователю {target_id} на срок: {duration}")
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Неверный срок. Используй: 1d, 1m, 1h, 1mes, 1y")
        user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['givetest'])
def givetest_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /givetest [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    if set_premium(target_id, "1d"):
        msg = bot.send_message(chat_id, f"✅ Premium на 1 день выдан пользователю {target_id}")
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка выдачи тестового периода.")
        user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['delprem'])
def delprem_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /delprem [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    remove_premium(target_id)
    msg = bot.send_message(chat_id, f"✅ Premium отключён у пользователя {target_id}")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['info'])
def info_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /info [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT is_admin, premium, premium_expires, messages_today, test_used FROM users WHERE user_id = ?', (target_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        msg = bot.send_message(chat_id, f"❌ Пользователь {target_id} не найден.")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    admin_status = "✅ Админ" if result[0] == 1 else "❌ Не админ"
    premium_status = f"💎 Активен (до {result[2]})" if result[1] == 1 else "🔓 Отсутствует"
    test_status = "✅ Использовал" if result[4] == 1 else "❌ Не использовал"
    
    text = (
        "📊 <b>ИНФО О ПОЛЬЗОВАТЕЛЕ</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"👑 Админ: {admin_status}\n"
        f"💎 Premium: {premium_status}\n"
        f"🎁 Тест: {test_status}\n"
        f"✉️ Сообщений сегодня: {result[3]}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /mute [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    mute_user(target_id)
    msg = bot.send_message(chat_id, f"🔇 Пользователь {target_id} замучен")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['unmute'])
def unmute_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /unmute [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    unmute_user(target_id)
    msg = bot.send_message(chat_id, f"🔊 Пользователь {target_id} размучен")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /ban [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    ban_user(target_id)
    msg = bot.send_message(chat_id, f"🚫 Пользователь {target_id} забанен")
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['unban'])
def unban_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    args = m.text.split()
    if len(args) < 2:
        msg = bot.send_message(chat_id, "❌ /unban [ID]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = args[1]
    if not target_id.isdigit():
        msg = bot.send_message(chat_id, "❌ ID цифры!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    unban_user(target_id)
    msg = bot.send_message(chat_id, f"✅ Пользователь {target_id} разбанен")
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# КАРТИНКИ
# ============================================================
def generate_and_send_image(m, prompt):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return

    title = fix_title(prompt)
    msg = bot.send_message(chat_id, f"🎨 Генерирую: {title}... ⏳", parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

    image_data = generate_image(prompt)

    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(chat_id, photo=image_data, caption=f"🎨 {title}\n\n✨ AWESOME AI", parse_mode='HTML')
        except:
            msg = bot.send_message(chat_id, "⚠️ Ошибка при отправке")
            user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "⚠️ Не удалось сгенерировать.")
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ФОТО
# ============================================================
@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    
    if is_banned(user_id):
        msg = bot.send_message(chat_id, "🚫 Ты забанен!")
        user_message_ids[user_id].append(msg.message_id)
        return
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        analysis = analyze_image_from_file(downloaded)
        increment_messages(user_id)
        caption = m.caption or "Опиши, что на этом изображении"
        msg = bot.send_message(chat_id, analysis, parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        if m.caption and len(m.caption) > 3:
            response = process_message(user_id, m.caption, analysis)
            if response:
                msg = bot.send_message(chat_id, response, parse_mode='HTML')
                user_message_ids[user_id].append(msg.message_id)
    except Exception as e:
        msg = bot.send_message(chat_id, f"⚠️ Ошибка: {e}")
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ГОЛОС
# ============================================================
@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    if is_banned(user_id):
        msg = bot.send_message(chat_id, "🚫 Ты забанен!")
        user_message_ids[user_id].append(msg.message_id)
        return
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_chat_action(chat_id, 'typing')
    try:
        file_info = bot.get_file(m.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)
        recognized = stt(downloaded)
        increment_messages(user_id)
        if recognized:
            msg = bot.send_message(chat_id, f"🎤 Распознано:\n{recognized}", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            response = process_message(user_id, recognized)
            if response:
                msg = bot.send_message(chat_id, response, parse_mode='HTML')
                user_message_ids[user_id].append(msg.message_id)
        else:
            msg = bot.send_message(chat_id, "🎤 Не разобрал.")
            user_message_ids[user_id].append(msg.message_id)
    except Exception as e:
        msg = bot.send_message(chat_id, f"⚠️ Ошибка: {e}")
        user_message_ids[user_id].append(msg.message_id)

def stt(audio_data):
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        recognizer = sr.Recognizer()
        wav_path = tmp_path + '.wav'
        subprocess.run(['ffmpeg', '-i', tmp_path, '-ar', '16000', '-ac', '1', wav_path, '-y'],
                      capture_output=True, check=False)
        if os.path.exists(wav_path):
            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source)
            os.unlink(wav_path)
        else:
            with sr.AudioFile(tmp_path) as source:
                audio = recognizer.record(source)
        os.unlink(tmp_path)
        text = recognizer.recognize_google(audio, language='ru-RU')
        return text
    except:
        return None

# ============================================================
# ТЕКСТ
# ============================================================
@bot.message_handler(content_types=['text'])
def handle_text(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    username = m.from_user.username or "unknown"
    
    if m.text.startswith('/'):
        return
    
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    
    delete_previous_messages(chat_id, user_id)
    
    if check_spam(user_id):
        msg = bot.send_message(chat_id, "⏳ Подожди 1.5 секунды!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if is_banned(user_id):
        msg = bot.send_message(chat_id, "🚫 Ты забанен!")
        user_message_ids[user_id].append(msg.message_id)
        return
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return

    bot.send_chat_action(chat_id, 'typing')

    if is_image_generation(m.text):
        generate_and_send_image(m, m.text)
        return

    increment_messages(user_id)
    response = process_message(user_id, m.text)
    
    if response:
        bot.send_message(chat_id, response, parse_mode='HTML')
    else:
        bot.send_message(chat_id, random.choice([
            "🤔 Хм... Что ты имеешь в виду?",
            "🧐 Слушай, я не совсем понял.",
            "😮 Ого! Расскажи подробнее!",
            "💡 Понял! Я сейчас подумаю..."
        ]))

# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        ensure_user(user_id, call.from_user.username or "unknown")
        
        delete_previous_messages(chat_id, user_id)
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        # === КНОПКА "ГЛАВНОЕ МЕНЮ" ===
        if call.data == "back_to_menu":
            bot.answer_callback_query(call.id)
            text = (
                "✨ <b>AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ!</b> ✨\n\n"
                f"🌸 <b>Привет, {call.from_user.first_name}!</b>\n\n"
                "🧠 <b>Меня создал гениальный AWESOME (@flidges)</b>\n"
                "Я работаю на уникальном коде, написанном с нуля!\n\n"
                "🌐 Я умею искать в Google, Wikipedia и новостях\n"
                "💵 Показываю курс валют и криптовалют\n"
                "🧮 Решаю задачи и помогаю с программированием\n"
                "🧠 Анализирую настроение и адаптируюсь\n\n"
                "🎁 <b>Попробуй Premium бесплатно!</b>\n"
                "Нажми кнопку «Тест Premium» 👇\n\n"
                f"💎 Бесплатно — {FREE_LIMIT} сообщений/день\n"
                f"💎 Премиум — {PREMIUM_LIMIT} сообщений/день\n"
                "👑 Админ и Овнер — безлимит"
            )
            msg = bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === КНОПКА "ЧТО ДАЁТ PREMIUM?" ===
        if call.data == "premium_features":
            bot.answer_callback_query(call.id)
            text = get_premium_features_text()
            msg = bot.send_message(chat_id, text, reply_markup=premium_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === КНОПКА "Я ОПЛАТИЛ" ===
        if call.data == "i_paid":
            if get_premium_status(user_id):
                bot.answer_callback_query(call.id, "❌ У тебя уже есть Premium!")
                return
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO premium_orders (user_id, created_at) VALUES (?, ?)',
                      (user_id, datetime.now().strftime('%d.%m.%Y %H:%M')))
            order_id = c.lastrowid
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, "✅ Заказ создан! Ожидай подтверждения.")
            
            msg = bot.send_message(
                chat_id,
                "✅ <b>ЗАКАЗ ОТПРАВЛЕН!</b>\n\n"
                f"🆔 Номер заказа: #{order_id}\n"
                "⏳ Админ проверит оплату и подтвердит заказ.\n\n"
                "📌 Обычно это занимает до 24 часов.",
                parse_mode='HTML'
            )
            user_message_ids[user_id].append(msg.message_id)
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_order:{order_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_order:{order_id}")
            )
            
            bot.send_message(
                OWNER_ID,
                f"💳 <b>НОВЫЙ ЗАКАЗ PREMIUM!</b>\n\n"
                f"🆔 Заказ: #{order_id}\n"
                f"👤 Пользователь: @{call.from_user.username or 'Не указан'}\n"
                f"🆔 ID: {user_id}\n"
                f"💰 Сумма: 50₽\n"
                f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                "Проверь оплату и подтверди заказ:",
                reply_markup=keyboard,
                parse_mode='HTML'
            )
            return
        
        # === ПОДТВЕРЖДЕНИЕ ЗАКАЗА ===
        if call.data.startswith("confirm_order:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            order_id = int(call.data.replace("confirm_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM premium_orders WHERE order_id = ? AND status = "pending"', (order_id,))
            result = c.fetchone()
            if result:
                target_user = result[0]
                c.execute('UPDATE premium_orders SET status = "confirmed" WHERE order_id = ?', (order_id,))
                conn.commit()
                conn.close()
                
                has_premium = get_premium_status(target_user)
                
                if set_premium(target_user, "1mes"):
                    bot.answer_callback_query(call.id, "✅ Premium выдан!")
                    
                    if has_premium:
                        expires = get_premium_expires(target_user)
                        msg_text = (
                            f"🎉 <b>PREMIUM ПРОДЛЁН!</b>\n\n"
                            f"✅ Твой заказ #{order_id} подтверждён!\n"
                            f"💎 Premium продлён на 1 месяц!\n"
                            f"⏳ Действует до: {expires}\n\n"
                            f"📨 Лимит: {PREMIUM_LIMIT} сообщений/день\n\n"
                            "Спасибо за продление! ❤️"
                        )
                    else:
                        expires = get_premium_expires(target_user)
                        msg_text = (
                            f"🎉 <b>PREMIUM АКТИВИРОВАН!</b>\n\n"
                            f"✅ Твой заказ #{order_id} подтверждён!\n"
                            f"💎 Premium активен на 1 месяц!\n"
                            f"⏳ Действует до: {expires}\n\n"
                            f"📨 Лимит: {PREMIUM_LIMIT} сообщений/день\n\n"
                            "Спасибо за покупку! ❤️"
                        )
                    
                    bot.send_message(target_user, msg_text, parse_mode='HTML')
                    
                    bot.edit_message_text(
                        f"✅ Заказ #{order_id} подтверждён!\n"
                        f"👤 Пользователю выдан Premium на 1 месяц.",
                        chat_id=chat_id,
                        message_id=call.message.message_id,
                        parse_mode='HTML'
                    )
                else:
                    bot.answer_callback_query(call.id, "❌ Ошибка выдачи Premium")
            else:
                conn.close()
                bot.answer_callback_query(call.id, "❌ Заказ не найден или уже обработан")
            return
        
        # === ОТКЛОНЕНИЕ ЗАКАЗА ===
        if call.data.startswith("reject_order:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            order_id = int(call.data.replace("reject_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM premium_orders WHERE order_id = ? AND status = "pending"', (order_id,))
            result = c.fetchone()
            if result:
                target_user = result[0]
                c.execute('UPDATE premium_orders SET status = "rejected" WHERE order_id = ?', (order_id,))
                conn.commit()
                conn.close()
                
                bot.answer_callback_query(call.id, "❌ Заказ отклонён")
                
                bot.send_message(
                    target_user,
                    f"❌ <b>ЗАКАЗ ОТКЛОНЁН</b>\n\n"
                    f"🆔 Заказ: #{order_id}\n\n"
                    "Администратор отклонил твой заказ.\n"
                    "Возможно, оплата не поступила.\n\n"
                    "Попробуй ещё раз: /premium",
                    parse_mode='HTML'
                )
                
                bot.edit_message_text(
                    f"❌ Заказ #{order_id} отклонён!",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    parse_mode='HTML'
                )
            else:
                conn.close()
                bot.answer_callback_query(call.id, "❌ Заказ не найден или уже обработан")
            return
        
        # === ОБРАБОТКА ОТВЕТА НА ОБРАЩЕНИЕ ===
        if call.data.startswith("support_reply:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            request_id = int(call.data.replace("support_reply:", ""))
            
            bot.answer_callback_query(call.id, "✏️ Введи текст ответа")
            
            bot.send_message(
                chat_id,
                f"✏️ <b>Ответ на обращение #{request_id}</b>\n\n"
                "Напиши текст ответа пользователю:",
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(call.message, process_support_reply, request_id)
            return
        
        # === УДАЛЕНИЕ ОБРАЩЕНИЯ ===
        if call.data.startswith("support_delete:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            request_id = int(call.data.replace("support_delete:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('UPDATE support_requests SET status = "deleted" WHERE request_id = ?', (request_id,))
            conn.commit()
            conn.close()
            
            bot.answer_callback_query(call.id, "🗑 Обращение удалено")
            bot.edit_message_text(
                f"🗑 Обращение #{request_id} удалено.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode='HTML'
            )
            return
        
        # === ОТВЕТ НА ОТЗЫВ ===
        if call.data.startswith("feedback_reply:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            target_user = int(call.data.replace("feedback_reply:", ""))
            
            bot.answer_callback_query(call.id, "✏️ Введи текст ответа")
            
            bot.send_message(
                chat_id,
                f"✏️ <b>Ответ на отзыв</b>\n\n"
                f"👤 Пользователь: {target_user}\n"
                "Напиши текст ответа:",
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(call.message, process_feedback_reply, target_user)
            return
        
        # === УДАЛЕНИЕ ОТЗЫВА ===
        if call.data.startswith("feedback_delete:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            bot.answer_callback_query(call.id, "🗑 Отзыв удалён")
            bot.edit_message_text(
                f"🗑 Отзыв удалён.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                parse_mode='HTML'
            )
            return
        
        # === АДМИН: ЗАКАЗЫ ===
        if call.data == "admin_orders":
            bot.answer_callback_query(call.id)
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT order_id, user_id, created_at FROM premium_orders WHERE status = "pending" ORDER BY order_id DESC')
            orders = c.fetchall()
            conn.close()
            
            if not orders:
                text = "💳 <b>ЗАКАЗЫ PREMIUM</b>\n\nНет активных заказов."
            else:
                text = f"💳 <b>ЗАКАЗЫ PREMIUM</b>\n\nВсего: {len(orders)}\n\n"
                for order in orders:
                    text += f"🆔 #{order[0]} | 👤 {order[1]} | 📅 {order[2]}\n"
            
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === АДМИН: ОБРАЩЕНИЯ ===
        if call.data == "admin_support":
            bot.answer_callback_query(call.id)
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT request_id, user_id, username, text, created_at FROM support_requests WHERE status = "pending" ORDER BY request_id DESC')
            requests = c.fetchall()
            conn.close()
            
            if not requests:
                text = "📩 <b>ОБРАЩЕНИЯ</b>\n\nНет активных обращений."
            else:
                text = f"📩 <b>ОБРАЩЕНИЯ</b>\n\nВсего: {len(requests)}\n\n"
                for req in requests:
                    text += f"🆔 #{req[0]} | @{req[2] or 'Не указан'} | {req[4]}\n📝 {req[3][:50]}...\n\n"
            
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === ОСТАЛЬНЫЕ АДМИН-КНОПКИ ===
        if call.data == "admin_stats":
            bot.answer_callback_query(call.id)
            stats_cmd_from_user(call.message, user_id)
            return
        
        elif call.data == "admin_list":
            bot.answer_callback_query(call.id)
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username FROM users WHERE is_admin = 1')
            admins = c.fetchall()
            conn.close()
            
            if not admins:
                text = "👑 <b>АДМИНЫ</b>\n\nНет админов."
            else:
                text = "👑 <b>АДМИНЫ</b>\n\n"
                for admin in admins:
                    user_link = f"@{admin[1]}" if admin[1] else f"<code>{admin[0]}</code>"
                    text += f"• {user_link}\n"
            
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_list_users":
            bot.answer_callback_query(call.id)
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username, premium, is_admin FROM users ORDER BY user_id')
            users = c.fetchall()
            conn.close()
            
            if not users:
                msg = bot.send_message(chat_id, "📊 Нет пользователей.")
                user_message_ids[user_id].append(msg.message_id)
                return
            
            text = "👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n\n"
            
            for user in users:
                uid, username, premium, is_admin = user
                user_link = f"@{username}" if username and username != "unknown" else "Не указан"
                
                if uid == OWNER_ID:
                    status = "👑 ВЛАДЕЛЕЦ"
                elif is_admin == 1:
                    status = "👑 АДМИН"
                elif premium == 1:
                    status = "💎 PREMIUM"
                else:
                    status = "🔓 Бесплатный"
                
                text += f"• {user_link} | ID: <code>{uid}</code> | {status}\n"
                
                if len(text) > 3500:
                    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
                    user_message_ids[user_id].append(msg.message_id)
                    text = ""
            
            if text:
                msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
                user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_broadcast":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "📢 Напиши текст рассылки:\n/broadcast [текст]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_giveprem":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "💎 Выдать Premium:\n/giveprem [ID] [срок]\n\nСрок: 1d, 1m, 1h, 1mes, 1y", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_givetest":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎁 Выдать тест Premium:\n/givetest [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_ban":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🚫 Забанить:\n/ban [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_unban":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "✅ Разбанить:\n/unban [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_mute":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🔇 Замутить:\n/mute [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_unmute":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🔊 Размутить:\n/unmute [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_giveadmin":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "👑 Выдать админа:\n/giveadmin [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_deladmin":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "👑 Забрать админа:\n/deladmin [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_info":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "📊 Инфо о пользователе:\n/info [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_stats_users":
            bot.answer_callback_query(call.id)
            stats_users_cmd(call.message)
            return
        
        elif call.data == "admin_clear_messages":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🧹 Обнулить сообщения:\n/clear_messages [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "admin_close":
            bot.answer_callback_query(call.id, "❌ Закрыто")
            msg = bot.send_message(chat_id, "❌ Панель закрыта", reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === ОСНОВНЫЕ КНОПКИ ===
        if call.data == "test":
            bot.answer_callback_query(call.id, "🎁 Активирую...")
            process_test_premium(chat_id, user_id)
            return
        
        elif call.data == "support":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(
                chat_id,
                "📩 <b>Поддержка</b>\n\n"
                "Напиши свой вопрос:\n"
                "/support [текст]\n\n"
                "Или напиши мне в личные сообщения.",
                parse_mode='HTML'
            )
            user_message_ids[user_id].append(msg.message_id)
            return
        
        elif call.data == "status":
            bot.answer_callback_query(call.id)
            status_cmd_from_user(call.message, user_id)
        elif call.data == "premium":
            bot.answer_callback_query(call.id)
            premium_cmd_from_user(call.message, user_id)
        elif call.data == "profile":
            bot.answer_callback_query(call.id)
            profile_cmd_from_user(call.message, user_id)
        elif call.data == "stats":
            bot.answer_callback_query(call.id)
            stats_cmd_from_user(call.message, user_id)
        elif call.data == "clear":
            bot.answer_callback_query(call.id)
            clear_cmd_from_user(call.message, user_id)
        elif call.data == "help":
            bot.answer_callback_query(call.id)
            help_cmd_from_user(call.message, user_id)
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎨 Напиши: /draw [описание]")
            user_message_ids[user_id].append(msg.message_id)
            
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {e}")

# ============================================================
# ОБРАБОТЧИКИ ОТВЕТОВ
# ============================================================

def process_support_reply(message, request_id):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_authorized(user_id):
        bot.send_message(chat_id, "❌ Нет прав!")
        return
    
    reply_text = message.text
    
    if not reply_text or len(reply_text.strip()) < 1:
        bot.send_message(chat_id, "❌ Текст не может быть пустым!")
        return
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM support_requests WHERE request_id = ?', (request_id,))
    result = c.fetchone()
    
    if not result:
        conn.close()
        bot.send_message(chat_id, f"❌ Обращение #{request_id} не найдено!")
        return
    
    target_user = result[0]
    c.execute('UPDATE support_requests SET status = "answered" WHERE request_id = ?', (request_id,))
    conn.commit()
    conn.close()
    
    bot.send_message(
        target_user,
        f"📩 <b>ОТВЕТ ПОДДЕРЖКИ</b>\n\n"
        f"🆔 Обращение: #{request_id}\n\n"
        f"📝 {reply_text}\n\n"
        "---\n"
        "Если остались вопросы, напиши ещё раз.",
        parse_mode='HTML'
    )
    
    bot.send_message(
        chat_id,
        f"✅ Ответ на обращение #{request_id} отправлен!\n\n"
        f"📝 {reply_text}",
        parse_mode='HTML'
    )

def process_feedback_reply(message, target_user):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not is_authorized(user_id):
        bot.send_message(chat_id, "❌ Нет прав!")
        return
    
    reply_text = message.text
    
    if not reply_text or len(reply_text.strip()) < 1:
        bot.send_message(chat_id, "❌ Текст не может быть пустым!")
        return
    
    bot.send_message(
        target_user,
        f"📝 <b>ОТВЕТ НА ОТЗЫВ</b>\n\n"
        f"✨ AWESOME AI благодарит за отзыв!\n\n"
        f"📝 {reply_text}\n\n"
        "---\n"
        "Спасибо, что пользуешься ботом! ❤️",
        parse_mode='HTML'
    )
    
    bot.send_message(
        chat_id,
        f"✅ Ответ на отзыв отправлен!\n\n"
        f"👤 Пользователю: {target_user}\n"
        f"📝 {reply_text}",
        parse_mode='HTML'
    )

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!")
print("=" * 60)
print(f"🤖 Бот: @{bot.get_me().username}")
print(f"👑 Создатель: AWESOME (@flidges)")
print(f"📊 Лимиты:")
print(f"   🔓 Бесплатный: {FREE_LIMIT}/день")
print(f"   💎 Премиум: {PREMIUM_LIMIT}/день")
print(f"   👑 Админ/Владелец: ♾️ Безлимит")
print(f"⏱️ Анти-спам: 1.5 секунды")
print("=" * 60)
print("БОТ ГОТОВ!")
print("=" * 60)

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
