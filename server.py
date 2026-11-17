import os, requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
CORS(app)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PK_TZ = pytz.timezone("Asia/Karachi")

@app.route("/")
def home():
    return send_from_directory(".", "index.html")

@app.route("/api/live")
def live():
    out = {}
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8).json()
        out["dollar_pkr"] = round(r["rates"].get("PKR", 276), 2)
    except Exception:
        out["dollar_pkr"] = 276.56
    try:
        r = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=8).json()
        out["bitcoin_usd"] = float(r["data"]["amount"])
        out["bitcoin_change"] = 0
    except Exception:
        out["bitcoin_usd"] = 0
        out["bitcoin_change"] = 0
    try:
        pkr = out.get("dollar_pkr") or 276
        out["gold_tola_pkr"] = round(2650 * pkr * 11.6638 / 31.1035)
    except Exception:
        out["gold_tola_pkr"] = 0
    try:
        r = requests.get("https://wttr.in/Lahore?format=j1", timeout=8).json()
        cur = r["current_condition"][0]
        out["lahore_weather"] = {"temp": int(cur["temp_C"]), "cond": cur["weatherDesc"][0]["value"]}
    except Exception:
        out["lahore_weather"] = {"temp": 22, "cond": "Clear"}
    out["time_pk"] = datetime.now(PK_TZ).strftime("%I:%M %p, %d %b %Y")
    return jsonify(out)

@app.route("/api/breaking")
def breaking():
    return jsonify({"breaking": ["Nexa AI Live - Dollar, Bitcoin, Gold aur Mausam live hai."]})

@app.route("/api/new-chat", methods=["POST"])
def new_chat():
    return jsonify({"ok": True})

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True, silent=True) or {}
    msg = data.get("message", "")
    lang_instr = data.get("langInstruction", "")
    if not GEMINI_API_KEY:
        return jsonify({"reply": "GEMINI_API_KEY WSGI me nahi hai."})
    # SIRF NAYA MODEL - 3.8-flash, purana koi model nahi
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
        prompt = f"{lang_instr}\nUser: {msg}\nReply short, helpful."
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        j = r.json()
        if "candidates" in j:
            return jsonify({"reply": j["candidates"][0]["content"]["parts"][0]["text"]})
        if "error" in j:
            return jsonify({"reply": f"Gemini Error: {j['error'].get('message','')[:250]}"})
        return jsonify({"reply": "Gemini se khali jawab aaya."})
    except Exception as e:
        return jsonify({"reply": f"Connect Error: {str(e)[:200]}"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
