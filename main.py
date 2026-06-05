import os
import html
import requests
from datetime import datetime, timedelta, timezone

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
ODDSPAPI_API_KEY = os.getenv("ODDSPAPI_API_KEY")
BAI_API_KEY = os.getenv("BAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BAI_MODEL = "gpt-5.2"
WITA_OFFSET = 8
TELEGRAM_LIMIT = 3500

# KUNCI REGION GLOBAL: Mengambil pasaran dari bandar judi seluruh dunia
ODDS_API_REGIONS = ["eu", "us", "uk", "au"]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

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
                print(f"Gagal mengirim Telegram chunk: {e}")


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
        print("Error get sports:", e)
        return []


def fetch_odds_the_odds_api(sport, region):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": region,
        "markets": "spreads,totals",
        "oddsFormat": "decimal"
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        return r.json()
    except Exception as e:
        print(f"Error fetch odds {sport} (region={region}):", e)
        return []


def fetch_odds_oddspapi():
    if not ODDSPAPI_API_KEY:
        print("OddsPAPI key not set, skipping OddsPAPI fetch")
        return []

    try:
        url = "https://api.oddspapi.io/v4/tournaments"
        params = {"apiKey": ODDSPAPI_API_KEY}
        r = requests.get(url, params=params, timeout=20)
        tournaments = r.json()

        if not isinstance(tournaments, list):
            return []

        active_tournaments = [
            t for t in tournaments
            if t.get("sport_id") == 10 and t.get("active") is not False
        ]

        # Scan maksimal 100 turnamen sepak bola teraktif di dunia
        tournament_ids = [str(t["id"]) for t in active_tournaments[:100]]  

        if not tournament_ids:
            print("No active tournaments found on OddsPAPI")
            return []

        print(f"FETCH MAXIMAL: Mendeteksi {len(tournament_ids)} turnamen global di OddsPAPI...")

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
            except Exception as e:
                print(f"Error fetching OddsPAPI tournament {tournament_id}: {e}")
                continue

        return all_fixtures

    except Exception as e:
        print("Error OddsPAPI global fetch:", e)
        return []


def is_match_now_to_6am(commence_time):
    if not commence_time:
        return False, None

    try:
        if isinstance(commence_time, str):
            match_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        else:
            match_utc = datetime.fromtimestamp(commence_time, tz=timezone.utc)
    except:
        return False, None

    now_utc = datetime.now(timezone.utc)
    
    # Toleransi mundur 6 jam agar pasaran yang sedang bersiap/baru kickoff tidak hilang
    start_scan_utc = now_utc - timedelta(hours=6)
    
    # Jendela scan 18 jam ke depan agar semua match malam s/d subuh terjaring total tanpa terpotong zona waktu API
    cutoff_utc = now_utc + timedelta(hours=18)

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
    if source == "odds-api":
        commence_time = event.get("commence_time")
    else:  
        commence_time = event.get("start_time") or event.get("commence_time")

    allowed, match_wita = is_match_now_to_6am(commence_time)
    if not allowed:
        return None

    home = event.get("home_team", "Home").strip()
    away = event.get("away_team", "Away").strip()
    league = event.get("sport_title") or event.get("tournament_name") or "-"

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

    seen_ah = set()
    seen_ou = set()

    bookmakers = event.get("bookmakers", [])
    for bookmaker in bookmakers:
        book = bookmaker.get("title", "-")
        markets = bookmaker.get("markets", [])
        for market in markets:
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "spreads":
                for o in outcomes:
                    name = o.get("name")
                    point = o.get("point")
                    price = o.get("price")

                    if name is None or point is None or price is None:
                        continue

                    item_key = (name, point, price)
                    if item_key in seen_ah:
                        continue
                    seen_ah.add(item_key)

                    match["ah"].append({
                        "team": name,
                        "point": point,
                        "odds": price,
                        "book": book
                    })

            elif key == "totals":
                for o in outcomes:
                    name = o.get("name")
                    point = o.get("point")
                    price = o.get("price")

                    if name is None or point is None or price is None:
                        continue

                    item_key = (name, point, price)
                    if item_key in seen_ou:
                        continue
                    seen_ou.add(item_key)

                    match["ou"].append({
                        "side": name,
                        "point": point,
                        "odds": price,
                        "book": book
                    })

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


def build_raw_market_message(matches, total_leagues):
    msg = "📊 <b>TONIGHT PARLAY MATCH LIST (MAX GLOBAL SCAN)</b>\n"
    msg += "Target Rentang: Fokus Malam ini s/d Besok Subuh\n"
    msg += f"Total Match Terdeteksi: {len(matches)}\n\n"

    for m in matches:
        msg += f"📅 <b>{html.escape(m['date'])}</b> | ⏰ <b>{html.escape(m['time'])}</b>\n"
        msg += f"<b>{html.escape(m['home'])} vs {html.escape(m['away'])}</b>\n"
        msg += f"League: {html.escape(m['league'])}\n\n"

        msg += "<b>ASIAN HANDICAP</b>\n"
        if m["ah"]:
            for ah in m["ah"]:
                msg += f"{html.escape(ah['team'])} {format_point(ah['point'])} @{ah['odds']} ({html.escape(ah['book'])})\n"
        else:
            msg += "-\n"

        msg += "\n<b>OVER / UNDER</b>\n"
        if m["ou"]:
            for ou in m["ou"]:
                msg += f"{html.escape(ou['side'])} {ou['point']:g} @{ou['odds']} ({html.escape(ou['book'])})\n"
        else:
            msg += "-\n"

        msg += "\n━━━━━━━━━━━━━━\n\n"

    return msg


def build_ai_prompt(matches):
    text = ""
    for i, m in enumerate(matches, 1):
        text += f"{i}. {m['home']} vs {m['away']}\n"
        text += f"League: {m['league']}\n"
        text += f"Time: {m['date']} {m['time']}\n"
        text += "Asian Handicap:\n"
        for ah in m["ah"]:
            text += f"- {ah['team']} {format_point(ah['point'])} @{ah['odds']} ({ah['book']})\n"
        text += "Over/Under:\n"
        for ou in m["ou"]:
            text += f"- {ou['side']} {ou['point']:g} @{ou['odds']} ({ou['book']})\n"
        text += "\n"

    return f"""
You are a professional Asian Handicap and Over/Under football market reader.
Analyze ONLY the odds data provided. Do not invent info.

CRITICAL INSTRUCTION FOR OUTPUT FORMAT:
Your response MUST be extremely brief, direct, and easy to read on Telegram. 
Do not write long paragraphs. Use the exact Indonesian template below.

--- TEMPLATE OUTPUT ---
📋 **RINGKASAN PREDIKSI MATCH NIGHT (MAX SCAN)**
• **[Tim Home] vs [Tim Away]**
  - Pick Utama: [Tulis taruhan terbaik, misal: Under 2.5 @1.50 atau Juventude +0.25 @1.80]
  - Confidence: [0-100]% | Risiko: [Low/Medium/High]

🔥 **REKOMENDASI PARLAY (SIAP PASANG)**
1. [Match 1] -> [Pick] @[Odds]
2. [Match 2] -> [Pick] @[Odds]
3. [Match 3] -> [Pick] @[Odds]

❌ **AVOID LIST**
- [Match] (Alasan singkat)
--- END TEMPLATE ---

DATA:
{text}
"""


def analyze_with_bai(matches):
    if not BAI_API_KEY:
        return "❌ BAI_API_KEY belum diset."

    prompt = build_ai_prompt(matches)
    try:
        r = requests.post(
            "https://api.b.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {BAI_API_KEY}", "Content-Type": "application/json"},
            json={"model": BAI_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.25, "max_tokens": 3000, "stream": False},
            timeout=120
        )
        data = r.json()
        if "choices" not in data:
            return f"❌ BAI Error:\n{data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Error BAI API: {e}"


def main():
    if not ODDS_API_KEY:
        send_telegram("❌ ODDS_API_KEY belum diset.")
        return

    print("Starting mega scraper...")
    sports = get_all_soccer_sports()

    if not sports:
        send_telegram("❌ Gagal mengambil daftar liga.")
        return

    matches = []
    
    # 1. Tarik Data dari The Odds API (4 Region Terbesar Dunia)
    for sport in sports:
        for region in ODDS_API_REGIONS:
            data = fetch_odds_the_odds_api(sport, region)
            if not isinstance(data, list):
                continue
            for event in data:
                m = parse_event(event, source="odds-api")
                if m:
                    matches.append(m)

    # 2. Tarik Data dari OddsPAPI (Global Dunia)
    oddspapi_events = fetch_odds_oddspapi()
    if oddspapi_events:
        for event in oddspapi_events:
            m = parse_event(event, source="oddspapi")
            if m:
                matches.append(m)

    # 3. Penggabungan Pasaran & Pembersihan Duplikasi
    matches = merge_matches(matches)
    matches = sorted(matches, key=lambda x: (x["date"], x["time"]))

    # Batasan potong dinonaktifkan (Semua match malam ini dikirim utuh)

    if not matches:
        send_telegram("Tidak ada pertandingan dalam rentang waktu malam ini yang lolos penyaringan.")
        return

    raw_msg = build_raw_market_message(matches, len(sports))
    send_telegram(raw_msg)

    print("Analyzing with AI...")
    ai_result = analyze_with_bai(matches)
    ai_msg = "🤖 <b>GPT-5.2 TONIGHT PARLAY ANALYSIS (MAX SCAN)</b>\n\n"
    ai_msg += html.escape(ai_result)
    send_telegram(ai_msg)

    print("Done!")


if __name__ == "__main__":
    main()
