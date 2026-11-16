# server.py - Nexa AI - FULL - SQLite DATABASE + Silent Brain + Smart Reply
import os, re, time, threading, sqlite3, hashlib, json
from datetime import datetime
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pytz

app = Flask(__name__)
CORS(app)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PK_TZ = pytz.timezone("Asia/Karachi")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexa.db")
MODELS = ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

# ========== DATABASE ==========
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        status TEXT DEFAULT 'ACTIVE',
        created_at TEXT,
        total_messages INTEGER DEFAULT 0,
        total_images INTEGER DEFAULT 0,
        total_voice INTEGER DEFAULT 0
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        chat_id TEXT,
        title TEXT,
        who TEXT,
        text TEXT,
        created_at TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS brain (
        email TEXT PRIMARY KEY,
        name TEXT,
        last_topic TEXT,
        last_question TEXT,
        last_answer TEXT,
        last_chat_time TEXT,
        facts TEXT,
        topics TEXT,
        last_chat TEXT,
        summary TEXT,
        total_chats INTEGER DEFAULT 0,
        total_messages INTEGER DEFAULT 0,
        updated_at TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        name TEXT,
        login_time TEXT,
        logout_time TEXT,
        duration TEXT,
        status TEXT DEFAULT 'ACTIVE',
        session_id TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        user_name TEXT,
        action TEXT,
        detail TEXT,
        time TEXT
    )''')
    db.execute('''CREATE TABLE IF NOT EXISTS attempts (
        email TEXT PRIMARY KEY,
        count INTEGER DEFAULT 0,
        blocked INTEGER DEFAULT 0,
        lock_until INTEGER DEFAULT 0
    )''')
    db.commit()
    cur = db.execute("SELECT * FROM users WHERE email='admin@nexa.ai'")
    if not cur.fetchone():
        db.execute("INSERT INTO users (name,email,password,role,status,created_at) VALUES (?,?,?,?,?,?)",
            ("Admin","admin@nexa.ai",hash_pass("12345"),"admin","ACTIVE",datetime.now(PK_TZ).strftime("%d %b %Y, %I:%M %p")))
        db.commit()
    db.close()
    print("[DB] nexa.db ready", flush=True)

def hash_pass(p): return hashlib.sha256(str(p).encode()).hexdigest()
def check_pass(p, h): return hashlib.sha256(str(p).encode()).hexdigest() == h

init_db()

LIVE = {"updated_at":"Not yet","updated_ts":0,"dollar_pkr":None,"euro_pkr":None,"riyal_pkr":None,"dirham_pkr":None,"bitcoin_usd":None,"bitcoin_change":None,"eth_usd":None,"gold_tola_pkr":None,"gold_gram_pkr":None,"petrol_pkr":264.61,"diesel_pkr":274.08,"lahore_weather":{"temp":None,"cond":"Loading...","humidity":None,"wind":None},"karachi_weather":{"temp":None,"cond":"Loading..."},"islamabad_weather":{"temp":None,"cond":"Loading..."},"time_pk":"","date_pk":"","breaking":[],"news_world":[],"news_pakistan":[],"status":"starting"}
def pk_now(): return datetime.now(PK_TZ)
def now_str(): return pk_now().strftime("%d %b %Y, %I:%M %p")
def update_time():
    n=pk_now(); LIVE["time_pk"]=n.strftime("%I:%M %p"); LIVE["date_pk"]=n.strftime("%A, %d %B %Y"); LIVE["updated_at"]=n.strftime("%I:%M:%S %p - %d %B %Y"); LIVE["updated_ts"]=int(time.time())
def fetch_currency():
    try:
        r=requests.get("https://api.exchangerate.host/latest?base=USD&symbols=PKR,EUR,SAR,AED",timeout=10); d=r.json(); rates=d.get("rates",{})
        if "PKR" in rates:
            LIVE["dollar_pkr"]=round(rates["PKR"],2)
            if rates.get("EUR"): LIVE["euro_pkr"]=round(rates["PKR"]/rates["EUR"],2)
            if rates.get("SAR"): LIVE["riyal_pkr"]=round(rates["PKR"]/rates["SAR"],2)
            if rates.get("AED"): LIVE["dirham_pkr"]=round(rates["PKR"]/rates["AED"],2)
            return True
    except: pass
    try:
        r=requests.get("https://open.er-api.com/v6/latest/USD",timeout=10); d=r.json()
        if d.get("rates",{}).get("PKR"): LIVE["dollar_pkr"]=round(d["rates"]["PKR"],2); return True
    except: pass
    return False
def fetch_crypto():
    try:
        r=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true",timeout=12); d=r.json()
        if "bitcoin" in d:
            LIVE["bitcoin_usd"]=round(d["bitcoin"]["usd"],2); LIVE["bitcoin_change"]=round(d["bitcoin"].get("usd_24h_change",0),2)
            if "ethereum" in d: LIVE["eth_usd"]=round(d["ethereum"]["usd"],2)
            return True
    except: pass
    try:
        r=requests.get("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",timeout=10); d=r.json()
        if "lastPrice" in d: LIVE["bitcoin_usd"]=round(float(d["lastPrice"]),2); LIVE["bitcoin_change"]=round(float(d.get("priceChangePercent",0)),2); return True
    except: pass
    return False
def fetch_gold():
    try:
        r=requests.get("https://api.metals.live/v1/spot",timeout=10); d=r.json()
        if isinstance(d,list):
            for item in d:
                if item.get("metal")=="gold":
                    oz=float(item.get("price",0))
                    if oz and LIVE["dollar_pkr"]:
                        tola=(oz/31.1035)*11.664*LIVE["dollar_pkr"]; LIVE["gold_tola_pkr"]=round(tola); LIVE["gold_gram_pkr"]=round(tola/11.664); return True
    except: pass
    if LIVE["gold_tola_pkr"] is None and LIVE["dollar_pkr"]:
        LIVE["gold_tola_pkr"]=round((2650/31.1035)*11.664*LIVE["dollar_pkr"]); LIVE["gold_gram_pkr"]=round(LIVE["gold_tola_pkr"]/11.664)
    return False
def fetch_weather_city(city):
    coords={"Lahore":(31.5204,74.3587),"Karachi":(24.8607,67.0011),"Islamabad":(33.6844,73.0479)}; lat,lon=coords.get(city,coords["Lahore"])
    try:
        r=requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=Asia%2FKarachi",timeout=10); d=r.json(); cur=d.get("current",{}); mp={0:"Saaf ☀️",1:"Halke Badal 🌤️",2:"Badal ⛅",3:"Badal ☁️",45:"Dhund 🌫️",51:"Halki Barish 🌦️",53:"Barish 🌧️",61:"Barish 🌧️",65:"Tez Barish 🌧️",95:"Toofan ⛈️"}
        return {"temp":cur.get("temperature_2m"),"cond":mp.get(cur.get("weather_code",0),"Theek 🌤️"),"humidity":cur.get("relative_humidity_2m"),"wind":cur.get("wind_speed_10m")}
    except: return None
def fetch_all_weather():
    for city,key in [("Lahore","lahore_weather"),("Karachi","karachi_weather"),("Islamabad","islamabad_weather")]:
        w=fetch_weather_city(city)
        if w: LIVE[key]=w
def fetch_news():
    try:
        import xml.etree.ElementTree as ET
        for url,key in [("https://news.google.com/rss/search?q=Pakistan&hl=en-PK&gl=PK&ceid=PK:en","news_pakistan"),("https://news.google.com/rss?hl=en-PK&gl=PK&ceid=PK:en","news_world")]:
            r=requests.get(url,timeout=12,headers={"User-Agent":"Mozilla/5.0"}); root=ET.fromstring(r.content); items=[]
            for it in root.findall(".//item")[:6]:
                t=it.findtext("title","")
                if t: items.append(re.sub(r"\s*-\s*[^-]+$","",t).strip())
            if items:
                LIVE[key]=items
                if key=="news_world": LIVE["breaking"]=items[:4]
    except: pass
def refresh_all_live():
    update_time(); fetch_currency(); fetch_crypto(); fetch_gold(); fetch_all_weather(); fetch_news(); update_time(); LIVE["status"]="live"
    print(f"[LIVE] DONE Dollar {LIVE['dollar_pkr']} BTC ${LIVE['bitcoin_usd']}",flush=True)
def live_loop():
    try: refresh_all_live()
    except: pass
    while True:
        time.sleep(180)
        try: refresh_all_live()
        except: pass
threading.Thread(target=live_loop,daemon=True).start()

def build_system_prompt(lang_instr,history_text,memory_text):
    update_time()
    live_block=f"""
[LIVE DATA - SIRF REFERENCE - HAR JAWAB ME MAT CHIPKANA]
Time:{LIVE['time_pk']} Date:{LIVE['date_pk']}
Dollar:{LIVE['dollar_pkr']} Euro:{LIVE['euro_pkr']} Riyal:{LIVE['riyal_pkr']} Dirham:{LIVE['dirham_pkr']}
Bitcoin:${LIVE['bitcoin_usd']} ({LIVE['bitcoin_change']}%) Eth:${LIVE['eth_usd']}
Gold Tola:{LIVE['gold_tola_pkr']} Gram:{LIVE['gold_gram_pkr']} Petrol:{LIVE['petrol_pkr']} Diesel:{LIVE['diesel_pkr']}
Lahore:{LIVE['lahore_weather'].get('temp')}C {LIVE['lahore_weather'].get('cond')}
Karachi:{LIVE['karachi_weather'].get('temp')}C {LIVE['karachi_weather'].get('cond')}
Islamabad:{LIVE['islamabad_weather'].get('temp')}C {LIVE['islamabad_weather'].get('cond')}
Breaking:{' | '.join(LIVE['breaking'][:3])}
"""
    return f"""You are Nexa AI. Samajhdar dost jaisa bano.
SAB SE ZAROORI RULES:
1. SIRF WAHI JAWAB DO JO USER NE POOCHA HAI. Khud se extra MAT joro.
2. Joke sunao to SIRF 1 Joke. Dollar/Bitcoin/Gold/Mausam MAT batao.
3. Hi to sirf Hi ka jawab. Dollar pooche to SIRF Dollar. Mausam pooche to SIRF us sheher ka mausam.
4. LIVE DATA sirf tab jab user ne us cheez ke baare me poocha ho.
5. Chhota sawal = Chhota jawab. Lamba sawal = Detail.
6. Same language me jawab do.
7. Follow-up "or detail / 2 / agle step" to pichli baat ka detail hai.
8. User "2" likhe to sirf option 2 ki FULL detail do.
9. Kabhi "I don't know / I can't / As an AI" mat kaho.
10. SILENT MEMORY: Agar memory me user ka naam / pichli baat hai to usko aise istemal karo jaise tumhe pehle se pata hai. Ye MAT kaho ke "mujhe yaad hai pichli baar...". Sirf tab batana jab user khud pooche "mera naam kya hai / pichli baar kya baat hui".
BANNED: "I am fully updated, alert, and ready to assist you" / "What would you like to work on or discuss today?" / "How can I help you today?" / "Is there anything else I can help you with?" / "Feel free to ask me anything" / "Let me know if you need anything else" / "Nexa AI Update" / "Live Data" heading har jawab me.
Naam Nexa AI hai. {lang_instr} {live_block} MEMORY:{memory_text} HISTORY:{history_text}"""
def get_available_model():
    try:
        r=requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}",timeout=15); d=r.json(); names=[]
        for m in d.get("models",[]):
            n=m.get("name","").replace("models/","")
            if "generateContent" in str(m.get("supportedGenerationMethods",[])): names.append(n)
        for want in ["gemini-3.8-flash","gemini-3-flash-preview","gemini-2.5-flash"]:
            if want in names: return want
        for n in names:
            if "flash" in n and "image" not in n and "tts" not in n: return n
        if names: return names[0]
    except Exception as e: print(f"[GEMINI] List fail: {e}",flush=True)
    return "gemini-3.8-flash"
def call_gemini(prompt):
    payload={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"maxOutputTokens":2048}}
    live_model=get_available_model(); try_list=[live_model]+[m for m in MODELS if m!=live_model]; last_err=""
    for model in try_list:
        try:
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"; r=requests.post(url,json=payload,timeout=30); d=r.json()
            if "candidates" in d and d["candidates"]:
                parts=d["candidates"][0].get("content",{}).get("parts",[])
                if parts: print(f"[GEMINI] Success {model}",flush=True); return parts[0].get("text","")
            last_err=str(d)[:500]; continue
        except Exception as e: last_err=str(e); continue
    return f"Server live hai lekin Gemini se jawab nahi aa raha. Error: {last_err[:200]}"

# ========== DATABASE APIs ==========
@app.route("/api/db/register", methods=["POST"])
def db_register():
    d=request.get_json(force=True) or {}
    name=d.get("name","").strip(); email=d.get("email","").strip().lower(); pw=d.get("password","")
    if not name or not email or len(pw)<4: return jsonify({"ok":False,"msg":"Fill all fields, password min 4"})
    db=get_db()
    if db.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone():
        db.close(); return jsonify({"ok":False,"msg":"Ye email pehle se hai"})
    db.execute("INSERT INTO users (name,email,password,role,status,created_at) VALUES (?,?,?,?,?,?)",(name,email,hash_pass(pw),"user","ACTIVE",now_str()))
    db.execute("INSERT INTO activity (email,user_name,action,detail,time) VALUES (?,?,?,?,?)",(email,name,"SIGNUP","New account - DB",now_str()))
    db.commit(); db.close()
    return jsonify({"ok":True,"user":{"name":name,"email":email,"role":"user"}})

@app.route("/api/db/login", methods=["POST"])
def db_login():
    d=request.get_json(force=True) or {}
    email=d.get("email","").strip().lower(); pw=d.get("password","")
    db=get_db()
    att=db.execute("SELECT * FROM attempts WHERE email=?",(email,)).fetchone()
    if att and att["blocked"]: db.close(); return jsonify({"ok":False,"msg":"BLOCKED. Contact Admin."})
    if att and att["lock_until"] and int(time.time()) < att["lock_until"]:
        db.close(); return jsonify({"ok":False,"msg":f"Locked {int((att['lock_until']-time.time())/60)+1} min."})
    u=db.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not u:
        db.execute("INSERT OR REPLACE INTO attempts (email,count,blocked,lock_until) VALUES (?,?,?,?)",(email,(att["count"]+1 if att else 1),0,0))
        db.commit(); db.close(); return jsonify({"ok":False,"msg":"Email registered nahi!"})
    if u["status"]=="BLOCKED": db.close(); return jsonify({"ok":False,"msg":"BLOCKED. Admin se contact karo."})
    if not check_pass(pw, u["password"]):
        cnt=(att["count"]+1 if att else 1); blocked=1 if cnt>=5 else 0; lock=int(time.time())+300 if cnt>=3 and cnt<5 else 0
        db.execute("INSERT OR REPLACE INTO attempts (email,count,blocked,lock_until) VALUES (?,?,?,?)",(email,cnt,blocked,lock))
        if cnt>=5: db.execute("UPDATE users SET status='BLOCKED' WHERE email=?",(email,))
        db.commit(); db.close()
        return jsonify({"ok":False,"msg":"Wrong Password! "+str(cnt)+"/5" if not blocked else "5 bar galat! BLOCKED."})
    db.execute("DELETE FROM attempts WHERE email=?",(email,))
    sid=f"SES-{int(time.time())}-{u['id']}"
    db.execute("INSERT INTO sessions (email,name,login_time,duration,status,session_id) VALUES (?,?,?,?,?,?)",(email,u["name"],now_str(),"Active","ACTIVE",sid))
    db.execute("INSERT INTO activity (email,user_name,action,detail,time) VALUES (?,?,?,?,?)",(email,u["name"],"LOGIN","Logged in - DB",now_str()))
    db.commit(); db.close()
    return jsonify({"ok":True,"user":{"name":u["name"],"email":u["email"],"role":u["role"],"session_id":sid}})

@app.route("/api/db/brain", methods=["GET"])
def db_brain_get():
    email=request.args.get("email","").lower()
    db=get_db(); row=db.execute("SELECT * FROM brain WHERE email=?",(email,)).fetchone(); db.close()
    if not row: return jsonify({"ok":True,"brain":None})
    return jsonify({"ok":True,"brain":{"name":row["name"],"last_topic":row["last_topic"],"last_question":row["last_question"],"last_answer":row["last_answer"],"facts":json.loads(row["facts"] or "[]"),"topics":json.loads(row["topics"] or "[]"),"last_chat":json.loads(row["last_chat"] or "[]"),"summary":row["summary"]}})

@app.route("/api/db/brain", methods=["POST"])
def db_brain_save():
    d=request.get_json(force=True) or {}
    email=d.get("email","").lower()
    if not email: return jsonify({"ok":False})
    db=get_db()
    db.execute("INSERT OR REPLACE INTO brain (email,name,last_topic,last_question,last_answer,last_chat_time,facts,topics,last_chat,summary,total_chats,total_messages,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (email,d.get("name","User"),d.get("last_topic",""),d.get("last_question",""),d.get("last_answer",""),now_str(),json.dumps(d.get("facts",[])),json.dumps(d.get("topics",[])),json.dumps(d.get("last_chat",[])),d.get("summary",""),d.get("total_chats",0),d.get("total_messages",0),now_str()))
    db.commit(); db.close()
    return jsonify({"ok":True})

@app.route("/api/db/chat-save", methods=["POST"])
def db_chat_save():
    d=request.get_json(force=True) or {}
    email=d.get("email","").lower(); who=d.get("who","user"); text=d.get("text","")[:2000]; chat_id=d.get("chat_id",""); title=d.get("title","")
    if not email or not text: return jsonify({"ok":False})
    db=get_db()
    db.execute("INSERT INTO chats (email,chat_id,title,who,text,created_at) VALUES (?,?,?,?,?,?)",(email,chat_id,title,who,text,now_str()))
    if who=="user": db.execute("UPDATE users SET total_messages=total_messages+1 WHERE email=?",(email,))
    db.commit(); db.close()
    return jsonify({"ok":True})

@app.route("/api/db/chats", methods=["GET"])
def db_chats():
    email=request.args.get("email","").lower()
    db=get_db(); rows=db.execute("SELECT * FROM chats WHERE email=? ORDER BY id DESC LIMIT 100",(email,)).fetchall(); db.close()
    chats=[]
    for r in reversed(rows):
        chats.append({"who":r["who"],"text":r["text"],"chat_id":r["chat_id"],"title":r["title"],"time":r["created_at"]})
    return jsonify({"ok":True,"chats":chats})

@app.route("/api/db/admin", methods=["GET"])
def db_admin():
    email=request.args.get("email","").lower()
    db=get_db(); u=db.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
    if not u or u["role"]!="admin": db.close(); return jsonify({"ok":False,"msg":"Only Admin"})
    users2=[]
    for r in db.execute("SELECT id,name,email,role,status,created_at,total_messages,total_images FROM users ORDER BY id DESC").fetchall():
        users2.append(dict(r))
    sessions=[dict(r) for r in db.execute("SELECT * FROM sessions ORDER BY id DESC LIMIT 50").fetchall()]
    activity=[dict(r) for r in db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 50").fetchall()]
    db.close()
    return jsonify({"ok":True,"users":users2,"sessions":sessions,"activity":activity})

@app.route("/api/db/block", methods=["POST"])
def db_block():
    d=request.get_json(force=True) or {}
    admin=d.get("admin","").lower(); target=d.get("target","").lower(); action=d.get("action","block")
    db=get_db(); u=db.execute("SELECT * FROM users WHERE email=?",(admin,)).fetchone()
    if not u or u["role"]!="admin": db.close(); return jsonify({"ok":False})
    db.execute("UPDATE users SET status=? WHERE email=?",("BLOCKED" if action=="block" else "ACTIVE",target))
    if action=="unblock": db.execute("DELETE FROM attempts WHERE email=?",(target,))
    db.commit(); db.close(); return jsonify({"ok":True})

@app.route("/api/db/logout", methods=["POST"])
def db_logout():
    d=request.get_json(force=True) or {}
    sid=d.get("session_id","")
    db=get_db(); db.execute("UPDATE sessions SET status='ENDED', logout_time=?, duration=? WHERE session_id=?",(now_str(),"Ended",sid)); db.commit(); db.close()
    return jsonify({"ok":True})

@app.route("/")
def home(): return send_from_directory(".","index.html")
@app.route("/api/live")
def api_live(): update_time(); return jsonify(LIVE)
@app.route("/api/breaking")
def api_breaking(): return jsonify({"breaking":LIVE["breaking"],"pakistan":LIVE["news_pakistan"],"world":LIVE["news_world"],"updated_at":LIVE["updated_at"]})
@app.route("/api/new-chat", methods=["POST"])
def new_chat(): return jsonify({"ok":True})
@app.route("/api/chat", methods=["POST"])
def chat():
    data=request.get_json(force=True) or {}; msg=data.get("message","").strip(); lang_instr=data.get("langInstruction",""); history=data.get("history",[]); memory=data.get("memory",{})
    if not msg: return jsonify({"reply":"Kuch likho to sahi."})
    if int(time.time())-LIVE["updated_ts"]>300: threading.Thread(target=refresh_all_live,daemon=True).start()
    history_text=""
    for h in history[-10:]:
        role="User" if h.get("role")=="user" else "Nexa"; history_text+=f"{role}: {h.get('text','')[:600]}\n"
    memory_text=""
    try:
        if isinstance(memory,dict):
            if memory.get("lastTopic"): memory_text+=f"Last Topic: {memory.get('lastTopic')}\n"
            for f in (memory.get("facts") or [])[-5:]: memory_text+=f"Fact: {f.get('fact','')}\n"
    except: pass
    email=(data.get("email") or "").lower()
    if email:
        try:
            db=get_db(); row=db.execute("SELECT * FROM brain WHERE email=?",(email,)).fetchone(); db.close()
            if row and row["last_question"]:
                memory_text+=f"\n[DB BRAIN - SILENT] Naam:{row['name']} LastQ:{row['last_question']} Facts:{row['facts']}\n"
        except: pass
    full=build_system_prompt(lang_instr,history_text,memory_text)+f"\nUSER: {msg}\nSIRF ISI SAWAL KA JAWAB DO, EXTRA KUCH MAT JORO:"
    reply=call_gemini(full)
    for b in ["I am fully updated, alert, and ready to assist you","What would you like to work on or discuss today?","How can I help you today?","Is there anything else I can help you with?","Feel free to ask me anything","Let me know if you need anything else"]: reply=reply.replace(b,"").strip()
    return jsonify({"reply":reply})
@app.route("/api/health")
def health(): update_time(); return jsonify({"status":"live","updated_at":LIVE["updated_at"],"dollar":LIVE["dollar_pkr"],"btc":LIVE["bitcoin_usd"],"model":"gemini-3.8-flash-auto","db":"sqlite nexa.db"})
if __name__=="__main__":
    port=int(os.environ.get("PORT",5000)); print("NEXA AI - DATABASE + Silent Brain",flush=True); app.run(host="0.0.0.0",port=port,debug=False,threaded=True)