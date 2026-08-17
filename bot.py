#!/usr/bin/env python3
import sys
print("🔴 БОТ НАЧАЛ ЗАПУСК!", flush=True)

import telebot
print("✅ telebot", flush=True)

import requests
print("✅ requests", flush=True)

# ОТКЛЮЧАЕМ SSL ДЛЯ GIGACHAT
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import json
import re
import os
import sqlite3
import time
import random
import urllib.parse
from datetime import datetime, timedelta, timezone
from telebot import types
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

print("✅ ВСЕ БИБЛИОТЕКИ!", flush=True)

# ============================================================
# НАСТРОЙКА
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

# ТАЙМАУТЫ
SEARCH_TIMEOUT = 3
GIGACHAT_TIMEOUT = 3
YANDEX_TIMEOUT = 3

print("✅ НАСТРОЙКА ЗАГРУЖЕНА!", flush=True)

# ============================================================
# КЭШ
# ============================================================
CACHE = {}
CACHE_TTL = 300

def get_cache(key):
    if key in CACHE:
        data, ts = CACHE[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del CACHE[key]
    return None

def set_cache(key, data):
    CACHE[key] = (data, time.time())

# ============================================================
# ВРЕМЯ (МОСКОВСКОЕ)
# ============================================================
MOSCOW_TZ = timezone(timedelta(hours=3))

def get_moscow_time():
    return datetime.now(MOSCOW_TZ)

def format_date(date_str):
    if not date_str:
        return "неизвестно"
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        date_obj = date_obj.replace(tzinfo=MOSCOW_TZ)
        return date_obj.strftime('%d.%m.%Y %H:%M') + " МСК"
    except:
        return date_str

def get_current_date():
    return get_moscow_time().strftime('%d.%m.%Y')

def get_current_date_full():
    return get_moscow_time().strftime('%d.%m.%Y %H:%M') + " МСК"

# ============================================================
# БАЗА ДАННЫХ
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
                  joined_at TEXT,
                  is_owner INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS muted (user_id INTEGER PRIMARY KEY)''')
    c.execute('''CREATE TABLE IF NOT EXISTS total_stats
                 (user_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0)''')
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
    try:
        c.execute('ALTER TABLE users ADD COLUMN is_owner INTEGER DEFAULT 0')
    except:
        pass
    conn.commit()
    conn.close()
    print("✅ БД ГОТОВА!", flush=True)

def get_db_user(user_id):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    if result:
        columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
        return dict(zip(columns, result))
    return None

def update_db_user(user_id, data):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
    values = list(data.values()) + [user_id]
    c.execute(f'UPDATE users SET {set_clause} WHERE user_id = ?', values)
    conn.commit()
    conn.close()
    return True

def ensure_user(user_id, username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    if user is None:
        joined_at = get_moscow_time().strftime('%d.%m.%Y %H:%M')
        is_owner = 1 if user_id == OWNER_ID else 0
        c.execute('''INSERT INTO users 
                     (user_id, username, messages_today, last_reset, is_admin, test_used, joined_at, is_owner) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, username, 0, get_moscow_time().strftime('%Y-%m-%d'), is_owner, 0, joined_at, is_owner))
        c.execute('INSERT OR IGNORE INTO total_stats (user_id, total_messages) VALUES (?, 0)', (user_id,))
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

def set_premium(user_id, duration_str):
    now = get_moscow_time()
    if duration_str.endswith('d'):
        delta = timedelta(days=int(duration_str[:-1]))
    elif duration_str.endswith('m'):
        delta = timedelta(minutes=int(duration_str[:-1]))
    elif duration_str.endswith('h'):
        delta = timedelta(hours=int(duration_str[:-1]))
    elif duration_str.endswith('mes'):
        delta = timedelta(days=30 * int(duration_str[:-3]))
    elif duration_str.endswith('y'):
        delta = timedelta(days=365 * int(duration_str[:-1]))
    else:
        return False
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT premium_expires FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
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
            expires_date = expires_date.replace(tzinfo=MOSCOW_TZ)
            if get_moscow_time() > expires_date:
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
    return result[0] if result else None

def add_month_to_premium(user_id):
    now = get_moscow_time()
    expires = get_premium_expires(user_id)
    
    if expires:
        try:
            current_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                new_expires = (current_date + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                new_expires = (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        except:
            new_expires = (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        new_expires = (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (new_expires, user_id))
    conn.commit()
    conn.close()
    return new_expires

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
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET is_admin = ? WHERE user_id = ?', (1 if status else 0, user_id))
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

def reset_messages_if_needed(user_id):
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

# ============================================================
# МАТЕМАТИКА - ТОЛЬКО ЧИСЛО
# ============================================================
def solve_math(text):
    text_lower = text.lower().strip()
    
    if not re.search(r'\d', text_lower):
        return None
    
    if any(kw in text_lower for kw in ['кто', 'что', 'где', 'когда', 'почему', 'зачем', 'праздник', 'погода', 'курс']):
        return None
    
    clean_text = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример', 'скок', 'равно', 'a', 'b', 'с']:
        clean_text = clean_text.replace(word, '').strip()
    
    clean_text = clean_text.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    clean_text = clean_text.replace('х', '*').replace('×', '*').replace('÷', '/')
    
    if not re.search(r'[+\-*/]', clean_text):
        return None
    
    expr = re.sub(r'[^0-9+\-*/()=.]', '', clean_text)
    
    if expr and len(expr) > 1:
        try:
            if any(op in expr for op in ['__', 'import', 'eval', 'exec']):
                return None
            result = eval(expr)
            if result == int(result):
                return str(int(result))
            else:
                return str(round(result, 2))
        except:
            pass
    return None

# ============================================================
# ПОИСК ПО ВСЕМ ИСТОЧНИКАМ (ПАРАЛЛЕЛЬНО)
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('div.g')[:3]:
                title_elem = result.select_one('h3')
                snippet_elem = result.select_one('div.VwiC3b')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    if title and len(title) > 3:
                        results.append(f"🔹 {title}\n📝 {snippet[:150]}")
            if results:
                return "\n\n".join(results)
    except:
        pass
    return None

def search_wikipedia(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            results = data.get('query', {}).get('search', [])
            if results:
                text = ""
                for item in results[:3]:
                    title = item.get('title', '')
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))[:150]
                    text += f"📚 {title}\n📝 {snippet}\n\n"
                return text
    except:
        pass
    return None

def search_news(query):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=ru&gl=RU&ceid=RU:ru"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:3]
            if items:
                text = ""
                for item in items:
                    title = item.find('title')
                    if title:
                        text += f"📰 {title.text}\n"
                return text
    except:
        pass
    return None

def search_youtube(query):
    try:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for video in soup.select('ytd-video-renderer')[:2]:
                title_elem = video.select_one('yt-formatted-string#video-title')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        results.append(f"🎬 {title}")
            if results:
                return "📹 YouTube:\n" + "\n".join(results)
    except:
        pass
    return None

def search_telegram(query):
    try:
        url = f"https://t.me/s/{query.split()[0]}" if query.split() else None
        if url:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                for post in soup.select('.tgme_widget_message_text')[:2]:
                    text = post.get_text(strip=True)[:150]
                    if text:
                        return f"📱 Telegram:\n{text}"
    except:
        pass
    return None

def search_vk(query):
    try:
        url = f"https://vk.com/search?c[q]={urllib.parse.quote(query)}&c[section]=all"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for post in soup.select('.wall_text')[:2]:
                text = post.get_text(strip=True)[:150]
                if text:
                    return f"📌 VK:\n{text}"
    except:
        pass
    return None

def search_all_sources(query):
    """ПАРАЛЛЕЛЬНЫЙ ПОИСК ПО ВСЕМ ИСТОЧНИКАМ"""
    cache_key = f"search_{hash(query)}_{int(time.time()/300)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    sources = [
        ("Google", search_google),
        ("Wikipedia", search_wikipedia),
        ("News", search_news),
        ("YouTube", search_youtube),
        ("Telegram", search_telegram),
        ("VK", search_vk)
    ]
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(func, query): name for name, func in sources}
        for future in as_completed(futures):
            try:
                result = future.result(timeout=SEARCH_TIMEOUT + 1)
                if result:
                    results.append(result)
            except:
                pass
    
    if results:
        final = "\n\n---\n\n".join(results[:4])
        set_cache(cache_key, final)
        return final
    
    return None

# ============================================================
# ПОГОДА
# ============================================================
def get_weather_fast(city):
    cache_key = f"weather_{city}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description']
            wind = data['wind']['speed']
            result = f"🌤 {city}: {round(temp)}°C, {desc}\n💨 Ветер: {wind} м/с"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

# ============================================================
# КУРС ВАЛЮТ
# ============================================================
def get_currency_fast():
    cache_key = "currency"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            rates = data.get('rates', {})
            usd_rub = rates.get('RUB', '?')
            eur_usd = rates.get('EUR', 1)
            eur_rub = usd_rub / eur_usd if eur_usd else '?'
            result = f"💵 USD: {round(usd_rub, 2)}₽\nEUR: {round(eur_rub, 2)}₽"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

# ============================================================
# КРИПТОВАЛЮТЫ
# ============================================================
def get_crypto_fast():
    cache_key = "crypto"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json()
            btc = data.get('bitcoin', {}).get('usd', '?')
            eth = data.get('ethereum', {}).get('usd', '?')
            result = f"🪙 BTC: ${btc}\nETH: ${eth}"
            set_cache(cache_key, result)
            return result
    except:
        pass
    return None

# ============================================================
# ПРАЗДНИКИ - КАЛЕНДАРЬ
# ============================================================
HOLIDAYS = {
    '01.01': 'Новый год',
    '07.01': 'Рождество Христово',
    '23.02': 'День защитника Отечества',
    '08.03': 'Международный женский день',
    '01.05': 'Праздник Весны и Труда',
    '09.05': 'День Победы',
    '12.06': 'День России',
    '04.11': 'День народного единства',
    '14.01': 'Старый Новый год',
    '25.01': 'Татьянин день',
    '14.02': 'День всех влюбленных',
    '01.04': 'День смеха',
    '12.04': 'День космонавтики',
    '01.06': 'День защиты детей',
    '22.06': 'День памяти и скорби',
    '08.07': 'День семьи, любви и верности',
    '02.09': 'День окончания Второй мировой войны',
    '01.10': 'День пожилого человека',
    '05.10': 'День учителя',
    '31.10': 'Хэллоуин',
    '30.11': 'День матери',
    '12.12': 'День Конституции РФ',
}

def get_holidays(date_str):
    cache_key = f"holidays_{date_str}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    month_day = date_str[3:5] + '.' + date_str[0:2]
    if month_day in HOLIDAYS:
        set_cache(cache_key, HOLIDAYS[month_day])
        return HOLIDAYS[month_day]
    
    extra = {
        '17.08': '17 августа:\n• День авиации\n• День строителя\n• Международный день бездомных животных'
    }
    if date_str in extra:
        set_cache(cache_key, extra[date_str])
        return extra[date_str]
    
    set_cache(cache_key, "Праздников не найдено")
    return "Праздников не найдено"

# ============================================================
# GIGACHAT
# ============================================================
gigachat_token_cache = None
gigachat_token_time = 0

def get_gigachat_token():
    global gigachat_token_cache, gigachat_token_time
    if gigachat_token_cache and time.time() - gigachat_token_time < 300:
        return gigachat_token_cache
    
    if not GIGACHAT_AUTH_KEY:
        return None
    try:
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": "00000000-0000-0000-0000-000000000000",
            "Authorization": f"Basic {GIGACHAT_AUTH_KEY}"
        }
        data = {"scope": "GIGACHAT_API_PERS", "grant_type": "client_credentials"}
        response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
        if response.status_code == 200:
            gigachat_token_cache = response.json().get("access_token")
            gigachat_token_time = time.time()
            return gigachat_token_cache
    except:
        pass
    return None

def generate_with_gigachat(user_text):
    try:
        token = get_gigachat_token()
        if not token:
            return None
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {"role": "system", "content": "Ты - AWESOME AI. Отвечай КОРОТКО и по делу. Максимум 2-3 предложения. Дай полезную информацию."},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.7,
            "max_tokens": 200
        }
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
    except:
        pass
    return None

# ============================================================
# YANDEXGPT
# ============================================================
def generate_with_yandexgpt(user_text):
    try:
        if not YANDEX_API_KEY:
            return None
        
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://b1g4aq87c7j61c6g3i5l/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 150},
            "messages": [
                {"role": "system", "text": "Отвечай КОРОТКО и по делу. Максимум 2-3 предложения."},
                {"role": "user", "text": user_text}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=YANDEX_TIMEOUT)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
    except:
        pass
    return None

# ============================================================
# FALLBACK
# ============================================================
def generate_fallback_response(user_text):
    text_lower = user_text.lower()
    if "привет" in text_lower:
        return "👋 Привет! Я AWESOME AI. Чем могу помочь?"
    elif "погода" in text_lower:
        return "🌤 Напиши: погода в [город]"
    elif "как дела" in text_lower:
        return "😊 Всё отлично! А у тебя?"
    else:
        return "🤖 Задай вопрос, я найду ответ в интернете!"

# ============================================================
# ОСНОВНАЯ ОБРАБОТКА (БЫСТРАЯ)
# ============================================================
def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    
    # 1. МАТЕМАТИКА (МГНОВЕННО)
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    # 2. ПРАЗДНИКИ (МГНОВЕННО)
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник', 'сегодня праздник', 'седня']):
        today = get_current_date()
        holidays = get_holidays(today)
        return f"📅 {today}\n\n{holidays}"
    
    # 3. ПОГОДА (2 СЕКУНДЫ)
    if any(kw in text_lower for kw in ['погода', 'weather']):
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            weather = get_weather_fast(city)
            if weather:
                return weather
            return f"🌤 Не удалось получить погоду для '{city}'"
        return "🌤 Напиши: погода в [город]"
    
    # 4. КУРС ВАЛЮТ (2 СЕКУНДЫ)
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
        currency = get_currency_fast()
        if currency:
            return currency
        return "💵 Не удалось получить курс"
    
    # 5. КРИПТОВАЛЮТЫ (2 СЕКУНДЫ)
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта']):
        crypto = get_crypto_fast()
        if crypto:
            return crypto
        return "🪙 Не удалось получить курс криптовалют"
    
    # 6. ПОИСК ПО ВСЕМ ИСТОЧНИКАМ (3-5 СЕКУНД)
    if len(user_text) > 2:
        search_result = search_all_sources(user_text)
        if search_result:
            return f"🔍 {user_text}\n\n{search_result}"
    
    # 7. НЕЙРОСЕТИ (ПАРАЛЛЕЛЬНО, 3 СЕКУНДЫ)
    if image_description:
        user_text = f"{user_text}\n\nОписание фото: {image_description}"
    
    try:
        results = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = []
            if GIGACHAT_AUTH_KEY:
                futures.append(executor.submit(generate_with_gigachat, user_text))
            if YANDEX_API_KEY:
                futures.append(executor.submit(generate_with_yandexgpt, user_text))
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=3)
                    if result and len(result) > 5:
                        results.append(result[:300])
                except:
                    pass
        
        if results:
            return results[0]
    except:
        pass
    
    # 8. FALLBACK
    return generate_fallback_response(user_text)

# ============================================================
# МЕНЮ И КНОПКИ
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
    keyboard.add(types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu"))
    return keyboard

def premium_menu(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton(
            "💳 Оплатить Premium (100₽/мес)", 
            url="https://yoomoney.ru/quickpay/fundraise/button?billNumber=1JN0VV54CV0.260817&"
        ),
        types.InlineKeyboardButton("✅ Я оплатил", callback_data="i_paid"),
    )
    if get_premium_status(user_id) or is_admin(user_id) or user_id == OWNER_ID:
        keyboard.add(types.InlineKeyboardButton("📋 Что даёт Premium?", callback_data="premium_features"))
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
# ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================
def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200 and len(response.content) > 1000:
            return response.content
    except:
        pass
    return None

def fix_title(prompt):
    title = prompt
    for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
        title = title.replace(word, '').strip()
    if not title or len(title) < 2:
        return "Картинка"
    return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

def is_image_generation(text):
    image_keywords = ['нарисуй', 'покажи', 'картинку', 'изображение']
    return any(kw in text.lower() for kw in image_keywords)

# ============================================================
# КОМАНДЫ БОТА
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)
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

@bot.message_handler(commands=['start'])
def start(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    try:
        delete_previous_messages(chat_id, user_id)
    except:
        pass
    ensure_user(user_id, m.from_user.username or "unknown")
    
    text = (
        "✨ <b>AWESOME AI — СУПЕР-БЫСТРЫЙ!</b> ✨\n\n"
        f"🌸 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🧠 <b>Меня создал гениальный AWESOME</b>\n\n"
        "🚀 <b>ОТВЕЧАЮ ЗА 3-5 СЕКУНД!</b>\n\n"
        "🌐 <b>ЧТО Я УМЕЮ:</b>\n"
        "🔍 Ищу в Google, Wikipedia, YouTube, Telegram, VK, News\n"
        "📅 Показываю праздники (мгновенно)\n"
        "🌤 Точная погода (2 сек)\n"
        "💵 Курс валют и криптовалют (2 сек)\n"
        "🧮 Решаю математику (мгновенно)\n"
        "🤖 Отвечаю как GigaChat и YandexGPT\n"
        "🎨 Генерирую картинки\n\n"
        "💎 <b>Цена Premium: 100₽/месяц</b>\n\n"
        "🎁 <b>Тест Premium на 2 дня — всего 1 раз!</b>"
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
    text = (
        "🧠 <b>AWESOME AI — ПОМОЩЬ</b>\n\n"
        "🌐 <b>Что я умею:</b>\n"
        "🔍 Ищу в Google, Wikipedia, YouTube, Telegram, VK, News\n"
        "📅 Праздники (напиши 'праздники')\n"
        "🌤 Погода (напиши 'погода в [город]')\n"
        "💵 Курс валют (напиши 'курс доллара')\n"
        "🧮 Математика (напиши пример)\n"
        "🎨 Генерирую картинки (/draw [описание])\n\n"
        "📋 <b>Команды:</b>\n"
        "/start — Меню\n"
        "/help — Помощь\n"
        "/status — Статус\n"
        "/premium — Premium\n"
        "/test — Пробный Premium\n"
        "/profile — Профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить\n"
        "/ping — Проверка работы\n"
        "/draw — Сгенерировать картинку\n\n"
        "💎 <b>Лимиты:</b>\n"
        f"🔓 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Premium — ♾️ БЕЗЛИМИТНО"
    )
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['ping'])
def ping_cmd(m):
    bot.send_message(m.chat.id, "🏓 PONG! Бот работает!")

@bot.message_handler(commands=['status'])
def status_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    if user_id == OWNER_ID:
        status_text = "👑 ВЛАДЕЛЕЦ — ♾️ БЕЗЛИМИТ!"
    elif is_admin(user_id):
        status_text = "👑 АДМИН — ♾️ БЕЗЛИМИТ!"
    else:
        premium = get_premium_status(user_id)
        user_data = get_db_user(user_id)
        if user_data:
            messages = user_data.get('messages_today', 0)
            expires = user_data.get('premium_expires')
        else:
            messages = 0
            expires = None
        
        if premium:
            if expires and expires != "None":
                expires_formatted = format_date(expires)
                status_text = f"💎 PREMIUM (до {expires_formatted})"
            else:
                status_text = "💎 PREMIUM"
            status_text += f"\n📨 Лимит: ♾️ БЕЗЛИМИТНО"
        else:
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text = f"🔓 Бесплатный: осталось {remaining} из {FREE_LIMIT}"
    
    msg = bot.send_message(chat_id, f"📊 ТВОЙ СТАТУС\n\n{status_text}", reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    has_premium = get_premium_status(user_id)
    expires = get_premium_expires(user_id)
    
    if has_premium:
        if expires and expires != "None":
            expires_formatted = format_date(expires)
            text = (
                f"💎 У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!\n\n"
                f"⏳ Действует до: {expires_formatted}\n"
                f"📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n"
                f"🌟 Можешь продлить подписку!\n"
                f"💰 100₽/месяц"
            )
        else:
            text = (
                f"💎 У ТЕБЯ УЖЕ ЕСТЬ PREMIUM!\n\n"
                f"📨 Лимит: ♾️ БЕЗЛИМИТНО\n\n"
                f"🌟 Можешь продлить подписку!\n"
                f"💰 100₽/месяц"
            )
    else:
        text = (
            f"💎 <b>PREMIUM AWESOME AI</b>\n\n"
            f"🔥 <b>ЧТО ТЫ ПОЛУЧАЕШЬ:</b>\n"
            f"♾️ <b>БЕЗЛИМИТНЫЕ СООБЩЕНИЯ</b>\n"
            f"🚀 Приоритетная обработка\n"
            f"🧠 Максимально глубокие ответы\n"
            f"💎 VIP-поддержка\n\n"
            f"💰 <b>Цена: 100₽/месяц</b>"
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['test'])
def test_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
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
    
    if get_premium_status(user_id):
        msg = bot.send_message(chat_id, "💎 У тебя уже есть Premium!", reply_markup=premium_menu(user_id), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        msg = bot.send_message(chat_id, "⛔ Ты уже использовал тест Premium!\nКупи Premium: /premium", reply_markup=premium_menu(user_id), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "2d"):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET test_used = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        msg = bot.send_message(
            chat_id, 
            f"🎉 *ПРОБНЫЙ PREMIUM АКТИВИРОВАН НА 2 ДНЯ!*\n\n"
            f"✅ Приоритетная обработка\n"
            f"✅ ♾️ БЕЗЛИМИТНЫЕ СООБЩЕНИЯ\n"
            f"✅ Более качественные ответы\n\n"
            f"⏳ Доступ активен 48 часов.\n"
            f"🔥 Наслаждайся!",
            reply_markup=premium_menu(user_id), 
            parse_mode='HTML'
        )
        user_message_ids[user_id].append(msg.message_id)
    else:
        msg = bot.send_message(chat_id, "❌ Ошибка.")
        user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    user_data = get_db_user(user_id)
    if user_data:
        messages = user_data.get('messages_today', 0)
        expires = user_data.get('premium_expires')
        premium = user_data.get('premium', 0) == 1
        joined_at = user_data.get('joined_at', 'Неизвестно')
    else:
        messages = 0
        expires = None
        premium = False
        joined_at = "Неизвестно"
    
    if not get_premium_status(user_id):
        premium = False
    
    if user_id == OWNER_ID:
        status = "👑 ВЛАДЕЛЕЦ"
        limit_text = "♾️ Безлимит"
    elif is_admin(user_id):
        status = "👑 АДМИН"
        limit_text = "♾️ Безлимит"
    elif premium:
        if expires and expires != "None":
            expires_formatted = format_date(expires)
            status = f"💎 PREMIUM (до {expires_formatted})"
        else:
            status = "💎 PREMIUM"
        limit_text = "♾️ Безлимит"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
        limit_text = f"{FREE_LIMIT}/день"
    
    username = m.from_user.username
    user_link = f"@{username}" if username else "Не указан"
    text = (
        f"👤 ТВОЙ ПРОФИЛЬ\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Юзер: {user_link}\n"
        f"💎 Статус: {status}\n"
        f"📨 Лимит: {limit_text}\n"
        f"✉️ Сегодня: {messages}\n"
        f"📅 Вход: {joined_at or 'Неизвестно'} (МСК)"
    )
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    if user_id == OWNER_ID or is_admin(user_id):
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users')
        users = c.fetchall()
        conn.close()
        
        total_users = len(users)
        premium_users = 0
        admin_users = 0
        for user in users:
            if user[2] == 1:
                premium_users += 1
            if user[6] == 1:
                admin_users += 1
        
        text = (
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Всего: {total_users}\n"
            f"👑 Админов: {admin_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users - admin_users}"
        )
    else:
        user_data = get_db_user(user_id)
        if user_data:
            messages_today = user_data.get('messages_today', 0)
            premium = get_premium_status(user_id)
            
            if premium:
                status = "💎 PREMIUM"
                limit_text = "♾️ Безлимит"
            else:
                remaining = FREE_LIMIT - messages_today
                if remaining < 0:
                    remaining = 0
                status = "🔓 Бесплатный"
                limit_text = f"{remaining}/{FREE_LIMIT}"
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,))
            result = c.fetchone()
            conn.close()
            total = result[0] if result else 0
            
            text = (
                "📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
                f"👤 Статус: {status}\n"
                f"📨 Лимит: {limit_text}\n"
                f"✉️ Сегодня: {messages_today}\n"
                f"📊 Всего: {total}"
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
    if user_id in user_message_ids:
        user_message_ids[user_id] = []
    msg = bot.send_message(chat_id, "🧹 ИСТОРИЯ ОЧИЩЕНА", reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    prompt = m.text.replace('/draw', '').strip()
    if not prompt:
        msg = bot.send_message(chat_id, "❌ /draw [описание]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
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

@bot.message_handler(commands=['support'])
def support_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/support', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📩 Напиши: /support [текст]", parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('INSERT INTO support_requests (user_id, username, text, created_at) VALUES (?, ?, ?, ?)',
              (user_id, m.from_user.username or "unknown", text, get_moscow_time().strftime('%d.%m.%Y %H:%M')))
    conn.commit()
    conn.close()
    
    msg = bot.send_message(chat_id, "✅ Обращение отправлено!", parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📩 НОВОЕ ОБРАЩЕНИЕ!\n\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='HTML')
    except:
        pass

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/feedback', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📝 Напиши: /feedback [текст]", parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    msg = bot.send_message(chat_id, "✅ Спасибо за отзыв! ❤️")
    user_message_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📝 НОВЫЙ ОТЗЫВ!\n\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='HTML')
    except:
        pass

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if not is_authorized(user_id):
        msg = bot.send_message(chat_id, "❌ Нет прав!")
        user_message_ids[user_id].append(msg.message_id)
        return
    msg = bot.send_message(chat_id, "🛡️ АДМИН-ПАНЕЛЬ", reply_markup=admin_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ
# ============================================================
@bot.message_handler(func=lambda m: True)
def handle_all_messages(m):
    try:
        chat_id = m.chat.id
        user_id = m.from_user.id
        text = m.text.strip() if m.text else ""
        
        if text.startswith('/'):
            return
        
        if is_banned(user_id):
            bot.send_message(chat_id, "🚫 Ты забанен!")
            return
        
        if is_muted(user_id):
            bot.send_message(chat_id, "🔇 Ты замучен!")
            return
        
        ensure_user(user_id, m.from_user.username or "unknown")
        
        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            messages = user_data.get('messages_today', 0) if user_data else 0
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            bot.send_message(
                chat_id,
                f"🔴 Лимит исчерпан! Осталось: {remaining}/{FREE_LIMIT}\n💎 Купи Premium: /premium",
                reply_markup=premium_menu(user_id),
                parse_mode='HTML'
            )
            return
        
        # ОБРАБОТКА ФОТО
        if m.photo:
            try:
                file_id = m.photo[-1].file_id
                file_info = bot.get_file(file_id)
                file_content = bot.download_file(file_info.file_path)
                # Простой анализ фото
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(file_content))
                width, height = img.size
                img_desc = f"📸 Анализ: {width}×{height}"
                response = process_message(user_id, text or "Что на картинке?", img_desc)
                increment_messages(user_id)
                bot.send_message(chat_id, response, reply_markup=back_to_menu(), parse_mode='HTML')
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ Ошибка обработки фото: {e}")
            return
        
        # ОБРАБОТКА ТЕКСТА
        if text:
            # Генерация картинки
            if is_image_generation(text):
                draw_cmd(m)
                return
            
            bot.send_chat_action(chat_id, 'typing')
            
            start_time = time.time()
            response = process_message(user_id, text)
            elapsed = time.time() - start_time
            
            if response:
                increment_messages(user_id)
                bot.send_message(
                    chat_id,
                    response,
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
                print(f"✅ Ответ за {elapsed:.1f}с")
            else:
                bot.send_message(
                    chat_id,
                    "❌ Не удалось обработать запрос.",
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        
        try:
            bot.answer_callback_query(call.id)
        except:
            pass
        
        ensure_user(user_id, call.from_user.username or "unknown")
        
        if call.data == "status":
            status_cmd(call.message)
            return
        if call.data == "premium":
            premium_cmd(call.message)
            return
        if call.data == "test":
            test_cmd(call.message)
            return
        if call.data == "profile":
            profile_cmd(call.message)
            return
        if call.data == "stats":
            stats_cmd(call.message)
            return
        if call.data == "clear":
            clear_cmd(call.message)
            return
        if call.data == "help":
            help_cmd(call.message)
            return
        if call.data == "support":
            msg = bot.send_message(chat_id, "📩 Напиши: /support [текст]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "draw":
            msg = bot.send_message(chat_id, "🎨 Напиши: /draw [описание]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "back_to_menu":
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            start(call.message)
            return
        if call.data == "premium_features":
            if not get_premium_status(user_id) and not is_admin(user_id) and user_id != OWNER_ID:
                msg = bot.send_message(chat_id, "❌ Эта информация доступна только Premium пользователям!", reply_markup=back_to_menu(), parse_mode='HTML')
                user_message_ids[user_id].append(msg.message_id)
                return
            text = (
                f"💎 <b>PREMIUM AWESOME AI</b>\n\n"
                f"🔥 <b>ЧТО ТЫ ПОЛУЧАЕШЬ:</b>\n"
                f"♾️ <b>БЕЗЛИМИТНЫЕ СООБЩЕНИЯ</b>\n"
                f"🚀 Приоритетная обработка\n"
                f"🧠 Максимально глубокие ответы\n"
                f"💎 VIP-поддержка\n\n"
                f"💰 <b>Цена: 100₽/месяц</b>"
            )
            msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "i_paid":
            has_premium = get_premium_status(user_id)
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('INSERT INTO premium_orders (user_id, status, created_at) VALUES (?, ?, ?)',
                      (user_id, 'pending', get_moscow_time().strftime('%d.%m.%Y %H:%M')))
            order_id = c.lastrowid
            conn.commit()
            conn.close()
            
            order_type = "ПРОДЛЕНИЕ" if has_premium else "ПОКУПКА"
            expires = get_premium_expires(user_id)
            expires_text = f"до {format_date(expires)}" if expires and has_premium else "отсутствует"
            
            msg = bot.send_message(chat_id, 
                f"✅ ЗАКАЗ ОТПРАВЛЕН!\n\n"
                f"🆔 Номер заказа: #{order_id}\n"
                f"📌 Тип: {order_type}\n"
                f"⏳ Текущий статус: {expires_text}\n"
                f"⏳ Ожидай подтверждения от админа.", 
                reply_markup=back_to_menu(),
                parse_mode='HTML'
            )
            user_message_ids[user_id].append(msg.message_id)
            
            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_order:{order_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_order:{order_id}")
            )
            try:
                bot.send_message(
                    OWNER_ID, 
                    f"💳 НОВЫЙ ЗАКАЗ PREMIUM!\n\n"
                    f"🆔 Заказ: #{order_id}\n"
                    f"👤 @{call.from_user.username or 'Не указан'}\n"
                    f"💰 100₽\n"
                    f"📌 Тип: {order_type}\n"
                    f"📅 Время: {get_moscow_time().strftime('%d.%m.%Y %H:%M')} (МСК)", 
                    reply_markup=keyboard, 
                    parse_mode='HTML'
                )
            except:
                pass
            return
        
        # АДМИН-КНОПКИ
        if call.data == "admin_stats":
            stats_cmd(call.message)
            return
        if call.data == "admin_list":
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username FROM users WHERE is_admin = 1')
            admins = c.fetchall()
            conn.close()
            if not admins:
                text = "👑 АДМИНЫ\n\nНет админов."
            else:
                text = "👑 АДМИНЫ\n\n"
                for admin in admins:
                    text += f"• @{admin[1] if admin[1] else admin[0]}\n"
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_list_users":
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, username, premium, is_admin FROM users ORDER BY user_id')
            users = c.fetchall()
            conn.close()
            text = "👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ\n\n"
            for user in users:
                uid, username, premium, is_admin_flag = user
                status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag == 1 else "💎 PREMIUM" if premium == 1 else "🔓 Бесплатный"
                text += f"• @{username if username and username != 'unknown' else 'Не указан'} | ID: <code>{uid}</code> | {status}\n"
            msg = bot.send_message(chat_id, text[:4000], reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_broadcast":
            msg = bot.send_message(chat_id, "📢 /broadcast [текст]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_giveprem":
            msg = bot.send_message(chat_id, "💎 /giveprem [ID] [срок]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_givetest":
            msg = bot.send_message(chat_id, "🎁 /givetest [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_ban":
            msg = bot.send_message(chat_id, "🚫 /ban [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_unban":
            msg = bot.send_message(chat_id, "✅ /unban [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_mute":
            msg = bot.send_message(chat_id, "🔇 /mute [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_unmute":
            msg = bot.send_message(chat_id, "🔊 /unmute [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_giveadmin":
            msg = bot.send_message(chat_id, "👑 /giveadmin [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_deladmin":
            msg = bot.send_message(chat_id, "👑 /deladmin [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_info":
            msg = bot.send_message(chat_id, "📊 /info [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_stats_users":
            stats_cmd(call.message)
            return
        if call.data == "admin_clear_messages":
            msg = bot.send_message(chat_id, "🧹 /clear_messages [ID]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_close":
            msg = bot.send_message(chat_id, "❌ Панель закрыта", reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_orders":
            admin_orders_cmd(call.message, user_id)
            return
        if call.data == "admin_support":
            admin_support_cmd(call.message, user_id)
            return
        
        # ОБРАБОТКА ЗАКАЗОВ
        if call.data.startswith("confirm_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("confirm_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, status FROM premium_orders WHERE order_id = ?', (order_id,))
            result = c.fetchone()
            conn.close()
            if not result:
                return
            target_user, status = result
            
            if status != 'pending':
                return
            
            new_expires = add_month_to_premium(target_user)
            
            if new_expires:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('UPDATE premium_orders SET status = "confirmed" WHERE order_id = ?', (order_id,))
                conn.commit()
                conn.close()
                
                try:
                    bot.send_message(chat_id, f"✅ Заказ #{order_id} ПОДТВЕРЖДЁН!", parse_mode='HTML')
                except:
                    pass
                
                expires_formatted = format_date(new_expires)
                msg_text = f"🎉 PREMIUM АКТИВИРОВАН!\n\n✅ Заказ #{order_id} подтверждён!\n💎 Premium активен на 1 месяц!\n⏳ Действует до: {expires_formatted}"
                try:
                    bot.send_message(target_user, msg_text, parse_mode='HTML')
                except:
                    pass
            return
        
        if call.data.startswith("reject_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("reject_order:", ""))
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id, status FROM premium_orders WHERE order_id = ?', (order_id,))
            result = c.fetchone()
            conn.close()
            if not result:
                return
            target_user, status = result
            
            if status != 'pending':
                return
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('UPDATE premium_orders SET status = "rejected" WHERE order_id = ?', (order_id,))
            conn.commit()
            conn.close()
            
            try:
                bot.send_message(chat_id, f"❌ Заказ #{order_id} ОТКЛОНЁН!", parse_mode='HTML')
            except:
                pass
            try:
                bot.send_message(target_user, f"❌ ЗАКАЗ ОТКЛОНЁН\n\nЗаказ #{order_id}", parse_mode='HTML')
            except:
                pass
            return
        
        if call.data.startswith("confirm_broadcast:"):
            if not is_authorized(user_id):
                return
            text = call.data.replace("confirm_broadcast:", "")
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM users')
            users = c.fetchall()
            conn.close()
            
            sent = 0
            failed = 0
            for user in users:
                try:
                    bot.send_message(user[0], f"📢 ОБЪЯВЛЕНИЕ\n\n{text}", parse_mode='HTML')
                    sent += 1
                    time.sleep(0.05)
                except:
                    failed += 1
            bot.send_message(chat_id, f"✅ Рассылка завершена!\n\n📤 Отправлено: {sent}\n❌ Ошибок: {failed}", parse_mode='HTML')
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            return
        
        if call.data == "cancel_broadcast":
            try:
                bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            bot.send_message(call.message.chat.id, "❌ Отменено.", parse_mode='HTML')
            return
        
    except Exception as e:
        print(f"❌ Ошибка в callback: {e}")

# ============================================================
# АДМИН-КОМАНДЫ
# ============================================================
def is_authorized(user_id):
    if user_id == OWNER_ID:
        return True
    return is_admin(user_id)

def admin_orders_cmd(message, user_id):
    chat_id = message.chat.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT order_id, user_id, created_at FROM premium_orders WHERE status = "pending" ORDER BY order_id DESC')
    orders = c.fetchall()
    conn.close()
    
    if not orders:
        text = "💳 ЗАКАЗЫ PREMIUM\n\nНет активных заказов."
    else:
        text = f"💳 ЗАКАЗЫ PREMIUM\n\nВсего: {len(orders)}\n\n"
        for order in orders:
            text += f"🆔 #{order[0]} | 👤 {order[1]} | 📅 {order[2]}\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def admin_support_cmd(message, user_id):
    chat_id = message.chat.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT request_id, user_id, username, text, created_at FROM support_requests WHERE status = "pending" ORDER BY request_id DESC')
    requests = c.fetchall()
    conn.close()
    
    if not requests:
        text = "📩 ОБРАЩЕНИЯ\n\nНет активных обращений."
    else:
        text = f"📩 ОБРАЩЕНИЯ\n\nВсего: {len(requests)}\n\n"
        for req in requests:
            text += f"🆔 #{req[0]} | @{req[2] or 'Не указан'} | {req[4]}\n📝 {req[3][:50]}...\n\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ЗАПУСК
# ============================================================
init_db()

print("=" * 60)
print("🧠 AWESOME AI — СУПЕР-БЫСТРЫЙ!")
print("=" * 60)
print(f"⏱️ ТАЙМАУТЫ:")
print(f"   GigaChat: {GIGACHAT_TIMEOUT} сек")
print(f"   YandexGPT: {YANDEX_TIMEOUT} сек")
print(f"   Поиск: {SEARCH_TIMEOUT} сек")
print("=" * 60)
print("🌐 ИСТОЧНИКИ:")
print("✅ Google")
print("✅ Wikipedia")
print("✅ YouTube")
print("✅ Telegram")
print("✅ VK")
print("✅ News")
print("✅ GigaChat")
print("✅ YandexGPT")
print("=" * 60)
try:
    print(f"🤖 Бот: @{bot.get_me().username}")
except:
    print("🤖 Бот: @unknown")
print("=" * 60)

print("✅ БОТ ЗАПУЩЕН!")

while True:
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
