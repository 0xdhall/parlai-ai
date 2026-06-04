import os
import requests
from datetime import datetime, timedelta

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORTS = [
    "soccer_brazil_campeonato",
    "soccer_japan_j_league",
    "soccer_sweden_allsvenskan",
    "soccer_sweden_superettan",
    "soccer_norway_eliteserien",
    "soccer_finland_veikkausliiga",
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

def score_pick(odds, point, market_type):
    score = 50

    if 1.55 <= odds <= 1.85:
        score += 25
    elif 1.86 <= odds <= 2.05:
        score += 15
    elif odds < 1.55:
        score += 5
    else:
        score -= 10

    if market_type == "totals":
        if point in [2.0, 2.25, 2.5, 2.75, 3.0]:
            score += 15
        else:
            score += 5

    if market_type == "spreads":
        if point in [-0.25, 0, 0.25, 0.5, -0.5]:
            score += 15
        else:
            score -= 5

    return max(0, min(100, score))

def analyze_event(event):
    picks = []

    home = event.get("home_team")
    away = event.get("away_team")
    league = event.get("sport_title")

    commence_time = event.get("commence_time")

    if commence_time:
        match_time = datetime.fromisoformat(
            commence_time.replace("Z", "+00:00")
        )

        match_time_wita = match_time + timedelta(hours=8)
        now_wita = datetime.utcnow() + timedelta(hours=8)

        tomorrow_4am = (
            now_wita + timedelta(days=1)
        ).replace(
            hour=4,
            minute=0,
            second=0,
            microsecond=0
        )

        if match_time_wita < now_wita:
            return []

        if match_time_wita > tomorrow_4am:
            return []

    for bookmaker in event.get("bookmakers", []):
        book = bookmaker.get("title")

        for market in bookmaker.get("markets", []):
            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "totals":
                over = next((x for x in outcomes if x["name"] == "Over"), None)
                under = next((x for x in outcomes if x["name"] == "Under"), None)

                if over and under:
                    if over["price"] <= under["price"]:
                        score = score_pick(over["price"], over["point"], "totals")
                        picks.append((score, f"Over {over['point']}", over["price"], home, away, league, book))
                    else:
                        score = score_pick(under["price"], under["point"], "totals")
                        picks.append((score, f"Under {under['point']}", under["price"], home, away, league, book))

            if key == "spreads":
                for o in outcomes:
                    odds = o["price"]
                    point = o["point"]

                    if 1.50 <= odds <= 2.10:
                        score = score_pick(odds, point, "spreads")
                        pick = f"{o['name']} {point:+}"
                        picks.append((score, pick, odds, home, away, league, book))

    return picks

def remove_duplicates(picks):
    unique = {}

    for p in picks:
        score, bet, odds, home, away, league, book = p
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
        send_telegram("Tidak ada pick kuat dari sekarang sampai jam 04:00 WITA.")
        return

    msg = "📊 <b>Parlay AI Signal V2</b>\n\n"
    msg += "Filter waktu: sekarang sampai 04:00 WITA\n"
    msg += "Top kandidat OU + Asian Handicap:\n\n"

    for i, pick in enumerate(all_picks, 1):
        score, bet, odds, home, away, league, book = pick

        if score >= 85:
            label = "🔥 Strong"
        elif score >= 75:
            label = "🟡 Medium"
        else:
            label = "⚪ Watch"

        msg += f"{i}. <b>{home} vs {away}</b>\n"
        msg += f"League: {league}\n"
        msg += f"Pick: {bet}\n"
        msg += f"Odds: {odds}\n"
        msg += f"Book: {book}\n"
        msg += f"Score: {score}/100 {label}\n\n"

    msg += "🎯 Rekomendasi: ambil maksimal 4–5 leg terbaik.\n"
    msg += "⚠️ Ini scanner market, bukan jaminan menang."

    send_telegram(msg)

if __name__ == "__main__":
    main()
