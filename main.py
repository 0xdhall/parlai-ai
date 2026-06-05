import os
import requests

# Konfigurasi dari GitHub Secrets
API_KEY = os.getenv("ODDS_API_KEY")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def main():
    # Menargetkan soccer_epl (bisa diganti sesuai liga yang tersedia di paket gratis Anda)
    url = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds/"
    
    params = {
        "apiKey": API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal"
    }

    try:
        response = requests.get(url, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            
            if not data:
                print("Tidak ada data pertandingan saat ini.")
                return

            msg = "⚽ <b>JADWAL & ODDS EPL</b>\n\n"
            for match in data[:5]:
                home = match.get("home_team")
                away = match.get("away_team")
                msg += f"⚔️ <b>{home} vs {away}</b>\n"
                msg += "━━━━━━━━━━━━━━\n"
            
            # Kirim ke Telegram
            telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            requests.post(telegram_url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})
            print("Berhasil kirim ke Telegram!")
            
        else:
            print(f"Error API: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"Error sistem: {e}")

if __name__ == "__main__":
    main()
