import os
import html
import requests
from datetime import datetime, timedelta, timezone

# Mengambil semua API & Token dari GitHub Secrets / Environment
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
ODDSPAPI_API_KEY = os.getenv("ODDSPAPI_API_KEY")
BAI_API_KEY = os.getenv("BAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BAI_MODEL = "gpt-5.2"
WITA_OFFSET = 8
TELEGRAM_LIMIT = 3500

# 4 Region Utama untuk menyedot bandar taruhan seluruh dunia di The Odds API
ODDS_API_REGIONS = ["eu", "us", "uk", "au"]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Memotong pesan otomatis jika melebihi batas karakter Telegram agar tidak error
    chunks = []
    while len(text) > TELEGRAM_LIMIT:
        cut = text.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut == -1:
            cut = TELEGRAM_LIMIT
        chunks.append(text[:cut])
        text = text[cut:]
    chunks.append(text)

    for chunk in chunks:
        if chunk.strip():
            try:
                requests.post(
                    url,
                    json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": chunk,
                        "parse_mode": "HTML"
                    },
                    timeout=20
                )
            except Exception as e:
                print(f"Gagal mengirim Telegram: {e}")


def get_all_soccer_sports():
    url = "https://api.the-odds-api.com/v4/sports/"
    params = {"apiKey": ODDS_API_KEY}
    try:
        r = requests.get(url, params=params, timeout=20)
        sports = r.json()
        return [
            s["key"]
            for s in sports
            if s.get("group") == "Soccer"
            and s.get("active")
            and not s.get("has_outrights")
        ]
    except Exception as e:
        print("Error mengambil daftar liga:", e)
        return []


def fetch_odds_the_odds_api(sport, region):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    # Mengaktifkan pasaran utama + babak pertama (HT) + alternatif agar tembus +100 market
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": region,
        "markets": "spreads,totals,h2h,h2h_1st_half,spreads_1st_half,totals_1st_half",
        "oddsFormat": "decimal"
    }
    try:
        r = requests.get(url, params=params, timeout=25)
        return r.json()
    except Exception as e:
        print(f"Error fetch The Odds API {sport}: {e}")
        return []


def fetch_odds_oddspapi():
    if not ODDSPAPI_API_KEY:
        print("OddsPAPI key tidak diset di secrets.")
        return []
    try:
        # Menembak daftar turnamen sepak bola (sport_id 10) yang aktif
        url = "https://api.oddspapi.io/v4/tournaments"
        params = {"apiKey": ODDSPAPI_API_KEY, "sportId": 10}
        r = requests.get(url, params=params, timeout=20)
        tournaments = r.json()

        if not isinstance(tournaments, list):
            return []

        active_tournaments = [t for t in tournaments if t.get("active") is not False]
        tournament_ids = [str(t["id"]) for t in active_tournaments[:40]]  # Batasi 40 turnamen teraktif

        if not tournament_ids:
            return []

        all_fixtures = []
        for tournament_id in tournament_ids:
            try:
                url = "https://api.oddspapi.io/v4/odds-by-tournaments"
                params = {
                    "apiKey": ODDSPAPI_API_KEY,
                    "tournamentIds": tournament_id,
                    "oddsFormat": "decimal"
                }
                r = requests.get(url, params=params, timeout=20)
                fixtures = r.json()
                if isinstance(fixtures, list):
                    all_fixtures.extend(fixtures)
            except:
                continue
        return all_fixtures
    except Exception as e:
        print("Error OddsPAPI fetch:", e)
        return []


def is_match_now_to_6am(commence_time):
    if not commence_time:
        return False, None
    try:
        if isinstance(commence_time, str):
            t_str = commence_time.strip()
            if t_str.endswith("Z"):
                t_str = t_str.replace("Z", "+00:00")
            if "+" not in t_str and "-" not in t_str[10:]:
                t_str += "+00:00"
            match_utc = datetime.fromisoformat(t_str)
        else:
            match_utc = datetime.fromtimestamp(commence_time, tz=timezone.utc)
    except:
        return False, None

    now_utc = datetime.now(timezone.utc)
    # Jendela scan fleksibel 24 jam ke depan agar menangkap laga malam ini s/d subuh tanpa zonk
    start_scan_utc = now_utc - timedelta(hours=6)
    cutoff_utc = now_utc + timedelta(hours=24)

    is_allowed = start_scan_utc <= match_utc <= cutoff_utc
    match_wita = match_utc + timedelta(hours=WITA_OFFSET)

    return is_allowed, match_wita


def format_point(point):
    if point is None:
        return ""
    if point > 0:
        return f"+{point:g}"
    return f"{point:g}"


def parse_event(event, source="odds-api"):
    commence_time = event.get("commence_time") if source == "odds-api" else (event.get("start_time") or event.get("commence_time"))
    allowed, match_wita = is_match_now_to_6am(commence_time)
    if not allowed:
        return None

    home = event.get("home_team", "Home").strip()
    away = event.get("away_team", "Away").strip()
    league = event.get("sport_title") or event.get("tournament_name") or "Other League"

    match_key = f"{home.lower()}_{away.lower()}_{match_wita.strftime('%Y%m%d')}"
    match = {
        "home": home,
        "away": away,
        "league": league,
        "date": match_wita.strftime("%d %b %Y"),
        "time": match_wita.strftime("%H:%M WITA"),
        "ah": [],
        "ou": [],
        "match_key": match_key
    }

    seen_ah, seen_ou = set(), set()
    bookmakers = event.get("bookmakers", [])
    
    for bookmaker in bookmakers:
        book = bookmaker.get("title", "-")
        for market in bookmaker.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key in ["spreads", "spreads_1st_half"]:
                for o in outcomes:
                    name, point, price = o.get("name"), o.get("point"), o.get("price")
                    if name is None or point is None or price is None:
                        continue
                    item_key = (name, point, price)
                    if item_key in seen_ah:
                        continue
                    seen_ah.add(item_key)
                    match["ah"].append({"team": name, "point": point, "odds": price, "book": f"{book}-HT" if "1st" in key else book})

            elif key in ["totals", "totals_1st_half"]:
                for o in outcomes:
                    name, point, price = o.get("name"), o.get("point"), o.get("price")
                    if name is None or point is None or price is None:
                        continue
                    item_key = (name, point, price)
                    if item_key in seen_ou:
                        continue
                    seen_ou.add(item_key)
                    match["ou"].append({"side": name, "point": point, "odds": price, "book": f"{book}-HT" if "1st" in key else book})

    match["ah"] = sorted(match["ah"], key=lambda x: x["point"])
    match["ou"] = sorted(match["ou"], key=lambda x: x["point"])

    if not match["ah"] and not match["ou"]:
        return None
    return match


def merge_matches(matches_list):
    seen_keys = set()
    merged = []
    for match in matches_list:
        key = match.get("match_key")
        if key not in seen_keys:
            seen_keys.add(key)
            merged.append(match)
        else:
            for existing in merged:
                if existing.get("match_key") == key:
                    existing["ah"].extend(match["ah"])
                    existing["ou"].extend(match["ou"])
                    existing["ah"] = list({(x["team"], x["point"], x["odds"], x["book"]): x for x in existing["ah"]}.values())
                    existing["ou"] = list({(x["side"], x["point"], x["odds"], x["book"]): x for x in existing["ou"]}.values())
                    existing["ah"] = sorted(existing["ah"], key=lambda x: x["point"])
                    existing["ou"] = sorted(existing["ou"], key=lambda x: x["point"])
                    break
    return merged


def build_raw_market_message(matches):
    msg = "📊 <b>TONIGHT PARLAY HYBRID DATA (MAX SCAN)</b>\n"
    msg += f"Total Pertandingan Lolos Filter: {len(matches)}\n\n"
    for m in matches[:10]:  # Kirim max 10 data mentah teratas agar Telegram rapi
        msg += f"📅 <b>{html.escape(m['date'])}</b> | ⏰ <b>{html.escape(m['time'])}</b>\n"
        msg += f"<b>{html.escape(m['home'])} vs {html.escape(m['away'])}</b>\n"
        msg += f"League: {html.escape(m['league'])}\n\n"
        msg += "<b>HANDICAP / SPREADS</b>\n"
        if m["ah"]:
            for ah in m["ah"][:4]:  # Batasi tampilan sampel odds per match
                msg += f"• {html.escape(ah['team'])} {format_point(ah['point'])} @{ah['odds']} ({html.escape(ah['book'])})\n"
        else:
            msg += "-\n"
        msg += "\n<b>OVER / UNDER</b>\n"
        if m["ou"]:
            for ou in m["ou"][:4]:
                msg += f"• {html.escape(ou['side'])} {ou['point']:g} @{ou['odds']} ({html.escape(ou['book'])})\n"
        else:
            msg += "-\n"
        msg += "\n━━━━━━━━━━━━━━\n\n"
    return msg


def analyze_with_bai(matches):
    if not BAI_API_KEY:
        return "❌ BAI_API_KEY tidak diset di GitHub Secrets."
    
    text = ""
    for i, m in enumerate(matches[:15], 1):
        text += f"{i}. {m['home']} vs {m['away']} ({m['league']}) - {m['time']}\n"
        text += "Odds:\n"
        for ah in m["ah"][:2]: text += f" - AH: {ah['team']} {format_point(ah['point'])} @{ah['odds']}\n"
        for ou in m["ou"][:2]: text += f" - O/U: {ou['side']} {ou['point']:g} @{ou['odds']}\n"

    prompt = f"""
You are a professional football analyst. Analyze these match markets and provide the best parlay picks.
Output MUST be direct and follow this exact template:

📋 **RINGKASAN PREDIKSI MATCH NIGHT**
• [Tim Home] vs [Tim Away]
  - Pick: [e.g., Over 2.5 @1.85 or Home -0.5 @1.90]
  - Confidence: 0-100%

🔥 **REKOMENDASI PARLAY (SIAP PASANG)**
1. [Match 1] -> [Pick]
2. [Match 2] -> [Pick]
3. [Match 3] -> [Pick]

DATA:
{text}
"""
    try:
        r = requests.post(
            "https://api.b.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {BAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": BAI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2, "max_tokens": 2500, "stream": False},
            timeout=90
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Gagal analisa AI: {e}"


def main():
    if not ODDS_API_KEY and not ODDSPAPI_API_KEY:
        send_telegram("❌ Kedua API Key Kosong. Set di GitHub Secrets terlebih dahulu.")
        return

    print("Memulai pemindaian pasar...")
    matches = []

    # Ambil Data dari The Odds API
    sports = get_all_soccer_sports()
    if sports:
        for sport in sports[:5]:  # Batasi 5 liga teraktif untuk menghemat kuota request
            for region in ODDS_API_REGIONS:
                data = fetch_odds_the_odds_api(sport, region)
                if isinstance(data, list):
                    for event in data:
                        m = parse_event(event, source="odds-api")
                        if m: matches.append(m)

    # Ambil Data dari OddsPAPI
    oddspapi_events = fetch_odds_oddspapi()
    if isinstance(oddspapi_events, list):
        for event in oddspapi_events:
            m = parse_event(event, source="oddspapi")
            if m: matches.append(m)

    # Penggabungan & Sorting
    matches = merge_matches(matches)
    matches = sorted(matches, key=lambda x: (x["date"], x["time"]))

    if not matches:
        send_telegram("Tidak ada pertandingan malam ini yang lolos penyaringan filter waktu.")
        return

    # Kirim Data Mentah Bursa Pasaran ke Telegram
    raw_msg = build_raw_market_message(matches)
    send_telegram(raw_msg)

    # Kirim Prediksi Jadi Hasil Analisa AI ke Telegram
    print("Menganalisis pasaran menggunakan AI...")
    ai_result = analyze_with_bai(matches)
    ai_msg = "🤖 <b>AI PARLAY PREDICTION REPORT</b>\n\n" + html.escape(ai_result)
    send_telegram(ai_msg)
    print("Selesai!")


if __name__ == "__main__":
    main()
