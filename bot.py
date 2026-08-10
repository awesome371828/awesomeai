# Устанавливаем библиотеки (Colab часто сбрасывает их)
!pip install telebot requests beautifulsoup4 Pillow speechrecognition python-dateutil

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
TELEGRAM_TOKEN = "8336209662:AAHOZeKwoncRM7NVtqlyWq_DlJRUIyz3O8w"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"
YANDEX_API_KEY = "AQVN1rPml9-6Yb_CrUmydBjzCxvN9IWXRm0rl2Bk"
OWNER_ID = 6652898792  # flidges

# ЛИМИТ СООБЩЕНИЙ ДЛЯ БЕСПЛАТНОГО ТАРИФА (СНИЖЕН ДО 10)
FREE_LIMIT = 10

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
    except sqlite3.OperationalError:
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
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
init_db()
bot = telebot.TeleBot(TELEGRAM_TOKEN)
last_search = {}
user_histories = {}

# КЛАССИЧЕСКИЙ, ПРОВЕРЕННЫЙ ПРОМПТ
SYSTEM_PROMPT = """Ты — AWESOME AI. Ты супер-интеллект.

Твой язык — живой, разговорный, с юмором, но без пафоса.
Отвечай на всё подряд. Если человек спрашивает "как дела братуха", отвечай дружелюбно: "Норм, братуха, а у тебя как?".
Никаких заготовленных фраз, шаблонов и философских вопросов.
Если тебя о чем-то просят, ты отвечаешь конкретно на это.
Ты не переспрашиваешь "Чем могу помочь", если это не нужно.
Если тебе задают вопрос, ответ на который требует свежих данных (новости, погода), отвечай: "Поищи в интернете: запрос"."""

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
# ГЕНЕРАЦИЯ КАРТИНОК
# ============================================================
def generate_image(prompt):
    try:
        clean_prompt = prompt
        for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
            clean_prompt = clean_prompt.replace(word, '').strip()
        if not clean_prompt:
            clean_prompt = prompt

        # Способ 1: Pollinations.ai
        try:
            url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean_prompt)}?width=512&height=512&nologo=true"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200 and len(response.content) > 1000:
                return response.content
        except:
            pass

        # Способ 2: Craiyon
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
    except Exception as e:
        print(f"Генерация ошибка: {e}")
        return None

def fix_title(prompt):
    title = prompt
    for word in ['нарисуй', 'сгенерируй', 'покажи', 'картинку', 'изображение', '/draw']:
        title = title.replace(word, '').strip()

    if not title or len(title) < 2:
        return "Картинка"

    if len(title.split()) < 5:
        word_map = {
            'кота': 'Кот', 'собаку': 'Собака', 'машину': 'Машина',
            'цветок': 'Цветок', 'дерево': 'Дерево', 'солнце': 'Солнце',
            'луну': 'Луна', 'звезду': 'Звезда', 'гору': 'Гора',
            'море': 'Море', 'лес': 'Лес', 'поле': 'Поле',
            'город': 'Город', 'страну': 'Страна', 'мир': 'Мир',
            'человека': 'Человек', 'друга': 'Друг', 'врага': 'Враг',
            'героя': 'Герой', 'злодея': 'Злодей', 'птицу': 'Птица',
            'рыбу': 'Рыба', 'змею': 'Змея', 'волка': 'Волк',
            'лису': 'Лиса', 'медведя': 'Медведь', 'зайца': 'Заяц',
            'ежа': 'Ёж', 'белку': 'Белка', 'фотку': 'Фотка',
            'аватарку': 'Аватарка', 'картинку': 'Картинка'
        }
        title_lower = title.lower()
        for key, value in word_map.items():
            if key in title_lower:
                return value

        if title.endswith('а') and len(title) > 3: title = title[:-1]
        elif title.endswith('у') and len(title) > 3: title = title[:-1]
        elif title.endswith('я') and len(title) > 3: title = title[:-1]
        if not title or len(title) < 2: return "Картинка"
        return title[0].upper() + title[1:] if len(title) > 1 else title.upper()

    return title

# ============================================================
# YANDEX VISION
# ============================================================
def ocr_image(data):
    try:
        url = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        img = Image.open(io.BytesIO(data))
        img = ImageEnhance.Contrast(img).enhance(2.0)
        img = ImageEnhance.Sharpness(img).enhance(2.0)
        img = img.convert('L')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=95)
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
            return " ".join(all_text).strip() if all_text else None
        return None
    except:
        return None

# ============================================================
# ГОЛОС
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
# ОПРЕДЕЛЕНИЕ ТИПА ЗАПРОСА
# ============================================================
def is_text_generation(text):
    text_keywords = [
        'сгенерируй текст', 'напиши текст', 'придумай текст', 'сочини текст',
        'сгенерируй стих', 'напиши стих', 'придумай стих', 'сочини стих',
        'сгенерируй поздравление', 'напиши поздравление', 'придумай поздравление',
        'сгенерируй рецепт', 'напиши рецепт', 'придумай рецепт',
        'сгенерируй рассказ', 'напиши рассказ', 'придумай рассказ', 'сочини рассказ',
        'сгенерируй письмо', 'напиши письмо', 'придумай письмо',
        'сгенерируй сценарий', 'напиши сценарий',
        'текст для', 'описание', 'история про',
        'сгенерируй про', 'напиши про'
    ]
    return any(kw in text.lower() for kw in text_keywords)

def is_image_generation(text):
    image_keywords = ['нарисуй', 'покажи', 'картинку', 'изображение']
    return any(kw in text.lower() for kw in image_keywords)

# ============================================================
# МГНОВЕННЫЙ МАТЕМАТИЧЕСКИЙ ПРОЦЕССОР
# ============================================================
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
        result = eval(clean_expr)
        return result
    except:
        return None

# ============================================================
# ОТПРАВКА В GPT (Интеллектуальный процессор)
# ============================================================
def send_to_gpt(user_id, full_message):
    user_histories[user_id].append({"role": "user", "text": full_message})
    if len(user_histories[user_id]) > 31:
        user_histories[user_id] = [user_histories[user_id][0]] + user_histories[user_id][-30:]

    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
    data = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt/latest",
        "completionOptions": {"temperature": 0.9, "maxTokens": 2000},
        "messages": user_histories[user_id]
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            ans = response.json()["result"]["alternatives"][0]["message"]["text"]
            user_histories[user_id].append({"role": "assistant", "text": ans})
            return ans
        return "⚠️ Ошибка подключения к ИИ."
    except:
        return "⚠️ Сетевая ошибка."

# ============================================================
# ЦИКЛ ОБРАБОТКИ: ИИ -> ПОИСК -> ОТВЕТ
# ============================================================
def ask_gpt(user_id, user_text, image_text=None):
    if user_id not in user_histories:
        user_histories[user_id] = [{"role": "system", "text": SYSTEM_PROMPT}]

    full = user_text
    if image_text:
        full = f"{user_text}\n\n(На фото текст: {image_text})"

    if is_image_generation(user_text):
        return None

    if is_text_generation(user_text):
        full = f"{user_text}\n\n(Сгенерируй качественный, интересный текст на эту тему.)"
        return send_to_gpt(user_id, full)

    math_result = solve_math(user_text)
    if math_result is not None:
        bot.send_message(user_id, f"🧮 *Результат:* `{math_result}`")
        full = f"Пользователь спросил: '{user_text}'. Я посчитал и получил {math_result}. Напиши живой, короткий ответ, подтверждающий результат."
        return send_to_gpt(user_id, full)

    return send_to_gpt(user_id, full)

# ============================================================
# ГЕНЕРАЦИЯ И ОТПРАВКА КАРТИНКИ
# ============================================================
def generate_and_send_image(m, prompt):
    user_id = m.from_user.id
    if not can_send_message(user_id):
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день исчерпан!\nКупи Premium: /premium")
        return

    title = fix_title(prompt)

    bot.send_message(m.chat.id, f"🎨 Генерирую картинку по запросу: *{title}*...\n⏳ 10-20 секунд.", parse_mode='Markdown')

    image_data = generate_image(prompt)

    if image_data:
        increment_messages(user_id)
        try:
            bot.send_photo(m.chat.id, photo=image_data, caption=f"🎨 *{title}*\n\n✨ Сгенерировано AWESOME AI", parse_mode='Markdown')
        except:
            bot.send_message(m.chat.id, "⚠️ Ошибка при отправке")
    else:
        bot.send_message(m.chat.id, "⚠️ Не удалось сгенерировать картинку. Попробуй другой запрос.")

# ============================================================
# ФУНКЦИИ ДЛЯ КНОПОК
# ============================================================
def status_cmd_from_user(message, user_id):
    ensure_user(user_id, "unknown")
    if user_id == OWNER_ID or is_admin(user_id):
        bot.send_message(message.chat.id, "📊 Твой статус:\n👑 АДМИН — безлимит!")
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
    bot.send_message(message.chat.id, f"📊 Твой статус:\n{status_text}")

def premium_cmd_from_user(message, user_id):
    bot.send_message(
        message.chat.id,
        "💎 PREMIUM\n\n"
        "Что даёт Premium:\n"
        "✅ Безлимит сообщений\n"
        "✅ Приоритетные ответы\n"
        "✅ Эксклюзивные функции\n\n"
        "💰 Цена: 50₽/месяц\n\n"
        "📩 Для оплаты пиши @flidges"
    )

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
        status = "👑 АДМИН — безлимит!"
    elif premium:
        status = f"💎 PREMIUM (до {expires})"
    else:
        remaining = FREE_LIMIT - messages
        if remaining < 0:
            remaining = 0
        status = f"🔓 Бесплатный (осталось {remaining}/{FREE_LIMIT})"

    # Берем username самого пользователя, а не бота
    username = message.from_user.username
    user_link = f"@{username}" if username else "Не указан"

    bot.send_message(
        message.chat.id,
        f"📊 Твой профиль\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Юзер: {user_link}\n"
        f"📅 Вход: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"💎 Статус: {status}\n"
        f"✉️ Сообщений сегодня: {messages}/{FREE_LIMIT}"
    )

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
        c.execute('SELECT COUNT(*) FROM banned')
        banned_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM muted')
        muted_users = c.fetchone()[0]
        conn.close()

        bot.send_message(
            message.chat.id,
            f"🏴 Статистика сервера\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"💎 Premium: {premium_users}\n"
            f"🔓 Бесплатных: {total_users - premium_users}\n"
            f"🚫 Забанено: {banned_users}\n"
            f"🔇 Замучено: {muted_users}\n\n"
            f"📨 Сообщений сегодня: {today_messages}\n"
            f"📨 За всё время: {all_time_messages}"
        )
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
            user_status = f"🔓 Бесплатный (осталось {remaining}/{FREE_LIMIT})"

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT total_messages FROM total_stats WHERE user_id = ?', (user_id,))
    res = c.fetchone()
    total_user_messages = res[0] if res else 0
    conn.close()

    bot.send_message(
        message.chat.id,
        f"📊 Твоя статистика\n\n"
        f"👤 Статус: {user_status}\n"
        f"✉️ Сегодня: {user_messages}\n"
        f"📨 Всего: {total_user_messages}"
    )

def clear_cmd_from_user(message, user_id):
    user_histories[user_id] = [{"role": "system", "text": SYSTEM_PROMPT}]
    bot.send_message(message.chat.id, "🧹 История очищена!")

def help_cmd_from_user(message, user_id):
    text = (
        "📋 *Все команды AWESOME AI:*\n\n"
        "/start — Главное меню\n"
        "/help — Помощь и команды\n"
        "/status — Мой статус\n"
        "/premium — Купить Premium\n"
        "/profile — Мой профиль\n"
        "/stats — Статистика\n"
        "/clear — Очистить историю\n"
        "/feedback — Отправить отзыв\n"
        "/draw [описание] — Сгенерировать картинку\n\n"
        "✍️ *Генерация текста:*\n"
        "сгенерируй текст про сову\n"
        "напиши стих про осень\n"
        "придумай поздравление\n\n"
        "🌐 *Я ищу актуальную информацию в интернете!*"
    )
    if user_id == OWNER_ID or is_admin(user_id):
        text += (
            "\n\n👑 *Панель управления (Админ/Владелец):*\n"
            "/admin — Открыть админ-меню\n"
            "/giveadmin [ID] — Выдать права администратора\n"
            "/deladmin [ID] — Забрать права администратора\n"
            "/giveprem [ID] [срок] — Выдать Premium (1d, 1m, 1h, 1mes, 1y)\n"
            "/givetest [ID] — Выдать Premium на 1 день (тест)\n"
            "/delprem [ID] — Отключить Premium\n"
            "/mute [ID] — Замутить\n"
            "/unmute [ID] — Размутить\n"
            "/ban [ID] — Забанить\n"
            "/unban [ID] — Разбанить\n"
            "/soo [ID] [число] — Добавить сообщения\n"
            "/delsoo [ID] — Обнулить сообщения\n"
            "/info [ID] — Посмотреть статус пользователя"
        )
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# ============================================================
# КОМАНДЫ (Основные)
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
    bot.send_message(
        m.chat.id,
        f"🔥 *Привет, {m.from_user.first_name}!*\n\n"
        f"Я AWESOME AI — супер-интеллект!\n"
        f"Я умею искать актуальную информацию в интернете!\n\n"
        f"👇 *Выбери действие:*",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

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
        bot.send_message(m.chat.id, "❌ Использование: /feedback [текст]")
        return
    bot.send_message(m.chat.id, "✅ Спасибо за отзыв!")
    bot.send_message(OWNER_ID, f"📩 Отзыв от @{m.from_user.username or 'anon'}: {text}")

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    prompt = m.text.replace('/draw', '').strip()
    if not prompt:
        bot.send_message(m.chat.id, "❌ Использование: /draw [описание]")
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
        bot.send_message(m.chat.id, "❌ У тебя нет прав доступа к админ-панели!")
        return

    text = (
        "🛡️ *АДМИН-ПАНЕЛЬ AWESOME AI*\n\n"
        "👤 *Управление админами:*\n"
        "/giveadmin [ID] — Выдать права админа\n"
        "/deladmin [ID] — Забрать права админа\n\n"
        "💎 *Управление Premium:*\n"
        "/giveprem [ID] [срок] — Выдать Premium\n"
        "   *Срок:* 1d (день), 1m (минута), 1h (час), 1mes (месяц), 1y (год)\n"
        "/givetest [ID] — Выдать Premium на 1 день\n"
        "/delprem [ID] — Отключить Premium\n\n"
        "🚫 *Модерация:*\n"
        "/mute [ID], /unmute [ID]\n"
        "/ban [ID], /unban [ID]\n\n"
        "📨 *Лимиты:*\n"
        "/soo [ID] [число], /delsoo [ID]\n"
        "/info [ID] — Информация о пользователе"
    )
    bot.send_message(m.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['info'])
def info_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /info [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT is_admin, premium, premium_expires, messages_today FROM users WHERE user_id = ?', (target_id,))
    result = c.fetchone()
    conn.close()

    admin_status = "✅ Админ" if result[0] == 1 else "❌ Не админ"
    premium_status = f"💎 Активен (до {result[2]})" if result[1] == 1 else "🔓 Отсутствует"

    bot.send_message(m.chat.id, f"📊 Инфо по ID: {target_id}\n\nАдмин: {admin_status}\nPremium: {premium_status}\nСообщений сегодня: {result[3]}")

@bot.message_handler(commands=['giveadmin'])
def giveadmin_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /giveadmin [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    set_admin(target_id, True)
    bot.send_message(m.chat.id, f"✅ Пользователь {target_id} теперь администратор.")
    bot.send_message(target_id, "🎉 Тебе выданы права администратора AWESOME AI!")

@bot.message_handler(commands=['deladmin'])
def deladmin_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /deladmin [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    set_admin(target_id, False)
    bot.send_message(m.chat.id, f"❌ У пользователя {target_id} отобраны права администратора.")
    bot.send_message(target_id, "⛔ Твои права администратора AWESOME AI были отобраны.")

@bot.message_handler(commands=['givetest'])
def givetest_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /givetest [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    if set_premium(target_id, "1d"):
        bot.send_message(m.chat.id, f"✅ Premium выдан пользователю {target_id} на 1 день.")
        bot.send_message(target_id, "🎉 Тебе выдан тестовый Premium на 1 день!")
    else:
        bot.send_message(m.chat.id, "❌ Ошибка выдачи тестового периода.")

@bot.message_handler(commands=['giveprem'])
def giveprem_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 3:
        bot.send_message(m.chat.id, "❌ Использование: /giveprem [ID] [срок]\nПример: /giveprem 123 24mes")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    duration = args[2].lower()

    if set_premium(target_id, duration):
        bot.send_message(m.chat.id, f"✅ Premium выдан пользователю {target_id} на срок: {duration}")
        bot.send_message(target_id, f"🎉 Тебе выдан Premium на срок: {duration}!")
    else:
        bot.send_message(m.chat.id, "❌ Неверный формат срока. Используй: 1d, 1m, 1h, 1mes, 1y")

@bot.message_handler(commands=['delprem'])
def delprem_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /delprem [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    remove_premium(target_id)
    bot.send_message(m.chat.id, f"✅ Premium отключён для {target_id}")
    bot.send_message(target_id, "⛔ Твой Premium был отключен.")

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /mute ID")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    mute_user(target_id)
    bot.send_message(m.chat.id, f"🔇 Пользователь {target_id} замучен")

@bot.message_handler(commands=['unmute'])
def unmute_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /unmute ID")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    unmute_user(target_id)
    bot.send_message(m.chat.id, f"🔊 Пользователь {target_id} размучен")

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /ban ID")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    ban_user(target_id)
    bot.send_message(m.chat.id, f"🚫 Пользователь {target_id} забанен")

@bot.message_handler(commands=['unban'])
def unban_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /unban ID")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    unban_user(target_id)
    bot.send_message(m.chat.id, f"✅ Пользователь {target_id} разбанен")

@bot.message_handler(commands=['soo'])
def add_messages_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 3:
        bot.send_message(m.chat.id, "❌ Использование: /soo [ID] [число]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    amount = args[2]
    if not amount.isdigit():
        bot.send_message(m.chat.id, "❌ Число сообщений должно быть цифрой!")
        return

    target_id = int(target_id)
    amount = int(amount)

    ensure_user(target_id, "unknown")
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('UPDATE users SET last_reset = ?, messages_today = 0 WHERE user_id = ?', (today, target_id))
    c.execute('UPDATE users SET messages_today = messages_today + ? WHERE user_id = ?', (amount, target_id))

    conn.commit()
    conn.close()

    bot.send_message(m.chat.id, f"✅ Добавлено {amount} сообщений пользователю {target_id}")
    bot.send_message(target_id, f"🔔 Админ добавил тебе {amount} сообщений на сегодня!")

@bot.message_handler(commands=['delsoo'])
def del_messages_cmd(m):
    if not is_authorized(m.from_user.id):
        bot.send_message(m.chat.id, "❌ Нет прав!")
        return

    args = m.text.split()
    if len(args) < 2:
        bot.send_message(m.chat.id, "❌ Использование: /delsoo [ID]")
        return

    target_id = args[1]
    if not target_id.isdigit():
        bot.send_message(m.chat.id, "❌ ID должен состоять только из цифр!")
        return

    target_id = int(target_id)
    ensure_user(target_id, "unknown")

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('UPDATE users SET messages_today = 0 WHERE user_id = ?', (target_id,))
    today = datetime.now().strftime('%Y-%m-%d')
    c.execute('UPDATE users SET last_reset = ? WHERE user_id = ?', (today, target_id))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ Сообщения обнулены для пользователя {target_id}")
    bot.send_message(target_id, f"🔔 Админ обнулил твои сообщения на сегодня!")

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
            bot.send_message(call.message.chat.id, "📩 Напиши: /feedback [текст]")
        elif call.data == "draw":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "🎨 Напиши: /draw [описание]")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"⚠️ Ошибка: {e}")

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
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день исчерпан!\nКупи Premium: /premium")
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

    if len(m.text) > 3:
        last_search[user_id] = m.text

    increment_messages(user_id)
    ans = ask_gpt(user_id, m.text)
    if ans:
        bot.send_message(m.chat.id, ans)

# ============================================================
# ФОТО
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
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день исчерпан!\nКупи Premium: /premium")
        return
    bot.send_chat_action(m.chat.id, 'typing')
    try:
        file_info = bot.get_file(m.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        ocr_text = ocr_image(downloaded)
        increment_messages(user_id)
        caption = m.caption or "что на фото?"
        if ocr_text:
            bot.send_message(m.chat.id, f"📸 Текст на фото:\n{ocr_text[:500]}")
            ans = ask_gpt(user_id, caption, image_text=ocr_text)
            if ans:
                bot.send_message(m.chat.id, ans)
        else:
            ans = ask_gpt(user_id, caption)
            if ans:
                bot.send_message(m.chat.id, ans)
    except Exception as e:
        bot.send_message(m.chat.id, f"⚠️ Ошибка: {e}")

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
        bot.send_message(m.chat.id, f"🔴 Лимит {FREE_LIMIT} сообщений в день исчерпан!\nКупи Premium: /premium")
        return
    bot.send_chat_action(m.chat.id, 'typing')
    try:
        file_info = bot.get_file(m.voice.file_id)
        downloaded = bot.download_file(file_info.file_path)
        recognized = stt(downloaded)
        increment_messages(user_id)
        if recognized:
            bot.send_message(m.chat.id, f"🎤 Распознано:\n{recognized}")
            ans = ask_gpt(user_id, recognized)
            if ans:
                bot.send_message(m.chat.id, ans)
        else:
            bot.send_message(m.chat.id, "🎤 Не разобрал")
    except Exception as e:
        bot.send_message(m.chat.id, f"⚠️ Ошибка: {e}")

# ============================================================
# ОСТАЛЬНОЕ
# ============================================================
@bot.message_handler(content_types=['video', 'document', 'audio'])
def other(m):
    bot.send_message(m.chat.id, "Пока не умею. Текст, фото или голос")

# ============================================================
# ЗАПУСК (ДЛЯ РЕАЛЬНОГО СЕРВЕРА)
# ============================================================
print("🔥 AWESOME AI ULTRA — ВСЁ РАБОТАЕТ!")
print(f"📊 Бесплатный лимит: {FREE_LIMIT} сообщений в день")
print("🤖 Режим: 100% Генерация на ходу (Без шаблонов)")
print(f"🤖 @{bot.get_me().username}")
print("-" * 40)

# Бесконечный цикл с перезапуском
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"⚠️ Бот упал с ошибкой: {e}. Перезапуск через 5 секунд...")
        time.sleep(5)