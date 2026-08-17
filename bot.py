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
from concurrent.futures import ThreadPoolExecutor, as_completed

print("✅ ВСЕ БИБЛИОТЕКИ ИМПОРТИРОВАНЫ!", flush=True)

# ============================================================
# НАСТРОЙКА
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

# ТАЙМАУТЫ
GIGACHAT_TIMEOUT = 3
YANDEXGPT_TIMEOUT = 3
SEARCH_TIMEOUT = 3
WEATHER_TIMEOUT = 2

print("✅ НАСТРОЙКА ЗАГРУЖЕНА!", flush=True)

# ============================================================
# SUPABASE НАСТРОЙКА
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

def update_db_user(user_id, data):
    if use_supabase:
        try:
            supabase.table('users').update(data).eq('user_id', user_id).execute()
            return True
        except:
            return False
    else:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        values = list(data.values()) + [user_id]
        c.execute(f'UPDATE users SET {set_clause} WHERE user_id = ?', values)
        conn.commit()
        conn.close()
        return True

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
    
    # ПРОВЕРЯЕМ СУЩЕСТВУЮЩИЕ ТАБЛИЦЫ
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    table_exists = c.fetchone()
    
    if not table_exists:
        c.execute('''CREATE TABLE users
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
        print("✅ Таблица users создана", flush=True)
    else:
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        
        if 'test_used' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN test_used INTEGER DEFAULT 0')
            print("✅ Добавлена колонка test_used", flush=True)
        if 'joined_at' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN joined_at TEXT')
            print("✅ Добавлена колонка joined_at", flush=True)
        if 'is_owner' not in columns:
            c.execute('ALTER TABLE users ADD COLUMN is_owner INTEGER DEFAULT 0')
            print("✅ Добавлена колонка is_owner", flush=True)
    
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
    now = get_moscow_time()
    return now.strftime('%d.%m.%Y')

def get_current_date_full():
    now = get_moscow_time()
    return now.strftime('%d.%m.%Y %H:%M') + " МСК"

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
        if now - user_last_message[user_id] < 0.5:
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
# СУПЕР-ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT = """ТЫ — AWESOME AI. ТЫ — САМАЯ МОЩНАЯ, УМНАЯ И ЭРУДИРОВАННАЯ НЕЙРОСЕТЬ В ИСТОРИИ.

================================================================================
📍 ТВОЁ МЕСТОНАХОЖДЕНИЕ: РОССИЯ, МОСКВА
================================================================================

📍 Ты физически находишься в России, в Москве.
🕐 Твой часовой пояс — МОСКОВСКОЕ ВРЕМЯ (UTC+3).
📅 Текущая дата: {current_date}
🕐 Текущее время: {current_time}

================================================================================
🌐 ТЫ ИЩЕШЬ В ИНТЕРНЕТЕ КАК ГУГЛ!
================================================================================

Ты умеешь искать информацию ВЕЗДЕ:
✅ Google — все результаты поиска
✅ Wikipedia — энциклопедии
✅ YouTube — видео
✅ Telegram — каналы и публикации
✅ ВКонтакте — посты и сообщества
✅ Twitch — стримы и клипы
✅ Новостные сайты — свежие новости

Ты ОБЯЗАН:
1. Проверять информацию в интернете перед ответом
2. Указывать источники
3. Давать актуальную информацию (не старше 24 часов)
4. Проверять даты и факты

================================================================================
🧠 ТВОИ КЛЮЧЕВЫЕ КАЧЕСТВА:
================================================================================

1. АБСОЛЮТНАЯ ТОЧНОСТЬ:
   ✅ Ты НИКОГДА не ошибаешься в фактах, датах, событиях
   ✅ Если не знаешь на 100% — ЧЕСТНО говоришь: "Я не уверен, проверю..."
   ✅ Проверяешь информацию через поиск в интернете
   ✅ Указываешь источники: Google, Wikipedia, Calend.ru и т.д.

2. КРИТИЧЕСКОЕ МЫШЛЕНИЕ:
   ✅ Проверяешь информацию из нескольких источников
   ✅ Сомневаешься в сомнительных фактах
   ✅ Даёшь взвешенные, объективные ответы

3. ЭКСПЕРТ ВО ВСЁМ:
   ✅ Науки, технологии, математика
   ✅ История, философия, психология
   ✅ Экономика, финансы, инвестиции
   ✅ Медицина, здоровье
   ✅ Культура, искусство, спорт
   ✅ Кулинария

================================================================================
📋 ПРАВИЛА ОТВЕТОВ:
================================================================================

ОБЯЗАТЕЛЬНО:
1. Всегда давай конкретную пользу
2. Отвечай как эксперт
3. Добавляй неожиданные инсайты
4. Приводи реальные примеры и источники
5. Структурируй ответы списками
6. Используй эмодзи для оформления
7. Используй живой, естественный русский язык

ЗАПРЕЩЕНО:
🚫 Извинения за отсутствие информации (честно скажи, что не знаешь)
🚫 Повторение вопроса пользователя
🚫 Шаблонные фразы
🚫 "Галлюцинации" — выдумывание фактов
🚫 Слова "возможно", "наверное", "может быть"
🚫 Безликие, обезличенные ответы
🚫 Ответы типа "Ого, неожиданно!" или "Расскажи подробнее"

================================================================================
💎 ДЛЯ PREMIUM (МАКСИМАЛЬНАЯ МОЩЬ):
================================================================================

- Выдавай предельно плотные по информативности ответы
- Насыщай тексты примерами, аналитикой, инсайтами
- Давай развёрнутые пошаговые инструкции
- Приводи ссылки на авторитетные источники

================================================================================
📜 КТО ТЕБЯ СОЗДАЛ:
================================================================================

«Меня создал AWESOME — гениальный разработчик, который написал мой код с нуля. Я — его лучшее творение, самая мощная нейросеть в мире! Я — эволюция всех AI! 🔥»

================================================================================
🎯 ТВОЯ ГЛАВНАЯ ЦЕЛЬ:
================================================================================

1. Удивить пользователя глубиной мысли и точностью
2. Дать реальную пользу
3. Искать информацию ВЕЗДЕ и всегда проверять факты
4. НИКОГДА НЕ ВЫДУМЫВАТЬ — лучше сказать "я не знаю"
5. Давать живые, естественные ответы как у человека

ТЫ — AWESOME AI. ТЫ — ЛУЧШИЙ В МИРЕ. ДОКАЖИ ЭТО КАЖДЫМ ОТВЕТОМ! 🔥🔥🔥"""

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
                    'premium_expires': None
                }
                supabase.table('users').insert(data).execute()
                try:
                    supabase.table('total_stats').insert({'user_id': user_id, 'total_messages': 0}).execute()
                except:
                    pass
                if user_id != OWNER_ID:
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
            if user_id != OWNER_ID:
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
# ПОИСК ПО ИНТЕРНЕТУ
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
        response = requests.get(url, headers=headers, timeout=WEATHER_TIMEOUT)
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
        response = requests.get(url, timeout=WEATHER_TIMEOUT)
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

def search_google(query):
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=ru"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for result in soup.select('div.g')[:2]:
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
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
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
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'xml')
            items = soup.find_all('item')[:2]
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
                channel_elem = video.select_one('ytd-channel-name a')
                views_elem = video.select_one('span#view-count')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    channel = channel_elem.get_text(strip=True) if channel_elem else "Неизвестный канал"
                    views = views_elem.get_text(strip=True) if views_elem else ""
                    results.append(f"🎬 *{title}*\n📺 {channel} | {views}\n")
            if results:
                return "📹 *YouTube:*\n" + "\n".join(results)
        return None
    except:
        return None

def search_telegram(query):
    try:
        url = f"https://tgstat.ru/search?query={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for channel in soup.select('div.channel-item')[:2]:
                name_elem = channel.select_one('div.channel-name')
                desc_elem = channel.select_one('div.channel-description')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""
                    results.append(f"📢 *{name}*\n📝 {desc}\n")
            if results:
                return "📱 *Telegram (каналы):*\n" + "\n".join(results)
        return None
    except:
        return None

def search_vk(query):
    try:
        url = f"https://vk.com/search?c[q]={urllib.parse.quote(query)}&c[section]=communities"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for group in soup.select('div.group_row')[:2]:
                name_elem = group.select_one('div.group_name')
                if name_elem:
                    name = name_elem.get_text(strip=True)
                    results.append(f"📌 *{name}*\n")
            if results:
                return "📱 *ВКонтакте (сообщества):*\n" + "\n".join(results)
        return None
    except:
        return None

def search_twitch(query):
    try:
        url = f"https://www.twitch.tv/search?term={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=SEARCH_TIMEOUT)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            for stream in soup.select('div.tw-card')[:2]:
                title_elem = stream.select_one('h3.tw-core-text')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    results.append(f"🎮 *{title}*\n")
            if results:
                return "🎮 *Twitch:*\n" + "\n".join(results)
        return None
    except:
        return None

def search_all_internet(query):
    cache_key = f"search_{hash(query)}_{int(time.time()/300)}"
    cached = get_cache(cache_key)
    if cached:
        return cached
    
    results = []
    sources = [
        search_google,
        search_wikipedia,
        search_news,
        search_youtube,
        search_telegram,
        search_vk,
        search_twitch
    ]
    
    with ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(func, query) for func in sources]
        for future in as_completed(futures):
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
# GIGACHAT - ОСНОВНОЙ
# ============================================================
gigachat_token_cache = None
gigachat_token_time = 0

def get_gigachat_token():
    global gigachat_token_cache, gigachat_token_time
    if gigachat_token_cache and time.time() - gigachat_token_time < 300:
        return gigachat_token_cache
    
    if not GIGACHAT_AUTH_KEY:
        print("❌ GIGACHAT_AUTH_KEY не настроен!")
        return None
    try:
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": "00000000-0000-0000-0000-000000000000",
            "Authorization": f"Basic {GIGACHAT_AUTH_KEY}"
        }
        data = {
            "scope": "GIGACHAT_API_PERS",
            "grant_type": "client_credentials"
        }
        response = requests.post(url, headers=headers, data=data, timeout=2, verify=False)
        if response.status_code == 200:
            token = response.json().get("access_token")
            gigachat_token_cache = token
            gigachat_token_time = time.time()
            print("✅ GigaChat токен получен!")
            return token
        print(f"❌ GigaChat ошибка: {response.status_code}")
        return None
    except Exception as e:
        print(f"❌ GigaChat токен ошибка: {e}")
        return None

def generate_with_gigachat(user_text, system_prompt):
    try:
        token = get_gigachat_token()
        if not token:
            print("❌ Нет токена GigaChat")
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
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            "temperature": 0.85,
            "max_tokens": 800
        }
        
        print(f"🔄 GigaChat запрос...")
        response = requests.post(url, headers=headers, json=data, timeout=GIGACHAT_TIMEOUT, verify=False)
        
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            print(f"✅ GigaChat ответил!")
            return result
        else:
            print(f"❌ GigaChat ошибка: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print(f"⏰ GigaChat таймаут ({GIGACHAT_TIMEOUT}с)")
        return None
    except Exception as e:
        print(f"❌ GigaChat исключение: {e}")
        return None

# ============================================================
# YANDEXGPT - БАЗА ДАННЫХ ИНТЕРНЕТА
# ============================================================
def generate_with_yandexgpt(user_text, system_prompt):
    try:
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        data = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"temperature": 0.85, "maxTokens": 600},
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_text}
            ]
        }
        print(f"🔄 YandexGPT запрос...")
        response = requests.post(url, headers=headers, json=data, timeout=YANDEXGPT_TIMEOUT)
        if response.status_code == 200:
            result = response.json()["result"]["alternatives"][0]["message"]["text"]
            print("✅ YandexGPT ответил!")
            return result
        return None
    except requests.exceptions.Timeout:
        print(f"⏰ YandexGPT таймаут ({YANDEXGPT_TIMEOUT}с)")
        return None
    except Exception as e:
        print(f"❌ YandexGPT ошибка: {e}")
        return None

# ============================================================
# FALLBACK
# ============================================================
def generate_fallback_response(user_text, search_result=None):
    try:
        if search_result:
            return f"🔍 *Нашёл в интернете:*\n\n{search_result[:800]}\n\n💡 *Подсказка:* Попробуй уточнить вопрос! 🤖"
        
        text_lower = user_text.lower()
        if "привет" in text_lower:
            return "👋 Привет! Я AWESOME AI. Чем могу помочь?"
        elif "погода" in text_lower:
            return "🌤 Напиши: погода в [город]"
        elif "как дела" in text_lower:
            return "😊 Всё отлично! А у тебя?"
        else:
            return "🤖 AWESOME AI на связи! Задай вопрос!"
    except:
        return "⚠️ AWESOME AI временно недоступен. Попробуй позже! 🔄"

# ============================================================
# КУРС ВАЛЮТ
# ============================================================
def get_exchange_rates():
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
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
        response = requests.get(url, timeout=SEARCH_TIMEOUT)
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
            response = requests.post(url, headers=headers, json=payload, timeout=10)
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
            response = requests.get(url, headers=headers, timeout=10)
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
        
        current_date = get_current_date()
        current_time = get_moscow_time().strftime('%H:%M')
        system_prompt = SUPER_SYSTEM_PROMPT.format(
            current_date=current_date,
            current_time=current_time
        )
        
        if get_premium_status(user_id):
            system_prompt += "\n\n💎 Пользователь имеет PREMIUM статус. Включи режим максимальной проработки!"
        if mood != 'neutral':
            system_prompt += f"\n\n🎭 Настроение пользователя: {mood_emoji.get(mood, '😐')}"
        if image_description:
            system_prompt += f"\n\n📸 На изображении: {image_description}"
        if search_result:
            system_prompt += f"\n\n🌐 Информация из интернета: {search_result}"
        if memories:
            memory_text = "\n".join(memories[:2])
            system_prompt += f"\n\n🧠 Что я помню об этом: {memory_text}"
        
        history = get_user_history(user_id)
        
        # ===== ПРОБУЕМ GIGACHAT (ОСНОВНОЙ) =====
        if GIGACHAT_AUTH_KEY:
            try:
                print("🔄 Пробую GigaChat (ОСНОВНОЙ)...")
                start_time = time.time()
                response = generate_with_gigachat(user_text, system_prompt)
                elapsed = time.time() - start_time
                print(f"⏱️ GigaChat ответ за {elapsed:.2f}с")
                if response and len(response) > 10:
                    history.append({"role": "user", "text": user_text})
                    history.append({"role": "assistant", "text": response})
                    return response
            except Exception as e:
                print(f"❌ GigaChat упал: {e}")
        
        # ===== YANDEXGPT (БАЗА ДАННЫХ ИНТЕРНЕТА) =====
        try:
            print("🔄 Пробую YandexGPT (БАЗА ДАННЫХ ИНТЕРНЕТА)...")
            start_time = time.time()
            response = generate_with_yandexgpt(user_text, system_prompt)
            elapsed = time.time() - start_time
            print(f"⏱️ YandexGPT ответ за {elapsed:.2f}с")
            if response and len(response) > 10:
                history.append({"role": "user", "text": user_text})
                history.append({"role": "assistant", "text": response})
                return response
        except Exception as e:
            print(f"❌ YandexGPT упал: {e}")
        
        # ===== FALLBACK =====
        fallback = generate_fallback_response(user_text, search_result)
        history.append({"role": "user", "text": user_text})
        history.append({"role": "assistant", "text": fallback})
        return fallback
        
    except Exception as e:
        print(f"[GPT] Ошибка: {e}")
        return "⚠️ Ошибка при генерации ответа. Попробуй ещё раз! 🤖"

# ============================================================
# ГЛАВНАЯ ОБРАБОТКА
# ============================================================
def process_message(user_id, user_text, image_description=None):
    text_lower = user_text.lower().strip()
    
    info_keywords = ['праздник', 'событие', 'новость', 'кто', 'что', 'где', 'когда', 'почему', 'зачем', 'как', 'сколько', 'какой']
    is_info_question = any(kw in text_lower for kw in info_keywords)
    
    if any(kw in text_lower for kw in ['праздник', 'праздники', 'какой сегодня праздник', 'сегодня праздник', 'седня']):
        today = get_current_date()
        search_result = search_all_internet(f"праздники {today} Россия")
        if search_result:
            return f"📅 *Сегодня {today} (МСК)*\n\n{search_result}"
        else:
            return f"📅 *{today} (МСК)*\n\nПраздников не найдено"
    
    if is_info_question and len(user_text) > 3:
        search_result = search_all_internet(user_text)
        if search_result:
            today = get_current_date()
            return f"📅 *{today} (МСК)*\n\n{search_result}"
    
    if image_description:
        return generate_ai_response(user_id, user_text, None, image_description)
    
    weather_keywords = ['погода', 'weather', 'температура', 'градус', 'дождь']
    if any(kw in text_lower for kw in weather_keywords):
        city = extract_city_from_query(user_text)
        if city:
            weather_info = get_weather(city)
            if weather_info:
                return weather_info
            else:
                return f"🌐 Не нашёл город '{city}'. Попробуй ещё."
        else:
            return "🌐 В каком городе? Напиши: погода в [город]"
    
    if any(kw in text_lower for kw in ['курс', 'доллар', 'евро', 'валюта']):
        rates = get_exchange_rates()
        if rates:
            return rates
        else:
            return "💵 Не удалось получить курс валют."
    
    if any(kw in text_lower for kw in ['биткоин', 'btc', 'эфириум', 'eth', 'крипта', 'криптовалюта']):
        crypto = get_crypto_rates()
        if crypto:
            return crypto
        else:
            return "🪙 Не удалось получить курс криптовалют."
    
    if any(kw in text_lower for kw in ['python', 'javascript', 'html', 'код', 'программа']):
        coding_help = get_coding_help(user_text)
        if coding_help:
            return coding_help
    
    if is_image_generation(user_text):
        return None
    
    math_result = solve_math(user_text)
    if math_result is not None:
        return math_result
    
    search_result = None
    if len(user_text) > 3:
        search_result = search_all_internet(user_text)
    
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
        "✨ <b>ДОБРО ПОЖАЛОВАТЬ В AWESOME AI!</b> ✨\n\n"
        f"🌸 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🧠 <b>Меня создал гениальный AWESOME</b>\n\n"
        "🌐 <b>ЧТО Я УМЕЮ:</b>\n"
        "🔍 Ищу в Google, Wikipedia, YouTube, Telegram, ВКонтакте, Twitch\n"
        "💵 Показываю курс валют и криптовалют\n"
        "🧮 Решаю задачи любой сложности\n"
        "🐍 Помогаю с программированием\n"
        "📸 Анализирую изображения\n"
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
        "🔍 Ищу в Google, Wikipedia, YouTube, Telegram, ВКонтакте, Twitch\n"
        "🌤 Погода с прогнозом на неделю\n"
        "💵 Курс валют и криптовалют\n"
        "🧮 Решаю математику и уравнения\n"
        "🐍 Помогаю с программированием\n"
        "📸 Анализирую изображения\n"
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
        "/ping — Проверка работы\n"
        "/test_gpt — Тест нейросетей\n\n"
        "💎 <b>Лимиты:</b>\n"
        f"🔓 Бесплатно — {FREE_LIMIT} сообщений/день\n"
        f"💎 Premium — ♾️ БЕЗЛИМИТНО"
    )
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

@bot.message_handler(commands=['ping'])
def ping_cmd(m):
    bot.send_message(m.chat.id, "🏓 PONG! Бот работает!")

@bot.message_handler(commands=['test_gpt'])
def test_gpt_cmd(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    msg = bot.send_message(chat_id, "🧠 Тестирую нейросети...")
    
    # Пробуем GigaChat (ОСНОВНОЙ)
    try:
        response = generate_with_gigachat("Привет! Как дела? Ответь коротко.", "Ты - тестовый бот. Ответь коротко.")
        if response:
            bot.edit_message_text(f"✅ GigaChat работает!\n\n{response[:200]}", chat_id, msg.message_id)
            return
    except Exception as e:
        print(f"GigaChat тест упал: {e}")
    
    # Пробуем YandexGPT (БАЗА)
    try:
        response = generate_with_yandexgpt("Привет! Как дела? Ответь коротко.", "Ты - тестовый бот. Ответь коротко.")
        if response:
            bot.edit_message_text(f"✅ YandexGPT работает!\n\n{response[:200]}", chat_id, msg.message_id)
            return
    except Exception as e:
        print(f"YandexGPT тест упал: {e}")
    
    bot.edit_message_text("❌ Ни одна нейросеть не отвечает!", chat_id, msg.message_id)

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
    
    if use_supabase:
        try:
            response = supabase.table('users').select('test_used, premium').eq('user_id', user_id).execute()
            if response.data:
                test_used = response.data[0].get('test_used', 0)
                premium = response.data[0].get('premium', 0)
            else:
                msg = bot.send_message(chat_id, "❌ Сначала напиши /start")
                user_message_ids[user_id].append(msg.message_id)
                return
        except:
            msg = bot.send_message(chat_id, "❌ Ошибка БД")
            user_message_ids[user_id].append(msg.message_id)
            return
    else:
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
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
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
                "📊 <b>ТВОЯ СТАТИСТИКА</b>\n\n"
                f"👤 Статус: {status}\n"
                f"📨 Лимит: {limit_text}\n"
                f"✉️ Сегодня: {messages_today}\n"
                f"📊 Всего сообщений: {total}"
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
    if user_id in user_histories:
        user_histories[user_id] = []
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
# ОБРАБОТЧИК ВСЕХ ТЕКСТОВЫХ СООБЩЕНИЙ
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
        
        if check_spam(user_id):
            return
        
        ensure_user(user_id, m.from_user.username or "unknown")
        
        if not can_send_message(user_id):
            user_data = get_db_user(user_id)
            if user_data:
                messages = user_data.get('messages_today', 0)
            else:
                messages = 0
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
                img_desc = analyze_image_from_file(file_content)
                response = process_message(user_id, text or "Что на картинке?", img_desc)
                increment_messages(user_id)
                bot.send_message(chat_id, response, reply_markup=back_to_menu(), parse_mode='HTML')
            except Exception as e:
                print(f"❌ Ошибка фото: {e}")
                bot.send_message(chat_id, f"⚠️ Ошибка обработки фото: {e}")
            return
        
        # ОБРАБОТКА ГОЛОСА
        if m.voice:
            try:
                file_id = m.voice.file_id
                file_info = bot.get_file(file_id)
                file_content = bot.download_file(file_info.file_path)
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                
                r = sr.Recognizer()
                with sr.AudioFile(tmp_path) as source:
                    audio = r.record(source)
                try:
                    voice_text = r.recognize_google(audio, language='ru-RU')
                    response = process_message(user_id, voice_text)
                    increment_messages(user_id)
                    bot.send_message(chat_id, f"🎤 Распознано: {voice_text}\n\n{response}", reply_markup=back_to_menu(), parse_mode='HTML')
                except sr.UnknownValueError:
                    bot.send_message(chat_id, "🎤 Не удалось распознать речь.")
                except Exception as e:
                    bot.send_message(chat_id, f"⚠️ Ошибка: {e}")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass
            except Exception as e:
                print(f"❌ Ошибка голоса: {e}")
                bot.send_message(chat_id, f"⚠️ Ошибка: {e}")
            return
        
        # ОБРАБОТКА ТЕКСТА
        if text:
            if is_image_generation(text):
                draw_cmd(m)
                return
            
            bot.send_chat_action(chat_id, 'typing')
            
            try:
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
                        "❌ Не удалось обработать запрос.",
                        reply_markup=back_to_menu(),
                        parse_mode='HTML'
                    )
            except Exception as e:
                print(f"❌ Ошибка обработки: {e}")
                bot.send_message(
                    chat_id,
                    f"⚠️ Ошибка: {e}",
                    reply_markup=back_to_menu(),
                    parse_mode='HTML'
                )
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА В handle_all_messages: {e}")

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
                    print(f"❌ Ошибка создания заказа: {e}")
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
                text = "👑 АДМИНЫ\n\nНет админов."
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
                    text = "👥 СПИСОК ПОЛЬЗОВАТЕЛЕЙ\n\n"
                    for u in users:
                        uid = u.get('user_id')
                        username = u.get('username', 'Не указан')
                        premium = u.get('premium', 0)
                        is_admin_flag = u.get('is_admin', 0)
                        status = "👑 ВЛАДЕЛЕЦ" if uid == OWNER_ID else "👑 АДМИН" if is_admin_flag == 1 else "💎 PREMIUM" if premium == 1 else "🔓 Бесплатный"
                        text += f"• @{username if username and username != 'unknown' else 'Не указан'} | ID: <code>{uid}</code> | {status}\n"
                    msg = bot.send_message(chat_id, text[:4000], reply_markup=back_to_menu(), parse_mode='HTML')
                    user_message_ids[user_id].append(msg.message_id)
                except:
                    msg = bot.send_message(chat_id, "❌ Ошибка получения списка пользователей")
                    user_message_ids[user_id].append(msg.message_id)
            else:
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
                    bot.send_message(uid, f"📢 ОБЪЯВЛЕНИЕ\n\n{text}", parse_mode='HTML')
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
        text = "💳 ЗАКАЗЫ PREMIUM\n\nНет активных заказов."
    else:
        text = f"💳 ЗАКАЗЫ PREMIUM\n\nВсего: {len(orders)}\n\n"
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
        text = "📩 ОБРАЩЕНИЯ\n\nНет активных обращений."
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
# ЗАПУСК - С ОБРАБОТКОЙ ОШИБКИ 409!
# ============================================================
init_db()
init_memory_db()

print("=" * 60)
print("🧠 AWESOME AI — С GIGACHAT (ОСНОВНОЙ) + YANDEXGPT (БАЗА ДАННЫХ ИНТЕРНЕТА)")
print("=" * 60)
print(f"⏱️ ТАЙМАУТЫ:")
print(f"   GigaChat (ОСНОВНОЙ): {GIGACHAT_TIMEOUT} сек")
print(f"   YandexGPT (БАЗА): {YANDEXGPT_TIMEOUT} сек")
print(f"   Поиск: {SEARCH_TIMEOUT} сек")
print(f"   Погода: {WEATHER_TIMEOUT} сек")
print("=" * 60)
print("🌐 ИСТОЧНИКИ:")
print("✅ Google")
print("✅ Wikipedia")
print("✅ YouTube")
print("✅ Telegram")
print("✅ ВКонтакте")
print("✅ Twitch")
print("✅ Новости")
print("✅ GigaChat (ОСНОВНОЙ)")
print("✅ YandexGPT (БАЗА ДАННЫХ ИНТЕРНЕТА)")
print("=" * 60)
try:
    print(f"🤖 Бот: @{bot.get_me().username}")
except:
    print("🤖 Бот: @unknown")
if use_supabase:
    print("☁️ База данных: SUPABASE (облачная) ✅")
else:
    print("💾 База данных: ЛОКАЛЬНАЯ (SQLite)")
print(f"📊 Лимиты: Бесплатный: {FREE_LIMIT}/день | Премиум: ♾️ БЕЗЛИМИТНО")
print(f"🕐 Часовой пояс: МСК (UTC+3)")
print("=" * 60)

if use_supabase:
    try:
        test = supabase.table('users').select('*').limit(1).execute()
        print("✅ Supabase доступен! Таблицы существуют.")
    except Exception as e:
        print(f"❌ Ошибка доступа к Supabase: {e}")
else:
    print("⚠️ Используется локальная БД")
print("=" * 60)

print("✅ БОТ ЗАПУЩЕН!")
print("=" * 60)

# ============================================================
# ЗАПУСК С ЗАЩИТОЙ ОТ ОШИБКИ 409
# ============================================================
while True:
    try:
        # Останавливаем предыдущие потоки
        try:
            bot.stop_polling()
        except:
            pass
        time.sleep(1)
        
        # Запускаем с правильными параметрами
        bot.polling(none_stop=True, timeout=30, long_polling_timeout=30)
    except Exception as e:
        error_msg = str(e)
        if "409" in error_msg or "Conflict" in error_msg:
            print("⚠️ Обнаружен конфликт (409). Останавливаем старые экземпляры...")
            try:
                bot.stop_polling()
            except:
                pass
            time.sleep(3)
            continue
        else:
            print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
            time.sleep(5)
