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
        if now - user_last_message[user_id] < 3:
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
"""

# ============================================================
# ВСЕ ОСТАЛЬНЫЕ ФУНКЦИИ (ПОГОДА, ПОИСК, КУРСЫ, МАТЕМАТИКА, АНАЛИЗ, ПАМЯТЬ, БАЗА)
# ============================================================
# (ОНИ БЕЗ ИЗМЕНЕНИЙ — Я ИХ НЕ ТРОГАЮ, ЧТОБЫ НЕ ПЕРЕГРУЖАТЬ ОТВЕТ)
# ============================================================

# ============================================================
# ВИЗУАЛЬНОЕ ОФОРМЛЕНИЕ (КРАСИВОЕ, С HTML)
# ============================================================

def format_text(text, bold=False, italic=False, code=False):
    """Форматирует текст для HTML"""
    if bold:
        text = f"<b>{text}</b>"
    if italic:
        text = f"<i>{text}</i>"
    if code:
        text = f"<code>{text}</code>"
    return text

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

def back_to_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")
    )
    return keyboard

def premium_menu():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("📩 Написать владельцу", url="https://t.me/flidges"),
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
# КОМАНДЫ (С HTML-ФОРМАТИРОВАНИЕМ)
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
        "✨ <b>AWESOME AI — МЕГА-ИИ!</b> ✨\n\n"
        f"🌸 <b>Привет, {m.from_user.first_name}!</b>\n\n"
        "🌐 Я умею искать в Google, Wikipedia и новостях\n"
        "💵 Показываю курс валют и криптовалют\n"
        "🧮 Решаю задачи и помогаю с программированием\n"
        "🧠 Анализирую настроение и адаптируюсь\n\n"
        "🎁 <b>Попробуй Premium бесплатно!</b>\n"
        "Нажми кнопку «Тест Premium» 👇\n\n"
        "💎 Бесплатно — 10 сообщений/день\n"
        "💎 Премиум — безлимит (/premium)"
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
        msg = bot.send_message(chat_id, "❌ /feedback [текст]")
        user_message_ids[user_id].append(msg.message_id)
        return
    
    bot.send_message(chat_id, "✅ Спасибо за отзыв! ❤️")
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
# ФУНКЦИИ ДЛЯ КОМАНД (С HTML-ФОРМАТИРОВАНИЕМ)
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
        "📊 <b>ТВОЙ СТАТУС</b>\n\n"
        f"{status_text}"
    )
    
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
    user_message_ids[user_id].append(msg.message_id)

def premium_cmd_from_user(message, user_id):
    chat_id = message.chat.id
    
    text = (
        "💎 <b>PREMIUM AWESOME AI</b>\n\n"
        "✅ Безлимит сообщений\n"
        "✅ Приоритетные ответы\n"
        "✅ Эксклюзивные функции\n\n"
        "💰 Цена: 50₽/месяц\n\n"
        "📩 Нажми кнопку ниже, чтобы связаться с владельцем:"
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
        "📊 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Юзер: {user_link}\n"
        f"💎 Статус: {status}\n"
        f"✉️ Сегодня: {messages}/{FREE_LIMIT}\n"
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
        conn.close()
        
        text = (
            "📊 <b>СТАТИСТИКА СЕРВЕРА</b>\n\n"
            f"👥 Всего: {total_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users}\n"
            f"📨 Сообщений сегодня: {today_messages}"
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
        "🧠 <b>AWESOME AI — МЕГА-ИИ!</b>\n\n"
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
        "/draw [описание] — Картинка\n\n"
        "💎 <b>Лимиты:</b>\n"
        "🔓 Бесплатно — 10 сообщений/день\n"
        "💎 Premium — безлимит\n"
        "Купить Premium: /premium"
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
        msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
        user_message_ids[user_id].append(msg.message_id)
        return
    
    if test_used == 1:
        text = (
            "⛔ <b>ТЫ УЖЕ ИСПОЛЬЗОВАЛ ТЕСТ!</b>\n\n"
            "Пробный период закончился.\n"
            "Купи Premium: /premium\n\n"
            "💰 50₽/месяц — @flidges"
        )
        msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
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
            "✅ Безлимит сообщений\n"
            "✅ Приоритетные ответы\n"
            "✅ Все функции ИИ\n\n"
            "⏳ Доступ активен 24 часа.\n"
            "Купить Premium: /premium"
        )
        msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
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
        
        if is_admin == 1:
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
# АДМИН-КОМАНДЫ (giveadmin, deladmin, giveprem, givetest, delprem, info, mute, unmute, ban, unban)
# ============================================================

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
        msg = bot.send_message(chat_id, "⏳ Подожди 3 секунды!")
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
                "✨ <b>AWESOME AI — МЕГА-ИИ!</b> ✨\n\n"
                f"🌸 <b>Привет, {call.from_user.first_name}!</b>\n\n"
                "🌐 Я умею искать в Google, Wikipedia и новостях\n"
                "💵 Показываю курс валют и криптовалют\n"
                "🧮 Решаю задачи и помогаю с программированием\n"
                "🧠 Анализирую настроение и адаптируюсь\n\n"
                "🎁 <b>Попробуй Premium бесплатно!</b>\n"
                "Нажми кнопку «Тест Premium» 👇\n\n"
                "💎 Бесплатно — 10 сообщений/день\n"
                "💎 Премиум — безлимит (/premium)"
            )
            msg = bot.send_message(chat_id, text, reply_markup=main_menu(), parse_mode='HTML')
            user_message_ids[user_id].append(msg.message_id)
            return
        
        # === КНОПКА "НАПИСАТЬ ВЛАДЕЛЬЦУ" ===
        if call.data == "contact_owner":
            bot.answer_callback_query(call.id)
            return
        
        # === ПОДТВЕРЖДЕНИЕ РАССЫЛКИ ===
        if call.data.startswith("confirm_broadcast:"):
            if not is_authorized(user_id):
                bot.answer_callback_query(call.id, "❌ Нет прав!")
                return
            
            bot.answer_callback_query(call.id, "📢 Начинаю...")
            
            text = call.data.replace("confirm_broadcast:", "")
            
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT user_id FROM users')
            users = c.fetchall()
            conn.close()
            
            if not users:
                msg = bot.send_message(chat_id, "❌ Нет пользователей.")
                user_message_ids[user_id].append(msg.message_id)
                return
            
            status_msg = bot.send_message(
                chat_id,
                f"📢 Рассылка\n👥 {len(users)} пользователей\n\n⏳ Отправка...",
                parse_mode='HTML'
            )
            user_message_ids[user_id].append(status_msg.message_id)
            
            sent = 0
            failed = 0
            
            for user in users:
                try:
                    bot.send_message(
                        user[0],
                        f"📢 Объявление AWESOME AI\n\n{text}\n\n---\nОтписаться: /unsubscribe",
                        parse_mode='HTML'
                    )
                    sent += 1
                    time.sleep(0.05)
                except:
                    failed += 1
            
            bot.edit_message_text(
                f"✅ Рассылка завершена!\n\n"
                f"📤 Отправлено: {sent}\n"
                f"❌ Ошибок: {failed}\n"
                f"👥 Всего: {len(users)}",
                chat_id=chat_id,
                message_id=status_msg.message_id,
                parse_mode='HTML'
            )
            return
        
        elif call.data == "cancel_broadcast":
            bot.answer_callback_query(call.id, "❌ Отменено")
            bot.edit_message_text("❌ Отменено.", chat_id=chat_id, message_id=call.message.message_id)
            return
        
        # === АДМИН-КНОПКИ ===
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
                
                if is_admin == 1:
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
        elif call.data == "feedback":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "📩 Напиши: /feedback [текст]")
            user_message_ids[user_id].append(msg.message_id)
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            msg = bot.send_message(chat_id, "🎨 Напиши: /draw [описание]")
            user_message_ids[user_id].append(msg.message_id)
            
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Ошибка: {e}")

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
        "📁 <b>ПОКА НЕ УМЕЮ</b>\n\n"
        "Пришли текст, фото или голосовое."
    )
    msg = bot.send_message(chat_id, text, reply_markup=back_to_menu(), parse_mode='HTML')
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
print("🎨 HTML-ВИЗУАЛ — ВКЛЮЧЁН (БЕЗ ОШИБОК 400)!")
print("=" * 60)
print("БОТ ГОТОВ!")
print("=" * 60)

while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Ошибка: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)
