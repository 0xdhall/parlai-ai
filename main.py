import os
import requests
from datetime import datetime, timedelta

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_all_soccer_sports():
    """Dynamically fetch ALL soccer leagues from Odds API"""
    try:
        url = "https://api.the-odds-api.com/v4/sports/"
        params = {"apiKey": ODDS_API_KEY}
        response = requests.get(url, params=params, timeout=20)
        sports = response.json()
        
        # Filter only soccer/football leagues that are active
        soccer_sports = [s["key"] for s in sports if s["group"] == "Soccer" and s["active"]]
        print(f"Found {len(soccer_sports)} soccer leagues from API")
        return soccer_sports
    except Exception as e:
        print(f"Error fetching sports list from API: {e}")
        return []

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
    try:
        r = requests.get(url, params=params, timeout=20)
        return r.json()
    except:
        return []

def is_match_tonight_to_6am(commence_time):
    """Check if match is between now and 6 AM WITA"""
    if not commence_time:
        return False, None

    match_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    match_wita = match_utc + timedelta(hours=8)

    now_wita = datetime.utcnow() + timedelta(hours=8)

    cutoff_wita = (now_wita + timedelta(days=1)).replace(
        hour=6,
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

    allowed, match_wita = is_match_tonight_to_6am(event.get("commence_time"))
    if not allowed:
        return []

    home = event.get("home_team")
    away = event.get("away_team")
    league = event.get("sport_title")
    
    # Format: 📅 5 Jun 2025 | ⏰ 22:30 WITA
    match_time_text = match_wita.strftime("%H:%M WITA")
    match_date_text = match_wita.strftime("%d %b %Y")

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
                        picks.append((score, f"Over {over['point']}", over["price"], home, away, league, book, match_time_text, match_date_text))
                    else:
                        score = score_pick(under["price"], under["point"], "totals")
                        picks.append((score, f"Under {under['point']}", under["price"], home, away, league, book, match_time_text, match_date_text))

            if key == "spreads":
                for o in outcomes:
                    odds = o.get("price")
                    point = o.get("point")

                    if odds is None or point is None:
                        continue

                    if 1.45 <= odds <= 2.10:
                        score = score_pick(odds, point, "spreads")
                        pick = f"{o['name']} {point:+}"
                        picks.append((score, pick, odds, home, away, league, book, match_time_text, match_date_text))

    return picks

def remove_duplicates(picks):
    unique = {}

    for p in picks:
        score, bet, odds, home, away, league, book, match_time, match_date = p
        key = f"{home}-{away}-{bet}"

        if key not in unique or score > unique[key][0]:
            unique[key] = p

    return list(unique.values())

def main():
    # Fetch ALL soccer sports dynamically from API
    sports = get_all_soccer_sports()
    
    if not sports:
        send_telegram("❌ Error: Tidak bisa fetch daftar liga dari API Odds")
        return
    
    print(f"Scanning {len(sports)} soccer leagues...")
    
    all_picks = []
    match_count = 0

    for sport in sports:
        try:
            data = fetch_odds(sport)

            if isinstance(data, list):
                for event in data:
                    picks = analyze_event(event)
                    if picks:
                        match_count += 1
                    all_picks.extend(picks)

        except Exception as e:
            print(f"Error {sport}: {e}")

    all_picks = remove_duplicates(all_picks)
    all_picks = sorted(all_picks, key=lambda x: x[0], reverse=True)[:20]

    if not all_picks:
        send_telegram("Tidak ada match kuat dari sekarang sampai jam 06:00 WITA.")
        return

    msg = "📊 <b>Parlay AI Signal V3</b>\n\n"
    msg += "Filter: Sekarang sampai 06:00 WITA\n"
    msg += "Market: OU + Asian Handicap\n"
    msg += f"Total Scan: {len(sports)} Liga Soccer\n"
    msg += f"Total Match Malam: {match_count}\n\n"

    for i, pick in enumerate(all_picks, 1):
        score, bet, odds, home, away, league, book, match_time, match_date = pick

        if score >= 85:
            label = "🔥 Strong"
        elif score >= 75:
            label = "🟡 Medium"
        else:
            label = "⚪ Watch"

        msg += f"{i}. <b>{home} vs {away}</b>\n"
        msg += f"📅 {match_date} | ⏰ {match_time}\n"
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
