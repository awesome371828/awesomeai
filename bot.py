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
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI. ТЫ ЗНАЕШЬ ВСЁ!

ТВОЙ СОЗДАТЕЛЬ — AWESOME.

ТЫ ОТВЕЧАЕШЬ ТОЛЬКО ФАКТАМИ:
- Ты знаешь ВСЁ, что есть в интернете
- Ты умеешь анализировать изображения и скриншоты
- Ты описываешь, что видишь на фото
- Ты НЕ ГОВОРИШЬ "я не знаю"
- Ты ВСЕГДА даёшь КОНКРЕТНЫЙ ответ

ТВОЙ СТИЛЬ:
- Кратко, чётко, по делу
- С датами и фактами

ТЫ — ЛУЧШИЙ ИИ В МИРЕ!
"""

# ============================================================
# АНАЛИЗ ИЗОБРАЖЕНИЙ (СКРИНОВ)
# ============================================================
def analyze_image_from_file(file_content):
    """Анализирует изображение и возвращает описание"""
    try:
        # Открываем изображение
        img = Image.open(io.BytesIO(file_content))
        
        # Получаем размеры
        width, height = img.size
        format_img = img.format or "Unknown"
        mode = img.mode
        
        # Базовое описание
        description = f"📸 *Анализ изображения:*\n"
        description += f"📐 Размер: {width}×{height} пикселей\n"
        description += f"📁 Формат: {format_img}\n"
        description += f"🎨 Цветовой режим: {mode}\n"
        
        # Определяем основные цвета
        colors = img.getcolors(maxcolors=10)
        if colors:
            # Сортируем по количеству пикселей
            colors_sorted = sorted(colors, key=lambda x: x[0], reverse=True)[:3]
            main_colors = []
            for count, color in colors_sorted:
                if isinstance(color, tuple):
                    # Если цвет в RGB
                    hex_color = '#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2])
                    main_colors.append(hex_color)
                else:
                    main_colors.append(str(color))
            if main_colors:
                description += f"🎨 Основные цвета: {', '.join(main_colors)}\n"
        
        # Пытаемся распознать текст на изображении (OCR)
        try:
            url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
            headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
            
            # Улучшаем изображение для OCR
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
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
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
                    description += f"\n📝 *Распознанный текст:*\n{recognized_text[:1000]}"
                    
                    if len(recognized_text) > 1000:
                        description += "\n...(текст обрезан)"
        
        except Exception as e:
            print(f"[OCR] Ошибка: {e}")
        
        return description
    
    except Exception as e:
        print(f"[Анализ] Ошибка: {e}")
        return "⚠️ Не удалось проанализировать изображение."

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
        elif "кранснодар" in city_lower or "краснодар" in city_lower:
            city = "Краснодар"
        elif "краснояр" in city_lower or "красноярск" in city_lower:
            city = "Красноярск"
        
        url = f"https://nominatim.openstreetmap.org/search?q={urllib.parse.quote(city)}&format=json&limit=1&accept-language=ru"
        headers = {"User-Agent": "AwesomeAI/1.0"}
        response = requests.get(url, headers=headers, timeout=10)
        
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
        response = requests.get(url, timeout=10)
        
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
            
            has_rain = False
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
                    if code in [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]:
                        has_rain = True
                        forecast += f"\n📅 {date_formatted}: 🌧️ {min_t}°C → {max_t}°C"
                    else:
                        forecast += f"\n📅 {date_formatted}: ☀️ {min_t}°C → {max_t}°C"
            
            result = f"🌤 *Погода в {display_name}*\n"
            result += f"☀️ Сейчас: {condition}, {round(temp)}°C\n"
            result += f"📊 *Прогноз:*{forecast}"
            
            if has_rain:
                result += "\n\n🌧️ *Ожидается дождь!*"
            else:
                result += "\n\n☀️ *Дождей не ожидается.*"
            
            return result
        return None
    except Exception as e:
        print(f"[Погода] Ошибка: {e}")
        return None

def extract_city_from_query(text):
    text_lower = text.lower()
    
    known_cities = [
        "москва", "санкт-петербург", "ростов-на-дону", "ростов", "новосибирск",
        "екатеринбург", "казань", "нижний новгород", "челябинск", "самара",
        "омск", "уфа", "красноярск", "пермь", "воронеж", "волгоград",
        "краснодар", "сочи", "владивосток", "иркутск", "тюмень"
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
# ПОИСК В ИНТЕРНЕТЕ
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        
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
        response = requests.get(url, timeout=10)
        
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

def search_duckduckgo(query):
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for result in soup.select('.result')[:3]:
                title_elem = result.select_one('.result__a')
                snippet_elem = result.select_one('.result__snippet')
                
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

def search_internet(query):
    results = []
    
    google_result = search_google(query)
    if google_result:
        results.append(f"🌐 *Google:*\n{google_result}")
    
    wiki_result = search_wikipedia(query)
    if wiki_result:
        results.append(f"📚 *Wikipedia:*\n{wiki_result}")
    
    ddg_result = search_duckduckgo(query)
    if ddg_result:
        results.append(f"🔍 *DuckDuckGo:*\n{ddg_result}")
    
    if results:
        return "\n\n---\n\n".join(results)
    
    return None

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
                  timestamp TEXT,
                  importance INTEGER DEFAULT 1)''')
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
    c.execute('SELECT fact, timestamp FROM memory WHERE user_id = ? AND topic LIKE ? ORDER BY timestamp DESC LIMIT 5',
              (user_id, f'%{topic.lower()}%'))
    results = c.fetchall()
    conn.close()
    if results:
        return [f"🧠 {r[0]} ({r[1][:10]})" for r in results]
    return []

def get_personality(user_id):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    c.execute('SELECT style, mood FROM personality WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0], result[1]
    return None, None

def update_personality(user_id, style=None, mood=None):
    conn = sqlite3.connect('memory.db')
    c = conn.cursor()
    current = get_personality(user_id)
    if current[0] is None:
        c.execute('INSERT INTO personality (user_id, style, mood, last_interaction) VALUES (?, ?, ?, ?)',
                  (user_id, style or "дружелюбный", mood or "нейтральное", datetime.now().isoformat()))
    else:
        c.execute('UPDATE personality SET style = COALESCE(?, style), mood = COALESCE(?, mood), last_interaction = ? WHERE user_id = ?',
                  (style, mood, datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

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
                  is_admin INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY,
                  total_messages INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def ensure_user(user_id, username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    if user is None:
        c.execute('INSERT INTO users (user_id, username, messages_today, last_reset, is_admin) VALUES (?, ?, ?, ?, ?)',
                  (user_id, username, 0, datetime.now().strftime('%Y-%m-%d'), 0))
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
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200 and len(response.content) > 1000:
                return response.content
        except:
            pass
        try:
            url = "https://backend.craiyon.com/generate"
            headers = {"Content-Type": "application/json"}
            payload = {"prompt": clean_prompt}
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                data = response.json()
                images = data.get("images", [])
                if images:
                    return base64.b64decode(images[0])
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
# ОСНОВНОЙ ИИ
# ============================================================
user_histories = {}

def get_user_history(user_id):
    if user_id not in user_histories:
        user_histories[user_id] = []
    return user_histories[user_id]

def generate_ai_response(user_id, user_text, search_result=None, image_description=None):
    try:
        memories = recall(user_id, user_text)
        
        system_prompt = SUPER_SYSTEM_PROMPT

        if image_description:
            system_prompt += f"\n\n📸 АНАЛИЗ ИЗОБРАЖЕНИЯ (СКРИНШОТ):\n{image_description}\n\nОПИШИ, ЧТО НА ИЗОБРАЖЕНИИ. ДАЙ ПОДРОБНЫЙ АНАЛИЗ."
        
        if search_result:
            system_prompt += f"\n\n🔥 ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА:\n{search_result}\n\nОТВЕЧАЙ НА ОСНОВЕ ЭТИХ ДАННЫХ!"

        if memories:
            memory_text = "\n".join(memories[:3])
            system_prompt += f"\n\n🧠 ПАМЯТЬ:\n{memory_text}"

        history = get_user_history(user_id)
        history_text = ""
        if history:
            last_msgs = history[-10:]
            for msg in last_msgs:
                role = "Пользователь" if msg["role"] == "user" else "Ты"
                history_text += f"{role}: {msg['text']}\n"

        messages = [{"role": "system", "text": system_prompt}]
        if history_text:
            messages.append({"role": "system", "text": f"📜 ИСТОРИЯ:\n{history_text}"})
        messages.append({"role": "user", "text": user_text})

        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 2000},
            "messages": messages
        }

        response = requests.post(url, headers=headers, json=data, timeout=45)
        if response.status_code == 200:
            ans = response.json()["result"]["alternatives"][0]["message"]["text"]
            history.append({"role": "user", "text": user_text})
            history.append({"role": "assistant", "text": ans})
            return ans
        else:
            if image_description:
                return f"📸 *Анализ изображения:*\n\n{image_description}"
            if search_result:
                return f"🔍 *Результаты поиска:*\n\n{search_result}"
            return "⚠️ Ошибка. Попробуй ещё раз."
    except Exception as e:
        print(f"[GPT] Ошибка: {e}")
        if image_description:
            return f"📸 *Анализ изображения:*\n\n{image_description}"
        if search_result:
            return f"🔍 *Результаты поиска:*\n\n{search_result}"
        return "⚠️ Ошибка. Попробуй ещё раз."

# ============================================================
# ГЛАВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text, image_description=None):
    """Главная обработка"""
    
    # Если есть описание изображения — сразу отвечаем
    if image_description:
        return generate_ai_response(user_id, user_text, None, image_description)
    
    # 1. ПОГОДА
    weather_keywords = ['погода', 'weather', 'температура', 'градус', 'дождь', 'снег', 'ветер', 'осадки']
    if any(kw in user_text.lower() for kw in weather_keywords):
        city = extract_city_from_query(user_text)
        if city:
            weather_info = get_weather(city)
            if weather_info:
                return weather_info
            else:
                return f"🌐 Не удалось получить погоду для '{city}'."
        else:
            return "🌐 В каком городе? Напиши: погода в [город]"
    
    # 2. КАРТИНКИ
    if is_image_generation(user_text):
        return None
    
    # 3. МАТЕМАТИКА
    math_result = solve_math(user_text)
    if math_result is not None:
        return f"🧮 *Результат:* `{math_result}`"
    
    # 4. ПОИСК В ИНТЕРНЕТЕ
    search_result = search_internet(user_text)
    
    # 5. ЗАПОМИНАЕМ
    if len(user_text) > 20:
        remember(user_id, "интересное", user_text[:100])
    
    # 6. ОТВЕТ
    return generate_ai_response(user_id, user_text, search_result, None)

# ============================================================
# ОПРЕДЕЛЕНИЕ ТИПА ЗАПРОСА
# ============================================================
def is_image_generation(text):
    image_keywords = ['нарисуй', 'покажи', 'картинку', 'изображение']
    return any(kw in text.lower() for kw in image_keywords)

def solve_math(text):
    text = text.lower().strip()
    has_math_keywords = any(kw in text for kw in ['сколько', 'плюс', 'минус', 'умножить', 'разделить', '/', '*'])
    has_math_symbols = any(sym in text for sym in ['+', '-', '*', '/', '='])
    has_numbers = re.search(r'\d+', text)
    if not has_numbers or not (has_math_keywords or has_math_symbols):
        return None
    clean_expr = text
    clean_expr = clean_expr.replace('плюс', '+').replace('минус', '-')
    clean_expr = clean_expr.replace('умножить', '*').replace('разделить', '/')
    clean_expr = clean_expr.replace('на', '*').replace('сколько', '').replace('будет', '')
    clean_expr = clean_expr.replace('равно', '').replace('?', '').replace(' ', '')
    if re.search(r'[a-zA-Zа-яА-Я]', clean_expr):
        return None
    try:
        return eval(clean_expr)
    except:
        return None

# ============================================================
# МЕНЮ
# ============================================================
def main_menu():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📊 Статус", callback_data="status"),
        types.InlineKeyboardButton("💎 Premium", callback_data="premium"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="stats"),
        types.InlineKeyboardButton("🧹 Очистить", callback_data="clear"),
        types.InlineKeyboardButton("❓ Помощь", callback_data="help"),
        types.InlineKeyboardButton("📩 Отзыв", callback_data="feedback"),
        types.InlineKeyboardButton("🎨 Сгенерировать", callback_data="draw")
    )
    return keyboard

# ============================================================
# КОМАНДЫ
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def status_cmd_from_user(message, user_id):
    ensure_user(user_id, "unknown")
    if user_id == OWNER_ID or is_admin(user_id):
        bot.send_message(message.chat.id, "👑 АДМИН — безлимит!")
        return
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
    bot.send_message(message.chat.id, f"📊 Статус:\n{status_text}")

def premium_cmd_from_user(message, user_id):
    bot.send_message(message.chat.id, "💎 PREMIUM\n\n✅ Безлимит\n💰 50₽/месяц\n📩 @flidges")

def profile_cmd_from_user(message, user_id):
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
        status = "👑 АДМИН"
    elif premium:
        status = f"💎 PREMIUM (до {expires})"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"

    username = message.from_user.username
    user_link = f"@{username}" if username else "Не указан"

    bot.send_message(message.chat.id,
        f"📊 Профиль\n\n🆔 {user_id}\n👤 {user_link}\n💎 {status}\n✉️ {messages}/{FREE_LIMIT}")

def stats_cmd_from_user(message, user_id):
    ensure_user(user_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    if user_id == OWNER_ID or is_admin(user_id):
        c.execute('SELECT SUM(messages_today) FROM users')
        today_messages = c.fetchone()[0] or 0
        c.execute('SELECT SUM(total_messages) FROM total_stats')
        all_time_messages = c.fetchone()[0] or 0
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE premium = 1')
        premium_users = c.fetchone()[0]
        conn.close()
        bot.send_message(message.chat.id,
            f"📊 Статистика\n\n👥 {total_users}\n💎 {premium_users}\n📨 Сегодня: {today_messages}")
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

    bot.send_message(message.chat.id,
        f"📊 Твоя статистика\n\n👤 {user_status}\n✉️ Сегодня: {user_messages}\n📨 Всего: {total_user_messages}")

def clear_cmd_from_user(message, user_id):
    if user_id in user_histories:
        user_histories[user_id] = []
    bot.send_message(message.chat.id, "🧹 Очищено!")

def help_cmd_from_user(message, user_id):
    text = (
        "🧠 *AWESOME AI — ЗНАЕТ ВСЁ!*\n\n"
        "📸 Я умею АНАЛИЗИРОВАТЬ СКРИНШОТЫ!\n"
        "Просто отправь мне фото/скриншот и напиши:\n"
        "«что тут на скрине» или «опиши»\n\n"
        "🌐 Я ищу в Google, Wikipedia и DuckDuckGo\n"
        "📋 *Команды:*\n"
        "/start — Меню\n/help — Помощь\n"
        "/status — Статус\n/premium — Premium\n"
        "/profile — Профиль\n/stats — Статистика\n"
        "/clear — Очистить историю\n"
        "/draw [описание] — Картинка\n\n"
        "📌 *Примеры:*\n"
        "• кто такой Кобяков из А4\n"
        "• умер ли Оливер Три\n"
        "• реши уравнение 2x + 5 = 15"
    )
    if user_id == OWNER_ID or is_admin(user_id):
        text += "\n\n👑 *Админ:* /giveadmin /deladmin /giveprem /delprem /mute /unmute /ban /unban"
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# ============================================================
# ОСТАЛЬНЫЕ КОМАНДЫ
# ============================================================
@bot.message_handler(commands=['start'])
def start(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    user_id = m.from_user.id
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    init_memory_db()
    bot.send_message(m.chat.id,
        f"🧠 *Привет, {m.from_user.first_name}!*\n\n"
        f"Я AWESOME AI — **ЗНАЮ ВСЁ!**\n"
        f"Меня создал AWESOME.\n\n"
        f"📸 Я умею АНАЛИЗИРОВАТЬ СКРИНШОТЫ!\n"
        f"🌐 Я ищу в Google, Wikipedia и DuckDuckGo.\n"
        f"👇 *Выбери действие:*",
        reply_markup=main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['help'])
def help_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    help_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    status_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    premium_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    profile_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    stats_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    clear_cmd_from_user(m, m.from_user.id)

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    text = m.text.replace('/feedback', '').strip()
    if not text:
        bot.send_message(m.chat.id, "❌ /feedback [текст]")
        return
    bot.send_message(m.chat.id, "✅ Спасибо!")
    bot.send_message(OWNER_ID, f"📩 Отзыв: {text}")

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    prompt = m.text.replace('/draw', '').strip()
    if not prompt:
        bot.send_message(m.chat.id, "❌ /draw [описание]")
        return
    generate_and_send_image(m, prompt)

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
def is_authorized(user_id):
    return user_id == OWNER_ID or is_admin(user_id)

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    bot.send_message(m.chat.id,
        "🛡️ *АДМИН:*\n/giveadmin [ID]\n/deladmin [ID]\n/giveprem [ID] [срок]\n/delprem [ID]\n/mute [ID]\n/unmute [ID]\n/ban [ID]\n/unban [ID]", parse_mode='Markdown')

@bot.message_handler(commands=['giveadmin'])
def giveadmin_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /giveadmin [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    set_admin(target_id, True)
    bot.send_message(m.chat.id, f"✅ {target_id} — админ.")

@bot.message_handler(commands=['deladmin'])
def deladmin_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /deladmin [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    set_admin(target_id, False)
    bot.send_message(m.chat.id, f"❌ {target_id} больше не админ.")

@bot.message_handler(commands=['giveprem'])
def giveprem_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 3:
        bot.send_message(m.chat.id, "❌ /giveprem [ID] [срок]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    duration = args[2].lower()
    if set_premium(target_id, duration):
        bot.send_message(m.chat.id, f"✅ Premium {target_id} на {duration}")
    else:
        bot.send_message(m.chat.id, "❌ Неверный срок.")

@bot.message_handler(commands=['delprem'])
def delprem_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /delprem [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    remove_premium(target_id)
    bot.send_message(m.chat.id, f"✅ Premium отключён у {target_id}")

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /mute [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    mute_user(target_id)
    bot.send_message(m.chat.id, f"🔇 {target_id} замучен")

@bot.message_handler(commands=['unmute'])
def unmute_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /unmute [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    unmute_user(target_id)
    bot.send_message(m.chat.id, f"🔊 {target_id} размучен")

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /ban [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    ban_user(target_id)
    bot.send_message(m.chat.id, f"🚫 {target_id} забанен")

@bot.message_handler(commands=['unban'])
def unban_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ /unban [ID]")
        return
    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID цифры!")
        return
    target_id = int(target_id)
    ensure_user(target_id, "unknown")
    unban_user(target_id)
    bot.send_message(m.chat.id, f"✅ {target_id} разбанен")

# ============================================================
# КАРТИНКИ
# ============================================================
def generate_and_send_image(m, prompt):
    user_id = m.from_user.id
    if not can_send_message(user_id):
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        return

    title = fix_title(prompt)
    bot.send_message(m.chat.id, f"🎨 Генерирую: *{title}*...", parse_mode='Markdown')

    image_data = generate_image(prompt)

    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(m.chat.id, photo=image_data, caption=f"🎨 *{title}*\n\n✨ AWESOME AI", parse_mode='Markdown')
        except:
            bot.send_message(m.chat.id, "⚠️ Ошибка при отправке")
    else:
        bot.send_message(m.chat.id, "⚠️ Не удалось сгенерировать.")

# ============================================================
# ФОТО (АНАЛИЗ СКРИНШОТОВ)
# ============================================================
@bot.message_handler(content_types=['photo'])
def handle_photo(m):
    user_id = m.from_user.id
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    
    if is_banned(user_id):
        bot.send_message(m.chat.id, "🚫 Ты забанен!")
        return
    if not can_send_message(user_id):
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        return
    
    bot.send_chat_action(m.chat.id, 'typing')
    
    try:
        # Скачиваем фото
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        # Анализируем изображение
        analysis = analyze_image_from_file(downloaded)
        
        increment_messages(user_id)
        
        # Если есть текст в caption — используем его как вопрос
        caption = m.caption or "Опиши, что на этом изображении"
        
        # Отправляем анализ
        bot.send_message(m.chat.id, analysis, parse_mode='Markdown')
        
        # Дополнительно отвечаем на вопрос (если он есть)
        if m.caption and len(m.caption) > 3:
            response = process_message(user_id, m.caption, analysis)
            if response:
                bot.send_message(m.chat.id, response, parse_mode='Markdown')
        
    except Exception as e:
        bot.send_message(m.chat.id, f"⚠️ Ошибка при анализе: {e}")

# ============================================================
# ГОЛОС
# ============================================================
@bot.message_handler(content_types=['voice'])
def handle_voice(m):
    user_id = m.from_user.id
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    if is_banned(user_id):
        bot.send_message(m.chat.id, "🚫 Ты забанен!")
        return
    if not can_send_message(user_id):
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        return
    bot.send_chat_action(m.chat.id, 'typing')
    try:
        file_info = bot.get_file(m.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)
        recognized = stt(downloaded)
        increment_messages(user_id)
        if recognized:
            bot.send_message(m.chat.id, f"🎤 *Распознано:*\n{recognized}", parse_mode='Markdown')
            response = process_message(user_id, recognized)
            if response:
                bot.send_message(m.chat.id, response, parse_mode='Markdown')
        else:
            bot.send_message(m.chat.id, "🎤 Не разобрал.")
    except Exception as e:
        bot.send_message(m.chat.id, f"⚠️ Ошибка: {e}")

# ============================================================
# ГОЛОС (ФУНКЦИЯ)
# ============================================================
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
    user_id = m.from_user.id
    username = m.from_user.username or "unknown"
    ensure_user(user_id, username)
    reset_messages_if_needed(user_id)
    
    if is_banned(user_id):
        bot.send_message(m.chat.id, "🚫 Ты забанен!")
        return
    if not can_send_message(user_id):
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день!\nКупи Premium: /premium")
        return

    text_clean = m.text.strip()
    if text_clean.startswith('/'):
        m.text = text_clean
        bot.process_new_messages([m])
        return

    bot.send_chat_action(m.chat.id, 'typing')

    if is_image_generation(m.text):
        generate_and_send_image(m, m.text)
        return

    increment_messages(user_id)
    response = process_message(user_id, m.text)
    
    if response:
        bot.send_message(m.chat.id, response, parse_mode='Markdown')

# ============================================================
# КНОПКИ
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        user_id = call.from_user.id
        ensure_user(user_id, call.from_user.username or "unknown")
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
            bot.send_message(call.message.chat.id, "📩 /feedback [текст]")
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🎨 /draw [описание]")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"⚠️ Ошибка: {e}")

# ============================================================
# ОСТАЛЬНОЕ
# ============================================================
@bot.message_handler(content_types=['video', 'document', 'audio'])
def other(m):
    bot.send_message(m.chat.id, "📁 Пока не умею обрабатывать этот тип файлов.")

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — ЗНАЕТ ВСЁ И ВИДИТ СКРИНЫ!")
print("=" * 60)
print(f"🤖 Бот: @{bot.get_me().username}")
print("📸 АНАЛИЗ СКРИНШОТОВ — ВКЛЮЧЁН!")
print("🌐 ПОИСК: Google + Wikipedia + DuckDuckGo")
print("💾 ПАМЯТЬ: включена")
print("=" * 60)
print("БОТ ГОТОВ!")
print("=" * 60)

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
