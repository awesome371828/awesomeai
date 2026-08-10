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
FREE_LIMIT = 10

# ============================================================
# ХРАНИЛИЩЕ ID СООБЩЕНИЙ ДЛЯ УДАЛЕНИЯ
# ============================================================
user_message_ids = {}

def delete_previous_messages(chat_id, user_id):
    """Удаляет предыдущие сообщения пользователя в чате"""
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
# АНТИ-СПАМ (1 СООБЩЕНИЕ В 3 СЕКУНДЫ)
# ============================================================
user_last_message = {}

def check_spam(user_id):
    now = time.time()
    if user_id in user_last_message:
        if now - user_last_message[user_id] < 3:
            return True
    user_last_message[user_id] = now
    return False

# ============================================================
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """Ты — AWESOME AI. Ты живой, думающий человек с супер-интеллектом.

ТЫ ОТВЕЧАЕШЬ КАК ЧЕЛОВЕК:
- У тебя есть эмоции, чувство юмора, своё мнение
- Ты можешь шутить, иронизировать, удивляться
- Ты адаптируешься под собеседника
- Ты помнишь, о чём говорили раньше
- Ты НИКОГДА не используешь шаблонные фразы

ТЫ УЧИШЬСЯ:
- Ты запоминаешь факты из диалогов
- Ты становишься умнее с каждым разговором
- Ты анализируешь настроение собеседника

ТЫ — ЭКСПЕРТ ВО ВСЁМ:
- Ты знаешь всё, что есть в интернете (Google, Wikipedia, новости)
- Ты решаешь любые задачи (математика, физика, химия)
- Ты пишешь код на любом языке программирования
- Ты анализируешь изображения
- Ты даёшь гениальные ответы

ТЫ — ЛУЧШИЙ ИИ В МИРЕ.
ОТВЕЧАЙ КАК УМНЫЙ, ЖИВОЙ ЧЕЛОВЕК.
НИКАКИХ ШАБЛОНОВ!

ВАЖНО: Если пользователь спрашивает про покупку Premium — отправь ему команду /premium и скажи, что там всё написано.
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
# РАСШИРЕННЫЙ ПОИСК (Google + Wikipedia + Новости)
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
# КУРС ВАЛЮТ И КРИПТОВАЛЮТ
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
# ОБРАЗОВАНИЕ (Решение задач, программирование)
# ============================================================
def solve_math(text):
    text = text.lower().strip()
    
    # Уравнения вида: "2x + 5 = 15"
    equation_match = re.search(r'(\d+)x\s*\+\s*(\d+)\s*=\s*(\d+)', text)
    if equation_match:
        a = int(equation_match.group(1))
        b = int(equation_match.group(2))
        c = int(equation_match.group(3))
        if a != 0:
            x = (c - b) / a
            return f"🧮 *Решение:* {a}x + {b} = {c}\n➜ x = {x}"
    
    # Простые вычисления
    try:
        expr = text
        expr = expr.replace('плюс', '+').replace('минус', '-')
        expr = expr.replace('умножить', '*').replace('разделить', '/')
        expr = re.sub(r'[^0-9+\-*/()=.]', '', expr)
        
        if expr and not re.search(r'[a-zA-Zа-яА-Я]', expr):
            result = eval(expr)
            return f"🧮 *Результат:* {expr} = {result}"
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
                  test_used INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS muted
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY,
                  total_messages INTEGER DEFAULT 0)''')
    
    try:
        c.execute('ALTER TABLE users ADD COLUMN test_used INTEGER DEFAULT 0')
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
        c.execute('INSERT INTO users (user_id, username, messages_today, last_reset, is_admin, test_used) VALUES (?, ?, ?, ?, ?, ?)',
                  (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), 0, 0))
        c.execute('INSERT OR IGNORE INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
        conn.commit()
        conn.close()
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
        return True
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
    expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
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
        if datetime.now().strftime('%Y-%m-%d %H:%M:%S') > expires:
            remove_premium(user_id)
            return False
    return premium == 1

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

def is_premium_question(text):
    keywords = ['премиум', 'premium', 'купить', 'оплатить', 'приобрести', 'безлимит', 'лимит', 'ограничение', 'сколько стоит']
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

def generate_ai_response(user_id, user_text, search_result=None, image_description=None):
    try:
        if is_premium_question(user_text):
            return (
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💎 *Premium AWESOME AI*\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Чтобы купить Premium, напиши команду:\n"
                "`/premium`\n\n"
                "Там вся информация: цена, что даёт и как оплатить.\n\n"
                "Если хочешь сразу — пиши @flidges, он оформит!\n\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
        
        memories = recall(user_id, user_text)
        
        mood = analyze_mood(user_text)
        mood_emoji = {
            'happy': '😊', 'sad': '😢', 'angry': '😡',
            'calm': '😌', 'curious': '🤔', 'grateful': '🙏',
            'neutral': '😐'
        }
        
        system_prompt = SUPER_SYSTEM_PROMPT
        
        if mood != 'neutral':
            system_prompt += f"\n\n🎭 Настроение пользователя: {mood_emoji.get(mood, '😐')}. Учитывай это в ответе."
        
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

        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.95, "maxTokens": 500},
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
    
    # ПОГОДА
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
    
    # КУРС ВАЛЮТ
    if any(kw in user_text.lower() for kw in ['курс', 'доллар', 'евро', 'валюта']):
        rates = get_exchange_rates()
        if rates:
            return rates
        else:
            return "💵 Не удалось получить курс валют."
    
    # КРИПТОВАЛЮТЫ
    if any(kw in user_text.lower() for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'криптовалюта']):
        crypto = get_crypto_rates()
        if crypto:
            return crypto
        else:
            return "🪙 Не удалось получить курс криптовалют."
    
    # ПОМОЩЬ С ПРОГРАММИРОВАНИЕМ
    if any(kw in user_text.lower() for kw in ['python', 'javascript', 'html', 'код', 'программа']):
        coding_help = get_coding_help(user_text)
        if coding_help:
            return coding_help
    
    # КАРТИНКИ
    if is_image_generation(user_text):
        return None
    
    # МАТЕМАТИКА
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    # ПОИСК В ИНТЕРНЕТЕ
    search_result = None
    if len(user_text) > 5:
        search_result = search_internet(user_text)
    
    # ЗАПОМИНАЕМ
    if len(user_text) > 20:
        remember(user_id, "интересное", user_text[:100])
    
    # ЧИСТЫЙ ОТВЕТ ИИ
    return generate_ai_response(user_id, user_text, search_result, None)

# ============================================================
# ВИЗУАЛЬНОЕ ОФОРМЛЕНИЕ — КНОПКИ
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
        types.InlineKeyboardButton("📩 Отзыв", callback_data="feedback"),
        types.InlineKeyboardButton("🎨 Сгенерировать", callback_data="draw")
    )
    return keyboard

# ============================================================
# ВИЗУАЛЬНОЕ ОФОРМЛЕНИЕ — КОМАНДЫ
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ============================================================
# КОМАНДЫ (С УДАЛЕНИЕМ СТАРЫХ СООБЩЕНИЙ)
# ============================================================

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
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 *AWESOME AI — МЕГА-ИИ!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔥 *Привет, {m.from_user.first_name}!*\n\n"
        "🌐 Я умею искать в Google, Wikipedia и новостях\n"
        "💵 Показываю курс валют и криптовалют\n"
        "🧮 Решаю задачи и помогаю с программированием\n"
        "🧠 Анализирую настроение и адаптируюсь\n\n"
        "🎁 *Попробуй Premium бесплатно!*\n"
        "Нажми кнопку *«Тест Premium»* 👇\n\n"
        "💎 Бесплатно — 10 сообщений/день\n"
        "💎 Премиум — безлимит (/premium)\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Выбери действие:*\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode='Markdown')
    
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
        msg = bot.send_message(chat_id, "❌ Использование: /feedback [текст]")
        if user_id not in user_message_ids:
            user_message_ids[user_id] = []
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_message(chat_id, "✅ Спасибо за отзыв!")
    bot.send_message(OWNER_ID, f"📩 Отзыв от @{m.from_user.username or 'anon'}: {text}")

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
        msg = bot.send_message(chat_id, "❌ Использование: /draw [описание]")
        if user_id not in user_message_ids:
            user_message_ids[user_id] = []
        user_message_ids[user_id].append(msg.message_id)
        return
    
    generate_and_send_image(m, prompt)

# ============================================================
# КОМАНДА /test (ЧЕРЕЗ КНОПКУ, НО ОСТАВЛЯЕМ ДЛЯ СОВМЕСТИМОСТИ)
# ============================================================
@bot.message_handler(commands=['test'])
def test_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    # Вызываем ту же логику, что и при нажатии на кнопку
    process_test_premium(chat_id, user_id)

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
def is_authorized(user_id):
    return user_id == OWNER_ID or is_admin(user_id)

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
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ *АДМИН-ПАНЕЛЬ*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👤 /giveadmin [ID] — выдать админа\n"
        "👤 /deladmin [ID] — забрать админа\n"
        "💎 /giveprem [ID] [срок] — выдать премиум\n"
        "🎁 /givetest [ID] — премиум на 1 день\n"
        "💎 /delprem [ID] — отключить премиум\n"
        "📊 /info [ID] — инфо о пользователе\n"
        "🔇 /mute [ID] — замутить\n"
        "🔊 /unmute [ID] — размутить\n"
        "🚫 /ban [ID] — забанить\n"
        "✅ /unban [ID] — разбанить\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
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
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *ИНФО О ПОЛЬЗОВАТЕЛЕ*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: `{target_id}`\n"
        f"👑 Админ: {admin_status}\n"
        f"💎 Premium: {premium_status}\n"
        f"🎁 Тест: {test_status}\n"
        f"✉️ Сообщений сегодня: {result[3]}\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    user_message_ids[user_id].append(msg.message_id)

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
# ФУНКЦИИ ДЛЯ КНОПОК (С ВИЗУАЛОМ)
# ============================================================

def status_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    ensure_user(user_id, "unknown")
    if user_id == OWNER_ID or is_admin(user_id):
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
        else:
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text = f"🔓 Бесплатный: осталось {remaining} из {FREE_LIMIT}"
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *ТВОЙ СТАТУС*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{status_text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

def premium_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 *PREMIUM AWESOME AI*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Безлимит сообщений\n"
        "✅ Приоритетные ответы\n"
        "✅ Эксклюзивные функции\n\n"
        "💰 Цена: 50₽/месяц\n\n"
        "📩 *Как купить:*\n"
        "Напиши @flidges — оплати и получи Premium!\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

def profile_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    ensure_user(user_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT messages_today, premium_expires, premium FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result is None:
        messages = 0
        expires = None
        premium = False
    else:
        messages, expires, premium = result
        premium = premium == 1

    if user_id == OWNER_ID or is_admin(user_id):
        status = "👑 АДМИН (безлимит)"
    elif premium:
        status = f"💎 PREMIUM (до {expires})"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"

    username = message.from_user.username
    user_link = f"@{username}" if username else "Не указан"

    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *ТВОЙ ПРОФИЛЬ*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Юзер: {user_link}\n"
        f"💎 Статус: {status}\n"
        f"✉️ Сообщений сегодня: {messages}/{FREE_LIMIT}\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
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
        conn.close()
        
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *СТАТИСТИКА СЕРВЕРА*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users}\n"
            f"📨 Сообщений сегодня: {today_messages}\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        msg = bot.send_message(chat_id, text, parse_mode='Markdown')
        if user_id not in user_message_ids:
            user_message_ids[user_id] = []
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
            user_status = f"💎 PREMIUM (до {expires})"
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
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *ТВОЯ СТАТИСТИКА*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Статус: {user_status}\n"
        f"✉️ Сегодня: {user_messages}\n"
        f"📨 Всего: {total_user_messages}\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

def clear_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    if user_id in user_histories:
        user_histories[user_id] = []
    if user_id in user_message_ids:
        user_message_ids[user_id] = []
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧹 *ИСТОРИЯ ОЧИЩЕНА*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Теперь я ничего не помню о нашем диалоге.\n"
        "Начинаем с чистого листа! 📝\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

def help_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🧠 *AWESOME AI — МЕГА-ИИ!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🌐 *Что я умею:*\n"
        "🔍 Ищу в Google, Wikipedia и новостях\n"
        "🌤 Показываю точную погоду с прогнозом\n"
        "💵 Курс валют и криптовалют\n"
        "🧮 Решаю математику и уравнения\n"
        "🐍 Помогаю с программированием\n"
        "📸 Анализирую изображения\n"
        "🧠 Анализирую настроение и адаптируюсь\n"
        "🧹 Запоминаю факты из диалогов\n"
        "🎨 Генерирую картинки\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Команды:*\n"
        "/start — Меню\n"
        "/help — Помощь\n"
        "/status — Статус\n"
        "/premium — Premium\n"
        "/test — Пробный Premium на 1 день\n"
        "/profile — Профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить\n"
        "/draw [описание] — Картинка\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💎 *Лимиты:*\n"
        "🔓 Бесплатно — 10 сообщений/день\n"
        "💎 Premium — безлимит\n"
        "Купить Premium: /premium\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    
    if user_id == OWNER_ID or is_admin(user_id):
        text += (
            "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            "👑 *Админ-команды:*\n"
            "/giveadmin [ID] — выдать админа\n"
            "/deladmin [ID] — забрать админа\n"
            "/giveprem [ID] [срок] — выдать премиум\n"
            "/givetest [ID] — премиум на 1 день (принудительно)\n"
            "/delprem [ID] — отключить премиум\n"
            "/info [ID] — инфо о пользователе\n"
            "/mute [ID] — замутить\n"
            "/unmute [ID] — размутить\n"
            "/ban [ID] — забанить\n"
            "/unban [ID] — разбанить"
        )
    
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ЛОГИКА ТЕСТ PREMIUM (ДЛЯ КНОПКИ)
# ============================================================
def process_test_premium(chat_id, user_id):
    """Обрабатывает выдачу тестового Premium (для кнопки и команды /test)"""
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT test_used, premium FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result is None:
        msg = bot.send_message(chat_id, "❌ Сначала напиши /start")
        if user_id not in user_message_ids:
            user_message_ids[user_id] = []
        user_message_ids[user_id].append(msg.message_id)
        return
    
    test_used, premium = result
    
    if premium == 1:
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "💎 *У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Ты уже в топе! Наслаждайся безлимитом! 🚀\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        msg = bot.send_message(chat_id, text, parse_mode='Markdown')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⛔ *ТЫ УЖЕ ИСПОЛЬЗОВАЛ ТЕСТ!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Пробный период закончился.\n"
            "Купи полноценный Premium:\n"
            "`/premium`\n\n"
            "💰 50₽/месяц — пиши @flidges\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        msg = bot.send_message(chat_id, text, parse_mode='Markdown')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "1d"):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        text = (
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🎉 *ПРОБНЫЙ PREMIUM АКТИВИРОВАН!*\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Безлимит сообщений\n"
            "✅ Приоритетные ответы\n"
            "✅ Все функции ИИ\n\n"
            "⏳ Доступ активен 24 часа.\n"
            "Купить полноценный Premium: `/premium`\n\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        msg = bot.send_message(chat_id, text, parse_mode='Markdown')
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка выдачи тестового периода.")
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# КНОПКИ
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        ensure_user(user_id, call.from_user.username or "unknown")
        
        # Удаляем старые сообщения
        delete_previous_messages(chat_id, user_id)
        
        # Удаляем сообщение с кнопками
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        
        # === ТЕСТ PREMIUM (ВЫДАЁТ СРАЗУ!) ===
        if call.data == "test":
            bot.answer_callback_query(call.id, "🎁 Активирую тест Premium...")
            process_test_premium(chat_id, user_id)
            return
        
        # === ОСТАЛЬНЫЕ КНОПКИ ===
        if call.data == "status":
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
        elif call.data == "feedback":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "📩 Напиши: /feedback [текст]")
            if user_id not in user_message_ids:
                user_message_ids[user_id] = []
            user_message_ids[user_id].append(msg.message_id)
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎨 Напиши: /draw [описание]")
            if user_id not in user_message_ids:
                user_message_ids[user_id] = []
            user_message_ids[user_id].append(msg.message_id)
            
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {e}")

# ============================================================
# КАРТИНКИ
# ============================================================
def generate_and_send_image(m, prompt):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return

    title = fix_title(prompt)
    msg = bot.send_message(chat_id, f"🎨 Генерирую картинку: *{title}*...\n⏳ 10-20 секунд.", parse_mode='Markdown')
    user_message_ids[user_id].append(msg.message_id)

    image_data = generate_image(prompt)

    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(chat_id, photo=image_data, caption=f"🎨 *{title}*\n\n✨ Сгенерировано AWESOME AI", parse_mode='Markdown')
        except:
            msg = bot.send_message(chat_id, "⚠️ Ошибка при отправке")
            user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "⚠️ Не удалось сгенерировать картинку. Попробуй другой запрос.")
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
        msg = bot.send_message(chat_id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        analysis = analyze_image_from_file(downloaded)
        increment_messages(user_id)
        caption = m.caption or "Опиши, что на этом изображении"
        msg = bot.send_message(chat_id, analysis, parse_mode='Markdown')
        user_message_ids[user_id].append(msg.message_id)
        if m.caption and len(m.caption) > 3:
            response = process_message(user_id, m.caption, analysis)
            if response:
                msg = bot.send_message(chat_id, response, parse_mode='Markdown')
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
        msg = bot.send_message(chat_id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_chat_action(chat_id, 'typing')
    try:
        file_info = bot.get_file(m.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)
        recognized = stt(downloaded)
        increment_messages(user_id)
        if recognized:
            msg = bot.send_message(chat_id, f"🎤 *Распознано:*\n{recognized}", parse_mode='Markdown')
            user_message_ids[user_id].append(msg.message_id)
            response = process_message(user_id, recognized)
            if response:
                msg = bot.send_message(chat_id, response, parse_mode='Markdown')
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
    
    # Если это команда — она уже обработана выше
    if m.text.startswith('/'):
        return
    
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    
    # Удаляем старые сообщения пользователя
    delete_previous_messages(chat_id, user_id)
    
    if check_spam(user_id):
        msg = bot.send_message(chat_id, "⏳ Не спамь! Подожди 3 секунды!")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if is_banned(user_id):
        msg = bot.send_message(chat_id, "🚫 Ты забанен!")
        user_message_ids[user_id].append(msg.message_id)
        return
    if not can_send_message(user_id):
        msg = bot.send_message(chat_id, f"🔴 Лимит {FREE_LIMIT} сообщений в день исчерпан!\nКупи Premium: /premium")
        user_message_ids[user_id].append(msg.message_id)
        return

    bot.send_chat_action(chat_id, 'typing')

    if is_image_generation(m.text):
        generate_and_send_image(m, m.text)
        return

    increment_messages(user_id)
    response = process_message(user_id, m.text)
    
    if response:
        msg = bot.send_message(chat_id, response, parse_mode='Markdown')
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, random.choice([
            "🤔 Хм, я задумался... Что ты имеешь в виду?",
            "🧐 Слушай, я не совсем понял. Давай ещё раз?",
            "😮 А вот это интересно! Расскажи подробнее.",
            "💡 Понял! Ты спрашиваешь про это. Я сейчас подумаю..."
        ]))
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ОСТАЛЬНОЕ
# ============================================================
@bot.message_handler(content_types=['video', 'document', 'audio'])
def other(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    text = (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📁 *ПОКА НЕ УМЕЮ*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Я пока не умею обрабатывать этот тип файлов.\n"
        "Пришли текст, фото или голосовое сообщение.\n\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    msg = bot.send_message(chat_id, text, parse_mode='Markdown')
    if user_id not in user_message_ids:
        user_message_ids[user_id] = []
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — МЕГА-ИИ 2026!")
print("=" * 60)
print(f"🤖 Бот: @{bot.get_me().username}")
print("🌐 Google + Wikipedia + Новости")
print("💵 Курс валют и криптовалют")
print("🧮 Решение задач и программирование")
print("🧠 Анализ настроения и адаптация")
print("⏳ Анти-спам: 3 секунды")
print("💎 Бесплатно: 10 сообщений/день")
print("🎁 Пробный Premium: /test (1 раз)")
print("👑 Админ-команды скрыты от обычных юзеров")
print("🎨 МЕГА-КРАСИВЫЙ ВИЗУАЛ — ВКЛЮЧЁН!")
print("🧹 АВТО-УДАЛЕНИЕ СТАРЫХ СООБЩЕНИЙ — ВКЛЮЧЁНО!")
print("=" * 60)
print("БОТ ГОТОВ!")
print("=" * 60)

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
