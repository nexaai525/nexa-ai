
import os, sqlite3, hashlib, json, time, threading, secrets
from datetime import datetime, timedelta
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pytz

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, 'nexa.db')
PORT = int(os.environ.get("PORT", 5000))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ADMIN_EMAIL = "admin@nexa.ai"
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD", "12345")
PK = pytz.timezone("Asia/Karachi")

# ---------- DB ----------
def get_db():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, password TEXT, role TEXT DEFAULT 'user', status TEXT DEFAULT 'ACTIVE', created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, role TEXT, content TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS brain (id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, answer TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, action TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS attempts (email TEXT PRIMARY KEY, count INTEGER DEFAULT 0, blocked_until TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS live_cache (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)""")
    db.commit()
    # SAFE Admin - sirf code se banta hai, signup se kabhi nahi
    c.execute("SELECT * FROM users WHERE email=?", (ADMIN_EMAIL,))
    row = c.fetchone()
    h = hashlib.sha256(ADMIN_PASS.encode()).hexdigest()
    now = datetime.now(PK).isoformat()
    if not row:
        c.execute("INSERT INTO users (name,email,password,role,status,created_at) VALUES (?,?,?,?,?,?)", ("Admin", ADMIN_EMAIL, h, "admin", "ACTIVE", now))
        print("Admin created")
    else:
        # Agar pehle se User bana hua hai to usko Admin kar do - sirf isi email ke liye
        c.execute("UPDATE users SET role='admin', status='ACTIVE', password=? WHERE email=?", (h, ADMIN_EMAIL))
        print("Admin ensured")
        # Attempts clear taake block na rahe
        c.execute("DELETE FROM attempts WHERE email=?", (ADMIN_EMAIL,))
    db.commit()
    db.close()

init_db()

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def now_str(): return datetime.now(PK).isoformat()
def make_token(): return secrets.token_hex(24)

def get_user_from_token():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "): return None
    token = auth.replace("Bearer ", "").strip()
    db = get_db()
    s = db.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
    if not s: db.close(); return None
    u = db.execute("SELECT * FROM users WHERE id=?", (s["user_id"],)).fetchone()
    db.close()
    return dict(u) if u else None

def is_blocked(email):
    db = get_db()
    r = db.execute("SELECT * FROM attempts WHERE email=?", (email,)).fetchone()
    db.close()
    if not r: return False, 0
    if r["blocked_until"]:
        try:
            if datetime.fromisoformat(r["blocked_until"]) > datetime.now(PK):
                return True, r["count"]
        except: pass
    return False, r["count"]

def record_fail(email):
    db = get_db()
    r = db.execute("SELECT * FROM attempts WHERE email=?", (email,)).fetchone()
    cnt = (r["count"]+1) if r else 1
    blocked = None
    if cnt >= 5:
        blocked = (datetime.now(PK)+timedelta(minutes=5)).isoformat()
    if r:
        db.execute("UPDATE attempts SET count=?, blocked_until=? WHERE email=?", (cnt, blocked, email))
    else:
        db.execute("INSERT INTO attempts (email,count,blocked_until) VALUES (?,?,?)", (email, cnt, blocked))
    db.commit(); db.close()
    return cnt

def clear_attempts(email):
    db = get_db(); db.execute("DELETE FROM attempts WHERE email=?", (email,)); db.commit(); db.close()

# ---------- LIVE - On Demand Only, No Auto Loop ----------
def fetch_live(key):
    try:
        if key == "dollar":
            r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
            d = r.json()
            return {"USD_PKR": round(d["rates"].get("PKR", 0), 2)}
        if key == "crypto":
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd", timeout=5)
            return r.json()
        if key == "gold":
            return {"note": "Gold rate - use live search"}
    except Exception as e:
        return {"error": str(e)}
    return {}

# ---------- GEMINI ----------
def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        return "Gemini Key nahi lagi hui - Railway Variables me GEMINI_API_KEY daalo."
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        d = r.json()
        return d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Gemini error: {e}"

# ---------- ROUTES ----------
@app.route("/")
def home():
    return send_from_directory(BASE, "index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "live", "time": now_str(), "admin": ADMIN_EMAIL})

@app.route("/api/signup", methods=["POST"])
def signup():
    d = request.get_json(force=True) or {}
    name = (d.get("name") or "").strip()
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    if not name or not email or not pw:
        return jsonify({"success": False, "error": "Saari fields bharo"}), 400
    # SAFE: Admin email signup se nahi ban sakta - sirf init_db se banta hai
    if email == ADMIN_EMAIL:
        return jsonify({"success": False, "error": "Ye email reserved hai - Admin se contact karo"}), 403
    db = get_db()
    if db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone():
        db.close(); return jsonify({"success": False, "error": "Email pehle se registered hai"}), 400
    db.execute("INSERT INTO users (name,email,password,role,status,created_at) VALUES (?,?,?,?,?,?)", (name, email, hash_pw(pw), "user", "ACTIVE", now_str()))
    db.commit()
    u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    token = make_token()
    db.execute("INSERT INTO sessions (user_id,token,created_at) VALUES (?,?,?)", (u["id"], token, now_str()))
    db.commit(); db.close()
    return jsonify({"success": True, "token": token, "user": {"name": name, "email": email, "role": "user"}})

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(force=True) or {}
    email = (d.get("email") or "").strip().lower()
    pw = d.get("password") or ""
    blocked, cnt = is_blocked(email)
    if blocked:
        return jsonify({"success": False, "error": "Account 5 minute ke liye block hai - thoda wait karo"}), 403
    db = get_db()
    u = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not u:
        db.close()
        c = record_fail(email)
        return jsonify({"success": False, "error": f"Email registered nahi hai! Attempt {c}/5"}), 400
    if u["password"] != hash_pw(pw):
        db.close()
        c = record_fail(email)
        return jsonify({"success": False, "error": f"Password galat hai! Attempt {c}/5"}), 400
    if u["status"] != "ACTIVE":
        db.close(); return jsonify({"success": False, "error": "Account blocked hai"}), 403
    clear_attempts(email)
    token = make_token()
    db.execute("INSERT INTO sessions (user_id,token,created_at) VALUES (?,?,?)", (u["id"], token, now_str()))
    db.commit(); db.close()
    return jsonify({"success": True, "token": token, "user": {"name": u["name"], "email": u["email"], "role": u["role"]}})

@app.route("/api/chat", methods=["POST"])
def chat():
    user = get_user_from_token()
    if not user: return jsonify({"success": False, "error": "Login karo"}), 401
    d = request.get_json(force=True) or {}
    msg = (d.get("message") or "").strip()
    if not msg: return jsonify({"success": False, "error": "Message khaali hai"}), 400
    low = msg.lower()
    # Live on-demand
    if "dollar" in low or "euro" in low or "riyal" in low or "dirham" in low:
        live = fetch_live("dollar")
        reply = f"Live Dollar Rate: {live} - Ye live rate hai."
        return jsonify({"success": True, "reply": reply})
    if "bitcoin" in low or "crypto" in low:
        live = fetch_live("crypto")
        reply = f"Live Crypto: {live}"
        return jsonify({"success": True, "reply": reply})
    # Brain check
    db = get_db()
    b = db.execute("SELECT * FROM brain WHERE question LIKE ? ORDER BY id DESC LIMIT 1", (f"%{msg[:30]}%",)).fetchone()
    db.close()
    if b:
        return jsonify({"success": True, "reply": b["answer"]})
    reply = ask_gemini(msg)
    # Save to brain for next time
    db = get_db()
    db.execute("INSERT INTO brain (question,answer,created_at) VALUES (?,?,?)", (msg, reply, now_str()))
    db.commit(); db.close()
    return jsonify({"success": True, "reply": reply})

@app.route("/api/admin/users")
def admin_users():
    user = get_user_from_token()
    if not user or user["role"] != "admin":
        return jsonify({"success": False, "error": "Sirf Admin"}), 403
    db = get_db()
    rows = db.execute("SELECT id,name,email,role,status,created_at FROM users ORDER BY id DESC").fetchall()
    db.close()
    return jsonify({"success": True, "users": [dict(r) for r in rows]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
