import os, json, requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "12345")
PK_TZ = pytz.timezone("Asia/Karachi")

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/api/live")
def live():
    out = {}
    try:
        # Dollar PKR - free API
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8).json()
        out["dollar_pkr"] = round(r["rates"].get("PKR", 0), 2)
    except Exception as e:
        out["dollar_pkr"] = 0
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true", timeout=8).json()
        out["bitcoin_usd"] = r["bitcoin"]["usd"]
        out["bitcoin_change"] = round(r["bitcoin"].get("usd_24h_change", 0), 2)
    except Exception:
        out["bitcoin_usd"] = 0
        out["bitcoin_change"] = 0
    try:
        # Gold approx: XAU USD per ounce -> tola PKR
        r = requests.get("https://api.metals.live/v1/spot", timeout=8)
        gold_usd_oz = 0
        try:
            d = r.json()
            for x in d:
                if x.get("metal") == "gold":
                    gold_usd_oz = x.get("price", 0)
        except Exception:
            pass
        if not gold_usd_oz:
            gold_usd_oz = 2600
        pkr = out.get("dollar_pkr") or 280
        # 1 tola = 11.6638g, 1 oz = 31.1035g
        out["gold_tola_pkr"] = round(gold_usd_oz * pkr * 11.6638 / 31.1035)
    except Exception:
        out["gold_tola_pkr"] = 0
    try:
        # Lahore weather - Open-Meteo free, no key
        r = requests.get("https://api.open-meteo.com/v1/forecast?latitude=31.55&longitude=74.34&current=temperature_2m,weather_code&timezone=Asia%2FKarachi", timeout=8).json()
        out["lahore_weather"] = {"temp": r["current"]["temperature_2m"], "cond": str(r["current"]["weather_code"])}
    except Exception:
        out["lahore_weather"] = {"temp": 0, "cond": ""}
    try:
        out["time_pk"] = datetime.now(PK_TZ).strftime("%I:%M %p, %d %b %Y")
    except Exception:
        out["time_pk"] = ""
    return jsonify(out)

@app.route("/api/breaking")
def breaking():
    # Simple fallback - frontend expects list
    return jsonify({"breaking": ["Nexa AI Live - Dollar, Bitcoin, Gold aur Mausam live hai."]})

@app.route("/api/new-chat", methods=["POST"])
def new_chat():
    return jsonify({"ok": True})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message", "")
    lang = data.get("language", "english")
    lang_instr = data.get("langInstruction", "")
    if not GEMINI_API_KEY:
        return jsonify({"reply": "GEMINI_API_KEY Railway me lagi hui nahi hai. Railway > Variables me GEMINI_API_KEY daalo phir dobara try karo."})
    # Gemini API
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"{lang_instr}\nUser: {msg}\nReply short, helpful, in same language as user."
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        r = requests.post(url, json=payload, timeout=30)
        j = r.json()
        reply = j["candidates"][0]["content"]["parts"][0]["text"]
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"AI se connect nahi ho raha: {str(e)[:200]}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
