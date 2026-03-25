from bolt_utils import start_bolt_stream, get_bevents, stop_bolt_stream
from kalshi_utils import get_kevents
import asyncio
from dotenv import load_dotenv
import time
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
TRADE_LOG_PATH = os.getenv('TRADE_LOG_PATH', str(BASE_DIR / 'trade_log.csv'))
LOOP_INTERVAL_SECONDS = float(os.getenv('LOOP_INTERVAL_SECONDS', '2'))
WARMUP_SECONDS = float(os.getenv('WARMUP_SECONDS', '10'))

def get_implied_prob(odds1: float, odds2: float) -> float:
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
    
    year = kdate[:2]  # '26'
    month_str = kdate[2:5]  # 'MAR'
    day = kdate[5:]  # '05'
    
    month = months[month_str]
    
    return f"20{year}-{month}-{day}"

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
    'LA Clippers': 'Los Angeles C',  # Alternative format
    'Los Angeles Lakers': 'Los Angeles L',
    'LA Lakers': 'Los Angeles L',  # Alternative format
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
    'St. Louis Cardinals': 'St. Louis',
    'Tampa Bay Rays': 'Tampa Bay',
    'Texas Rangers': 'Texas',
    'Toronto Blue Jays': 'Toronto',
    'Washington Nationals': 'Washington'
}

def compute_average_odds(bolt_data):
    """Average odds across all sportsbooks for each game"""
    game_averages = {}
    
    # Group by (home_team, away_team, date)
    games = {}
    for key, info in bolt_data.items():
        if key not in games:
            games[key] = []
        games[key].append(info)
    
    # Average probabilities per game
    for key, infos in games.items():
        home_probs = [info['home_prob'] for info in infos]
        away_probs = [info['away_prob'] for info in infos]
        
        game_averages[key] = {
            'home_prob': sum(home_probs) / len(home_probs),
            'away_prob': sum(away_probs) / len(away_probs),
            'sportsbook': 'average'
        }
    
    return game_averages

def find_diffs(bolt_data, kalshi_data, positions):
    print()
    print("============ NOTABLE DIFFERENCES (2.5% lower on kalshi) ============")
    buy_trades = []
    sell_trades = []
    average_only = {k: v for k, v in bolt_data.items() if v['sportsbook'] == 'average'}
    # for key, bolt_info in bolt_data.items()
    for key, bolt_info in average_only.items():
        if key in kalshi_data:
            kalshi_info = kalshi_data[key]
            home_diff = bolt_info['home_prob'] - kalshi_info['home_odds']
            away_diff = bolt_info['away_prob'] - kalshi_info['away_odds']
            with open(TRADE_LOG_PATH, 'a') as f:
                if home_diff > 0.025:  # Threshold for "notable" difference
                    print(f"{key[2]}: {key[0]} vs {key[1]} in {key[3]}")
                    print(f"  Bolt ({bolt_info['sportsbook']}): Home {bolt_info['home_prob']:.4f}")
                    print(f"  Kalshi: Home {kalshi_info['home_odds']:.4f}")
                    print()
                    if kalshi_info['home_ticker'] not in positions: # only want to buy once currently
                        f.write(f"{key[2]}, {key[3]}, {key[0]}, {key[1]}, BUY, {kalshi_info['home_ticker']}, {kalshi_info['home_odds']:.4f}, {bolt_info['home_prob']:.4f}, {bolt_info['sportsbook']}, {datetime.now().isoformat()}\n")
                        buy_trades.append(kalshi_info['home_ticker'])
                if away_diff > 0.025:
                    print(f"{key[2]}: {key[0]} vs {key[1]} in {key[3]}")
                    print(f"  Bolt ({bolt_info['sportsbook']}): Away {bolt_info['away_prob']:.4f}")
                    print(f"  Kalshi: Away {kalshi_info['away_odds']:.4f}")
                    print()
                    if kalshi_info['away_ticker'] not in positions: # only want to buy once currently
                        f.write(f"{key[2]}, {key[3]}, {key[0]}, {key[1]}, BUY, {kalshi_info['away_ticker']}, {kalshi_info['away_odds']:.4f}, {bolt_info['away_prob']:.4f}, {bolt_info['sportsbook']}, {datetime.now().isoformat()}\n")
                        buy_trades.append(kalshi_info['away_ticker'])
                
                # check positions for closing (selling)
                if home_diff < 0.005:
                    if kalshi_info['home_ticker'] in positions:
                        f.write(f"{key[2]}, {key[3]}, {key[0]}, {key[1]}, SELL, {kalshi_info['home_ticker']}, {kalshi_info['home_odds']:.4f}, {bolt_info['home_prob']:.4f}, {bolt_info['sportsbook']}, {datetime.now().isoformat()}\n")
                        sell_trades.append(kalshi_info['home_ticker'])
                if away_diff < 0.005:
                    if kalshi_info['away_ticker'] in positions:
                        f.write(f"{key[2]}, {key[3]}, {key[0]}, {key[1]}, SELL, {kalshi_info['away_ticker']}, {kalshi_info['away_odds']:.4f}, {bolt_info['away_prob']:.4f}, {bolt_info['sportsbook']}, {datetime.now().isoformat()}\n")
                        sell_trades.append(kalshi_info['away_ticker'])

    return buy_trades, sell_trades

async def main():
    if not os.getenv('BOLT_API_KEY'):
        raise RuntimeError('Missing BOLT_API_KEY. Set it in environment or .env on EC2.')
    if not os.getenv('KALSHI_DEMO_API_KEY'):
        raise RuntimeError('Missing KALSHI_DEMO_API_KEY. Set it in environment or .env on EC2.')

    # Start the stream (runs in background)
    await start_bolt_stream()
    
    # Wait for data to come in
    print(f"Waiting {WARMUP_SECONDS:g} seconds for data...")
    await asyncio.sleep(WARMUP_SECONDS)  # Must use 'await' here
    positions = set()
    
    try:
        while True:
            # Get current game states anytime
            start = time.time()
            bolt_data = {}
            bevents = get_bevents()
            bevents = [event for event in bevents if datetime.strptime(event['data']['info']['when'], "%Y-%m-%d, %I:%M %p") > datetime.now()] # filtering for pregame only
            print()
            print("===================== BOLT EVENTS ===========================")
            for event in bevents:
                home_team = event['data']['home_team']
                away_team = event['data']['away_team']
                date = event['data']['info']['when'].split(',')[0]
                league = event['data']['sport']
                try:
                    home_line = event['data']['outcomes'][f'{home_team} Moneyline']['odds']
                    away_line = event['data']['outcomes'][f'{away_team} Moneyline']['odds']
                    home_team_prob, away_team_prob = get_implied_prob(home_line, away_line)
                except KeyError:
                    print(f"Missing moneyline odds for {home_team} vs {away_team} on {event['data']['sportsbook']}, skipping...")
                    continue
                home_team = bteam_to_klocation[home_team]
                away_team = bteam_to_klocation[away_team]
                print(f"{date}: {home_team} ({home_line}, {home_team_prob:.2f}) vs {away_team} ({away_line}, {away_team_prob:.2f}) on {event['data']['sportsbook']}")
                bolt_data[(home_team, away_team, date, league)] = {
                    'home_prob': home_team_prob,
                    'away_prob': away_team_prob,
                    'sportsbook': event['data']['sportsbook']
                }
            
            bolt_averages = compute_average_odds(bolt_data)
            for key, avg_info in bolt_averages.items():
                print(f'{key[2]}: {key[0]} ({avg_info["home_prob"]:.4f}) vs {key[1]} ({avg_info["away_prob"]:.4f}) on average')
            bolt_data.update(bolt_averages)
            
            kevents = get_kevents()
            kalshi_data = {}
            print()
            print("===================== KALSHI EVENTS ===========================")
            for event in kevents:
                swap = 0
                home_team = event['markets'][0]['yes_sub_title']
                away_team = event['markets'][1]['yes_sub_title']
                home_team_odds = float(event['markets'][0]['yes_ask_dollars'])
                away_team_odds = float(event['markets'][1]['yes_ask_dollars'])
                date = kdate_to_bdate(event['markets'][1]['event_ticker'][10:17])
                league = event['event_ticker'][2:5] # getting what league it is (NBA, NHL, MLB)
                if home_team != event['title'].split(' at ')[1]:
                    home_team, away_team = away_team, home_team
                    home_team_odds, away_team_odds = away_team_odds, home_team_odds
                    swap = 1
                print(f"{date}: {home_team} ({home_team_odds:.2f}) vs {away_team} ({away_team_odds:.2f}) on Kalshi")
                kalshi_data[(home_team, away_team, date, league)] = {
                    'title': event['title'],
                    'home_odds': home_team_odds,
                    'away_odds': away_team_odds,
                    'home_ticker': event['markets'][swap]['ticker'],
                    'away_ticker': event['markets'][1 - swap]['ticker']
                }

            buy_trades, sell_trades = find_diffs(bolt_data, kalshi_data, positions)
            positions.update(buy_trades)
            for ticker in sell_trades:
                if ticker in positions:
                    positions.remove(ticker)
            elapsed = time.time() - start
            await asyncio.sleep(max(0, LOOP_INTERVAL_SECONDS - elapsed))
    finally:
        await stop_bolt_stream()

if __name__ == "__main__":
    asyncio.run(main())