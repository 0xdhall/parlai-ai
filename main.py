[6/4/2026 7:36 PM] 4ng: import os
import requests

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SPORTS = [
    "soccer_brazil_campeonato",
    "soccer_japan_j_league",
    "soccer_sweden_allsvenskan",
]

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
    )

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

def analyze_event(event):
    picks = []

    home = event.get("home_team")
    away = event.get("away_team")
    league = event.get("sport_title")

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):

            key = market.get("key")
            outcomes = market.get("outcomes", [])

            if key == "totals":

                over = next(
                    (x for x in outcomes if x["name"] == "Over"),
                    None
                )

                under = next(
                    (x for x in outcomes if x["name"] == "Under"),
                    None
                )

                if over and under:

                    if over["price"] < under["price"]:
                        score = int(100 - (over["price"] * 10))

                        picks.append(
                            (
                                score,
                                f"Over {over['point']}",
                                over["price"],
                                home,
                                away,
                                league
                            )
                        )

                    else:
                        score = int(100 - (under["price"] * 10))

                        picks.append(
                            (
                                score,
                                f"Under {under['point']}",
                                under["price"],
                                home,
                                away,
                                league
                            )
                        )

            if key == "spreads":

                for o in outcomes:

                    if 1.55 <= o["price"] <= 2.05:

                        score = int(100 - (o["price"] * 10))

                        pick = f"{o['name']} {o['point']:+}"

                        picks.append(
                            (
                                score,
                                pick,
                                o["price"],
                                home,
                                away,
                                league
                            )
                        )

    return picks

def main():

    all_picks = []

    for sport in SPORTS:

        try:

            data = fetch_odds(sport)

            if isinstance(data, list):

                for event in data:
                    all_picks.extend(
                        analyze_event(event)
                    )

        except Exception as e:
            print(f"Error {sport}: {e}")

    all_picks = sorted(
        all_picks,
        reverse=True
    )[:8]

    if not all_picks:

        send_telegram(
            "Tidak ada pick kuat hari ini."
        )

        return

    msg = "📊 <b>Parlay AI Signal</b>\n\n"
    msg += "Top kandidat OU + Asian Handicap:\n\n"

    for i, pick in enumerate(all_picks, 1):

        score, bet, odds, home, away, league = pick

        msg += f"{i}. <b>{home} vs {away}</b>\n"
        msg += f"League: {league}\n"
        msg += f"Pick: {bet}\n"
        msg += f"Odds: {odds}\n"
        msg += f"Score: {score}/100\n\n"
        msg += (
        "⚠️ Ini scanner market, "
        "bukan jaminan menang. "
        "Pakai untuk filter parlay 4–5 leg."
    )

    send_telegram(msg)

if name == "__main__":
    main()
