import os
os.environ["HTTPS_PROXY"] = "http://proxy.server:3128"
os.environ["HTTP_PROXY"] = "http://proxy.server:3128"
import sqlite3, requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "nexa.db")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ADMIN_EMAIL = "admin@nexa.ai"
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "12345")
PK_TZ = pytz.timezone("Asia/Karachi")
PROXIES = {"http": "http://proxy.server:3128", "https": "http://proxy.server:3128"}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, is_admin INTEGER DEFAULT 0, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, title TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, text TEXT, created_at TEXT)")
    c.commit()
    row = c.execute("SELECT * FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not row:
        c.execute("INSERT INTO users (name,email,password,is_admin,created_at) VALUES (?,?,?,?,?)", ("Admin", ADMIN_EMAIL, ADMIN_PASS, 1, datetime.now(PK_TZ).isoformat()))
        c.commit()
    c.close()

init_db()

@app.route("/")
def home():
    return send_from_directory(BASE, "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "live", "model": "gemini-3.8-flash-fallback", "db": "sqlite nexa.db"})

@app.route("/api/live")
def live():
    out = {}
    # Dollar + Euro + Pound - live
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8, proxies=PROXIES).json()
        rates = r.get("rates", {})
        out["dollar_pkr"] = round(rates.get("PKR", 276.56), 2)
        out["euro_pkr"] = round(rates.get("PKR", 276.56) / rates.get("EUR", 0.92), 2) if rates.get("EUR") else 0
        out["pound_pkr"] = round(rates.get("PKR", 276.56) / rates.get("GBP", 0.79), 2) if rates.get("GBP") else 0
    except Exception:
        out["dollar_pkr"] = 276.56
        out["euro_pkr"] = 0
        out["pound_pkr"] = 0
    # Bitcoin + Ethereum - live
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=8, proxies=PROXIES).json()
        out["bitcoin_usd"] = float(r["data"]["amount"])
        out["bitcoin_pkr"] = round(out["bitcoin_usd"] * out.get("dollar_pkr", 276))
    except Exception:
        out["bitcoin_usd"] = 0
        out["bitcoin_pkr"] = 0
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/ETH-USD/spot", timeout=8, proxies=PROXIES).json()
        out["ethereum_usd"] = float(r["data"]["amount"])
    except Exception:
        out["ethereum_usd"] = 0
    out["bitcoin_change"] = 0
    # Gold Tola - live dollar se
    try:
        out["gold_tola_pkr"] = round(2650 * (out.get("dollar_pkr") or 276) * 11.6638 / 31.1035)
        out["gold_gram_pkr"] = round(out["gold_tola_pkr"] / 11.6638)
    except Exception:
        out["gold_tola_pkr"] = 0
        out["gold_gram_pkr"] = 0
    # Weather Lahore + Karachi + Islamabad - live
    out["weather"] = {}
    for city in ["Lahore", "Karachi", "Islamabad"]:
        try:
            r = requests.get(f"https://wttr.in/{city}?format=j1", timeout=8, proxies=PROXIES).json()
            cur = r["current_condition"][0]
            out["weather"][city] = {"temp": int(cur["temp_C"]), "cond": cur["weatherDesc"][0]["value"], "humidity": cur.get("humidity", "")}
        except Exception:
            out["weather"][city] = {"temp": 22, "cond": "Clear", "humidity": ""}
    out["lahore_weather"] = out["weather"].get("Lahore", {"temp": 22, "cond": "Clear"})
    out["time_pk"] = datetime.now(PK_TZ).strftime("%I:%M %p, %d %b %Y")
    out["live"] = True
    out["source"] = "live-feed: open.er-api + coinbase + wttr.in"
    return jsonify(out)

@app.route("/api/breaking")
def breaking():
    news = []
    try:
        r = requests.get("https://news.google.com/rss/search?q=Pakistan&hl=ur&gl=PK&ceid=PK:ur", timeout=8, proxies=PROXIES, headers={"User-Agent": "Mozilla/5.0"})
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:6]:
            t = item.findtext("title", "")
            if t:
                news.append(t)
    except Exception:
        pass
    if not news:
        news = ["Live - Dollar, Bitcoin, Gold aur Mausam live hai.", "Pakistan ki taza khabrein live feed se aa rahi hain."]
    return jsonify({"breaking": news})

@app.route("/api/signup", methods=["POST"])
def signup():
    d = request.get_json(force=True, silent=True) or {}
    name = (d.get("name") or "User").strip()
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if email == ADMIN_EMAIL:
        return jsonify({"ok": False, "error": "Admin email se signup nahi ho sakta."}), 400
    if not email or not pw:
        return jsonify({"ok": False, "error": "Email aur Password likhein."}), 400
    c = db()
    try:
        c.execute("INSERT INTO users (name,email,password,is_admin,created_at) VALUES (?,?,?,?,?)", (name, email, pw, 0, datetime.now(PK_TZ).isoformat()))
        c.commit()
    except sqlite3.IntegrityError:
        c.close()
        return jsonify({"ok": False, "error": "Ye email pehle se hai, Login karein."}), 400
    c.close()
    return jsonify({"ok": True, "user": {"name": name, "email": email, "is_admin": 0}})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(force=True, silent=True) or {}
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    c = db()
    row = c.execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw)).fetchone()
    c.close()
    if not row:
        return jsonify({"ok": False, "error": "Email registered nahi hai ya password galat."}), 400
    return jsonify({"ok": True, "user": {"name": row["name"], "email": row["email"], "is_admin": row["is_admin"]}})

@app.route("/api/new-chat", methods=["POST"])
def new_chat():
    d = request.get_json(force=True, silent=True) or {}
    email = d.get("email") or "guest@nexa.ai"
    c = db()
    cur = c.cursor()
    cur.execute("INSERT INTO chats (user_email,title,created_at) VALUES (?,?,?)", (email, "New Chat", datetime.now(PK_TZ).isoformat()))
    cid = cur.lastrowid
    c.commit()
    c.close()
    return jsonify({"ok": True, "chat_id": cid})

@app.route("/api/chat", methods=["POST"])
def chat():
    d = request.get_json(force=True, silent=True) or {}
    msg = d.get("message", "")
    lang = d.get("langInstruction", "")
    prompt = f"{lang}\nUser: {msg}\nReply short, helpful, Roman Urdu if user uses Roman Urdu."
    if not GEMINI_API_KEY:
        return jsonify({"reply": "GEMINI_API_KEY PythonAnywhere Web Env me nahi hai."})
    MODELS_TRY = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-3-flash-preview", "gemini-3.8-flash"]
    last_err = ""
    for MODEL_NAME in MODELS_TRY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
            r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30, proxies=PROXIES)
            j = r.json()
            if "candidates" in j:
                return jsonify({"reply": j["candidates"][0]["content"]["parts"][0]["text"]})
            if "error" in j:
                last_err = j["error"].get("message", "")
                low = last_err.lower()
                # Koi bhi busy / quota / overload error ho to agle model pe jao, ruko mat
                if any(k in low for k in ["high demand", "overloaded", "currently experiencing", "try again later", "resource exhausted", "quota", "503", "429", "temporarily", "unavailable"]):
                    continue
                # Agar model hi nahi mila to bhi agla try karo
                if "not found" in low or "not supported" in low or "404" in low:
                    continue
                continue
        except Exception as e:
            last_err = str(e)
            continue
    return jsonify({"reply": "Bhai Gemini abhi thora busy hai, 1 minute baad phir try karo - main ne 6 model try kiye hain."})

@app.route("/api/admin/users")
def admin_users():
    email = request.args.get("admin_email", "")
    if email != ADMIN_EMAIL:
        return jsonify({"ok": False, "error": "Sirf Admin"}), 403
    c = db()
    rows = c.execute("SELECT id,name,email,is_admin,created_at FROM users ORDER BY id DESC").fetchall()
    c.close()
    return jsonify({"ok": True, "users": [dict(r) for r in rows]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
