import os
import html
import requests
import time
import random
from datetime import datetime

# --- KONFIGURASI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BAI_API_KEY = os.getenv("BAI_API_KEY")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=20)
    except Exception as e:
        print(f"Gagal kirim Telegram: {e}")

def fetch_data():
    # Penyamaran sebagai browser asli
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Referer": "https://www.nowgoal.com/"
    }
    # Jeda acak 3-7 detik agar IP tidak terdeteksi bot/banned
    time.sleep(random.uniform(3, 7))
    
    url = "https://api.scorebat.com/video-api/v3/" # Menggunakan sumber data yang lebih stabil & publik
    try:
        response = requests.get(url, headers=headers, timeout=25)
        if response.status_code == 200:
            return response.json().get("response", [])
    except:
        return []
    return []

def analyze_with_ai(matches_text):
    if not BAI_API_KEY: return "AI Key tidak tersedia."
    
    prompt = f"Analisis data bola ini untuk parlay:\n{matches_text}"
    try:
        r = requests.post(
            "https://api.b.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {BAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": "gpt-5.2", "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=60
        )
        return r.json()["choices"][0]["message"]["content"]
    except:
        return "Gagal analisa AI."

def main():
    print("Mencari data pertandingan...")
    data = fetch_data()
    
    if not data:
        send_telegram("⚠️ Server sedang sibuk, bot akan mencoba lagi di jadwal berikutnya.")
        return

    msg = "📊 <b>DAFTAR PERTANDINGAN TERKINI</b>\n\n"
    ai_input = ""
    
    for match in data[:10]:
        home = match.get("title", "Unknown")
        msg += f"⚔️ {home}\n━━━━━━━━━━━━━━\n"
        ai_input += f"- {home}\n"

    send_telegram(msg)
    ai_result = analyze_with_ai(ai_input)
    send_telegram(f"🤖 <b>AI PARLAY REPORT</b>\n\n{ai_result}")

if __name__ == "__main__":
    main()
