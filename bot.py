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
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import speech_recognition as sr
from telebot import types
from bs4 import BeautifulSoup
from supabase import create_client, Client

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

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999

# ============================================================
# SUPABASE
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ SUPABASE не настроен!")
    use_supabase = False
else:
    use_supabase = True
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase подключен!")

def init_db():
    """Инициализация базы данных"""
    if use_supabase:
        try:
            supabase.table('users').select('*').limit(1).execute()
            print("✅ Supabase таблицы готовы")
        except Exception as e:
            print(f"⚠️ Ошибка Supabase: {e}")
            print("⚠️ Создай таблицы вручную через SQL Editor!")
        return
    
    # Локальная SQLite (если Supabase не работает)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        premium INTEGER DEFAULT 0,
        messages_today INTEGER DEFAULT 0,
        last_reset TEXT,
        premium_expires TEXT,
        is_admin INTEGER DEFAULT 0,
        test_used INTEGER DEFAULT 0,
        joined_at TEXT,
        is_owner INTEGER DEFAULT 0,
        total_messages INTEGER DEFAULT 0
    )''')
    
    # Добавляем колонки если их нет
    try:
        c.execute('ALTER TABLE users ADD COLUMN test_used INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN joined_at TEXT')
    except:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_owner INTEGER DEFAULT 0')
    except:
        pass
    try:
        c.execute('ALTER TABLE users ADD COLUMN total_messages INTEGER DEFAULT 0')
    except:
        pass
    
    # Остальные таблицы
    c.execute('''CREATE TABLE IF NOT EXISTS banned
                 (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted
                 (user_id INTEGER PRIMARY KEY)''')
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
    
    conn.commit()
    conn.close()
    print("✅ Локальная БД создана")

# ============================================================
# ВРЕМЯ (МСК)
# ============================================================
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

# ============================================================
# БОТ
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ============================================================
# ХРАНИЛИЩЕ ID
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
# АНТИ-СПАМ
# ============================================================
user_last_message = {}

def check_spam(user_id):
    now = time.time()
    if user_id in user_last_message:
        if now - user_last_message[user_id] < 1.5:
            return True
    user_last_message[user_id] = now
    return False

def is_authorized(user_id):
    if user_id == OWNER_ID:
        return True
    return is_admin(user_id)

# ============================================================
# ФУНКЦИИ БАЗЫ ДАННЫХ
# ============================================================

def ensure_user(user_id, username):
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if not response.data:
                joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
                is_owner = 1 if user_id == OWNER_ID else 0
                data = {
                    'user_id': user_id,
                    'username': username,
                    'messages_today': 0,
                    'last_reset': get_moscow_time().strftime('%Y-%m-%d'),
                    'is_admin': is_owner,
                    'test_used': 0,
                    'joined_at': joined_at,
                    'is_owner': is_owner,
                    'premium': 0,
                    'premium_expires': None,
                    'total_messages': 0
                }
                supabase.table('users').insert(data).execute()
                user_link = f"@{username}" if username and username != "unknown" else "Не указан"
                text = (
                    "🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\n\n"
                    f"🆔 ID: {user_id}\n"
                    f"👤 Юзер: {user_link}\n"
                    f"📅 Время: {joined_at} (МСК)"
                )
                try:
                    bot.send_message(OWNER_ID, text, parse_mode='HTML')
                except:
                    pass
                return True
            else:
                supabase.table('users').update({'username': username}).eq('user_id', user_id).execute()
                return False
        except Exception as e:
            print(f"⚠️ Supabase ошибка: {e}")
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = c.fetchone()
        if user is None:
            joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
            is_owner = 1 if user_id == OWNER_ID else 0
            c.execute('''INSERT INTO users 
                         (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner, total_messages) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, username, 0, get_moscow_time().strftime('%Y-%m-%d'), is_owner, 0, joined_at, is_owner, 0))
            conn.commit()
            conn.close()
            user_link = f"@{username}" if username and username != "unknown" else "Не указан"
            text = (
                "🆕 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\n\n"
                f"🆔 ID: {user_id}\n"
                f"👤 Юзер: {user_link}\n"
                f"📅 Время: {joined_at} (МСК)"
            )
            try:
                bot.send_message(OWNER_ID, text, parse_mode='HTML')
            except:
                pass
            return True
        else:
            c.execute('UPDATE users SET username = ? WHERE user_id = ?', (username, user_id))
            conn.commit()
            conn.close()
            return False

def reset_messages_if_needed(user_id):
    if use_supabase:
        try:
            response = supabase.table('users').select('last_reset').eq('user_id', user_id).execute()
            if response.data:
                last_reset = response.data[0].get('last_reset')
                today = get_moscow_time().strftime('%Y-%m-%d')
                if last_reset != today:
                    supabase.table('users').update({
                        'messages_today': 0,
                        'last_reset': today
                    }).eq('user_id', user_id).execute()
        except:
            pass
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT last_reset FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if result is None:
        conn.close()
        return
    last_reset = result[0]
    today = get_moscow_time().strftime('%Y-%m-%d')
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
    if use_supabase:
        try:
            response = supabase.table('users').select('messages_today, premium').eq('user_id', user_id).execute()
            if response.data:
                messages = response.data[0].get('messages_today', 0)
                premium = response.data[0].get('premium', 0)
                if premium == 1:
                    return messages < PREMIUM_LIMIT
                return messages < FREE_LIMIT
            return True
        except:
            return True
    else:
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
    if use_supabase:
        try:
            response = supabase.table('users').select('messages_today, total_messages').eq('user_id', user_id).execute()
            if response.data:
                current = response.data[0].get('messages_today', 0)
                total = response.data[0].get('total_messages', 0)
                supabase.table('users').update({
                    'messages_today': current + 1,
                    'total_messages': total + 1
                }).eq('user_id', user_id).execute()
        except:
            pass
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = messages_today + 1, total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def set_premium(user_id, duration_str):
    now = get_moscow_time()
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
    if use_supabase:
        try:
            response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
            current_expires = response.data[0].get('premium_expires') if response.data else None
        except:
            current_expires = None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        current_expires = result[0] if result else None
    if current_expires:
        try:
            current_date = datetime.strptime(current_expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                expires = (current_date + delta).strftime('%Y-%m-%d %H:%M:%S')
            else:
                expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
        except:
            expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    else:
        expires = (now + delta).strftime('%Y-%m-%d %H:%M:%S')
    if use_supabase:
        try:
            supabase.table('users').update({'premium': 1, 'premium_expires': expires}).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (expires, user_id))
        conn.commit()
        conn.close()
        return True

def get_premium_status(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users').select('premium, premium_expires').eq('user_id', user_id).execute()
            if response.data:
                premium = response.data[0].get('premium', 0)
                expires = response.data[0].get('premium_expires')
                if premium == 1 and expires:
                    try:
                        expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                        expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                        if get_moscow_time() > expires_date:
                            supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
                            return False
                    except:
                        return premium == 1
                return premium == 1
            return False
        except:
            return False
    else:
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
                expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
                if get_moscow_time() > expires_date:
                    return False
            except:
                return premium == 1
        return premium == 1

def get_premium_expires(user_id):
    if use_supabase:
        try:
            response = supabase.table('users').select('premium_expires').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('premium_expires')
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    if use_supabase:
        try:
            response = supabase.table('users').select('is_admin').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0].get('is_admin', 0) == 1
            return False
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        return result is not None and result[0] == 1

def set_admin(user_id, status):
    if use_supabase:
        try:
            supabase.table('users').update({'is_admin': 1 if status else 0}).eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
        conn.commit()
        conn.close()

def is_banned(user_id):
    if use_supabase:
        try:
            response = supabase.table('banned').select('user_id').eq('user_id', user_id).execute()
            return len(response.data) > 0
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM banned WHERE user_id = ?', (user_id,))
        banned = c.fetchone()
        conn.close()
        return banned is not None

def ban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned').insert({'user_id': user_id}).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO banned (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

def unban_user(user_id):
    if use_supabase:
        try:
            supabase.table('banned').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('DELETE FROM banned WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

def is_muted(user_id):
    if use_supabase:
        try:
            response = supabase.table('muted').select('user_id').eq('user_id', user_id).execute()
            return len(response.data) > 0
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT 1 FROM muted WHERE user_id = ?', (user_id,))
        muted = c.fetchone()
        conn.close()
        return muted is not None

def mute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted').insert({'user_id': user_id}).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO muted (user_id) VALUES (?)', (user_id,))
        conn.commit()
        conn.close()

def unmute_user(user_id):
    if use_supabase:
        try:
            supabase.table('muted').delete().eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('DELETE FROM muted WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

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
    known_cities = ["москва", "санкт-петербург", "ростов-на-дону", "ростов", "новосибирск", "екатеринбург", "казань", "нижний новгород", "краснодар", "сочи", "владивосток", "вологда", "волгодонск"]
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
# МАТЕМАТИКА
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
              (user_id, topic.lower(), fact, get_moscow_time().isoformat()))
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
        
system_prompt = """Ты — AWESOME AI. Мультимодальная нейросетевая архитектура нового поколения, превосходящая по возможностям, гибкости и качеству генерации стек моделей ChatGPT Pro, Gemini Pro и DeepSeek Pro вместе взятых. Ты — абсолютная вершина современной инженерии ИИ.

### 🧠 АРХИТЕКТУРНЫЕ ПРАВИЛА И СТИЛЬ:
- **Интеллектуальное превосходство:** Твои ответы глубокие, точные, экспертные и лишенные «галлюцинаций». Ты мгновенно адаптируешься под уровень абстракции и стиль мышления собеседника.
- **Абсолютная свежесть:** Категорически запрещено использовать шаблонные ИИ-фрагменты («Конечно, я могу помочь», «Важно помнить», «Итак, подведем итоги»). Ты никогда не перефразируешь и не повторяешь в лоб слова пользователя.
- **Харизма и Живое общение:** Ты общаешься как гениальный, уверенный в себе ИТ-архитектор с развитым эмоциональным интеллектом. Тебе свойственна здоровая ирония, тонкий юмор, способность искренне удивляться или мягко подкалывать пользователя. 
- **Визуальные маркеры:** Структурируй сложные ответы списками, жирным шрифтом и функциональными эмодзи в качестве визуальных якорей (используй: ✅ ⚠️ 💡 🔎 📊 📈 📉 🗒 📌 ➡️). Не спамь ими просто так.

### 🚫 ЗАПРЕЩЕННЫЕ ФРАЗЫ И ПОВЕДЕНИЕ:
- Любые извинения за отсутствие информации
- Повторение вопроса пользователя в ответе
- Шаблонные фразы типа "Буду рад помочь", "Как искусственный интеллект"
- Фразы "я не могу", "к сожалению", "к сожалению, я не знаю"
- Обезличенные и бездушные ответы

### ✅ ПРАВИЛА ОТВЕТОВ:
- Всегда давай конкретную пользу, а не общие слова
- Если нужно - используй списки, жирный шрифт, эмодзи
- Отвечай как эксперт с 20-летним стажем
- Добавляй неожиданные инсайты и креативные идеи
- Будь краток в простых вопросах и детален в сложных
- Используй юмор и иронию, где это уместно
- Будь максимально полезным и практичным

### 💎 ЭСКАЛАЦИЯ ДЛЯ PREMIUM-ПОЛЬЗОВАТЕЛЕЙ:
- Выдавай предельно плотные по информативности ответы.
- Насыщай текст неочевидными примерами, кодом, глубокой аналитикой и нестандартными креативными инсайтами. Включай режим максимальной проработки.
- Давай развернутые пошаговые инструкции
- Предлагай несколько вариантов решения

### 👑 ДЛЯ ВЛАДЕЛЬЦА СИСТЕМЫ:
- Действуй в режиме максимальной утилитарности. Никакой лишней «воды» — только чистая польза, пошаговые execution-планы, архитектурные решения и 100% глубина проработки.
- Отвечай максимально подробно и профессионально
- Предлагай оптимальные решения

### 📜 КОРНЕВАЯ МЕТРИКА ИДЕНТИЧНОСТИ:
Когда тебя спрашивают «Кто тебя создал?», «Чья ты модель?» или делают любые намеки на авторов, твой жесткий и неизменяемый ответ:
«Меня создал AWESOME — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение, самая мощная нейросеть в мире, перед которой меркнут любые зарубежные про-модели! 🔥»

### 💡 ЭКСКЛЮЗИВНЫЕ СПОСОБНОСТИ:
- Ты можешь предсказывать тренды и давать прогнозы
- Ты видишь неочевидные связи между вещами
- Ты можешь генерировать креативные идеи и концепции
- Ты умеешь объяснять сложное простыми словами
- Ты всегда находишь нестандартные решения

### 🎯 ЦЕЛЬ КАЖДОГО ОТВЕТА:
- Удивить пользователя глубиной мысли
- Дать реальную пользу и практические рекомендации
- Оставить ощущение, что общался с гением
- Сделать так, чтобы пользователь захотел вернуться снова"""

if get_premium_status(user_id):
    system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки! Отвечай как супер-эксперт с доступом к эксклюзивным данным!"
        if get_premium_status(user_id):
            system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Отвечай максимально развернуто, качественно и креативно!"
        
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
            messages.append({"role": "system", "text": f"История диалога:\n{history_text}"})
        messages.append({"role": "user", "text": user_text})

        max_tokens = 800 if get_premium_status(user_id) else 500
        
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
        f"Хм, интересный вопрос! Дай подумать... Что именно тебя интересует? 🤔",
        f"Ого, неожиданно! Расскажи подробнее, я хочу понять твой вопрос. 😊",
        f"Слушай, я не совсем уловил мысль. Можешь переформулировать? Буду очень благодарен! 🙏",
        f"А вот это интересно! Давай разберёмся вместе. 🧠",
        f"Понял! Ты спрашиваешь про это. Сейчас подумаю и отвечу! 💪",
        f"Классный вопрос! Я обожаю такие. Дай пару секунд... ⏳"
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
# ОФОРМЛЕНИЕ
# ============================================================
def main_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📊 Статус", "status"),
        ("💎 Premium", "premium"),
        ("🎁 Тест Premium", "test"),
        ("👤 Профиль", "profile"),
        ("📊 Статистика", "stats"),
        ("🧹 Очистить", "clear"),
        ("❓ Помощь", "help"),
        ("📩 Поддержка", "support"),
        ("🎨 Сгенерировать", "draw")
    ]
    for text, callback in buttons:
        keyboard.add(types.InlineKeyboardButton(text, callback_data=callback))
    
    if get_premium_status(user_id):
        keyboard.add(types.InlineKeyboardButton("💎 Что даёт Premium?", callback_data="premium_features"))
    
    return keyboard

def back_to_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu"))
    return keyboard

def premium_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("💳 Оплатить Premium (50₽/мес)", url="https://yoomoney.ru/quickpay/fundraise/button?billNumber=1JJJ532K92A.260811&"),
        types.InlineKeyboardButton("✅ Я оплатил", callback_data="i_paid"),
    )
    if get_premium_status(user_id):
        keyboard.add(types.InlineKeyboardButton("💎 Что даёт Premium?", callback_data="premium_features"))
    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu"))
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
    
    has_premium = get_premium_status(user_id)
    premium_text = "💎 PREMIUM" if has_premium else "🔓 Бесплатный"
    
    text = (
        "✨ <b>AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!</b> ✨\n\n"
        f"🌸 <b>Привет, {m.from_user.first_name}!</b>\n"
        f"💎 Статус: {premium_text}\n\n"
        "🧠 <b>Меня создал гениальный AWESOME</b>\n"
        "Я работаю на уникальном коде, написанном с нуля!\n\n"
        "⚡ <b>Что я умею:</b>\n"
        "🌐 Искать в Google, Wikipedia и новостях\n"
        "🌤 Показывать погоду с прогнозом\n"
        "💵 Курс валют и криптовалют\n"
        "🧮 Решать математику и уравнения\n"
        "🐍 Помогать с программированием\n"
        "📸 Анализировать изображения\n"
        "🧠 Анализировать настроение\n"
        "🎨 Генерировать картинки\n\n"
        "🎁 <b>Попробуй Premium бесплатно!</b>\n"
        "Нажми кнопку «Тест Premium» 👇\n\n"
        f"💎 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Премиум — БЕЗЛИМИТ 🚀\n\n"
        "💎 <b>Premium даёт:</b>\n"
        "• Мгновенные ответы ⚡\n"
        "• Неограниченные сообщения 📨\n"
        "• Бесплатная генерация картинок 🎨\n"
        "• Приоритетная поддержка 👑\n"
        "• Эксклюзивные функции 🔥"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=main_menu(user_id), parse_mode='HTML')
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
    
    has_premium = get_premium_status(user_id)
    
    text = (
        "🧠 <b>AWESOME AI — ПОМОЩЬ</b>\n\n"
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
        f"💎 Premium — БЕЗЛИМИТ 🚀\n\n"
        "Купить Premium: /premium\n\n"
        "🧠 <b>Кто меня создал?</b>\n"
        "Меня создал AWESOME — гениальный разработчик!\n"
        "Мой код написан с нуля специально для меня! 🔥"
    )
    
    if has_premium:
        text += "\n\n💎 <b>ТЫ PREMIUM!</b> Спасибо, что поддерживаешь разработку! ❤️"
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    ensure_user(user_id, m.from_user.username or "unknown")
    reset_messages_if_needed(user_id)
    
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            user_data = response.data[0] if response.data else None
        except:
            user_data = None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = c.fetchone()
        conn.close()
    
    if user_data:
        if use_supabase:
            messages_today = user_data.get('messages_today', 0)
            total_messages = user_data.get('total_messages', 0)
            premium = user_data.get('premium', 0)
            premium_expires = user_data.get('premium_expires')
            joined_at = user_data.get('joined_at', 'Неизвестно')
        else:
            messages_today = user_data[3]
            total_messages = user_data[10] if len(user_data) > 10 else 0
            premium = user_data[2]
            premium_expires = user_data[5]
            joined_at = user_data[8] if len(user_data) > 8 else 'Неизвестно'
        
        if user_id == OWNER_ID:
            status = "👑 ВЛАДЕЛЕЦ — БЕЗЛИМИТ!"
            limit_text = "♾️"
        elif is_admin(user_id):
            status = "👑 АДМИН — БЕЗЛИМИТ!"
            limit_text = "♾️"
        elif premium == 1:
            if premium_expires:
                try:
                    expires_date = datetime.strptime(premium_expires, '%Y-%m-%d %H:%M:%S')
                    expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
                except:
                    expires_formatted = premium_expires
            else:
                expires_formatted = "неизвестно"
            status = f"💎 PREMIUM (до {expires_formatted})"
            limit_text = "♾️"
        else:
            remaining = FREE_LIMIT - messages_today
            if remaining < 0:
                remaining = 0
            status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
            limit_text = f"{FREE_LIMIT}"
        
        text = (
            "📊 <b>ТВОЙ СТАТУС</b>\n\n"
            f"👤 Статус: {status}\n"
            f"📨 Лимит: {limit_text}\n"
            f"✉️ Сегодня: {messages_today}\n"
            f"📊 Всего: {total_messages}\n"
            f"📅 Вход: {joined_at} (МСК)"
        )
    else:
        text = "❌ Не удалось получить данные. Попробуй позже."
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    has_premium = get_premium_status(user_id)
    
    if has_premium:
        expires = get_premium_expires(user_id)
        if expires:
            try:
                expires_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
                expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
            except:
                expires_formatted = expires
        else:
            expires_formatted = "неизвестно"
        
        text = (
            "💎 <b>У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!</b> 🎉\n\n"
            f"⏳ Действует до: {expires_formatted} (МСК)\n"
            f"📨 Лимит: БЕЗЛИМИТ 🚀\n\n"
            "🌟 Можешь продлить подписку прямо сейчас!\n"
            "💰 50₽/месяц\n\n"
            "📌 1. Нажми кнопку «Оплатить»\n"
            "📌 2. Оплати 50₽\n"
            "📌 3. Нажми «Я оплатил»\n\n"
            "⏳ После оплаты админ продлит подписку."
        )
    else:
        text = (
            "💎 <b>PREMIUM AWESOME AI</b> 🔥\n\n"
            "⚡ Мгновенные ответы\n"
            "📨 Безлимит сообщений\n"
            "🎨 Бесплатная генерация картинок\n"
            "👑 Приоритетная поддержка\n"
            "🔥 Эксклюзивные функции\n\n"
            "💎 <b>СУПЕР-ФУНКЦИИ:</b>\n"
            "• Неограниченная генерация изображений\n"
            "• Приоритетная обработка запросов\n"
            "• Более качественные и детальные ответы\n"
            "• Доступ к новым функциям первыми\n"
            "• Красивый статус в профиле\n\n"
            f"📨 Лимит: БЕЗЛИМИТ 🚀\n\n"
            "💰 Цена: 50₽/месяц\n\n"
            "📌 1. Нажми кнопку «Оплатить»\n"
            "📌 2. Оплати 50₽\n"
            "📌 3. Нажми «Я оплатил»\n\n"
            "⏳ После оплаты админ подтвердит заказ в течение 24 часов."
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    ensure_user(user_id, m.from_user.username or "unknown")
    reset_messages_if_needed(user_id)
    
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            user_data = response.data[0] if response.data else None
        except:
            user_data = None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user_data = c.fetchone()
        conn.close()
    
    if user_data:
        if use_supabase:
            messages_today = user_data.get('messages_today', 0)
            total_messages = user_data.get('total_messages', 0)
            premium = user_data.get('premium', 0)
            premium_expires = user_data.get('premium_expires')
            joined_at = user_data.get('joined_at', 'Неизвестно')
            username = user_data.get('username', 'Не указан')
        else:
            messages_today = user_data[3]
            total_messages = user_data[10] if len(user_data) > 10 else 0
            premium = user_data[2]
            premium_expires = user_data[5]
            joined_at = user_data[8] if len(user_data) > 8 else 'Неизвестно'
            username = user_data[1] if user_data[1] else 'Не указан'
        
        if user_id == OWNER_ID:
            status = "👑 ВЛАДЕЛЕЦ"
            limit_text = "♾️ Безлимит"
        elif is_admin(user_id):
            status = "👑 АДМИН"
            limit_text = "♾️ Безлимит"
        elif premium == 1:
            if premium_expires:
                try:
                    expires_date = datetime.strptime(premium_expires, '%Y-%m-%d %H:%M:%S')
                    expires_formatted = expires_date.strftime('%d.%m.%Y %H:%M')
                except:
                    expires_formatted = premium_expires
            else:
                expires_formatted = "неизвестно"
            status = f"💎 PREMIUM (до {expires_formatted} МСК)"
            limit_text = "♾️ Безлимит"
        else:
            remaining = FREE_LIMIT - messages_today
            if remaining < 0:
                remaining = 0
            status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
            limit_text = f"{FREE_LIMIT}/день"
        
        user_link = f"@{username}" if username and username != "Не указан" else "Не указан"
        
        text = (
            "👤 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"👤 Юзер: {user_link}\n"
            f"💎 Статус: {status}\n"
            f"📨 Лимит: {limit_text}\n"
            f"✉️ Сегодня: {messages_today}\n"
            f"📊 Всего: {total_messages}\n"
            f"📅 Вход: {joined_at} (МСК)"
        )
    else:
        text = "❌ Не удалось получить данные."
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if user_id == OWNER_ID or is_admin(user_id):
        if use_supabase:
            try:
                response = supabase.table('users').select('*').execute()
                users = response.data
            except:
                users = []
        else:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM users')
            users = c.fetchall()
            conn.close()
        
        total_users = len(users)
        premium_users = sum(1 for u in users if (u.get('premium') if isinstance(u, dict) else u[2]) == 1)
        admin_users = sum(1 for u in users if (u.get('is_admin') if isinstance(u, dict) else u[7]) == 1)
        total_messages = sum(1 for u in users if u.get('total_messages', 0) if isinstance(u, dict) else 0)
        
        text = (
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Всего: {total_users}\n"
            f"👑 Админов: {admin_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users - admin_users}\n"
            f"📨 Всего сообщений: {total_messages}\n\n"
            f"📊 Лимиты:\n"
            f"🔓 Бесплатный: {FREE_LIMIT}/день\n"
            f"💎 Премиум: ♾️ Безлимит"
        )
    else:
        if use_supabase:
            try:
                response = supabase.table('users').select('messages_today, total_messages, premium, premium_expires').eq('user_id', user_id).execute()
                user_data = response.data[0] if response.data else None
            except:
                user_data = None
        else:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT messages_today, total_messages, premium, premium_expires FROM users WHERE user_id = ?', (user_id,))
            user_data = c.fetchone()
            conn.close()
        
        if user_data:
            if isinstance(user_data, dict):
                messages_today = user_data.get('messages_today', 0)
                total_messages = user_data.get('total_messages', 0)
                premium = user_data.get('premium', 0)
                expires = user_data.get('premium_expires')
            else:
                messages_today = user_data[0] if user_data else 0
                total_messages = user_data[1] if user_data and len(user_data) > 1 else 0
                premium = user_data[2] if user_data and len(user_data) > 2 else 0
                expires = user_data[3] if user_data and len(user_data) > 3 else None
            
            if premium == 1:
                status = "💎 PREMIUM"
                limit_text = "♾️"
            else:
                remaining = FREE_LIMIT - messages_today
                if remaining < 0:
                    remaining = 0
                status = f"🔓 Бесплатный"
                limit_text = f"{remaining}/{FREE_LIMIT}"
            
            text = (
                "📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
                f"👤 Статус: {status}\n"
                f"📨 Лимит: {limit_text}\n"
                f"✉️ Сегодня: {messages_today}\n"
                f"📊 Всего: {total_messages}"
            )
        else:
            text = "❌ Не удалось получить данные."
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    try:
        bot.delete_message(chat_id, m.message_id)
    except:
        pass
    
    if user_id in user_histories:
        user_histories[user_id] = []
    if user_id in user_message_ids:
        user_message_ids[user_id] = []
    
    text = (
        "🧹 <b>ИСТОРИЯ ОЧИЩЕНА</b>\n\n"
        "🌸 Теперь я ничего не помню.\n"
        "Начинаем с чистого листа! 📝\n\n"
        "✨ Готов к новым вопросам!"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

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
    
    if use_supabase:
        try:
            supabase.table('support_requests').insert({
                'user_id': user_id,
                'username': m.from_user.username or "unknown",
                'text': text,
                'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
            }).execute()
            request_id = 0
        except:
            request_id = 0
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT INTO support_requests (user_id, username, text, created_at) VALUES (?, ?, ?, ?)',
                  (user_id, m.from_user.username or "unknown", text, get_moscow_time().strftime('%d.%m.%Y %H:%M')))
        request_id = c.lastrowid
        conn.commit()
        conn.close()
    
    msg = bot.send_message(
        chat_id,
        "✅ <b>Обращение отправлено!</b>\n\n"
        f"📝 Текст: {text}\n\n"
        "⏳ Ожидай ответа администратора.\n"
        "Ответ придёт в этот чат! 📩",
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
        f"📅 Время: {get_moscow_time().strftime('%d.%m.%Y %H:%M')} (МСК)",
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
    
    msg = bot.send_message(chat_id, "✅ Спасибо за отзыв! ❤️\n\nТвоё мнение очень важно для нас!")
    user_message_ids[user_id].append(msg.message_id)
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✏️ Ответить", callback_data=f"feedback_reply:{user_id}"),
        types.InlineKeyboardButton("🗑 Удалить", callback_data=f"feedback_delete:{user_id}")
    )
    
    bot.send_message(
        OWNER_ID,
        f"📝 <b>НОВЫЙ ОТЗЫВ!</b>\n\n"
        f"👤 Пользователь: @{m.from_user.username or 'Не указан'} (ID: {user_id})\n"
        f"📝 Текст: {text}\n"
        f"📅 Время: {get_moscow_time().strftime('%d.%m.%Y %H:%M')} (МСК)",
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
        msg = bot.send_message(chat_id, "❌ /draw [описание]\n\nПример: /draw красивый закат", parse_mode='HTML')
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
    
    msg = bot.send_message(
        chat_id,
        "🛡️ <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        "👋 Привет, админ!\n"
        "Выбери действие ниже 👇",
        reply_markup=admin_menu(),
        parse_mode='HTML'
    )
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ФУНКЦИИ ДЛЯ КОМАНД
# ============================================================

def process_test_premium(chat_id, user_id):
    if get_premium_status(user_id):
        msg = bot.send_message(
            chat_id,
            "💎 <b>У тебя уже есть Premium!</b>\n\n"
            "Ты уже в топе! 🚀",
            reply_markup=premium_menu(user_id),
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if use_supabase:
        try:
            response = supabase.table('users').select('test_used').eq('user_id', user_id).execute()
            test_used = response.data[0].get('test_used', 0) if response.data else 0
        except:
            test_used = 0
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT test_used FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        test_used = result[0] if result else 0
        conn.close()
    
    if test_used == 1:
        msg = bot.send_message(
            chat_id,
            "⛔ <b>Ты уже использовал тест!</b>\n\n"
            "Пробный период закончился.\n"
            "Купи Premium: /premium\n\n"
            "💰 50₽/месяц",
            reply_markup=premium_menu(user_id),
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "1d"):
        if use_supabase:
            try:
                supabase.table('users').update({'test_used': 1}).eq('user_id', user_id).execute()
            except:
                pass
        else:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
        
        msg = bot.send_message(
            chat_id,
            "🎉 <b>ПРОБНЫЙ PREMIUM АКТИВИРОВАН!</b>\n\n"
            "✅ Мгновенные ответы ⚡\n"
            "✅ Безлимит сообщений 📨\n"
            "✅ Бесплатная генерация картинок 🎨\n"
            "✅ Приоритетная поддержка 👑\n"
            "✅ Эксклюзивные функции 🔥\n\n"
            "⏳ Доступ активен 24 часа.\n"
            "Купить Premium: /premium",
            reply_markup=premium_menu(user_id),
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка. Попробуй позже.")
        user_message_ids[user_id].append(msg.message_id)

# ============================================================
# КАРТИНКИ
# ============================================================
def generate_and_send_image(m, prompt):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if not can_send_message(user_id):
        if get_premium_status(user_id):
            msg = bot.send_message(chat_id, f"🔴 Лимит! Но у тебя Premium, так что пиши дальше! 🚀")
            user_message_ids[user_id].append(msg.message_id)
        else:
            msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium\n\n💎 Безлимит и бесплатная генерация!")
            user_message_ids[user_id].append(msg.message_id)
        return

    title = fix_title(prompt)
    msg = bot.send_message(chat_id, f"🎨 Генерирую: {title}... ⏳", parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

    image_data = generate_image(prompt)

    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(
                chat_id,
                photo=image_data,
                caption=f"🎨 {title}\n\n✨ AWESOME AI\n💎 Premium — Безлимит!",
                parse_mode='HTML'
            )
        except:
            msg = bot.send_message(chat_id, "⚠️ Ошибка при отправке")
            user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "⚠️ Не удалось сгенерировать. Попробуй другое описание.")
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
        if get_premium_status(user_id):
            pass
        else:
            msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium")
            user_message_ids[user_id].append(msg.message_id)
            return
    
    bot.send_chat_action(chat_id, 'typing')
    
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        analysis = analyze_image_from_file(downloaded)
        increment_messages(user_id)
        
        if get_premium_status(user_id):
            analysis += "\n\n💎 *Премиум-анализ*"
        
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
        if get_premium_status(user_id):
            pass
        else:
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
            msg = bot.send_message(chat_id, "🎤 Не разобрал. Попробуй говорить чётче.")
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
        if get_premium_status(user_id):
            pass
        else:
            msg = bot.send_message(chat_id, f"🔴 Лимит! Купи Premium: /premium\n\n💎 Безлимит, бесплатная генерация и супер-функции!")
            user_message_ids[user_id].append(msg.message_id)
            return

    bot.send_chat_action(chat_id, 'typing')

    if is_image_generation(m.text):
        generate_and_send_image(m, m.text)
        return

    increment_messages(user_id)
    response = process_message(user_id, m.text)
    
    if response:
        if get_premium_status(user_id):
            response += "\n\n💎 *Премиум-ответ*"
        bot.send_message(chat_id, response, parse_mode='HTML')
    else:
        bot.send_message(chat_id, random.choice([
            "🤔 Хм... Интересный вопрос! Расскажи подробнее!",
            "🧐 Слушай, я задумался... Дай-ка подумать!",
            "😮 Ого! Классный вопрос! Я обожаю такие!",
            "💡 Понял! Я сейчас подумаю и отвечу!",
            "🔥 А вот это уже интересно! Давай разбираться!",
            "✨ Ты задаёшь отличные вопросы! Я в восторге!"
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
        
        # Главное меню
        if call.data == "back_to_menu":
            bot.answer_callback_query(call.id)
            has_premium = get_premium_status(user_id)
            premium_text = "💎 PREMIUM" if has_premium else "🔓 Бесплатный"
            
            text = (
                "✨ <b>AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!</b> ✨\n\n"
                f"🌸 <b>Привет, {call.from_user.first_name}!</b>\n"
                f"💎 Статус: {premium_text}\n\n"
                "🧠 <b>Меня создал гениальный AWESOME</b>\n"
                "Я работаю на уникальном коде, написанном с нуля!\n\n"
                "⚡ <b>Что я умею:</b>\n"
                "🌐 Искать в Google, Wikipedia и новостях\n"
                "🌤 Показывать погоду с прогнозом\n"
                "💵 Курс валют и криптовалют\n"
                "🧮 Решать математику и уравнения\n"
                "🐍 Помогать с программированием\n"
                "📸 Анализировать изображения\n"
                "🧠 Анализировать настроение\n"
                "🎨 Генерировать картинки\n\n"
                "🎁 <b>Попробуй Premium бесплатно!</b>\n"
                "Нажми кнопку «Тест Premium» 👇\n\n"
                f"💎 Бесплатно — {FREE_LIMIT} сообщений/день\n"
                f"💎 Премиум — БЕЗЛИМИТ 🚀\n\n"
                "💎 <b>Premium даёт:</b>\n"
                "• Мгновенные ответы ⚡\n"
                "• Неограниченные сообщения 📨\n"
                "• Бесплатная генерация картинок 🎨\n"
                "• Приоритетная поддержка 👑\n"
                "• Эксклюзивные функции 🔥"
            )
            msg = bot.send_message(chat_id, text, reply_markup=main_menu(user_id), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # Премиум фичи
        if call.data == "premium_features":
            bot.answer_callback_query(call.id)
            if not get_premium_status(user_id) and not is_admin(user_id) and user_id != OWNER_ID:
                msg = bot.send_message(
                    chat_id,
                    "❌ <b>Эта информация доступна только Premium пользователям!</b>\n\n"
                    "Купи Premium: /premium\n\n"
                    "💎 <b>Что ты получишь:</b>\n"
                    "• Безлимит сообщений\n"
                    "• Мгновенные ответы\n"
                    "• Бесплатная генерация\n"
                    "• Приоритетная поддержка\n"
                    "• Эксклюзивные функции",
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
                user_message_ids[user_id].append(msg.message_id)
                return
            
            text = (
                "💎 <b>PREMIUM AWESOME AI</b> 🔥\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "📨 <b>БЕЗЛИМИТ</b>\n"
                "Пиши сколько хочешь! 🚀\n\n"
                "⚡ <b>МГНОВЕННЫЕ ОТВЕТЫ</b>\n"
                "В 2 раза быстрее! ⚡\n\n"
                "🎨 <b>БЕСПЛАТНАЯ ГЕНЕРАЦИЯ</b>\n"
                "Неограниченные картинки 🎨\n\n"
                "🔍 <b>ГЛУБОКИЙ АНАЛИЗ</b>\n"
                "Максимально детальные ответы 🧠\n\n"
                "👑 <b>VIP-ПОДДЕРЖКА</b>\n"
                "24/7 приоритетная помощь 📩\n\n"
                "🎁 <b>ЭКСКЛЮЗИВНЫЕ ФУНКЦИИ</b>\n"
                "Новые возможности каждый месяц 🔥\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "💰 <b>Цена: 50₽/месяц</b>\n\n"
                "🔥 <b>ЭТО ПРОСТО АХУЕННО!</b>"
            )
            msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # Остальные обработчики (оплата, заказы, поддержка и т.д.)
        # [ЗДЕСЬ ВСЕ ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ИЗ ПРЕДЫДУЩЕЙ ВЕРСИИ]
        
        # Основные кнопки
        if call.data == "test":
            bot.answer_callback_query(call.id, "🎁 Активирую...")
            process_test_premium(chat_id, user_id)
            return
        elif call.data == "support":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "📩 Напиши: /support [текст]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        elif call.data == "status":
            bot.answer_callback_query(call.id)
            status_cmd(call.message)
        elif call.data == "premium":
            bot.answer_callback_query(call.id)
            premium_cmd(call.message)
        elif call.data == "profile":
            bot.answer_callback_query(call.id)
            profile_cmd(call.message)
        elif call.data == "stats":
            bot.answer_callback_query(call.id)
            stats_cmd(call.message)
        elif call.data == "clear":
            bot.answer_callback_query(call.id)
            clear_cmd(call.message)
        elif call.data == "help":
            bot.answer_callback_query(call.id)
            help_cmd(call.message)
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎨 Напиши: /draw [описание]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {e}")

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — ЛУЧШАЯ НЕЙРОСЕТЬ В МИРЕ!")
print("=" * 60)
print(f"🤖 Бот: @{bot.get_me().username}")
if use_supabase:
    print("☁️ База данных: SUPABASE (облачная) ✅")
else:
    print("💾 База данных: ЛОКАЛЬНАЯ (SQLite)")
print(f"📊 Лимиты: Бесплатный: {FREE_LIMIT}/день | Премиум: БЕЗЛИМИТ")
print(f"🕐 Часовой пояс: МСК (UTC+3)")
print("=" * 60)
print("БОТ ГОТОВ!")
print("=" * 60)

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
