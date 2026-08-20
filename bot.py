#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AWESOME AI 2026 — ТГ-бот, ПОЛНАЯ связка Bot -> Supabase -> Сайт"""
import os, sys, io, re, time, json, base64, hashlib, random, hmac, urllib.parse, threading
from datetime import datetime, timedelta, timezone
import requests, urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import telebot
from telebot import types
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from dateutil.relativedelta import relativedelta

try:
    from supabase import create_client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False
    def create_client(*a, **k): return None

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ============================================================
# НАСТРОЙКА (ключи из окружения)
# ============================================================
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
YANDEX_API_KEY   = os.getenv("YANDEX_API_KEY")
FOLDER_ID        = os.getenv("FOLDER_ID", "b1g4aq87c7j61c6g3i5l")
GIGACHAT_AUTH_KEY= os.getenv("GIGACHAT_AUTH_KEY")
SUPABASE_URL     = os.getenv("SUPABASE_URL")
SUPABASE_KEY     = os.getenv("SUPABASE_ANON_KEY")
OWNER_ID         = 6652898792
FREE_LIMIT       = 20

if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("⚠️ SUPABASE не настроен — бот будет работать без синхронизации с сайтом!")

GIGACHAT_TIMEOUT = 14
YANDEXGPT_TIMEOUT= 12
SEARCH_TIMEOUT   = 3

MOSCOW_TZ = timezone(timedelta(hours=3))
def gm(): return datetime.now(MOSCOW_TZ)
def get_current_date(): return gm().strftime('%d.%m.%Y')
def get_current_time(): return gm().strftime('%H:%M')
def format_date(s):
    if not s: return "неизвестно"
    try: return datetime.strptime(str(s)[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ).strftime('%d.%m.%Y %H:%M')+' МСК'
    except: return str(s)

# Кэш (быстрота)
CACHE={}; CACHE_TTL=60
def get_cache(k):
    if k in CACHE:
        d,t=CACHE[k]
        if time.time()-t<CACHE_TTL: return d
        del CACHE[k]
    return None
def set_cache(k,d): CACHE[k]=(d,time.time())

# ============================================================
# SUPABASE — ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ
# ============================================================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY else None
use_supabase = bool(supabase)

def sb_exec(fn, *a, **k):
    if not use_supabase: return None
    try: return fn(*a, **k)
    except Exception as e:
        print(f"⚠️ Supabase: {e}"); return None

def get_db_user(user_id):
    """Читает пользователя из Supabase users (той же таблицы, что и сайт)."""
    if use_supabase:
        r=sb_exec(lambda: supabase.table('users').select('*').eq('user_id',int(user_id)).execute())
        return r.data[0] if r and r.data else None
    # фолбек на sqlite (если Supabase недоступен)
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id=?',(int(user_id),))
    r=c.fetchone(); conn.close()
    if r:
        cols=['user_id','username','name','password','telegram_id','premium','premium_expires','is_admin','is_owner','messages_today','test_used','theme','joined_at','xp','level']
        return dict(zip(cols,r[:len(cols)]))
    return None

def ensure_user(user_id, username=None):
    """Создаёт пользователя в Supabase (общая таблица с сайтом)."""
    u=get_db_user(user_id)
    if u:
        if use_supabase:
            sb_exec(lambda: supabase.table('users').update({'username':username}).eq('user_id',int(user_id)).execute())
        return False
    owner=1 if int(user_id)==OWNER_ID else 0
    data={'user_id':int(user_id),'name':username or '','username':username or 'unknown',
          'password':'','telegram_id':str(user_id),'premium':0,'premium_expires':None,
          'is_admin':owner,'is_owner':owner,'messages_today':0,'test_used':0,
          'theme':'dark','joined_at':gm().strftime('%Y-%m-%d %H:%M:%S'),'xp':0,'level':1}
    if use_supabase:
        sb_exec(lambda: supabase.table('users').insert(data).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute("""INSERT OR IGNORE INTO users (user_id,name,username,password,telegram_id,premium,premium_expires,is_admin,is_owner,messages_today,test_used,theme,joined_at,xp,level)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (int(user_id),username or '',username or 'unknown','',str(user_id),0,None,owner,owner,0,0,'dark',gm().strftime('%Y-%m-%d %H:%M:%S'),0,1))
        conn.commit(); conn.close()
    if int(user_id)!=OWNER_ID:
        try:
            telebot.TeleBot(TELEGRAM_TOKEN).send_message(OWNER_ID,f"🆕 Новый пользователь!\nID: {user_id}\n@{username or 'Не указан'}\n{data['joined_at']}")
        except: pass
    return True

# ===== PREMIUM / СТАТУС (единые функции, работают с Supabase) =====
def set_premium(user_id, duration_str):
    """Выдаёт Premium в Supabase users (сайт это увидит)."""
    m=re.match(r'(\d+)(\w+)', duration_str)
    if not m: return False
    n=int(m.group(1)); unit=m.group(2)
    if unit.endswith('mes'): delta=relativedelta(months=n)
    elif unit=='y': delta=relativedelta(years=n)
    elif unit=='d': delta=timedelta(days=n)
    elif unit=='h': delta=timedelta(hours=n)
    elif unit=='m': delta=timedelta(minutes=n)
    elif unit=='w': delta=timedelta(weeks=n)
    else: return False
    cur=get_db_user(user_id); cur_exp=cur.get('premium_expires') if cur else None
    now=gm()
    if cur_exp:
        try:
            cd=datetime.strptime(str(cur_exp)[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
            base=cd if cd>now else now
        except: base=now
    else: base=now
    exp=(base+delta).strftime('%Y-%m-%d %H:%M:%S')
    if use_supabase:
        sb_exec(lambda: supabase.table('users').update({'premium':1,'premium_expires':exp}).eq('user_id',int(user_id)).execute())
        return True
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute('UPDATE users SET premium=1,premium_expires=? WHERE user_id=?',(exp,int(user_id)))
    conn.commit(); conn.close(); return True

def add_month_to_premium(user_id):
    return set_premium(user_id,'1mes')

def get_premium_status(user_id):
    if int(user_id)==OWNER_ID: return True
    u=get_db_user(user_id)
    if not u: return False
    if u.get('is_owner')==1: return True
    if u.get('premium')==1:
        exp=u.get('premium_expires')
        if exp:
            try:
                if gm()>datetime.strptime(str(exp)[:19],'%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ):
                    if use_supabase: sb_exec(lambda: supabase.table('users').update({'premium':0,'premium_expires':None}).eq('user_id',int(user_id)).execute())
                    return False
            except: pass
        return True
    return False

def get_premium_expires(user_id):
    u=get_db_user(user_id)
    return u.get('premium_expires') if u else None

def is_admin(user_id):
    if int(user_id)==OWNER_ID: return True
    u=get_db_user(user_id)
    return bool(u and (u.get('is_admin')==1 or u.get('is_owner')==1))

def is_authorized(user_id): return is_admin(user_id)

def set_admin(user_id, status):
    if use_supabase:
        sb_exec(lambda: supabase.table('users').update({'is_admin':1 if status else 0}).eq('user_id',int(user_id)).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute('UPDATE users SET is_admin=? WHERE user_id=?',(1 if status else 0,int(user_id)))
        conn.commit(); conn.close()

# ===== БАН / МЬЮТ / ЛИМИТЫ =====
def _row_exists(table, uid):
    if use_supabase:
        r=sb_exec(lambda: supabase.table(table).select('user_id').eq('user_id',int(uid)).execute())
        return bool(r and r.data)
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute(f'SELECT 1 FROM {table} WHERE user_id=?',(int(uid),)); r=c.fetchone(); conn.close(); return bool(r)

def _insert_row(table, uid):
    if use_supabase:
        sb_exec(lambda: supabase.table(table).insert({'user_id':int(uid)}).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute(f'INSERT OR IGNORE INTO {table} (user_id) VALUES (?)',(int(uid),)); conn.commit(); conn.close()

def _delete_row(table, uid):
    if use_supabase:
        sb_exec(lambda: supabase.table(table).delete().eq('user_id',int(uid)).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute(f'DELETE FROM {table} WHERE user_id=?',(int(uid),)); conn.commit(); conn.close()

def is_banned(user_id): return _row_exists('banned',user_id)
def ban_user(user_id): _insert_row('banned',user_id)
def unban_user(user_id): _delete_row('banned',user_id)
def is_muted(user_id): return _row_exists('muted',user_id)
def mute_user(user_id): _insert_row('muted',user_id)
def unmute_user(user_id): _delete_row('muted',user_id)

def can_send_message(user_id):
    if int(user_id)==OWNER_ID or is_admin(user_id) or get_premium_status(user_id): return True
    if is_banned(user_id): return False
    u=get_db_user(user_id)
    return int(u.get('messages_today',0) if u else 0) < FREE_LIMIT

def increment_messages(user_id):
    if int(user_id)==OWNER_ID or is_admin(user_id): return
    u=get_db_user(user_id); cur=int(u.get('messages_today',0)) if u else 0
    if use_supabase:
        sb_exec(lambda: supabase.table('users').update({'messages_today':cur+1}).eq('user_id',int(user_id)).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute('UPDATE users SET messages_today=messages_today+1 WHERE user_id=?',(int(user_id),)); conn.commit(); conn.close()

def clear_messages(user_id):
    if use_supabase:
        sb_exec(lambda: supabase.table('users').update({'messages_today':0}).eq('user_id',int(user_id)).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute('UPDATE users SET messages_today=0 WHERE user_id=?',(int(user_id),)); conn.commit(); conn.close()

# ===== ПАМЯТЬ (как на сайте) =====
MEM={}
def remember(user_id, fact):
    fact=(fact or '').strip()[:300]
    if len(fact)<4: return
    MEM.setdefault(str(user_id),[]).append(fact)
    MEM[str(user_id)]=MEM[str(user_id)][-30:]
def recall(user_id):
    return ["🧠 "+f for f in MEM.get(str(user_id),[])]

# ===== ЗАКАЗЫ / ОБРАЩЕНИЯ (Supabase) =====
def add_order(user_id):
    if use_supabase:
        sb_exec(lambda: supabase.table('premium_orders').insert({'user_id':int(user_id),'status':'pending','created_at':gm().strftime('%d.%m.%Y %H:%M')}).execute())
        r=sb_exec(lambda: supabase.table('premium_orders').select('order_id').eq('user_id',int(user_id)).order('order_id',desc=True).limit(1).execute())
        return r.data[0]['order_id'] if r and r.data else None
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute('INSERT INTO premium_orders (user_id,status,created_at) VALUES (?,?,?)',(int(user_id),'pending',gm().strftime('%d.%m.%Y %H:%M')))
    oid=c.lastrowid; conn.commit(); conn.close(); return oid

def get_order(order_id):
    if use_supabase:
        r=sb_exec(lambda: supabase.table('premium_orders').select('*').eq('order_id',int(order_id)).execute())
        return r.data[0] if r and r.data else None
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute('SELECT order_id,user_id,status FROM premium_orders WHERE order_id=?',(int(order_id),))
    r=c.fetchone(); conn.close()
    if r: return {'order_id':r[0],'user_id':r[1],'status':r[2]}
    return None

def update_order(order_id, status):
    if use_supabase:
        sb_exec(lambda: supabase.table('premium_orders').update({'status':status}).eq('order_id',int(order_id)).execute())
    else:
        import sqlite3
        conn=sqlite3.connect('users.db'); c=conn.cursor()
        c.execute('UPDATE premium_orders SET status=? WHERE order_id=?',(status,int(order_id))); conn.commit(); conn.close()

def pending_orders():
    if use_supabase:
        r=sb_exec(lambda: supabase.table('premium_orders').select('*').eq('status','pending').order('order_id',desc=True).limit(50).execute())
        return r.data if r and r.data else []
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute('SELECT order_id,user_id,created_at FROM premium_orders WHERE status="pending" ORDER BY order_id DESC')
    r=[{'order_id':x[0],'user_id':x[1],'created_at':x[2]} for x in c.fetchall()]; conn.close(); return r

# ============================================================
# ПОИСК (параллельный, быстрый)
# ============================================================
def search_google(q):
    try:
        r=requests.get(f"https://www.google.com/search?q={urllib.parse.quote(q)}&hl=ru",headers={"User-Agent":"Mozilla/5.0"},timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            s=BeautifulSoup(r.text,'html.parser'); out=[]
            for res in s.select('div.g')[:2]:
                t=res.select_one('h3'); sn=res.select_one('div.VwiC3b')
                if t: out.append(f"🔹 {t.get_text(strip=True)}\n📝 {(sn.get_text(strip=True)[:100]) if sn else ''}")
            return "\n".join(out) if out else None
    except: pass
    return None

def search_wikipedia(q):
    try:
        r=requests.get(f"https://ru.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(q)}&format=json&utf8=1",timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            items=r.json().get('query',{}).get('search',[])
            if items:
                return "\n".join(f"📚 {it.get('title')}\n{re.sub(r'<[^>]+>','',it.get('snippet',''))[:100]}" for it in items[:2])
    except: pass
    return None

def search_news(q):
    try:
        r=requests.get(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ru&gl=RU&ceid=RU:ru",timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            s=BeautifulSoup(r.text,'xml'); items=s.find_all('item')[:2]
            if items: return "\n".join(f"📰 {it.find('title').text}" for it in items if it.find('title'))
    except: pass
    return None

def search_youtube(q):
    try:
        r=requests.get(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&hl=ru",headers={"User-Agent":"Mozilla/5.0"},timeout=SEARCH_TIMEOUT)
        if r.status_code==200:
            s=BeautifulSoup(r.text,'html.parser'); out=[]
            for v in s.select('ytd-video-renderer')[:2]:
                t=v.select_one('yt-formatted-string#video-title')
                if t: out.append("🎬 "+t.get_text(strip=True))
            return "YouTube:\n"+"\n".join(out) if out else None
    except: pass
    return None

def search_all_internet(q):
    ck=f"s_{hash(q)}_{int(time.time()/60)}"; c=get_cache(ck)
    if c: return c
    out=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs=[ex.submit(f,q) for f in [search_google,search_wikipedia,search_news,search_youtube]]
        for f in as_completed(futs):
            try:
                r=f.result(timeout=SEARCH_TIMEOUT+1)
                if r: out.append(r)
            except: pass
    if out:
        res="\n\n".join(out[:3]); set_cache(ck,res); return res
    return None

# ============================================================
# GIGACHAT (исправлен: data как строка + случайный RqUID)
# ============================================================
tok=None; tok_t=0
def get_gigachat_token():
    global tok,tok_t
    if tok and time.time()-tok_t<180: return tok
    if not GIGACHAT_AUTH_KEY: return None
    for _ in range(3):
        try:
            r=requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
                headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json",
                         "RqUID":hashlib.md5(str(time.time()).encode()).hexdigest()[:36],
                         "Authorization":"Basic "+GIGACHAT_AUTH_KEY},
                data="scope=GIGACHAT_API_PERS",timeout=10,verify=False)
            if r.status_code==200:
                j=r.json()
                if j.get('access_token'): tok=j['access_token']; tok_t=time.time(); return tok
        except: pass
        time.sleep(0.5)
    return None

def generate_with_gigachat(text, sysp):
    try:
        t=get_gigachat_token()
        if not t: return None
        r=requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization":"Bearer "+t,"Content-Type":"application/json","Accept":"application/json"},
            json={"model":"GigaChat-Pro","messages":[{"role":"system","content":sysp[:3000]},{"role":"user","content":text}],
                  "temperature":0.85,"max_tokens":1500},timeout=GIGACHAT_TIMEOUT,verify=False)
        if r.status_code==200:
            try: return r.json()["choices"][0]["message"]["content"]
            except: return None
    except: pass
    return None

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ (погода/курс/крипта/математика/перевод)
# ============================================================
def get_weather_fast(city):
    ck="w_"+city; c=get_cache(ck)
    if c: return c
    try:
        r=requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid=4c8f5c0b8a9f2c5d6e7f8g9h0i1j2k3l&units=metric&lang=ru",timeout=3)
        if r.status_code==200:
            d=r.json(); res=f"🌤 {city}: {round(d['main']['temp'])}°C, {d['weather'][0]['description']}\n💨 Ветер: {d['wind']['speed']} м/с"
            set_cache(ck,res); return res
    except: pass
    return None

def get_currency_fast():
    c=get_cache("cur")
    if c: return c
    try:
        d=requests.get("https://api.exchangerate-api.com/v4/latest/USD",timeout=3).json()
        usd=d.get('rates',{}).get('RUB','?'); eur=d.get('rates',{}).get('EUR',1)
        res=f"💵 USD: {round(usd,2)}₽\nEUR: {round(usd/eur,2) if eur else '?'}₽"
        set_cache("cur",res); return res
    except: return None

def get_crypto_fast():
    c=get_cache("cr")
    if c: return c
    try:
        d=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",timeout=3).json()
        res=f"🪙 BTC: ${d.get('bitcoin',{}).get('usd','?')}\nETH: ${d.get('ethereum',{}).get('usd','?')}"
        set_cache("cr",res); return res
    except: return None

def solve_math(text):
    tl=text.lower().strip()
    if not re.search(r'\d',tl): return None
    if any(k in tl for k in ['кто','что','где','когда','почему','праздник','погода','курс']): return None
    cl=tl
    for w in ['сколько','будет','посчитай','реши','пример','равно']: cl=cl.replace(w,'')
    cl=cl.replace(' ','').replace('плюс','+').replace('минус','-').replace('умножить','*').replace('разделить','/').replace('х','*').replace('×','*').replace('÷','/')
    if not re.search(r'[+\-*/]',cl): return None
    expr=re.sub(r'[^0-9+\-*/()=.]','',cl)
    if expr and len(expr)>1 and '__' not in expr and 'import' not in expr:
        try:
            res=eval(expr)
            return str(int(res)) if res==int(res) else str(round(res,2))
        except: pass
    return None

def translate_text(text,target='ru'):
    try:
        r=requests.get("https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="+target+"&dt=t&q="+urllib.parse.quote(text[:2000]),timeout=6)
        if r.status_code==200: return "".join(x[0] for x in r.json()[0] if x[0])
    except: pass
    return None

# ============================================================
# ГЛАВНЫЙ ПРОМПТ
# ============================================================
SUPER_SYSTEM_PROMPT="""ТЫ — AWESOME AI, живой умный ИИ-помощник нового поколения.
📍 Ты находишься в РОССИИ, Москва (UTC+3). Сегодня: {date}, время: {time}.
{memory}
{search}
ТВОЙ СТИЛЬ: отвечай как живой эксперт — живо, тепло, с юмором. Давай конкретику, цифры, примеры.
ФОРМАТ: разделяй на разделы **1. Название**. Важное выделяй **жирным**. Используй эмодзи (🔥🧠💡⚡🚀💎).
ПРАВИЛА: если есть свежие данные из поиска — ОБЯЗАТЕЛЬНО опирайся на них и дай ссылки. Никогда не выдумывай актуальные события, если их нет в поиске — так и скажи.
Ты полноценный собеседник — поддерживай разговор, задавай встречные вопросы, запоминай детали.💎"""

# ============================================================
# ОБРАБОТКА СООБЩЕНИЯ (много функций с сайта)
# ============================================================
def process_message(user_id, text, image_desc=None):
    tl=text.lower().strip()
    m=solve_math(text)
    if m is not None: return m
    if any(k in tl for k in ['праздник','какой сегодня праздник']):
        today=get_current_date(); md=today[3:5]+'.'+today[0:2]
        hol={'01.01':'Новый год','07.01':'Рождество','23.02':'День защитника Отечества','08.03':'Международный женский день','09.05':'День Победы','12.06':'День России','04.11':'День народного единства','14.02':'День влюбленных','01.04':'День смеха','12.04':'День космонавтики','01.09':'День знаний'}
        return f"📅 Сегодня {today}\n{hol.get(md,'Праздников не найдено')}"
    if 'время' in tl or 'какое сегодня число' in tl or 'дата' in tl:
        return f"🕒 Сейчас {get_current_time()} МСК, дата: {get_current_date()}."
    if 'погода' in tl:
        cm=re.search(r'(в|в городе)\s+([а-яА-Яa-zA-Z\- ]+)',tl)
        if cm:
            w=get_weather_fast(cm.group(2).strip()); return w if w else "🌤 Напиши: погода в [город]"
        return "🌤 Напиши: погода в [город]"
    if any(k in tl for k in ['курс','доллар','евро','валюта']):
        c=get_currency_fast(); return c if c else "💵 Не удалось получить курс"
    if any(k in tl for k in ['биткоин','btc','крипта','эфир']):
        c=get_crypto_fast(); return c if c else "🪙 Не удалось"
    if 'переведи' in tl:
        tgt='ru'
        if 'англ' in tl: tgt='en'
        elif 'немец' in tl: tgt='de'
        elif 'франц' in tl: tgt='fr'
        txt=re.sub(r'(переведи|на английский|на русский|на немецкий|на французский|пожалуйста)','',tl).strip()
        r=translate_text(txt,tgt); return "🌍 "+r if r else "Напиши что перевести."
    if 'запомни' in tl:
        fact=re.sub(r'(запомни|выучи|что)\s*','',tl).strip()[:300]
        if len(fact)>3:
            remember(user_id,fact); return "🧠 Запомнил: «"+fact+"»"
        return "🧠 Что именно запомнить?"
    if 'что ты помнишь' in tl or 'память' in tl:
        mem=recall(user_id); return "🧠 **Что я помню:**\n"+"\n".join(mem) if mem else "🧠 Пока ничего. Скажи «запомни...»"
    if any(k in tl for k in ['анекдот','шутк','рассмеши']):
        jokes=["— Почему программист перепутал Хэллоуин и Рождество? — Oct 31 == Dec 25 😄","— Админ заходит в бар, а там буферы переполнены 😅","— Что сказал сервер серверу? — Ты сегодня в сети? 📶"]
        return "😂 "+random.choice(jokes)
    if any(k in tl for k in ['комплимент','похвали','что во мне хорош']):
        return "✨ Ты потрясающий! Умный, любопытный и явно интересный человек. Таких приятно встречать!"
    if any(k in tl for k in ['стань моим','режим','будь моим']):
        return "⚡ Доступные режимы: юрист ⚖️, психолог 🧠, учитель 📚, кодер 💻, маркетолог 📈. Напиши роль!"
    if 'кто ты' in tl or 'что ты умеешь' in tl:
        return "Я **AWESOME AI** ✨\n\n• Ищу в интернете 🌐\n• Помню о тебе 🧠\n• Свежие новости 📰\n• Математика 🧮\n• Погода/валюта/крипта 🌤💵🪙\n• Перевод 🌍\n• Шутки 😂\n• Картинки 🎨\n\nЧто попробуем?"
    if 'привет' in tl or 'здравств' in tl or 'хай' in tl:
        return "👋 Привет! Я AWESOME AI. Чем помочь?"

    search_res=None
    needs=any(k in tl for k in ['новост','последн','сейчас','свеж','актуальн','сегодня','открылась','запусти','новый проект','расскажи про']) or re.search(r'\b(20\d\d|вчера|сегодня)\b',tl)
    if needs: search_res=search_all_internet(text)

    mem=recall(user_id)
    sysp=SUPER_SYSTEM_PROMPT.format(date=get_current_date(),time=get_current_time(),
        memory=("Помнишь о пользователе:\n"+"\n".join(mem)) if mem else "",
        search=("📰 Данные из интернета:\n"+search_res) if search_res else "")
    if get_premium_status(user_id): sysp+="\n💎 Premium — максимум глубины."
    if image_desc: sysp+=f"\n📸 На изображении: {image_desc}"

    a=generate_with_gigachat(text, sysp)
    if a and len(a)>4: return a
    if search_res: return "🔍 "+search_res[:600]
    return "🤖 Обрабатываю... Напиши подробнее, и я дам полный ответ!"

# ============================================================
# КЛАВИАТУРЫ
# ============================================================
bot=telebot.TeleBot(TELEGRAM_TOKEN)
user_command_ids={}

def delete_previous_messages(chat_id,user_id):
    try:
        for mid in user_command_ids.get(user_id,[]):
            try: bot.delete_message(chat_id,mid)
            except: pass
        user_command_ids[user_id]=[]
    except: pass

def main_menu():
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📊 Статус",callback_data="status"),
           types.InlineKeyboardButton("💎 Premium",callback_data="premium"),
           types.InlineKeyboardButton("🎁 Тест Premium",callback_data="test"),
           types.InlineKeyboardButton("👤 Профиль",callback_data="profile"),
           types.InlineKeyboardButton("📊 Статистика",callback_data="stats"),
           types.InlineKeyboardButton("🧹 Очистить",callback_data="clear"),
           types.InlineKeyboardButton("❓ Помощь",callback_data="help"),
           types.InlineKeyboardButton("📩 Поддержка",callback_data="support"),
           types.InlineKeyboardButton("🎨 Сгенерировать",callback_data="draw"))
    return kb

def back_to_menu():
    kb=types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🏠 Главное меню",callback_data="back_to_menu"))
    return kb

def premium_menu(user_id):
    kb=types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("💳 Оплатить (100₽/мес)",url="https://yoomoney.ru/quickpay/fundraise/button?billNumber=1JN0VV54CV0.260817&"),
           types.InlineKeyboardButton("✅ Я оплатил",callback_data="i_paid"))
    if get_premium_status(user_id) or is_admin(user_id):
        kb.add(types.InlineKeyboardButton("📋 Что даёт Premium?",callback_data="premium_features"),
               types.InlineKeyboardButton("🔄 Продлить",callback_data="extend_premium"))
    kb.add(types.InlineKeyboardButton("🏠 Главное меню",callback_data="back_to_menu"))
    return kb

def admin_menu():
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📊 Статистика",callback_data="admin_stats"),
           types.InlineKeyboardButton("👥 Все пользователи",callback_data="admin_list_users"),
           types.InlineKeyboardButton("📢 Рассылка",callback_data="admin_broadcast"),
           types.InlineKeyboardButton("💎 Заказы Premium",callback_data="admin_orders"),
           types.InlineKeyboardButton("📩 Обращения",callback_data="admin_support"),
           types.InlineKeyboardButton("💎 Выдать Premium",callback_data="admin_giveprem"),
           types.InlineKeyboardButton("🎁 Тест Premium",callback_data="admin_givetest"),
           types.InlineKeyboardButton("🚫 Забанить",callback_data="admin_ban"),
           types.InlineKeyboardButton("✅ Разбанить",callback_data="admin_unban"),
           types.InlineKeyboardButton("🔇 Замутить",callback_data="admin_mute"),
           types.InlineKeyboardButton("🔊 Размутить",callback_data="admin_unmute"),
           types.InlineKeyboardButton("👑 Выдать админа",callback_data="admin_giveadmin"),
           types.InlineKeyboardButton("👑 Забрать админа",callback_data="admin_deladmin"),
           types.InlineKeyboardButton("📊 Инфо",callback_data="admin_info"),
           types.InlineKeyboardButton("🧹 Обнулить",callback_data="admin_clear_messages"),
           types.InlineKeyboardButton("❌ Закрыть",callback_data="admin_close"))
    return kb

# ============================================================
# КОМАНДЫ
# ============================================================
@bot.message_handler(commands=['start'])
def start(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid); ensure_user(uid,m.from_user.username or 'unknown')
    txt=(f"✨ **ДОБРО ПОЖАЛОВАТЬ В AWESOME AI 2026!** ✨\n\n🌸 Привет, {m.from_user.first_name}!\n\n"
         "⚡ Отвечаю быстро через GigaChat!\n\n🌐 **ЧТО Я УМЕЮ:**\n"
         "• 🔍 Ищу в Google/Wiki/YouTube/Новостях\n• 💵 Курс валют и крипты\n• 🧮 Математика\n"
         "• 📸 Анализ фото\n• 🎨 Картинки\n• 🧠 Память\n• 🌍 Перевод\n\n"
         "💎 Premium: 100₽/мес\n🎁 Тест Premium на 2 дня — 1 раз!")
    msg=bot.send_message(cid,txt,reply_markup=main_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id)
    user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['help'])
def help_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    txt=("🧠 **ПОМОЩЬ**\n\n🌐 Функции:\n• 🔍 Поиск в интернете\n• 🌤 Погода\n• 💵 Курс/крипта\n"
         "• 🧮 Математика\n• 📸 Анализ фото\n• 🎨 Картинки\n• 🧠 Память («запомни...»)\n• 🌍 Перевод\n\n"
         "📋 Команды:\n/start /help /status /premium /test /profile /stats /clear /draw /support /feedback")
    if is_authorized(uid):
        txt+="\n\n🛡️ Админ:\n/admin /giveprem [ID] [срок] /givetest [ID] /ban [ID] /unban [ID] /mute [ID] /unmute [ID] /giveadmin [ID] /deladmin [ID] /info [ID] /clear_messages [ID] /broadcast [текст]"
    txt+=f"\n\n🔓 Лимит: {FREE_LIMIT}/день\n💎 Premium: ♾️"
    msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['status'])
def status_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    if uid==OWNER_ID: st="👑 ВЛАДЕЛЕЦ — ♾️"
    elif is_admin(uid): st="👑 АДМИН — ♾️"
    elif get_premium_status(uid):
        exp=get_premium_expires(uid)
        st=f"💎 PREMIUM{' (до '+format_date(exp)+')' if exp else ''}\n📨 ♾️ БЕЗЛИМИТ"
    else:
        u=get_db_user(uid); used=u.get('messages_today',0) if u else 0
        st=f"🔓 Бесплатный: осталось {max(0,FREE_LIMIT-used)} из {FREE_LIMIT}"
    msg=bot.send_message(cid,f"📊 **ТВОЙ СТАТУС**\n\n{st}",reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['premium'])
def premium_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    has=get_premium_status(uid)
    if has:
        exp=get_premium_expires(uid)
        txt=f"💎 У тебя уже есть Premium!\n⏳ До: {format_date(exp)}\n📨 ♾️ БЕЗЛИМИТ\n💰 100₽/мес"
    else:
        txt="💎 **PREMIUM AWESOME AI**\n\n🔥 ♾️ Безлимит\n🚀 Приоритет\n🧠 Глубокие ответы GigaChat\n💎 VIP-поддержка\n\n💰 100₽/месяц"
    msg=bot.send_message(cid,txt,reply_markup=premium_menu(uid),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['test'])
def test_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    ensure_user(uid)
    if get_premium_status(uid):
        msg=bot.send_message(cid,"💎 У тебя уже есть Premium!",reply_markup=premium_menu(uid),parse_mode='Markdown')
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    u=get_db_user(uid)
    if u and u.get('test_used')==1:
        msg=bot.send_message(cid,"⛔ Тест уже использован! /premium",reply_markup=premium_menu(uid),parse_mode='Markdown')
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    if set_premium(uid,'2d'):
        if use_supabase:
            sb_exec(lambda: supabase.table('users').update({'test_used':1}).eq('user_id',int(uid)).execute())
        msg=bot.send_message(cid,"🎉 **ПРОБНЫЙ PREMIUM НА 2 ДНЯ!**\n✅ ♾️ Безлимит\n✅ Приоритет GigaChat\n\n⏳ 48 часов!",reply_markup=premium_menu(uid),parse_mode='Markdown')
    else:
        msg=bot.send_message(cid,"❌ Ошибка.")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['profile'])
def profile_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    u=get_db_user(uid); used=u.get('messages_today',0) if u else 0
    joined=u.get('joined_at','Неизвестно') if u else 'Неизвестно'
    if uid==OWNER_ID or (u and u.get('is_owner')==1): status="👑 ВЛАДЕЛЕЦ"; lim="♾️"
    elif is_admin(uid): status="👑 АДМИН"; lim="♾️"
    elif get_premium_status(uid):
        exp=get_premium_expires(uid); status=f"💎 PREMIUM{' (до '+format_date(exp)+')' if exp else ''}"; lim="♾️"
    else: status="🔓 Бесплатный"; lim=f"{FREE_LIMIT}/день"
    txt=(f"👤 **ТВОЙ ПРОФИЛЬ**\n\n🆔 ID: `{uid}`\n👤 Юзер: @{m.from_user.username or 'Не указан'}\n"
         f"💎 Статус: {status}\n📨 Лимит: {lim}\n✉️ Сегодня: {used}\n📅 Вход: {joined}")
    msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    if is_authorized(uid):
        if use_supabase:
            r=sb_exec(lambda: supabase.table('users').select('*').execute())
            rows=r.data if r else []
            total=len(rows); prem=sum(1 for x in rows if x.get('premium')==1); adm=sum(1 for x in rows if x.get('is_admin')==1)
        else:
            import sqlite3
            conn=sqlite3.connect('users.db'); c=conn.cursor(); c.execute('SELECT * FROM users'); rows=c.fetchall(); conn.close()
            total=len(rows); prem=sum(1 for x in rows if x[2]==1); adm=sum(1 for x in rows if x[6]==1)
        txt=f"📊 **СТАТИСТИКА СЕРВЕРА**\n\n👥 Всего: {total}\n👑 Админов: {adm}\n💎 Premium: {prem}\n🔓 Бесплатных: {total-prem-adm}"
    else:
        u=get_db_user(uid); used=u.get('messages_today',0) if u else 0
        prem=get_premium_status(uid)
        status="💎 PREMIUM" if prem else "🔓 Бесплатный"
        lim="♾️" if prem else f"{max(0,FREE_LIMIT-used)}/{FREE_LIMIT}"
        txt=f"📊 **ТВОЯ СТАТИСТИКА**\n\n👤 {status}\n📨 Лимит: {lim}\n✉️ Сегодня: {used}"
    msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['clear'])
def clear_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    try:
        for mid in user_command_ids.get(uid,[]):
            try: bot.delete_message(cid,mid)
            except: pass
        user_command_ids[uid]=[]
    except: pass
    msg=bot.send_message(cid,"🧹 **ИСТОРИЯ ОЧИЩЕНА**",reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(msg.message_id)

@bot.message_handler(commands=['draw'])
def draw_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    prompt=m.text.replace('/draw','').strip()
    if not prompt:
        msg=bot.send_message(cid,"❌ /draw [описание]")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    if not can_send_message(uid):
        msg=bot.send_message(cid,"🔴 Лимит! /premium",reply_markup=premium_menu(uid),parse_mode='Markdown')
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    msg=bot.send_message(cid,"🎨 Генерирую... ⏳")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)
    clean=prompt
    for w in ['нарисуй','сгенерируй','покажи','картинку','изображение','/draw']: clean=clean.replace(w,'').strip()
    try:
        r=requests.get(f"https://image.pollinations.ai/prompt/{urllib.parse.quote(clean or prompt)}?width=512&height=512&nologo=true",headers={"User-Agent":"Mozilla/5.0"},timeout=15)
        if r.status_code==200 and len(r.content)>1000:
            increment_messages(uid)
            bot.send_photo(cid,r.content,caption=f"🎨 {clean or prompt}\n✨ AWESOME AI")
        else:
            bot.send_message(cid,"⚠️ Не удалось сгенерировать.")
    except:
        bot.send_message(cid,"⚠️ Ошибка генерации.")

@bot.message_handler(commands=['support'])
def support_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    text=m.text.replace('/support','').strip()
    if not text:
        msg=bot.send_message(cid,"📩 /support [текст]")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    if use_supabase:
        try: supabase.table('support_requests').insert({'user_id':int(uid),'username':m.from_user.username or 'unknown','text':text,'created_at':gm().strftime('%d.%m.%Y %H:%M')}).execute()
        except: pass
    msg=bot.send_message(cid,"✅ Обращение отправлено!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)
    try: bot.send_message(OWNER_ID,f"📩 ОБРАЩЕНИЕ\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}",parse_mode='Markdown')
    except: pass

@bot.message_handler(commands=['feedback'])
def feedback_cmd(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    text=m.text.replace('/feedback','').strip()
    if not text:
        msg=bot.send_message(cid,"📝 /feedback [текст]")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    msg=bot.send_message(cid,"✅ Спасибо за отзыв! ❤️")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)
    try: bot.send_message(OWNER_ID,f"📝 ОТЗЫВ\n👤 @{m.from_user.username or 'Не указан'}\n📝 {text}",parse_mode='Markdown')
    except: pass

@bot.message_handler(commands=['admin'])
def admin_panel(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    if not is_authorized(uid):
        msg=bot.send_message(cid,"❌ Нет прав!")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    msg=bot.send_message(cid,"🛡️ **АДМИН-ПАНЕЛЬ**",reply_markup=admin_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

# --- админ команды ---
def _admin_guard(m):
    cid=m.chat.id; uid=m.from_user.id
    delete_previous_messages(cid,uid)
    if not is_authorized(uid):
        msg=bot.send_message(cid,"❌ Нет прав!")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)
        return None
    return cid,uid

@bot.message_handler(commands=['giveprem'])
def giveprem_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<2:
        msg=bot.send_message(cid,"❌ /giveprem [ID] [срок]\nСрок: 1d, 7d, 1mes, 1y")
        user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id); return
    try: target=int(args[0]); dur=args[1]
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    if set_premium(target,dur):
        exp=get_premium_expires(target)
        msg=bot.send_message(cid,f"✅ Premium выдан {target}!\n⏳ До: {format_date(exp)}",parse_mode='Markdown')
        try: bot.send_message(target,f"🎉 ВАМ ВЫДАН PREMIUM!\n⏳ До: {format_date(exp)}",parse_mode='Markdown')
        except: pass
    else:
        msg=bot.send_message(cid,"❌ Ошибка")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['givetest'])
def givetest_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /givetest [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    if set_premium(target,'2d'):
        if use_supabase:
            sb_exec(lambda: supabase.table('users').update({'test_used':1}).eq('user_id',target).execute())
        exp=get_premium_expires(target)
        msg=bot.send_message(cid,f"✅ Тест Premium выдан {target}!\n⏳ До: {format_date(exp)}",parse_mode='Markdown')
        try: bot.send_message(target,f"🎉 ТЕСТ PREMIUM НА 2 ДНЯ!\n⏳ До: {format_date(exp)}",parse_mode='Markdown')
        except: pass
    else: msg=bot.send_message(cid,"❌ Ошибка")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /ban [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    if target==OWNER_ID:
        msg=bot.send_message(cid,"❌ Нельзя забанить владельца!"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    ban_user(target)
    msg=bot.send_message(cid,f"✅ {target} забанен!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['unban'])
def unban_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /unban [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    unban_user(target); msg=bot.send_message(cid,f"✅ {target} разбанен!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /mute [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    if target==OWNER_ID:
        msg=bot.send_message(cid,"❌ Нельзя!"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    mute_user(target); msg=bot.send_message(cid,f"✅ {target} замучен!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['unmute'])
def unmute_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /unmute [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    unmute_user(target); msg=bot.send_message(cid,f"✅ {target} размучен!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['giveadmin'])
def giveadmin_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /giveadmin [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    set_admin(target,True); msg=bot.send_message(cid,f"✅ {target} стал админом!")
    try: bot.send_message(target,"👑 ВЫ СТАЛИ АДМИНОМ!")
    except: pass
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['deladmin'])
def deladmin_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /deladmin [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    if target==OWNER_ID:
        msg=bot.send_message(cid,"❌ Нельзя у владельца!"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    set_admin(target,False); msg=bot.send_message(cid,f"✅ У {target} забрана админка!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['info'])
def info_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /info [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    u=get_db_user(target)
    if u:
        status="👑 ВЛАДЕЛЕЦ" if u.get('is_owner')==1 else "👑 АДМИН" if u.get('is_admin')==1 else "💎 PREMIUM" if u.get('premium')==1 else "🔓 Бесплатный"
        exp=u.get('premium_expires')
        txt=(f"📊 **ИНФО**\n\n🆔 `{target}`\n💎 {status}\n"
             f"📨 Premium: {('до '+format_date(exp)) if exp and u.get('premium')==1 else 'нет'}\n"
             f"✉️ Сегодня: {u.get('messages_today',0)}\n📅 Вход: {u.get('joined_at','Неизвестно')}")
    else: txt=f"❌ Пользователь {target} не найден"
    msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['clear_messages'])
def clear_messages_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g; args=m.text.split()[1:]
    if len(args)<1:
        msg=bot.send_message(cid,"❌ /clear_messages [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    try: target=int(args[0])
    except:
        msg=bot.send_message(cid,"❌ Неверный ID"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    clear_messages(target)
    msg=bot.send_message(cid,f"✅ Сообщения {target} обнулены!")
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    g=_admin_guard(m)
    if not g: return
    cid,uid=g
    text=m.text.replace('/broadcast','').strip()
    if not text:
        msg=bot.send_message(cid,"❌ /broadcast [текст]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
    kb=types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✅ Отправить",callback_data=f"confirm_broadcast:{text}"),
           types.InlineKeyboardButton("❌ Отмена",callback_data="cancel_broadcast"))
    msg=bot.send_message(cid,f"📢 **ПОДТВЕРДИТЕ**\n\n{text}",reply_markup=kb,parse_mode='Markdown')
    user_command_ids.setdefault(uid,[]).append(m.message_id); user_command_ids[uid].append(msg.message_id)

# ============================================================
# СООБЩЕНИЯ (текст и фото)
# ============================================================
@bot.message_handler(func=lambda m: True)
def handle_all(m):
    try:
        cid=m.chat.id; uid=m.from_user.id; text=(m.text or '').strip()
        if text.startswith('/'): return
        if is_banned(uid): bot.send_message(cid,"🚫 Ты забанен!"); return
        if is_muted(uid): bot.send_message(cid,"🔇 Ты замучен!"); return
        ensure_user(uid,m.from_user.username or 'unknown')
        if not can_send_message(uid):
            bot.send_message(cid,"🔴 Лимит! /premium",reply_markup=premium_menu(uid),parse_mode='Markdown'); return
        if m.photo:
            file_id=m.photo[-1].file_id; fi=bot.get_file(file_id); fc=bot.download_file(fi.file_path)
            desc="📸 фото"
            if HAS_PIL:
                try:
                    img=Image.open(io.BytesIO(fc)); desc=f"📸 {img.size[0]}×{img.size[1]}"
                except: pass
            resp=process_message(uid,text or 'Что на картинке?',desc)
            increment_messages(uid); bot.send_message(cid,resp,reply_markup=back_to_menu(),parse_mode='Markdown'); return
        if text:
            if any(k in text.lower() for k in ['нарисуй','покажи','картинку','изображение','сгенерируй']) and ' ' in text:
                fake=types.Message(m.message_id,m.from_user,m.date,m.chat,text,{})
                draw_cmd(fake); return
            bot.send_chat_action(cid,'typing')
            resp=process_message(uid,text)
            if resp:
                increment_messages(uid)
                bot.send_message(cid,resp,reply_markup=back_to_menu(),parse_mode='Markdown')
            else:
                bot.send_message(cid,"❌ Не удалось.",reply_markup=back_to_menu(),parse_mode='Markdown')
    except Exception as e:
        print(f"❌ {e}")

# ============================================================
# КНОПКИ
# ============================================================
@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    try:
        cid=call.message.chat.id; uid=call.from_user.id
        try: bot.delete_message(cid,call.message.message_id)
        except: pass
        try: bot.answer_callback_query(call.id)
        except: pass
        ensure_user(uid,call.from_user.username or 'unknown')
        d=call.data
        if d in ['status','premium','test','profile','stats','clear','help']:
            cmd_map={'status':status_cmd,'premium':premium_cmd,'test':test_cmd,'profile':profile_cmd,'stats':stats_cmd,'clear':clear_cmd,'help':help_cmd}
            cmd_map[d](call.message); return
        if d=='back_to_menu': start(call.message); return
        if d=='support':
            msg=bot.send_message(cid,"📩 /support [текст]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='draw':
            msg=bot.send_message(cid,"🎨 /draw [описание]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='premium_features':
            if not get_premium_status(uid) and not is_admin(uid):
                msg=bot.send_message(cid,"❌ Только Premium!",reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
            txt="💎 **PREMIUM**\n\n🔥 ♾️ Безлимит\n🚀 Приоритет\n🧠 Глубокие ответы GigaChat\n💎 VIP-поддержка\n\n💰 100₽/мес"
            msg=bot.send_message(cid,txt,reply_markup=premium_menu(uid),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='extend_premium':
            if not get_premium_status(uid):
                msg=bot.send_message(cid,"❌ Нет Premium!",reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
            oid=add_order(uid); exp=get_premium_expires(uid)
            msg=bot.send_message(cid,f"✅ Заказ #{oid} на продление!\n⏳ {format_date(exp)}",reply_markup=back_to_menu(),parse_mode='Markdown')
            user_command_ids.setdefault(uid,[]).append(msg.message_id)
            kb=types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton("✅",callback_data=f"confirm_order:{oid}"),types.InlineKeyboardButton("❌",callback_data=f"reject_order:{oid}"))
            try: bot.send_message(OWNER_ID,f"💳 Продление #{oid}\n👤 @{call.from_user.username or 'Не указан'}",reply_markup=kb,parse_mode='Markdown')
            except: pass
            return
        if d=='i_paid':
            oid=add_order(uid)
            msg=bot.send_message(cid,f"✅ Заказ #{oid} отправлен!\n⏳ Ожидай подтверждения.",reply_markup=back_to_menu(),parse_mode='Markdown')
            user_command_ids.setdefault(uid,[]).append(msg.message_id)
            kb=types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton("✅",callback_data=f"confirm_order:{oid}"),types.InlineKeyboardButton("❌",callback_data=f"reject_order:{oid}"))
            try: bot.send_message(OWNER_ID,f"💳 НОВЫЙ ЗАКАЗ #{oid}\n👤 @{call.from_user.username or 'Не указан'}\n💰 100₽",reply_markup=kb,parse_mode='Markdown')
            except: pass
            return
        if not is_authorized(uid): return
        if d=='admin_stats': stats_cmd(call.message); return
        if d=='admin_orders':
            ords=pending_orders()
            txt="💳 **ЗАКАЗЫ PREMIUM**\n\n" if ords else "💳 **ЗАКАЗЫ**\n\nНет активных."
            if ords:
                for o in ords: txt+=f"#{o['order_id']} | 👤 {o['user_id']} | {o.get('created_at','')}\n"
            msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_support':
            r=sb_exec(lambda: supabase.table('support_requests').select('*').eq('status','pending').order('request_id',desc=True).limit(20).execute()) if use_supabase else None
            rows=r.data if r else []
            txt="📩 **ОБРАЩЕНИЯ**\n\n" if rows else "📩 **ОБРАЩЕНИЯ**\n\nНет активных."
            for x in rows: txt+=f"#{x.get('request_id')} | @{x.get('username','')} | {x.get('text','')[:50]}\n"
            msg=bot.send_message(cid,txt,reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_list_users':
            if use_supabase:
                r=sb_exec(lambda: supabase.table('users').select('*').limit(200).execute()); rows=r.data if r else []
            else:
                import sqlite3
                conn=sqlite3.connect('users.db'); c=conn.cursor(); c.execute('SELECT user_id,username,premium,is_admin FROM users'); rows=c.fetchall(); conn.close()
                rows=[{'user_id':x[0],'username':x[1],'premium':x[2],'is_admin':x[3]} for x in rows]
            txt="👥 **ПОЛЬЗОВАТЕЛИ**\n\n"
            for x in rows[:100]:
                st="👑" if x.get('is_owner')==1 else "🛡️" if x.get('is_admin')==1 else "💎" if x.get('premium')==1 else "🔓"
                txt+=f"{st} @{x.get('username') or x.get('user_id')} | `{x.get('user_id')}`\n"
            msg=bot.send_message(cid,txt[:4000],reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_broadcast': msg=bot.send_message(cid,"📢 /broadcast [текст]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_giveprem': msg=bot.send_message(cid,"💎 /giveprem [ID] [срок]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_givetest': msg=bot.send_message(cid,"🎁 /givetest [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_ban': msg=bot.send_message(cid,"🚫 /ban [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_unban': msg=bot.send_message(cid,"✅ /unban [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_mute': msg=bot.send_message(cid,"🔇 /mute [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_unmute': msg=bot.send_message(cid,"🔊 /unmute [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_giveadmin': msg=bot.send_message(cid,"👑 /giveadmin [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_deladmin': msg=bot.send_message(cid,"👑 /deladmin [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_info': msg=bot.send_message(cid,"📊 /info [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_clear_messages': msg=bot.send_message(cid,"🧹 /clear_messages [ID]"); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d=='admin_close': msg=bot.send_message(cid,"❌ Закрыто",reply_markup=back_to_menu(),parse_mode='Markdown'); user_command_ids.setdefault(uid,[]).append(msg.message_id); return
        if d.startswith('confirm_order:'):
            oid=int(d.split(':')[1]); o=get_order(oid)
            if o and o['status']=='pending':
                if add_month_to_premium(o['user_id']):
                    update_order(oid,'confirmed'); exp=get_premium_expires(o['user_id'])
                    bot.send_message(cid,f"✅ Заказ #{oid} подтверждён!")
                    try: bot.send_message(o['user_id'],f"🎉 PREMIUM АКТИВИРОВАН!\n✅ #{oid}\n💎 До: {format_date(exp)}",parse_mode='Markdown')
                    except: pass
            return
        if d.startswith('reject_order:'):
            oid=int(d.split(':')[1]); o=get_order(oid)
            if o and o['status']=='pending':
                update_order(oid,'rejected')
                bot.send_message(cid,f"❌ Заказ #{oid} отклонён!")
                try: bot.send_message(o['user_id'],f"❌ ЗАКАЗ #{oid} ОТКЛОНЁН")
                except: pass
            return
        if d.startswith('confirm_broadcast:'):
            text=d.replace('confirm_broadcast:','')
            if use_supabase:
                r=sb_exec(lambda: supabase.table('users').select('user_id').execute()); ids=[x['user_id'] for x in (r.data if r else [])]
            else:
                import sqlite3
                conn=sqlite3.connect('users.db'); c=conn.cursor(); c.execute('SELECT user_id FROM users'); ids=[x[0] for x in c.fetchall()]; conn.close()
            sent=0
            for x in ids:
                try: bot.send_message(x,f"📢 **ОБЪЯВЛЕНИЕ**\n\n{text}",parse_mode='Markdown'); sent+=1; time.sleep(0.04)
                except: pass
            bot.send_message(cid,f"✅ **РАССЫЛКА**\n\n📤 {sent}/{len(ids)}",parse_mode='Markdown'); return
        if d=='cancel_broadcast': bot.send_message(cid,"❌ Отменено."); return
    except Exception as e:
        print(f"❌ callback: {e}")

# ============================================================
# SQLITE ФОЛБЕК (если Supabase недоступен)
# ============================================================
def init_db():
    if use_supabase:
        try: sb_exec(lambda: supabase.table('users').select('*').limit(1).execute())
        except: pass
        return
    import sqlite3
    conn=sqlite3.connect('users.db'); c=conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,name TEXT DEFAULT '',username TEXT DEFAULT '',password TEXT DEFAULT '',telegram_id TEXT DEFAULT '',premium INTEGER DEFAULT 0,premium_expires TEXT,is_admin INTEGER DEFAULT 0,is_owner INTEGER DEFAULT 0,messages_today INTEGER DEFAULT 0,test_used INTEGER DEFAULT 0,theme TEXT DEFAULT 'dark',joined_at TEXT,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS banned(user_id INTEGER PRIMARY KEY)""")
    c.execute("""CREATE TABLE IF NOT EXISTS muted(user_id INTEGER PRIMARY KEY)""")
    c.execute("""CREATE TABLE IF NOT EXISTS total_stats(user_id INTEGER PRIMARY KEY,total_messages INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS premium_orders(order_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,status TEXT DEFAULT 'pending',created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS support_requests(request_id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,username TEXT,text TEXT,status TEXT DEFAULT 'pending',created_at TEXT)""")
    conn.commit(); conn.close()

init_db()

# ============================================================
# KEEP-ALIVE
# ============================================================
def keep_alive():
    while True:
        time.sleep(300)
        try: bot.get_me()
        except: pass
threading.Thread(target=keep_alive,daemon=True).start()

if __name__=='__main__':
    print("🧠 AWESOME AI 2026 — ТГ-бот")
    print(f"🌐 Supabase: {'ДА (синхронизация с сайтом)' if use_supabase else 'НЕТ (sqlite фолбек)'}")
    try: print(f"🤖 @{bot.get_me().username}")
    except: pass
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    while True:
        try:
            bot.polling(none_stop=True,timeout=30,long_polling_timeout=30,allowed_updates=['message','callback_query'])
        except Exception as e:
            print(f"⚠️ {e}. Перезапуск...")
            time.sleep(3)
