# -*- coding: utf-8 -*-
"""
AwesomeNeiro Telegram Bot
Единый источник правды: Supabase users
"""
import os, json, time, random, string, hashlib, hmac, re, html
import threading, requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import telebot
from telebot import types

# ============ КЛЮЧИ И НАСТРОЙКИ ============
TELEGRAM_TOKEN = "8336209662:AAHdhYXhqWA-LtthwgydDSRU7A6A0ceC-HY"
SUPABASE_URL = "https://lprxbmshmuucymkgaqwk.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxwcnhibXNobXV1Y3lta2dhcXdrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY3NDk0MjgsImV4cCI6MjEwMjMyNTQyOH0.Ie9jSH5RMxeOq8aU-Dv6MXlojWMUTOLE723Hdg6heZU"
GIGACHAT_AUTH_KEY = "MDFhMDBkNmEtMmExNC03M2JkLWFlZmMtOTQ0OWVlOTc5M2U1OmE1ZWJhM2NlLTQwYjAtNDZlYi1iMmY2LTE3OTFmYzhhYTQ2MA=="
YANDEX_API_KEY = "AQVNyfn82epL9dy8C_kftzeypq6eF9lFd6SZnFzV"
FOLDER_ID = "b1g4aq87c7j61c6g3i5l"

OWNER_ID = 6652898792          # владелец
OWNER_PASSWORD = "qawsedrf2346"
DEFAULT_PREMIUM_DAYS = 30

MSK = timezone(timedelta(hours=3))
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ============ РАБОТА С SUPABASE ============
SBP = f"{SUPABASE_URL}/rest/v1"
SB_HEADERS = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def sb_select(table, col="*", eq=None, order=None, limit=None):
    url = f"{SBP}/{table}?select={col}"
    if eq:
        for k, v in eq.items():
            url += f"&{k}=eq.{v}"
    if order:
        url += f"&order={order}"
    if limit:
        url += f"&limit={limit}"
    r = requests.get(url, headers=SB_HEADERS, timeout=20)
    if r.status_code == 200:
        return r.json()
    return []

def sb_insert(table, data):
    r = requests.post(f"{SBP}/{table}", headers=SB_HEADERS, json=data, timeout=20)
    return r.json() if r.status_code in (200, 201) else []

def sb_update(table, eq, data):
    url = f"{SBP}/{table}?"
    for k, v in eq.items():
        url += f"{k}=eq.{v}&"
    r = requests.patch(url.rstrip("&"), headers=SB_HEADERS, json=data, timeout=20)
    return r.json() if r.status_code == 200 else []

def sha256(s):
    return hashlib.sha256(str(s).encode()).hexdigest()

# ---------- ПОЛЬЗОВАТЕЛИ ----------
def get_db_user(uid):
    rows = sb_select("users", col="*", eq={"telegram_id": str(uid)})
    return rows[0] if rows else None

def ensure_user(uid, name="", username=""):
    u = get_db_user(uid)
    if u:
        # пароль НЕ перезаписываем никогда
        patch = {}
        if name and u.get("name") in (None, ""):
            patch["name"] = name
        if username and u.get("username") in (None, ""):
            patch["username"] = username
        if patch:
            sb_update("users", {"telegram_id": str(uid)}, patch)
        return u
    data = {
        "telegram_id": str(uid),
        "name": name or f"User{uid}",
        "username": username or "",
        "password": None,
        "premium": 0, "premium_expires": None,
        "is_admin": 0, "is_owner": 0,
        "messages_today": 0, "test_used": 0,
        "theme": "dark", "joined_at": datetime.now(MSK).isoformat(),
        "xp": 0, "level": 1, "avatar": "",
        "ref_code": "", "ref_count": 0,
    }
    ins = sb_insert("users", data)
    return ins[0] if ins else data

# ---------- ПРАВА ----------
def is_owner(uid):  return str(uid) == str(OWNER_ID)
def is_admin(uid):
    if is_owner(uid): return True
    u = get_db_user(uid)
    return bool(u and (u.get("is_admin") == 1 or u.get("is_owner") == 1))

def get_premium_status(uid):
    u = get_db_user(uid)
    if not u: return False
    if u.get("premium") == 1:
        ex = u.get("premium_expires")
        if ex:
            try:
                dt = datetime.fromisoformat(str(ex).replace("Z", "+00:00"))
                if dt < datetime.now(timezone.utc):
                    return False
            except Exception:
                pass
        return True
    return False

def set_premium(uid, days):
    expires = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    sb_update("users", {"telegram_id": str(uid)}, {"premium": 1, "premium_expires": expires})
    return expires

# ============ GIGACHAT TOKEN ============
_gigachat_token = {"value": None, "exp": 0}

def get_gigachat_token():
    if _gigachat_token["value"] and time.time() < _gigachat_token["exp"] - 60:
        return _gigachat_token["value"]
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    headers = {
        "Authorization": f"Basic {GIGACHAT_AUTH_KEY}",
        "RqUID": str(uuid4()),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    try:
        r = requests.post(url, headers=headers, data="scope=GIGACHAT_API_PERS",
                          verify=False, timeout=30)
        j = r.json()
        _gigachat_token["value"] = j["access_token"]
        _gigachat_token["exp"] = time.time() + int(j.get("expires_at", 1800)) - int(time.time()) if "expires_at" in j else time.time() + 1800
        return _gigachat_token["value"]
    except Exception as e:
        return None

# ============ ГЕНЕРАЦИЯ ОТВЕТОВ ============
def generate_with_gigachat(prompt, system="", uid=None, temperature=0.8):
    tok = get_gigachat_token()
    if not tok:
        return None
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    payload = {"model": "GigaChat-Pro", "messages": msgs,
               "temperature": temperature, "max_tokens": 2048}
    try:
        r = requests.post(url, headers=headers, json=payload, verify=False, timeout=120)
        if r.status_code != 200:
            return None
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None

def generate_with_yandex(prompt, system="", uid=None):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}",
               "Content-Type": "application/json", "x-folder-id": FOLDER_ID}
    body = {
        "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"temperature": 0.8, "maxTokens": 2048},
        "messages": [{"role": "system", "text": system or "Ты умный собеседник."},
                     {"role": "user", "text": prompt}],
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=120)
        if r.status_code != 200:
            return None
        return r.json()["result"]["alternatives"][0]["message"]["text"].strip()
    except Exception:
        return None

# ============ СИСТЕМНЫЙ ПРОМПТ ============
SYSTEM_PROMPT = """
**1. Название**: AwesomeNeiro — «Твой умный собеседник нового поколения».
Ты — живой, тёплый и харизматичный ассистент. Общаешься естественно, с эмодзи, без канцелярита.
Важно выделяй ключевое жирным.
Сейчас время по Москве (UTC+3): {time}.
Отвечай лаконично, но по делу. Если нужно — считай, переводи, шути, делай комплименты, давай советы.
"""

# ============ УМНЫЕ ИНСТРУМЕНТЫ ============
memory = defaultdict(list)      # память (в оперативке + можно в Supabase)
web_cache = {}

def extract_facts(text):
    return text[:500]

def remember(uid, fact):
    memory[str(uid)].append(fact)
    memory[str(uid)] = memory[str(uid)][-20:]
    return True

def get_memory_text(uid):
    m = memory.get(str(uid), [])
    return "\n".join(f"- {x}" for x in m[-10:]) if m else ""

def now_msk():
    return datetime.now(MSK)

def msk_date_str():
    d = now_msk()
    months = ["января","февраля","марта","апреля","мая","июня",
              "июля","августа","сентября","октября","ноября","декабря"]
    days = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
    return f"{d.day} {months[d.month-1]} {d.year}, {days[d.weekday()]}"

def web_search(q):
    if q in web_cache and time.time() - web_cache[q][0] < 600:
        return web_cache[q][1]
    results = []
    try:
        r = requests.get("https://html.duckduckgo.com/html/", params={"q": q},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        import re as _re
        snippets = _re.findall(r'result__a[^>]*>(.*?)</a>', r.text)
        for s in snippets[:5]:
            txt = _re.sub('<[^>]+>', '', s)
            results.append(html.unescape(txt))
    except Exception:
        pass
    if not results:
        try:
            r = requests.get("https://www.bing.com/search", params={"q": q},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            import re as _re
            snippets = _re.findall(r'<h2[^>]*>(.*?)</h2>', r.text)
            for s in snippets[:5]:
                txt = _re.sub('<[^>]+>', '', s)
                results.append(html.unescape(txt))
        except Exception:
            pass
    web_cache[q] = (time.time(), results)
    return results

def translate_text(text, target="ru"):
    p = f"Переведи на {'русский' if target=='ru' else 'английский'} язык: {text}. Только перевод."
    return generate_with_gigachat(p, system="Ты переводчик. Отвечай только переводом.", temperature=0.3)

JOKES = [
    "Почему программисты путают Хэллоуин и Рождество? Потому что OCT 31 == DEC 25 😄",
    "— У меня есть план Б.\n— А план А?\n— План А — это тоже план Б, просто написанный плохо 🤣",
    "Собеседование:\n— Ваш самый большой недостаток?\n— Честность.\n— Да ладно, я считаю честность достоинством!\n— А мне всё равно, что вы считаете 🙃",
    "Компьютер говорит компьютеру: «Скучно... давай обменяемся файлами?» — «Давай!» Обменялись. Теперь у обоих вирусы 😅",
    "Мой кот требует объяснений, зачем ему питомец-человек. Я сказал: «Для еды и тепла». Он задумался и принял меня обратно 🐱",
]
COMPLIMENTS = [
    "У тебя отличное чувство стиля — даже шрифты завидуют ✨",
    "Ты излучаешь позитив, который сложно подделать 💫",
    "Твой ум — это настоящий квантовый компьютер среди обычных 🧠",
    "С тобой даже баги в коде становятся фичами 🌟",
    "Ты тот человек, ради которого хочется писать чистый код 💎",
]

def smart_answer(text, uid, mode="normal"):
    """Цепочка: инструменты -> GigaChat -> YandexGPT -> заготовки."""
    t = text.lower().strip()

    # --- режимы / специальные триггеры ---
    if any(k in t for k in ["какой день", "какое сегодня", "число", "дата"]):
        return f"Сегодня {msk_date_str()} 📅"
    if any(k in t for k in ["сколько время", "который час", "время"]):
        return f"Сейчас {now_msk().strftime('%H:%M')} по Москве ⏰"
    if "переведи" in t or "перевод" in t:
        target = "en" if "на англ" in t else "ru"
        src = t.replace("переведи", "").replace("перевод", "").strip(" :")
        if src:
            return translate_text(src, target)
    if any(k in t for k in ["шутка", "пошути", "рассмеши", "анекдот"]):
        return random.choice(JOKES)
    if any(k in t for k in ["комплимент", "похвали", "ты красивая", "ты красивый"]):
        return random.choice(COMPLIMENTS)
    if "поищи" in t or "найди в интернете" in t or t.startswith("найди"):
        q = t.replace("поищи", "").replace("найди в интернете", "").replace("найди", "").strip()
        if q:
            res = web_search(q)
            if res:
                return "🔎 Вот что нашёл в интернете:\n" + "\n".join(f"• {x}" for x in res)
            return "Не нашёл ничего по этому запросу 😕"
    if any(k in t for k in ["погода", "курс", "крипт", "биткоин", "доллар", "евро"]):
        info = get_market_info()
        return info
    if "режим" in t or "режим:" in t:
        return "🎛 Режимы: умный, краткий, подробный, эксперт, поэт, кодер.\nНапиши: `режим: краткий` и спроси что угодно."

    # --- обработка команд режима ---
    if t.startswith("режим:"):
        m = t.split(":", 1)[1].strip()
        return f"Режим «{m}» включён ✅ (в этой сборке применяется к системному промпту)"

    # --- память ---
    if "запомни" in t:
        fact = t.replace("запомни", "").strip(" :")
        if fact:
            remember(uid, fact)
            return f"Запомнил ✅"
    if "что ты знаешь обо мне" in t or "моя память" in t:
        m = get_memory_text(uid)
        return f"🧠 Моя память о тебе:\n{m}" if m else "Пока ничего не запомнил 🤷"

    # --- системный промпт ---
    system = SYSTEM_PROMPT.format(time=now_msk().strftime("%H:%M")) 
    mem = get_memory_text(uid)
    if mem:
        system += f"\n\n**Память о пользователе**:\n{mem}"
    if mode == "краткий":
        system += "\nОтвечай максимально кратко, 1-3 предложения."
    elif mode == "подробный":
        system += "\nОтвечай подробно и развёрнуто, структурируй."
    elif mode == "эксперт":
        system += "\nОтвечай как технический эксперт, точно и по делу."

    # --- цепочка нейросетей ---
    r = generate_with_gigachat(text, system=system, uid=uid)
    if r:
        return r
    r2 = generate_with_yandex(text, system=system, uid=uid)
    if r2:
        return r2
    return "🤖 Я сейчас немного перегружен, но жив! Задай вопрос чуть позже или напиши «режим», чтобы выбрать стиль общения."

def get_market_info():
    out = []
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=15)
        j = r.json()
        rub = j["rates"].get("RUB")
        out.append(f"💵 Доллар: ~{rub:.2f} ₽")
    except Exception:
        pass
    try:
        r = requests.get("https://api.coindesk.com/v1/bpi/currentprice.json", timeout=15)
        j = r.json()
        out.append(f"🪙 Биткоин: ${float(j['bpi']['USD']['rate'].replace(',','')):,.0f}")
    except Exception:
        pass
    try:
        r = requests.get("https://wttr.in/Moscow?format=3", timeout=15)
        out.append(f"🌤 {r.text.strip()}")
    except Exception:
        pass
    return "\n".join(out) if out else "Не удалось получить данные 😕"

# ============ КНОПКИ / МЕНЮ ============
def main_menu():
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    mk.add(
        types.KeyboardButton("🎛 Режимы"),
        types.KeyboardButton("🧠 Память"),
        types.KeyboardButton("🌦 Погода"),
        types.KeyboardButton("💱 Курс"),
        types.KeyboardButton("😄 Шутка"),
        types.KeyboardButton("💐 Комплимент"),
        types.KeyboardButton("ℹ️ Статус"),
        types.KeyboardButton("⚙️ Помощь"),
    )
    return mk

def help_text():
    return (
        "🤖 *AwesomeNeiro* — твой умный собеседник\n\n"
        "Просто пиши мне сообщение — отвечу!\n\n"
        "💡 *Команды:*\n"
        "`/start` — главное меню\n"
        "`/status` — твой статус (Premium, XP, уровень)\n"
        "`/help` — эта справка\n"
        "`/clear` — очистить память\n\n"
        "🎛 *Кнопки меню:*\n"
        "• Режимы — выбор стиля ответов\n"
        "• Память — что я о тебе помню\n"
        "• Погода / Курс — свежие данные\n"
        "• Шутка / Комплимент — настроение\n\n"
        "✨ *Ключевые слова:*\n"
        "«переведи ...», «найди ...», «запомни ...», «который час»\n\n"
        "👑 *Premium*: @awesomeneiro_bot — больше лимитов и функций!"
    )

# ============ ХЕНДЛЕРЫ ============
@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    name = m.from_user.first_name or ""
    uname = m.from_user.username or ""
    ensure_user(uid, name, uname)
    welcome = (
        f"👋 Привет, {name}! Я *AwesomeNeiro* — твой умный собеседник нового поколения.\n\n"
        "Задавай вопросы, проси советы, перевод, поиск — я всегда рядом! 🚀"
    )
    bot.send_message(uid, welcome, reply_markup=main_menu())

@bot.message_handler(commands=["status"])
def cmd_status(m):
    uid = m.from_user.id
    ensure_user(uid)
    u = get_db_user(uid)
    prem = get_premium_status(uid)
    role = "👑 Владелец" if is_owner(uid) else ("🛡 Админ" if is_admin(uid) else "👤 Пользователь")
    exp = u.get("premium_expires")
    exp_str = "бессрочно"
    if exp:
        try:
            exp_str = datetime.fromisoformat(str(exp).replace("Z", "+00:00")).strftime("%d.%m.%Y %H:%M")
        except Exception:
            exp_str = str(exp)
    xp = u.get("xp") or 0
    level = u.get("level") or 1
    txt = (
        f"📊 *Твой статус*\n\n"
        f"🆔 ID: `{uid}`\n"
        f"👤 Имя: {u.get('name') or '—'}\n"
        f"🏷 Роль: {role}\n"
        f"💎 Premium: {'✅ да' if prem else '❌ нет'}\n"
        f"📅 До: {exp_str if prem else '—'}\n"
        f"⭐ Уровень: {level}\n"
        f"⚡ XP: {xp}\n"
        f"💬 Сообщений сегодня: {u.get('messages_today') or 0}\n"
        f"🧪 Тест использован: {'да' if (u.get('test_used') or 0) else 'нет'}"
    )
    bot.send_message(uid, txt, parse_mode="Markdown")

@bot.message_handler(commands=["help"])
def cmd_help(m):
    bot.send_message(m.chat.id, help_text(), parse_mode="Markdown")

@bot.message_handler(commands=["clear"])
def cmd_clear(m):
    memory[str(m.from_user.id)] = []
    bot.send_message(m.chat.id, "🧹 Память очищена")

# ---------- кнопки ----------
@bot.message_handler(func=lambda m: m.text in ["🎛 Режимы", "🧠 Память", "🌦 Погода", "💱 Курс", "😄 Шутка", "💐 Комплимент", "ℹ️ Статус", "⚙️ Помощь"])
def handle_buttons(m):
    uid = m.from_user.id
    t = m.text
    if t == "ℹ️ Статус":
        return cmd_status(m)
    if t == "⚙️ Помощь":
        return cmd_help(m)
    if t == "🎛 Режимы":
        mk = types.InlineKeyboardMarkup()
        for mode in ["умный", "краткий", "подробный", "эксперт", "поэт", "кодер"]:
            mk.add(types.InlineKeyboardButton(mode.capitalize(), callback_data=f"mode:{mode}"))
        bot.send_message(uid, "Выбери режим ответов:", reply_markup=mk)
    elif t == "🧠 Память":
        mtext = get_memory_text(uid)
        bot.send_message(uid, f"🧠 Моя память о тебе:\n{mtext}" if mtext else "Пока ничего не запомнил 🤷")
    elif t == "🌦 Погода":
        bot.send_message(uid, get_market_info())
    elif t == "💱 Курс":
        bot.send_message(uid, get_market_info())
    elif t == "😄 Шутка":
        bot.send_message(uid, random.choice(JOKES))
    elif t == "💐 Комплимент":
        bot.send_message(uid, random.choice(COMPLIMENTS))

@bot.callback_query_handler(func=lambda c: c.data.startswith("mode:"))
def cb_mode(c):
    mode = c.data.split(":", 1)[1]
    bot.answer_callback_query(c.id, f"Режим: {mode}")
    bot.send_message(c.message.chat.id, f"🎛 Включён режим «{mode}». Просто задай вопрос!")

# ---------- административные команды (владелец/админ) ----------
@bot.message_handler(commands=["giveprem"])
def cmd_giveprem(m):
    if not is_admin(m.from_user.id):
        return bot.send_message(m.chat.id, "⛔ Нет прав")
    parts = m.text.split()
    if len(parts) < 3:
        return bot.send_message(m.chat.id, "Формат: /giveprem <id> <дней>")
    uid = parts[1]; days = int(parts[2])
    ensure_user(uid)
    exp = set_premium(uid, days)
    bot.send_message(m.chat.id, f"✅ Premium выдан пользователю {uid} на {days} дн. до {exp}")

@bot.message_handler(commands=["giveadmin"])
def cmd_giveadmin(m):
    if not is_owner(m.from_user.id):
        return bot.send_message(m.chat.id, "⛔ Только владелец")
    parts = m.text.split()
    if len(parts) < 2:
        return bot.send_message(m.chat.id, "Формат: /giveadmin <id>")
    ensure_user(parts[1])
    sb_update("users", {"telegram_id": parts[1]}, {"is_admin": 1})
    bot.send_message(m.chat.id, f"✅ {parts[1]} теперь админ")

@bot.message_handler(commands=["deladmin"])
def cmd_deladmin(m):
    if not is_owner(m.from_user.id):
        return bot.send_message(m.chat.id, "⛔ Только владелец")
    parts = m.text.split()
    if len(parts) < 2:
        return bot.send_message(m.chat.id, "Формат: /deladmin <id>")
    sb_update("users", {"telegram_id": parts[1]}, {"is_admin": 0})
    bot.send_message(m.chat.id, f"✅ {parts[1]} больше не админ")

@bot.message_handler(commands=["stats"])
def cmd_stats(m):
    if not is_admin(m.from_user.id):
        return bot.send_message(m.chat.id, "⛔ Нет прав")
    rows = sb_select("users", col="*")
    prem = sum(1 for r in rows if r.get("premium") == 1)
    bot.send_message(m.chat.id,
        f"📈 Статистика:\nПользователей: {len(rows)}\nPremium: {prem}")

# ---------- обычные сообщения (нейросеть) ----------
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(m):
    uid = m.from_user.id
    ensure_user(uid, m.from_user.first_name or "", m.from_user.username or "")
    # лимит сообщений для не-Premium
    if not get_premium_status(uid) and not is_admin(uid):
        u = get_db_user(uid)
        cnt = int(u.get("messages_today") or 0)
        if cnt >= 20:
            return bot.send_message(uid, "⏳ Дневной лимит исчерпан. Получи Premium: @awesomeneiro_bot")
        sb_update("users", {"telegram_id": str(uid)}, {"messages_today": cnt + 1})
    # индикатор набора
    bot.send_chat_action(uid, "typing")
    answer = smart_answer(m.text, uid)
    bot.send_message(uid, answer)

# ============ ЗАПУСК (с защитой от конфликта 409) ============
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print("🤖 Бот запущен...")
    # защита от нескольких экземпляров
    try:
        bot.remove_webhook()
    except Exception:
        pass
    for attempt in range(5):
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
            break
        except Exception as e:
            print(f"⚠️ Ошибка: {e}. Перезапуск через 10 сек...")
            time.sleep(10)
