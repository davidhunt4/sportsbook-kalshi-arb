from bolt_utils import start_bolt_stream, stop_bolt_stream
from kalshi_utils import get_kevents, start_kalshi_stream, stop_kalshi_stream
import argparse
import asyncio
from dotenv import load_dotenv
import os
from pathlib import Path
from datetime import datetime
import pytz

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
TRADE_LOG_PATH = os.getenv('TRADE_LOG_PATH', str(BASE_DIR / 'trade_log.csv'))
WARMUP_SECONDS = float(os.getenv('WARMUP_SECONDS', '10'))


def get_implied_prob(odds1: float, odds2: float):
    """Convert american odds to implied probability"""
    odds1 = float(odds1)
    odds2 = float(odds2)
    prob1 = 100 / (odds1 + 100) if odds1 > 0 else abs(odds1) / (abs(odds1) + 100)
    prob2 = 100 / (odds2 + 100) if odds2 > 0 else abs(odds2) / (abs(odds2) + 100)
    total = prob1 + prob2
    return prob1 / total, prob2 / total


def kdate_to_bdate(kdate: str) -> str:
    """Convert Kalshi date format (26MAR05) to Bolt date format (2026-03-05)"""
    months = {
        'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'
    }
    year = kdate[:2]
    month_str = kdate[2:5]
    day = kdate[5:]
    return f"20{year}-{months[month_str]}-{day}"


bteam_to_klocation = {
    'Atlanta Hawks': 'Atlanta',
    'Boston Celtics': 'Boston',
    'Brooklyn Nets': 'Brooklyn',
    'Charlotte Hornets': 'Charlotte',
    'Chicago Bulls': 'Chicago',
    'Cleveland Cavaliers': 'Cleveland',
    'Dallas Mavericks': 'Dallas',
    'Denver Nuggets': 'Denver',
    'Detroit Pistons': 'Detroit',
    'Golden State Warriors': 'Golden State',
    'Houston Rockets': 'Houston',
    'Indiana Pacers': 'Indiana',
    'Los Angeles Clippers': 'Los Angeles C',
    'LA Clippers': 'Los Angeles C',
    'Los Angeles Lakers': 'Los Angeles L',
    'LA Lakers': 'Los Angeles L',
    'Memphis Grizzlies': 'Memphis',
    'Miami Heat': 'Miami',
    'Milwaukee Bucks': 'Milwaukee',
    'Minnesota Timberwolves': 'Minnesota',
    'New Orleans Pelicans': 'New Orleans',
    'New York Knicks': 'New York',
    'Oklahoma City Thunder': 'Oklahoma City',
    'Orlando Magic': 'Orlando',
    'Philadelphia 76ers': 'Philadelphia',
    'Phoenix Suns': 'Phoenix',
    'Portland Trail Blazers': 'Portland',
    'Sacramento Kings': 'Sacramento',
    'San Antonio Spurs': 'San Antonio',
    'Toronto Raptors': 'Toronto',
    'Utah Jazz': 'Utah',
    'Washington Wizards': 'Washington',
    #### MLB ####
    'Arizona Diamondbacks': 'Arizona',
    'Atlanta Braves': 'Atlanta',
    'Baltimore Orioles': 'Baltimore',
    'Boston Red Sox': 'Boston',
    'Chicago Cubs': 'Chicago C',
    'Chicago White Sox': 'Chicago WS',
    'Cincinnati Reds': 'Cincinnati',
    'Cleveland Guardians': 'Cleveland',
    'Colorado Rockies': 'Colorado',
    'Detroit Tigers': 'Detroit',
    'Houston Astros': 'Houston',
    'Kansas City Royals': 'Kansas City',
    'Los Angeles Angels': 'Los Angeles A',
    'Los Angeles Dodgers': 'Los Angeles D',
    'Miami Marlins': 'Miami',
    'Milwaukee Brewers': 'Milwaukee',
    'Minnesota Twins': 'Minnesota',
    'New York Mets': 'New York M',
    'New York Yankees': 'New York Y',
    'Oakland Athletics': 'Oakland',
    'Philadelphia Phillies': 'Philadelphia',
    'Pittsburgh Pirates': 'Pittsburgh',
    'San Diego Padres': 'San Diego',
    'San Francisco Giants': 'San Francisco',
    'Seattle Mariners': 'Seattle',
    'St Louis Cardinals': 'St. Louis',
    'Tampa Bay Rays': 'Tampa Bay',
    'Texas Rangers': 'Texas',
    'Toronto Blue Jays': 'Toronto',
    'Washington Nationals': 'Washington',
    #### NHL ####
    'Anaheim Ducks': 'ANA Ducks',
    'Boston Bruins': 'BOS Bruins',
    'Buffalo Sabres': 'BUF Sabres',
    'Calgary Flames': 'CGY Flames',
    'Carolina Hurricanes': 'CAR Hurricanes',
    'Chicago Blackhawks': 'CHI Blackhawks',
    'Colorado Avalanche': 'COL Avalanche',
    'Columbus Blue Jackets': 'CBJ Blue Jackets',
    'Dallas Stars': 'DAL Stars',
    'Detroit Red Wings': 'DET Red Wings',
    'Edmonton Oilers': 'EDM Oilers',
    'Florida Panthers': 'FLA Panthers',
    'Los Angeles Kings': 'LA Kings',
    'Minnesota Wild': 'MIN Wild',
    'Montreal Canadiens': 'MTL Canadiens',
    'Nashville Predators': 'NSH Predators',
    'New Jersey Devils': 'NJ Devils',
    'New York Islanders': 'NYI Islanders',
    'New York Rangers': 'NYR Rangers',
    'Ottawa Senators': 'OTT Senators',
    'Philadelphia Flyers': 'PHI Flyers',
    'Pittsburgh Penguins': 'PIT Penguins',
    'San Jose Sharks': 'SJ Sharks',
    'Seattle Kraken': 'SEA Kraken',
    'St Louis Blues': 'STL Blues',
    'Tampa Bay Lightning': 'TB Lightning',
    'Toronto Maple Leafs': 'TOR Maple Leafs',
    'Vancouver Canucks': 'VAN Canucks',
    'Vegas Golden Knights': 'VGK Golden Knights',
    'Washington Capitals': 'WSH Capitals',
    'Winnipeg Jets': 'WPG Jets',
    'Utah Mammoth': 'UTA Mammoth'
}


def compute_fees(odds, contracts):
    """Compute fees based on odds. Placeholder for now."""
    return round(0.07 * odds * (1 - odds) * contracts, 2)


async def main(pregame_only: bool = True):
    if not os.getenv('BOLT_API_KEY'):
        raise RuntimeError('Missing BOLT_API_KEY. Set it in environment or .env on EC2.')
    if not os.getenv('KALSHI_PROD_API_KEY'):
        raise RuntimeError('Missing KALSHI_PROD_API_KEY. Set it in environment or .env on EC2.')

    et = pytz.timezone('America/New_York')

    # ── Shared state ──────────────────────────────────────────────────────────
    # Bolt: per-sportsbook odds and averaged odds, keyed by game_key tuple
    bolt_per_sportsbook = {}   # game_key -> {sportsbook: {home_prob, away_prob}}
    bolt_averages = {}         # game_key -> {home_prob, away_prob, sportsbook: 'average'}
    bolt_id_to_key = {}        # bolt game_id -> game_key

    # Kalshi: best bid/ask per market, keyed by game_key tuple
    kalshi_cache = {}          # game_key -> {home_odds_ask, away_odds_ask, home_odds_bid, away_odds_bid, home_ticker, away_ticker}
    kalshi_ticker_to_game = {} # market_ticker -> (game_key, 'home'|'away')

    positions = set()          # set of tickers we currently hold
    started_game_keys = set()  # game keys evicted because game has started (blacklist)

    # ── Single-game arb check ─────────────────────────────────────────────────
    def check_game(game_key):
        """Compare a single game's Bolt average vs Kalshi prices and log signals."""
        if game_key not in bolt_averages or game_key not in kalshi_cache:
            return

        bolt_info = bolt_averages[game_key]
        kalshi_info = kalshi_cache[game_key]

        if not kalshi_info.get('home_odds_ask') or not kalshi_info.get('away_odds_ask'):
            return

        home_diff_buy = bolt_info['home_prob'] - kalshi_info['home_odds_ask']
        away_diff_buy = bolt_info['away_prob'] - kalshi_info['away_odds_ask']
        home_diff_sell = bolt_info['home_prob'] - kalshi_info['home_odds_bid']
        away_diff_sell = bolt_info['away_prob'] - kalshi_info['away_odds_bid']

        try:
            game_time = datetime.strptime(bolt_info['when'], "%Y-%m-%d, %I:%M %p")
            is_pregame = game_time > datetime.now(et).replace(tzinfo=None)
        except (KeyError, ValueError):
            is_pregame = True  # default to pregame if time is unavailable

        with open(TRADE_LOG_PATH, 'a') as f:
            kalship_home_fees = compute_fees(kalshi_info['home_odds_ask'], 1)
            boltp_home_fees = compute_fees(bolt_info['home_prob'], 1)
            kalship_away_fees = compute_fees(kalshi_info['away_odds_ask'], 1)
            boltp_away_fees = compute_fees(bolt_info['away_prob'], 1)

            if home_diff_buy > (kalship_home_fees + boltp_home_fees): # fees estimated as fees on kalshi ask plus fees on the estimated sell price, which is the bolt implied probability
                print(f"\n{game_key[2]}: {game_key[0]} vs {game_key[1]} in {game_key[3]}")
                print(f"  Bolt (average): Home {bolt_info['home_prob']:.4f}")
                print(f"  Kalshi: Home {kalshi_info['home_odds_ask']:.4f}")
                if kalshi_info['home_ticker'] not in positions:
                    f.write(f"{game_key[2]}, {game_key[3]}, {game_key[0]}, {game_key[1]}, BUY, {kalshi_info['home_ticker']}, {kalshi_info['home_odds_ask']:.4f}, {bolt_info['home_prob']:.4f}, average, {kalship_home_fees}, {is_pregame}, {datetime.now().isoformat()}\n")
                    positions.add(kalshi_info['home_ticker'])

            if away_diff_buy > (kalship_away_fees + boltp_away_fees):
                print(f"\n{game_key[2]}: {game_key[0]} vs {game_key[1]} in {game_key[3]}")
                print(f"  Bolt (average): Away {bolt_info['away_prob']:.4f}")
                print(f"  Kalshi: Away {kalshi_info['away_odds_ask']:.4f}")
                if kalshi_info['away_ticker'] not in positions:
                    f.write(f"{game_key[2]}, {game_key[3]}, {game_key[0]}, {game_key[1]}, BUY, {kalshi_info['away_ticker']}, {kalshi_info['away_odds_ask']:.4f}, {bolt_info['away_prob']:.4f}, average, {kalship_away_fees}, {is_pregame}, {datetime.now().isoformat()}\n")
                    positions.add(kalshi_info['away_ticker'])

            if home_diff_sell < 0.005 and kalshi_info['home_ticker'] in positions:
                f.write(f"{game_key[2]}, {game_key[3]}, {game_key[0]}, {game_key[1]}, SELL, {kalshi_info['home_ticker']}, {kalshi_info['home_odds_bid']:.4f}, {bolt_info['home_prob']:.4f}, average, {kalship_home_fees}, {is_pregame}, {datetime.now().isoformat()}\n")
                positions.discard(kalshi_info['home_ticker'])

            if away_diff_sell < 0.005 and kalshi_info['away_ticker'] in positions:
                f.write(f"{game_key[2]}, {game_key[3]}, {game_key[0]}, {game_key[1]}, SELL, {kalshi_info['away_ticker']}, {kalshi_info['away_odds_bid']:.4f}, {bolt_info['away_prob']:.4f}, average, {kalship_away_fees}, {is_pregame}, {datetime.now().isoformat()}\n")
                positions.discard(kalshi_info['away_ticker'])

    # ── Bolt callbacks ────────────────────────────────────────────────────────
    async def on_bolt_update(game_id, sportsbook, game_data):
        """Fired by BoltOddsManager for initial_state, game_update, and line_update."""
        home_team_raw = game_data.get('home_team')
        away_team_raw = game_data.get('away_team')
        if not home_team_raw or not away_team_raw:
            return

        try:
            home_team = bteam_to_klocation[home_team_raw]
            away_team = bteam_to_klocation[away_team_raw]
        except KeyError:
            return

        try:
            when_str = game_data['info']['when']
            game_time = datetime.strptime(when_str, "%Y-%m-%d, %I:%M %p")
        except (KeyError, ValueError):
            return

        date = when_str.split(',')[0]
        league = game_data.get('sport', '')
        game_key = (home_team, away_team, date, league)

        if pregame_only:
            # Fast exit if already blacklisted
            if game_key in started_game_keys:
                return

            # Game has started — evict from caches and blacklist
            if game_time <= datetime.now(et).replace(tzinfo=None):
                bolt_per_sportsbook.pop(game_key, None)
                bolt_averages.pop(game_key, None)
                started_game_keys.add(game_key)
                return

        try:
            home_line = game_data['outcomes'][f'{home_team_raw} Moneyline']['odds']
            away_line = game_data['outcomes'][f'{away_team_raw} Moneyline']['odds']
        except KeyError:
            return
        if home_line is None or away_line is None or home_line == '' or away_line == '':
            return

        bolt_id_to_key[game_id] = game_key

        home_prob, away_prob = get_implied_prob(home_line, away_line)

        if game_key not in bolt_per_sportsbook:
            bolt_per_sportsbook[game_key] = {}
        bolt_per_sportsbook[game_key][sportsbook] = {
            'home_prob': home_prob,
            'away_prob': away_prob,
        }

        # Recompute average across all sportsbooks for this game
        book_data = bolt_per_sportsbook[game_key]
        avg_home = sum(v['home_prob'] for v in book_data.values()) / len(book_data)
        avg_away = sum(v['away_prob'] for v in book_data.values()) / len(book_data)
        bolt_averages[game_key] = {
            'home_prob': avg_home,
            'away_prob': avg_away,
            'sportsbook': 'average',
            'when': when_str,
        }

        check_game(game_key)

    async def on_bolt_remove(game_id, sportsbook):
        """Fired when Bolt removes a game (game_removed / sport_clear / book_clear)."""
        game_key = bolt_id_to_key.get(game_id)
        if game_key is None:
            return

        if game_key in bolt_per_sportsbook:
            bolt_per_sportsbook[game_key].pop(sportsbook, None)
            if not bolt_per_sportsbook[game_key]:
                del bolt_per_sportsbook[game_key]
                bolt_averages.pop(game_key, None)
                bolt_id_to_key.pop(game_id, None)
            else:
                book_data = bolt_per_sportsbook[game_key]
                avg_home = sum(v['home_prob'] for v in book_data.values()) / len(book_data)
                avg_away = sum(v['away_prob'] for v in book_data.values()) / len(book_data)
                bolt_averages[game_key] = {
                    'home_prob': avg_home,
                    'away_prob': avg_away,
                    'sportsbook': 'average',
                }

    # ── Started-games cleanup ─────────────────────────────────────────────────
    async def cleanup_started_games():
        """Hourly sweep to remove old entries from the started_game_keys blacklist.
        Keeps anything within 2 days of today to handle games that play past midnight.
        """
        while True:
            await asyncio.sleep(3600)
            today = datetime.now(et).date()
            stale = {k for k in started_game_keys
                     if (today - datetime.strptime(k[2], "%Y-%m-%d").date()).days > 2}
            started_game_keys -= stale
            if stale:
                print(f"[CLEANUP] Removed {len(stale)} stale started-game keys")

    # ── Kalshi callback ───────────────────────────────────────────────────────
    async def on_kalshi_update(ticker_msg):
        """Fired by KalshiOddsManager for every 'ticker' WebSocket message."""
        market_ticker = ticker_msg.get('market_ticker')
        if not market_ticker or market_ticker not in kalshi_ticker_to_game:
            return

        game_key, side = kalshi_ticker_to_game[market_ticker]
        if game_key not in kalshi_cache:
            return

        entry = kalshi_cache[game_key]
        updated = False

        yes_bid = ticker_msg.get('yes_bid_dollars')
        yes_ask = ticker_msg.get('yes_ask_dollars')

        if yes_bid is not None:
            try:
                val = float(yes_bid)
                entry['home_odds_bid' if side == 'home' else 'away_odds_bid'] = val
                updated = True
            except (ValueError, TypeError):
                pass

        if yes_ask is not None:
            try:
                val = float(yes_ask)
                entry['home_odds_ask' if side == 'home' else 'away_odds_ask'] = val
                updated = True
            except (ValueError, TypeError):
                pass

        if updated:
            check_game(game_key)

    # ── Bootstrap Kalshi state via REST ───────────────────────────────────────
    try:
        kevents = get_kevents()
    except Exception as e:
        print(f"[ERROR] Initial Kalshi fetch failed: {e}")
        kevents = []

    print(f"Loaded {len(kevents)} Kalshi events via REST")
    for event in kevents:
        try:
            swap = 0
            home_team = event['markets'][0]['yes_sub_title']
            away_team = event['markets'][1]['yes_sub_title']
            home_team_odds_ask = float(event['markets'][0]['yes_ask_dollars'])
            away_team_odds_ask = float(event['markets'][1]['yes_ask_dollars'])
            home_team_odds_bid = float(event['markets'][0]['yes_bid_dollars'])
            away_team_odds_bid = float(event['markets'][1]['yes_bid_dollars'])
            date = kdate_to_bdate(event['markets'][1]['event_ticker'][10:17])
            league = event['event_ticker'][2:5]

            if ' at ' in event['title']:
                home_in_title = event['title'].split(' at ')[1]
            else:
                home_in_title = event['title'].split(' vs ')[1]

            if home_team != home_in_title:
                home_team, away_team = away_team, home_team
                home_team_odds_ask, away_team_odds_ask = away_team_odds_ask, home_team_odds_ask
                home_team_odds_bid, away_team_odds_bid = away_team_odds_bid, home_team_odds_bid
                swap = 1

            game_key = (home_team, away_team, date, league)
            home_ticker = event['markets'][swap]['ticker']
            away_ticker = event['markets'][1 - swap]['ticker']

            kalshi_cache[game_key] = {
                'title': event['title'],
                'home_odds_ask': home_team_odds_ask,
                'away_odds_ask': away_team_odds_ask,
                'home_odds_bid': home_team_odds_bid,
                'away_odds_bid': away_team_odds_bid,
                'home_ticker': home_ticker,
                'away_ticker': away_ticker,
            }
            kalshi_ticker_to_game[home_ticker] = (game_key, 'home')
            kalshi_ticker_to_game[away_ticker] = (game_key, 'away')

        except Exception as e:
            print(f"[ERROR] Failed to parse Kalshi event {event.get('event_ticker', '?')}: {e}")

    print(f"Kalshi cache: {len(kalshi_cache)} games, {len(kalshi_ticker_to_game)} tickers")

    # ── Start streams ─────────────────────────────────────────────────────────
    await start_bolt_stream(on_update=on_bolt_update, on_remove=on_bolt_remove)
    print(f"Waiting {WARMUP_SECONDS:g}s for Bolt initial state...")
    await asyncio.sleep(WARMUP_SECONDS)

    all_tickers = list(kalshi_ticker_to_game.keys())
    await start_kalshi_stream(all_tickers, on_update=on_kalshi_update)
    if pregame_only:
        asyncio.create_task(cleanup_started_games())

    # Keep running until interrupted; streams live as background tasks
    try:
        await asyncio.get_running_loop().create_future()
    finally:
        await stop_bolt_stream()
        await stop_kalshi_stream()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kalshi/Bolt arbitrage bot")
    parser.add_argument(
        '--pregame-only',
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Only consider pre-game markets (default: True). Use --no-pregame-only to include in-game markets."
    )
    args = parser.parse_args()
    asyncio.run(main(pregame_only=args.pregame_only))
