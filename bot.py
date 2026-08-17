#!/usr/bin/env python3
import sys
print("🔴 БОТ НАЧАЛ ЗАПУСК!", flush=True)
print("🔴 ИМПОРТИРУЮ БИБЛИОТЕКИ...", flush=True)

import telebot
print("✅ telebot импортирован", flush=True)

import requests
print("✅ requests импортирован", flush=True)

# ОТКЛЮЧАЕМ ПРОВЕРКУ SSL ДЛЯ GIGACHAT
import ssl
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Создаем сессию с отключенной проверкой SSL
session = requests.Session()
session.verify = False

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
from PIL import Image, ImageEnhance, ImageFilter
import speech_recognition as sr
from telebot import types
from bs4 import BeautifulSoup
from supabase import create_client, Client
from concurrent.futures import ThreadPoolExecutor
import threading

print("✅ ВСЕ БИБЛИОТЕКИ ИМПОРТИРОВАНЫ!", flush=True)

# ============================================================
# НАСТРОЙКА - МАКСИМАЛЬНО БЫСТРАЯ
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
if not YANDEX_API_KEY:
    raise ValueError("❌ YANDEX_API_KEY не найден!")

FOLDER_ID = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
OWNER_ID = 6652898792

FREE_LIMIT = 20
PREMIUM_LIMIT = 999999999

# МАКСИМАЛЬНО БЫСТРЫЕ ТАЙМАУТЫ
GIGACHAT_TIMEOUT = 2   # 2 секунды
YANDEXGPT_TIMEOUT = 3  # 3 секунды
SEARCH_TIMEOUT = 2     # 2 секунды

print("✅ НАСТРОЙКА ЗАГРУЖЕНА!", flush=True)

# ============================================================
# КЭШ
# ============================================================
CACHE = {}
CACHE_TTL = 60  # 1 минута

def get_cache(key):
    if key in CACHE:
        data, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        del CACHE[key]
    return None

def set_cache(key, data):
    CACHE[key] = (data, time.time())

# ============================================================
# ВРЕМЯ
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
    now = get_moscow_time()
    return now.strftime('%d.%m.%Y')

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
# АНТИ-СПАМ
# ============================================================
user_last_message = {}

def check_spam(user_id):
    now = time.time()
    if user_id in user_last_message:
        if now - user_last_message[user_id] < 0.3:
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
# SUPABASE
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

use_supabase = True
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ Supabase подключен!", flush=True)
    try:
        test = supabase.table('users').select('*').limit(1).execute()
        print(f"✅ Таблица users найдена! Записей: {len(test.data)}", flush=True)
    except Exception as e:
        print(f"❌ Ошибка доступа к таблице users: {e}", flush=True)
        use_supabase = False
except Exception as e:
    print(f"❌ Ошибка подключения к Supabase: {e}", flush=True)
    use_supabase = False

def get_db_user(user_id):
    if use_supabase:
        try:
            response = supabase.table('users').select('*').eq('user_id', user_id).execute()
            if response.data:
                return response.data[0]
            return None
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result:
            columns = ['user_id', 'username', 'premium', 'messages_today', 'last_reset', 'premium_expires', 'is_admin', 'test_used', 'joined_at', 'is_owner']
            return dict(zip(columns, result))
        return None

def init_db():
    if use_supabase:
        try:
            try:
                supabase.table('users').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        premium INTEGER DEFAULT 0,
                        messages_today INTEGER DEFAULT 0,
                        last_reset TEXT,
                        premium_expires TEXT,
                        is_admin INTEGER DEFAULT 0,
                        test_used INTEGER DEFAULT 0,
                        joined_at TEXT,
                        is_owner INTEGER DEFAULT 0
                    )
                """).execute()
            
            try:
                supabase.table('banned').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS banned (
                        user_id BIGINT PRIMARY KEY
                    )
                """).execute()
            
            try:
                supabase.table('muted').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS muted (
                        user_id BIGINT PRIMARY KEY
                    )
                """).execute()
            
            try:
                supabase.table('total_stats').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS total_stats (
                        user_id BIGINT PRIMARY KEY,
                        total_messages INTEGER DEFAULT 0
                    )
                """).execute()
            
            try:
                supabase.table('premium_orders').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS premium_orders (
                        order_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            
            try:
                supabase.table('support_requests').select('*').limit(1).execute()
            except:
                supabase.sql("""
                    CREATE TABLE IF NOT EXISTS support_requests (
                        request_id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT,
                        text TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT
                    )
                """).execute()
            
            print("✅ Supabase таблицы готовы")
        except Exception as e:
            print(f"⚠️ Ошибка Supabase: {e}")
        return
    
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
    print("✅ Локальная SQLite база данных создана")

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
                    'premium_expires': None
                }
                supabase.table('users').insert(data).execute()
                try:
                    supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 0}).execute()
                except:
                    pass
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

def remove_premium(user_id):
    if use_supabase:
        try:
            supabase.table('users').update({'premium': 0, 'premium_expires': None}).eq('user_id', user_id).execute()
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 0, premium_expires = NULL WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()

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
                    remove_premium(user_id)
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

def add_month_to_premium(user_id):
    now = get_moscow_time()
    expires = get_premium_expires(user_id)
    
    if expires:
        try:
            current_date = datetime.strptime(expires, '%Y-%m-%d %H:%M:%S')
            current_date = current_date.replace(tzinfo=MOSCOW_TZ)
            if current_date > now:
                new_expires = (current_date + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
            else:
                new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
        except:
            new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        new_expires = (now + relativedelta(months=1)).strftime('%Y-%m-%d %H:%M:%S')
    
    if use_supabase:
        try:
            supabase.table('users').update({
                'premium': 1,
                'premium_expires': new_expires
            }).eq('user_id', user_id).execute()
            return new_expires
        except:
            return None
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('UPDATE users SET premium = 1, premium_expires = ? WHERE user_id = ?', (new_expires, user_id))
        conn.commit()
        conn.close()
        return new_expires

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
                    return True
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
            return True
        return messages < FREE_LIMIT

def increment_messages(user_id):
    if user_id == OWNER_ID or is_admin(user_id):
        return
    if use_supabase:
        try:
            response = supabase.table('users').select('messages_today').eq('user_id', user_id).execute()
            if response.data:
                current = response.data[0].get('messages_today', 0)
                supabase.table('users').update({'messages_today': current + 1}).eq('user_id', user_id).execute()
            response = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
            if response.data:
                total = response.data[0].get('total_messages', 0)
                supabase.table('total_stats').update({'total_messages': total + 1}).eq('user_id', user_id).execute()
            else:
                supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 1}).execute()
        except:
            pass
        return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = messages_today + 1 WHERE user_id = ?', (user_id,))
    c.execute('UPDATE total_stats SET total_messages = total_messages + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ============================================================
# МАТЕМАТИКА - ТОЛЬКО ЦИФРА!
# ============================================================
def solve_math(text):
    text_lower = text.lower().strip()
    
    # Проверяем что это математика
    if not re.search(r'\d', text_lower):
        return None
    
    # Проверяем что это не вопрос про человека или праздник
    if any(kw in text_lower for kw in ['кто', 'что', 'где', 'когда', 'почему', 'зачем']):
        return None
    
    # Убираем лишние слова
    clean_text = text_lower
    for word in ['сколько', 'будет', 'сколько будет', 'посчитай', 'реши', 'пример', 'скок', 'равно', 'a', 'b']:
        clean_text = clean_text.replace(word, '').strip()
    
    # Заменяем слова на символы
    clean_text = clean_text.replace(' ', '').replace('плюс', '+').replace('минус', '-')
    clean_text = clean_text.replace('умножить', '*').replace('разделить', '/')
    clean_text = clean_text.replace('х', '*').replace('×', '*').replace('÷', '/')
    
    # Проверяем что есть оператор
    if not re.search(r'[+\-*/]', clean_text):
        return None
    
    # Оставляем только цифры и операторы
    expr = re.sub(r'[^0-9+\-*/()=.]', '', clean_text)
    
    if expr and len(expr) > 1:
        try:
            # Защита
            if any(op in expr for op in ['__', 'import', 'eval', 'exec']):
                return None
            
            result = eval(expr)
            # ВОЗВРАЩАЕМ ТОЛЬКО ЧИСЛО!
            if result == int(result):
                return str(int(result))
            else:
                return str(round(result, 2))
        except:
            pass
    
    return None

# ============================================================
# БЫСТРЫЙ ПОИСК В ИНТЕРНЕТЕ
# ============================================================
def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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
        return None
    except:
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
                for item in results[:2]:
                    title = item.get('title', '')
                    snippet = re.sub(r'<[^>]+>', '', item.get('snippet', ''))[:150]
                    text += f"📚 {title}\n📝 {snippet}\n\n"
                return text
        return None
    except:
        return None

def search_all_internet(query):
    cache_key = f"search_{hash(query)}_{int(time.time()/60)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    
    # Параллельный поиск
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(search_google, query),
            executor.submit(search_wikipedia, query)
        ]
        
        for future in futures:
            try:
                result = future.result(timeout=SEARCH_TIMEOUT + 0.5)
                if result:
                    results.append(result)
            except:
                pass
    
    if results:
        final = "\n\n---\n\n".join(results)
        set_cache(cache_key, final)
        return final
    
    return None

# ============================================================
# GIGACHAT - СУПЕР БЫСТРЫЙ
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
        return None
    except:
        return None

def generate_with_gigachat(user_text, system_prompt):
    try:
        token = get_gigachat_token()
        if not token:
            return None
        
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        data = {
            "model": "GigaChat-Pro",
            "messages": [
                {"role": "system", "content": system_prompt[:800]},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.7,
            "max_tokens": 200
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        return None
    except:
        return None

# ============================================================
# YANDEXGPT
# ============================================================
def generate_with_yandexgpt(user_text, system_prompt):
    try:
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.7, "maxTokens": 150},
            "messages": [
                {"role": "system", "text": system_prompt[:800]},
                {"role": "user", "text": user_text}
            ]
        }
        response = requests.post(url, headers=headers, json=data, timeout=YANDEXGPT_TIMEOUT)
        if response.status_code == 200:
            return response.json()["result"]["alternatives"][0]["message"]["text"]
        return None
    except:
        return None

# ============================================================
# СИСТЕМНЫЙ ПРОМПТ - КОРОТКИЙ
# ============================================================
SYSTEM_PROMPT = """Ты AWESOME AI. Ты ищешь информацию в интернете и отвечаешь КОРОТКО.

📍 Москва, UTC+3
📅 {current_date}

ПРАВИЛА:
1. Отвечай КОРОТКО (1-2 предложения)
2. Давай ТОЛЬКО ФАКТЫ
3. Если не знаешь - скажи "Я не знаю"
4. Для математики отвечай ТОЛЬКО ЧИСЛО

Ты - самый быстрый и точный AI! 🔥"""

# ============================================================
# ГЛАВНАЯ ОБРАБОТКА - МАКСИМАЛЬНО БЫСТРАЯ
# ============================================================
def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    
    # ===== МАТЕМАТИКА - ТОЛЬКО ЦИФРА =====
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    # ===== ПРАЗДНИКИ =====
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник', 'сегодня праздник', 'седня']):
        today = get_current_date()
        search_result = search_all_internet(f"праздники {today}")
        if search_result:
            return f"📅 {today}\n\n{search_result}"
        else:
            return f"📅 {today}\n\nПраздников не найдено"
    
    # ===== ПОГОДА =====
    if any(kw in text_lower for kw in ['погода', 'weather']):
        city_match = re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)', text_lower)
        if city_match:
            city = city_match.group(2).strip()
            try:
                url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru"
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    temp = data['main']['temp']
                    desc = data['weather'][0]['description']
                    return f"🌤 {city}: {round(temp)}°C, {desc}"
            except:
                pass
            return f"🌤 Не удалось получить погоду"
        return "🌤 Напиши: погода в [город]"
    
    # ===== КУРС ВАЛЮТ =====
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро']):
        try:
            url = "https://api.exchangerate-api.com/v4/latest/USD"
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                data = response.json()
                rates = data.get('rates', {})
                usd_rub = rates.get('RUB', '?')
                eur_usd = rates.get('EUR', 1)
                eur_rub = usd_rub / eur_usd if eur_usd else '?'
                return f"💵 USD: {round(usd_rub, 2)}₽\nEUR: {round(eur_rub, 2)}₽"
        except:
            pass
        return "💵 Не удалось получить курс"
    
    # ===== БЫСТРЫЙ ПОИСК В ИНТЕРНЕТЕ =====
    if len(user_text) > 2:
        search_result = search_all_internet(user_text)
        if search_result:
            return f"🔍 {user_text}\n\n{search_result}"
    
    # ===== НЕЙРОСЕТИ (ПАРАЛЛЕЛЬНО) =====
    current_date = get_current_date()
    system_prompt = SYSTEM_PROMPT.format(current_date=current_date)
    
    if get_premium_status(user_id):
        system_prompt += "\n\n💎 PREMIUM"
    
    if image_description:
        system_prompt += f"\n\n📸 {image_description}"
    
    # Параллельный запуск
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        if GIGACHAT_AUTH_KEY:
            futures.append(executor.submit(generate_with_gigachat, user_text, system_prompt))
        futures.append(executor.submit(generate_with_yandexgpt, user_text, system_prompt))
        
        for future in futures:
            try:
                result = future.result(timeout=GIGACHAT_TIMEOUT + 0.5)
                if result and len(result) > 5:
                    results.append(result)
            except:
                pass
    
    if results:
        return results[0][:300]  # Коротко
    
    # ===== FALLBACK =====
    return "🤖 Задай вопрос, я найду ответ!"

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
# КОМАНДЫ БОТА
# ============================================================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

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
        "🌐 <b>ЧТО Я УМЕЮ:</b>\n"
        "🔍 Ищу в Google и Wikipedia\n"
        "💵 Показываю курс валют\n"
        "🧮 Решаю задачи (отвечаю только числом)\n"
        "🎨 Генерирую картинки\n\n"
        "💎 <b>Цена Premium: 100₽/месяц</b>\n\n"
        "🎁 <b>Тест Premium на 2 дня!</b>"
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
        "🔍 Ищу в Google и Wikipedia\n"
        "🌤 Погода\n"
        "💵 Курс валют\n"
        "🧮 Математика (только число)\n"
        "🎨 Генерирую картинки\n\n"
        "📋 <b>Команды:</b>\n"
        "/start — Меню\n"
        "/help — Помощь\n"
        "/status — Статус\n"
        "/premium — Premium\n"
        "/test — Пробный Premium\n"
        "/profile — Профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить\n\n"
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
        status_text = "👑 ВЛАДЕЛЕЦ — ♾️"
    elif is_admin(user_id):
        status_text = "👑 АДМИН — ♾️"
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
        else:
            remaining = FREE_LIMIT - messages
            if remaining < 0:
                remaining = 0
            status_text = f"🔓 Осталось: {remaining}/{FREE_LIMIT}"
    
    msg = bot.send_message(chat_id, f"📊 {status_text}", reply_markup=back_to_menu(), parse_mode='HTML')
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
            text = f"💎 PREMIUM до {expires_formatted}\n💰 100₽/месяц"
        else:
            text = "💎 У ТЕБЯ ЕСТЬ PREMIUM!\n💰 100₽/месяц"
    else:
        text = (
            f"💎 <b>PREMIUM</b>\n"
            f"♾️ БЕЗЛИМИТ\n"
            f"🚀 Приоритет\n"
            f"💰 100₽/месяц"
        )
    
    msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['test'])
def test_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
    if use_supabase:
        try:
            response = supabase.table('users').select('test_used, premium').eq('user_id', user_id).execute()
            if response.data:
                test_used = response.data[0].get('test_used', 0)
                premium = response.data[0].get('premium', 0)
            else:
                msg = bot.send_message(chat_id, "❌ Напиши /start")
                user_message_ids[user_id].append(msg.message_id)
                return
        except:
            msg = bot.send_message(chat_id, "❌ Ошибка")
            user_message_ids[user_id].append(msg.message_id)
            return
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT test_used, premium FROM users WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        if result is None:
            msg = bot.send_message(chat_id, "❌ Напиши /start")
            user_message_ids[user_id].append(msg.message_id)
            return
        test_used, premium = result
    
    if get_premium_status(user_id):
        msg = bot.send_message(chat_id, "💎 Уже Premium!", reply_markup=premium_menu(user_id), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        msg = bot.send_message(chat_id, "⛔ Тест использован!\nКупи: /premium", reply_markup=premium_menu(user_id), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if set_premium(user_id, "2d"):
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
            f"🎉 PREMIUM НА 2 ДНЯ!\n"
            f"♾️ БЕЗЛИМИТ\n"
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
        limit_text = "♾️"
    elif is_admin(user_id):
        status = "👑 АДМИН"
        limit_text = "♾️"
    elif premium:
        if expires and expires != "None":
            expires_formatted = format_date(expires)
            status = f"💎 PREMIUM (до {expires_formatted})"
        else:
            status = "💎 PREMIUM"
        limit_text = "♾️"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный ({remaining}/{FREE_LIMIT})"
        limit_text = f"{FREE_LIMIT}/день"
    
    username = m.from_user.username
    user_link = f"@{username}" if username else "Не указан"
    text = (
        f"👤 ПРОФИЛЬ\n\n"
        f"🆔 {user_id}\n"
        f"👤 {user_link}\n"
        f"💎 {status}\n"
        f"📨 {limit_text}\n"
        f"✉️ {messages}\n"
        f"📅 {joined_at or 'Неизвестно'}"
    )
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    
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
        premium_users = 0
        admin_users = 0
        for u in users:
            if isinstance(u, dict):
                if u.get('premium', 0) == 1:
                    premium_users += 1
                if u.get('is_admin', 0) == 1:
                    admin_users += 1
            else:
                if u[2] == 1:
                    premium_users += 1
                if u[7] == 1:
                    admin_users += 1
        
        text = (
            f"📊 СТАТИСТИКА\n\n"
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
                limit_text = "♾️"
            else:
                remaining = FREE_LIMIT - messages_today
                if remaining < 0:
                    remaining = 0
                status = "🔓 Бесплатный"
                limit_text = f"{remaining}/{FREE_LIMIT}"
            
            if use_supabase:
                try:
                    resp = supabase.table('total_stats').select('total_messages').eq('user_id', user_id).execute()
                    total = resp.data[0].get('total_messages', 0) if resp.data else 0
                except:
                    total = 0
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,))
                result = c.fetchone()
                conn.close()
                total = result[0] if result else 0
            
            text = (
                f"📊 ТВОЯ СТАТИСТИКА\n\n"
                f"👤 {status}\n"
                f"📨 {limit_text}\n"
                f"✉️ Сегодня: {messages_today}\n"
                f"📊 Всего: {total}"
            )
        else:
            text = "❌ Нет данных."
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    if user_id in user_histories:
        user_histories[user_id] = []
    if user_id in user_message_ids:
        user_message_ids[user_id] = []
    msg = bot.send_message(chat_id, "🧹 ОЧИЩЕНО", reply_markup=back_to_menu(), parse_mode='HTML')
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
        msg = bot.send_message(chat_id, f"🔴 Лимит! /premium")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt
        
        title = clean_prompt[:30]
        msg = bot.send_message(chat_id, f"🎨 {title}... ⏳", parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200 and len(response.content) > 1000:
            increment_messages(user_id)
            bot.send_photo(chat_id, photo=response.content, caption=f"🎨 {title}", parse_mode='HTML')
        else:
            msg = bot.send_message(chat_id, "⚠️ Ошибка.")
            user_message_ids[user_id].append(msg.message_id)
    except Exception as e:
        msg = bot.send_message(chat_id, f"⚠️ {e}")
        user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['support'])
def support_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/support', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📩 /support [текст]", parse_mode='HTML')
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
        except:
            pass
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('INSERT INTO support_requests (user_id, username, text, created_at) VALUES (?, ?, ?, ?)',
                  (user_id, m.from_user.username or "unknown", text, get_moscow_time().strftime('%d.%m.%Y %H:%M')))
        conn.commit()
        conn.close()
    msg = bot.send_message(chat_id, "✅ Отправлено!", parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📩 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='HTML')
    except:
        pass

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    delete_previous_messages(chat_id, user_id)
    text = m.text.replace('/feedback', '').strip()
    if not text:
        msg = bot.send_message(chat_id, "📝 /feedback [текст]", parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    msg = bot.send_message(chat_id, "✅ Спасибо! ❤️")
    user_message_ids[user_id].append(msg.message_id)
    try:
        bot.send_message(OWNER_ID, f"📝 @{m.from_user.username or 'Не указан'}\n📝 {text}", parse_mode='HTML')
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
    msg = bot.send_message(chat_id, "🛡️ АДМИН", reply_markup=admin_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ОБРАБОТЧИК ВСЕХ СООБЩЕНИЙ
# ============================================================
user_histories = {}

@bot.message_handler(func=lambda m: True)
def handle_all_messages(m):
    try:
        chat_id = m.chat.id
        user_id = m.from_user.id
        text = m.text.strip() if m.text else ""
        
        if text.startswith('/'):
            return
        
        if is_banned(user_id):
            bot.send_message(chat_id, "🚫 Забанен!")
            return
        
        if is_muted(user_id):
            bot.send_message(chat_id, "🔇 Замучен!")
            return
        
        if check_spam(user_id):
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
                f"🔴 Лимит! {remaining}/{FREE_LIMIT}\n💎 /premium",
                reply_markup=premium_menu(user_id),
                parse_mode='HTML'
            )
            return
        
        # ФОТО
        if m.photo:
            try:
                file_id = m.photo[-1].file_id
                file_info = bot.get_file(file_id)
                file_content = bot.download_file(file_info.file_path)
                img = Image.open(io.BytesIO(file_content))
                width, height = img.size
                img_desc = f"📸 {width}×{height}"
                response = process_message(user_id, text or "Что на картинке?", img_desc)
                increment_messages(user_id)
                bot.send_message(chat_id, response, reply_markup=back_to_menu(), parse_mode='HTML')
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ {e}")
            return
        
        # ТЕКСТ
        if text:
            bot.send_chat_action(chat_id, 'typing')
            
            response = process_message(user_id, text)
            if response:
                increment_messages(user_id)
                bot.send_message(
                    chat_id,
                    response,
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
            else:
                bot.send_message(
                    chat_id,
                    "❌ Ошибка.",
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
    except Exception as e:
        print(f"❌ Ошибка: {e}")

# ============================================================
# ОБРАБОТЧИК КНОПОК (сокращен)
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
            msg = bot.send_message(chat_id, "📩 /support [текст]", parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "draw":
            msg = bot.send_message(chat_id, "🎨 /draw [описание]", parse_mode='HTML')
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
                msg = bot.send_message(chat_id, "❌ Только Premium!", reply_markup=back_to_menu(), parse_mode='HTML')
                user_message_ids[user_id].append(msg.message_id)
                return
            text = (
                f"💎 PREMIUM\n"
                f"♾️ БЕЗЛИМИТ\n"
                f"🚀 Приоритет\n"
                f"💎 VIP\n\n"
                f"💰 100₽/месяц"
            )
            msg = bot.send_message(chat_id, text, reply_markup=premium_menu(user_id), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        if call.data == "i_paid":
            has_premium = get_premium_status(user_id)
            
            if use_supabase:
                try:
                    try:
                        supabase.table('premium_orders').select('*').limit(1).execute()
                    except:
                        supabase.sql("""
                            CREATE TABLE IF NOT EXISTS premium_orders (
                                order_id SERIAL PRIMARY KEY,
                                user_id BIGINT,
                                status TEXT DEFAULT 'pending',
                                created_at TEXT
                            )
                        """).execute()
                    
                    supabase.table('premium_orders').insert({
                        'user_id': user_id,
                        'status': 'pending',
                        'created_at': get_moscow_time().strftime('%d.%m.%Y %H:%M')
                    }).execute()
                    
                    response = supabase.table('premium_orders').select('order_id').eq('user_id', user_id).order('order_id', desc=True).limit(1).execute()
                    order_id = response.data[0]['order_id'] if response.data else None
                except Exception as e:
                    print(f"❌ Ошибка: {e}")
                    order_id = None
            else:
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
                f"✅ ЗАКАЗ #{order_id}\n"
                f"📌 {order_type}\n"
                f"⏳ {expires_text}\n"
                f"⏳ Ожидай.", 
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
                    f"💳 ЗАКАЗ #{order_id}\n"
                    f"👤 @{call.from_user.username or 'Не указан'}\n"
                    f"💰 100₽\n"
                    f"📌 {order_type}", 
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
            if use_supabase:
                try:
                    response = supabase.table('users').select('user_id, username').eq('is_admin', 1).execute()
                    admins = response.data
                except:
                    admins = []
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT user_id, username FROM users WHERE is_admin = 1')
                admins = c.fetchall()
                conn.close()
            if not admins:
                text = "👑 АДМИНЫ\n\nНет."
            else:
                text = "👑 АДМИНЫ\n\n"
                for admin in admins:
                    if isinstance(admin, dict):
                        text += f"• @{admin.get('username', admin.get('user_id'))}\n"
                    else:
                        text += f"• @{admin[1] if admin[1] else admin[0]}\n"
            msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_list_users":
            if use_supabase:
                try:
                    response = supabase.table('users').select('user_id, username, premium, is_admin').execute()
                    users = response.data
                    text = "👥 ПОЛЬЗОВАТЕЛИ\n\n"
                    for u in users:
                        uid = u.get('user_id')
                        username = u.get('username', 'Не указан')
                        premium = u.get('premium', 0)
                        is_admin_flag = u.get('is_admin', 0)
                        status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag == 1 else "💎 PREMIUM" if premium == 1 else "🔓 Бесплатный"
                        text += f"• @{username if username and username != 'unknown' else 'Не указан'} | {uid} | {status}\n"
                    msg = bot.send_message(chat_id, text[:4000], reply_markup=back_to_menu(), parse_mode='HTML')
                    user_message_ids[user_id].append(msg.message_id)
                except:
                    msg = bot.send_message(chat_id, "❌ Ошибка")
                    user_message_ids[user_id].append(msg.message_id)
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT user_id, username, premium, is_admin FROM users ORDER BY user_id')
                users = c.fetchall()
                conn.close()
                text = "👥 ПОЛЬЗОВАТЕЛИ\n\n"
                for user in users:
                    uid, username, premium, is_admin_flag = user
                    status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag == 1 else "💎 PREMIUM" if premium == 1 else "🔓 Бесплатный"
                    text += f"• @{username if username and username != 'unknown' else 'Не указан'} | {uid} | {status}\n"
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
            msg = bot.send_message(chat_id, "❌ Закрыто", reply_markup=back_to_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        if call.data == "admin_orders":
            admin_orders_cmd(call.message, user_id)
            return
        if call.data == "admin_support":
            admin_support_cmd(call.message, user_id)
            return
        
        # ЗАКАЗЫ
        if call.data.startswith("confirm_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("confirm_order:", ""))
            
            if use_supabase:
                try:
                    response = supabase.table('premium_orders').select('user_id, status').eq('order_id', order_id).execute()
                    if response.data:
                        target_user = response.data[0]['user_id']
                        status = response.data[0]['status']
                    else:
                        return
                except:
                    return
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT user_id, status FROM premium_orders WHERE order_id = ?', (order_id,))
                result = c.fetchone()
                conn.close()
                if result:
                    target_user, status = result
                else:
                    return
            
            if status != 'pending':
                return
            
            new_expires = add_month_to_premium(target_user)
            
            if new_expires:
                if use_supabase:
                    try:
                        supabase.table('premium_orders').update({'status': 'confirmed'}).eq('order_id', order_id).execute()
                    except:
                        pass
                else:
                    conn = sqlite3.connect('users.db')
                    c = conn.cursor()
                    c.execute('UPDATE premium_orders SET status = "confirmed" WHERE order_id = ?', (order_id,))
                    conn.commit()
                    conn.close()
                
                try:
                    bot.send_message(chat_id, f"✅ Заказ #{order_id} подтверждён!", parse_mode='HTML')
                except:
                    pass
                
                expires_formatted = format_date(new_expires)
                msg_text = f"🎉 PREMIUM АКТИВИРОВАН!\n✅ Заказ #{order_id}\n💎 До: {expires_formatted}"
                try:
                    bot.send_message(target_user, msg_text, parse_mode='HTML')
                except:
                    pass
            return
        
        if call.data.startswith("reject_order:"):
            if not is_authorized(user_id):
                return
            order_id = int(call.data.replace("reject_order:", ""))
            
            if use_supabase:
                try:
                    response = supabase.table('premium_orders').select('user_id, status').eq('order_id', order_id).execute()
                    if response.data:
                        target_user = response.data[0]['user_id']
                        status = response.data[0]['status']
                    else:
                        return
                except:
                    return
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT user_id, status FROM premium_orders WHERE order_id = ?', (order_id,))
                result = c.fetchone()
                conn.close()
                if result:
                    target_user, status = result
                else:
                    return
            
            if status != 'pending':
                return
            
            if use_supabase:
                try:
                    supabase.table('premium_orders').update({'status': 'rejected'}).eq('order_id', order_id).execute()
                except:
                    pass
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('UPDATE premium_orders SET status = "rejected" WHERE order_id = ?', (order_id,))
                conn.commit()
                conn.close()
            
            try:
                bot.send_message(chat_id, f"❌ Заказ #{order_id} отклонён!", parse_mode='HTML')
            except:
                pass
            try:
                bot.send_message(target_user, f"❌ ЗАКАЗ #{order_id} ОТКЛОНЁН", parse_mode='HTML')
            except:
                pass
            return
        
        if call.data.startswith("confirm_broadcast:"):
            if not is_authorized(user_id):
                return
            text = call.data.replace("confirm_broadcast:", "")
            if use_supabase:
                try:
                    response = supabase.table('users').select('user_id').execute()
                    users = response.data
                except:
                    users = []
            else:
                conn = sqlite3.connect('users.db')
                c = conn.cursor()
                c.execute('SELECT user_id FROM users')
                users = c.fetchall()
                conn.close()
            sent = 0
            failed = 0
            for user in users:
                try:
                    uid = user.get('user_id') if isinstance(user, dict) else user[0]
                    bot.send_message(uid, f"📢 {text}", parse_mode='HTML')
                    sent += 1
                    time.sleep(0.03)
                except:
                    failed += 1
            bot.send_message(chat_id, f"✅ {sent} | ❌ {failed}", parse_mode='HTML')
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
def admin_orders_cmd(message, user_id):
    chat_id = message.chat.id
    if use_supabase:
        try:
            response = supabase.table('premium_orders').select('*').eq('status', 'pending').order('order_id', desc=True).execute()
            orders = response.data
        except:
            orders = []
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT order_id, user_id, created_at FROM premium_orders WHERE status = "pending" ORDER BY order_id DESC')
        orders = c.fetchall()
        conn.close()
    if not orders:
        text = "💳 ЗАКАЗЫ\n\nНет."
    else:
        text = f"💳 ЗАКАЗЫ\n\nВсего: {len(orders)}\n\n"
        for order in orders:
            if isinstance(order, dict):
                text += f"🆔 #{order['order_id']} | 👤 {order['user_id']} | 📅 {order['created_at']}\n"
            else:
                text += f"🆔 #{order[0]} | 👤 {order[1]} | 📅 {order[2]}\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def admin_support_cmd(message, user_id):
    chat_id = message.chat.id
    if use_supabase:
        try:
            response = supabase.table('support_requests').select('*').eq('status', 'pending').order('request_id', desc=True).execute()
            requests = response.data
        except:
            requests = []
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT request_id, user_id, username, text, created_at FROM support_requests WHERE status = "pending" ORDER BY request_id DESC')
        requests = c.fetchall()
        conn.close()
    if not requests:
        text = "📩 ОБРАЩЕНИЯ\n\nНет."
    else:
        text = f"📩 ОБРАЩЕНИЯ\n\nВсего: {len(requests)}\n\n"
        for req in requests:
            if isinstance(req, dict):
                text += f"🆔 #{req['request_id']} | @{req.get('username', 'Не указан')} | {req['created_at']}\n📝 {req['text'][:50]}...\n\n"
            else:
                text += f"🆔 #{req[0]} | @{req[2] or 'Не указан'} | {req[4]}\n📝 {req[3][:50]}...\n\n"
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

# ============================================================
# ЗАПУСК
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — СУПЕР-БЫСТРЫЙ!")
print("=" * 60)
print(f"⏱️ ТАЙМАУТЫ:")
print(f"   GigaChat: {GIGACHAT_TIMEOUT} сек")
print(f"   YandexGPT: {YANDEXGPT_TIMEOUT} сек")
print(f"   Поиск: {SEARCH_TIMEOUT} сек")
print("=" * 60)
print("🧮 МАТЕМАТИКА: ТОЛЬКО ЧИСЛО")
print("🔍 ПОИСК В ИНТЕРНЕТЕ: ВКЛЮЧЕН")
print("=" * 60)
try:
    print(f"🤖 Бот: @{bot.get_me().username}")
except:
    print("🤖 Бот: @unknown")
if use_supabase:
    print("☁️ База: SUPABASE ✅")
else:
    print("💾 База: SQLite")
print("=" * 60)

print("✅ БОТ ЗАПУЩЕН!")

while True:
    try:
        bot.polling(none_stop=True, timeout=60)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск...")
        time.sleep(5)
