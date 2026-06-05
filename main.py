import os
import html
import requests
from datetime import datetime, timedelta, timezone

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
BAI_API_KEY = os.getenv("BAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BAI_MODEL = "gpt-5.2"
WITA_OFFSET = 8
SCAN_UNTIL_HOUR_WITA = 10
TELEGRAM_LIMIT = 3500


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
            requests.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "HTML"
                },
                timeout=20
            )


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


def fetch_odds(sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "spreads,totals",
        "oddsFormat": "decimal"
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        return r.json()
    except Exception as e:
        print(f"Error fetch odds {sport}:", e)
        return []


def is_match_now_to_10am(commence_time):
    if not commence_time:
        return False, None

    match_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    match_wita = match_utc + timedelta(hours=WITA_OFFSET)

    now_wita = datetime.now(timezone.utc) + timedelta(hours=WITA_OFFSET)

    if now_wita.hour < SCAN_UNTIL_HOUR_WITA:
        cutoff_wita = now_wita.replace(
            hour=SCAN_UNTIL_HOUR_WITA,
            minute=0,
            second=0,
            microsecond=0
        )
    else:
        cutoff_wita = (now_wita + timedelta(days=1)).replace(
            hour=SCAN_UNTIL_HOUR_WITA,
            minute=0,
            second=0,
            microsecond=0
        )

    return now_wita <= match_wita <= cutoff_wita, match_wita


def format_point(point):
    if point is None:
        return ""
    if point > 0:
        return f"+{point:g}"
    return f"{point:g}"


def parse_event(event):
    allowed, match_wita = is_match_now_to_10am(event.get("commence_time"))
    if not allowed:
        return None

    home = event.get("home_team", "Home")
    away = event.get("away_team", "Away")
    league = event.get("sport_title", "-")

    match = {
        "home": home,
        "away": away,
        "league": league,
        "date": match_wita.strftime("%d %b %Y"),
        "time": match_wita.strftime("%H:%M WITA"),
        "ah": [],
        "ou": []
    }

    seen_ah = set()
    seen_ou = set()

    for bookmaker in event.get("bookmakers", []):
        book = bookmaker.get("title", "-")

        for market in bookmaker.get("markets", []):
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


def build_raw_market_message(matches, total_leagues):
    msg = "📊 <b>MATCH LIST</b>\n"
    msg += f"Filter: Sekarang → {SCAN_UNTIL_HOUR_WITA:02d}:00 WITA\n"
    msg += "Market: Asian Handicap + Over/Under\n"
    msg += f"Total Liga Scan: {total_leagues}\n"
    msg += f"Total Match: {len(matches)}\n\n"

    for m in matches:
        msg += f"📅 <b>{html.escape(m['date'])}</b> | ⏰ <b>{html.escape(m['time'])}</b>\n"
        msg += f"<b>{html.escape(m['home'])} vs {html.escape(m['away'])}</b>\n"
        msg += f"League: {html.escape(m['league'])}\n\n"

        msg += "<b>ASIAN HANDICAP</b>\n"
        if m["ah"]:
            for ah in m["ah"]:
                msg += (
                    f"{html.escape(ah['team'])} "
                    f"{format_point(ah['point'])} "
                    f"@{ah['odds']} "
                    f"({html.escape(ah['book'])})\n"
                )
        else:
            msg += "-\n"

        msg += "\n<b>OVER / UNDER</b>\n"
        if m["ou"]:
            for ou in m["ou"]:
                msg += (
                    f"{html.escape(ou['side'])} "
                    f"{ou['point']:g} "
                    f"@{ou['odds']} "
                    f"({html.escape(ou['book'])})\n"
                )
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

Analyze ONLY the odds data provided.
Do not invent team statistics, injuries, standings, or news.
Focus on:
- Asian Handicap ladder
- Over/Under ladder
- Price distribution
- Market balance
- Safer parlay candidates

Return in Indonesian.

For each match, give:
1. Market Reading
2. Best AH Pick, or Skip AH
3. Best OU Pick, or Skip OU
4. Confidence 0-100
5. Risk: Low / Medium / High
6. Short reason

At the end, give:
- Top 4-5 safest parlay legs
- Avoid list

DATA:
{text}
"""


def analyze_with_bai(matches):
    if not BAI_API_KEY:
        return "❌ BAI_API_KEY belum diset di GitHub Secrets."

    prompt = build_ai_prompt(matches)

    try:
        r = requests.post(
            "https://api.b.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {BAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": BAI_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.25,
                "max_tokens": 4000,
                "stream": False
            },
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

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secret belum lengkap.")
        return

    sports = get_all_soccer_sports()

    if not sports:
        send_telegram("❌ Tidak bisa mengambil daftar liga soccer.")
        return

    matches = []

    for sport in sports:
        data = fetch_odds(sport)

        if not isinstance(data, list):
            continue

        for event in data:
            m = parse_event(event)
            if m:
                matches.append(m)

    matches = sorted(matches, key=lambda x: (x["date"], x["time"], x["league"]))

    if not matches:
        send_telegram(
            f"Tidak ada pertandingan dari sekarang sampai jam "
            f"{SCAN_UNTIL_HOUR_WITA:02d}:00 WITA."
        )
        return

    raw_msg = build_raw_market_message(matches, len(sports))
    send_telegram(raw_msg)

    ai_result = analyze_with_bai(matches)
    ai_msg = "🤖 <b>GPT-5.2 MARKET ANALYSIS</b>\n\n"
    ai_msg += html.escape(ai_result)

    send_telegram(ai_msg)


if __name__ == "__main__":
    main()
