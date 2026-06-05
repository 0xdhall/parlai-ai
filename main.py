import os
import html
import requests
import json
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BAI_API_KEY = os.getenv("BAI_API_KEY")

BAI_MODEL = "gpt-5.2"
WITA_OFFSET = 8
TELEGRAM_LIMIT = 3500

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks = []
    while len(text) > TELEGRAM_LIMIT:
        cut = text.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut == -1: cut = TELEGRAM_LIMIT
        chunks.append(text[:cut])
        text = text[cut:]
    chunks.append(text)

    for chunk in chunks:
        if chunk.strip():
            try:
                requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "parse_mode": "HTML"}, timeout=20)
            except Exception as e:
                print(f"Gagal mengirim Telegram: {e}")

def fetch_nowgoal_livescore_data():
    """
    Mengambil data bursa langsung dari feed publik Nowgoal Asia
    """
    # Menyamar sebagai browser asli agar tidak diblokir oleh sistem keamanan
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.nowgoal.com/"
    }
    
    # Menggunakan URL feed alternatif gratisan Nowgoal
    url = "https://interface.nowgoal.com/v8/odds.aspx?f=json" 
    
    try:
        response = requests.get(url, headers=headers, timeout=25)
        if response.status_code == 200:
            # Saringan keamanan jika data dikunci berupa string mentah javascript
            raw_data = response.text
            if raw_data.startswith("var"):
                # Konversi format variabel JS ke objek Python dictionary
                return clean_js_to_dict(raw_data)
            return response.json()
    except Exception as e:
        print(f"Gagal mengambil data Nowgoal Livescore: {e}")
        
    # Backup Fallback ke server cadangan jika URL utama sibuk
    return fetch_fallback_livescore()

def clean_js_to_dict(js_text):
    # Logika konversi teks mentah javascript menjadi struktur data Python bersih
    try:
        match_data = re.findall(r'\[.*?\]', js_text)
        return match_data
    except:
        return None

def fetch_fallback_livescore():
    # Menembak feed data publik cadangan (Format JSON Olahraga Terbuka)
    url = "https://api.scorebat.com/video-api/v3/"
    try:
        r = requests.get(url, timeout=15)
        return r.json().get("response", [])
    except:
        return []

def analyze_with_bai(matches_text):
    if not BAI_API_KEY: return "AI Key tidak terdeteksi."
    
    prompt = f"""
Anda adalah analis sepak bola profesional. Analisis data bursa livescore ini dan berikan prediksi parlay malam ini.
Template Output WAJIB rapi:
📋 **RINGKASAN PREDIKSI MATCH NIGHT**
• [Home] vs [Away] -> Pick: [Over/Under/Handicap]

🔥 **REKOMENDASI PARLAY (SIAP PASANG)**
1. [Match 1] -> [Pick]
2. [Match 2] -> [Pick]

DATA MATCH:
{matches_text}
"""
    try:
        r = requests.post(
            "https://api.b.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {BAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": BAI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=60
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Gagal analisa AI: {e}"

def main():
    print("Memulai pemindaian data via Livescore API...")
    data = fetch_nowgoal_livescore_data()
    
    if not data:
        # Jika feed internal Nowgoal sedang down, bot otomatis membaca data fallback
        send_telegram("⚠️ Server Utama Livescore sibuk. Mengaktifkan sistem pencarian alternatif...")
        return

    # Pemrosesan dan pengemasan pesan rapi ke Telegram
    msg = "📊 <b>LIVESCORE TONIGHT DATA (FREE API)</b>\n\n"
    ai_input = ""
    
    # Contoh pembacaan iterasi jika data berhasil dimuat
    count = 0
    if isinstance(data, list):
        for match in data[:12]: # Ambil 12 pertandingan teratas malam ini
            # Sesuaikan dengan key nama tim dari output json target
            home = match.get("title", match.get("home", "Unknown"))
            competition = match.get("competition", "Liga Utama")
            
            msg += f"⚔️ <b>{home}</b>\nLeague: {competition}\n"
            msg += "• Pasaran Utama: Terbuka (+100 Market Berjalan)\n"
            msg += "━━━━━━━━━━━━━━\n"
            
            ai_input += f"- {home} ({competition})\n"
            count += 1

    if count == 0:
        send_telegram("⚠️ Tidak ada pertandingan livescore baru yang terjaring menit ini.")
        return

    # Kirim data bursa mentah
    send_telegram(msg)
    
    # Jalankan analisa AI
    ai_analysis = analyze_with_bai(ai_input)
    send_telegram(f"🤖 <b>AI LIVESCORE REPORT</b>\n\n{ai_analysis}")

if __name__ == "__main__":
    main()
