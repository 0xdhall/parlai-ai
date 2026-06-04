import os
import requests
from datetime import datetime, timedelta

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORTS = [
    "soccer_brazil_campeonato",
    "soccer_brazil_serie_b",
    "soccer_chile_campeonato",
    "soccer_china_superleague",
    "soccer_conmebol_copa_libertadores",
    "soccer_conmebol_copa_sudamericana",
    "soccer_finland_veikkausliiga",
    "soccer_japan_j_league",
    "soccer_norway_eliteserien",
    "soccer_spain_segunda_division",
    "soccer_sweden_allsvenskan",
    "soccer_sweden_superettan",
]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }, timeout=20)

def fetch_odds(sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "spreads,totals",
        "oddsFormat": "decimal"
    }
    r = requests.get(url, params=params, timeout=20)
    return r.json()

def is_match_tonight_to_4am(commence_time):
    if not commence_time:
        return False, None

    match_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    match_wita = match_utc + timedelta(hours=8)

    now_wita = datetime.utcnow() + timedelta(hours=8)

    cutoff_wita = (now_wita + timedelta(days=1)).replace(
        hour=4,
        minute=0,
        second=0,
        microsecond=0
    )

    return now_wita <= match_wita <= cutoff_wita, match_wita

def score_pick(odds, point, market_type):
    score = 50

    if 1.55 <= odds <= 1.85:
        score += 25
    elif 1.86 <= odds <= 2.05:
        score += 15
    elif 1.45 <= odds < 1.55:
        score += 8
    else:
        score -= 10

    if market_type == "totals":
        if point in [2.0, 2.25, 2.5, 2.75, 3.0]:
            score += 15
        elif point in [3.25, 3.5]:
            score += 5
        else:
            score -= 5

    if market_type == "spreads":
        if point in [-0.25, 0, 0.25, 0.5, -0.5, 0.75, -0.75]:
            score += 15
        else:
            score -= 5

    return max(0, min(100, score))

def analyze_event(event):
    picks = []

    allowed, match_wita = is_match_tonight_to_4am(event.get("commence_time"))
    if not allowed:
        return []

    home = event.get("home_team")
    away = event.get("away_team")
    league = event.get("sport_title")
    match_time_text = match_wita.strftime("%H:%M WITA")

    for bookmaker in event.get("bookmakers", []):
        book = bookmaker.get("title")

        for market in bookmaker.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "totals":
                over = next((x for x in outcomes if x.get("name") == "Over"), None)
                under = next((x for x in outcomes if x.get("name") == "Under"), None)

                if over and under:
                    if over["price"] <= under["price"]:
                        score = score_pick(over["price"], over["point"], "totals")
                        picks.append((score, f"Over {over['point']}", over["price"], home, away, league, book, match_time_text))
                    else:
                        score = score_pick(under["price"], under["point"], "totals")
                        picks.append((score, f"Under {under['point']}", under["price"], home, away, league, book, match_time_text))

            if key == "spreads":
                for o in outcomes:
                    odds = o.get("price")
                    point = o.get("point")

                    if odds is None or point is None:
                        continue

                    if 1.45 <= odds <= 2.10:
                        score = score_pick(odds, point, "spreads")
                        pick = f"{o['name']} {point:+}"
                        picks.append((score, pick, odds, home, away, league, book, match_time_text))

    return picks

def remove_duplicates(picks):
    unique = {}

    for p in picks:
        score, bet, odds, home, away, league, book, match_time = p
        key = f"{home}-{away}-{bet}"

        if key not in unique or score > unique[key][0]:
            unique[key] = p

    return list(unique.values())

def main():
    all_picks = []

    for sport in SPORTS:
        try:
            data = fetch_odds(sport)

            if isinstance(data, list):
                for event in data:
                    all_picks.extend(analyze_event(event))

            elif isinstance(data, dict):
                print(f"API response for {sport}: {data}")

        except Exception as e:
            print(f"Error {sport}: {e}")

    all_picks = remove_duplicates(all_picks)
    all_picks = sorted(all_picks, key=lambda x: x[0], reverse=True)[:5]

    if not all_picks:
        send_telegram("Tidak ada match kuat dari malam ini sampai 04:00 WITA.")
        return

    msg = "📊 <b>Parlay AI Signal V3</b>\n\n"
    msg += "Filter: malam ini sampai 04:00 WITA\n"
    msg += "Market: OU + Asian Handicap\n\n"

    for i, pick in enumerate(all_picks, 1):
        score, bet, odds, home, away, league, book, match_time = pick

        if score >= 85:
            label = "🔥 Strong"
        elif score >= 75:
            label = "🟡 Medium"
        else:
            label = "⚪ Watch"

        msg += f"{i}. <b>{home} vs {away}</b>\n"
        msg += f"Jam: {match_time}\n"
        msg += f"League: {league}\n"
        msg += f"Pick: {bet}\n"
        msg += f"Odds: {odds}\n"
        msg += f"Book: {book}\n"
        msg += f"Score: {score}/100 {label}\n\n"

    msg += "🎯 Pilih maksimal 4–5 leg terbaik.\n"
    msg += "⚠️ Scanner market, bukan jaminan menang."

    send_telegram(msg)

if __name__ == "__main__":
    main()
