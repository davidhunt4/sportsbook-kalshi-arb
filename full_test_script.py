import time
import logging
from datetime import datetime
from kalshi_utils import get_kevents, get_time, sign_pss_text, private_key
from pinnacle_utils import get_pevents
import requests
import boto3
import os

# Get logger and set level
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# SNS client for notifications
sns_client = boto3.client('sns')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')  # Set this in Lambda env vars

def send_trade_notification(team, ev, price, count):
    """
    Send SMS/email notification via AWS SNS when a trade is executed.
    
    Args:
        team: Team name
        ev: Expected value
        price: Price in dollars (string)
        count: Number of contracts
    """
    if not SNS_TOPIC_ARN:
        return
    
    message = f"🚨 Trade Executed!\n\nTeam: {team}\nEV: {ev:.4f}\nPrice: ${price}\nCount: {count}"
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject="Kalshi Trade Alert",
            Message=message
        )
        logging.info("Trade notification sent")
    except Exception as e:
        logging.error(f"Failed to send notification: {e}")

def get_kalshi_headers(method, path):
    timestamp = get_time()
    path_without_query = path.split('?')[0]
    msg_string = timestamp + method + path_without_query
    signature = sign_pss_text(private_key, msg_string)
    
    return {
        'KALSHI-ACCESS-KEY': os.getenv('KALSHI_DEMO_API_KEY'),
        'KALSHI-ACCESS-SIGNATURE': signature,
        'KALSHI-ACCESS-TIMESTAMP': timestamp
    }

pteam_to_klocation = {
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
    'Los Angeles Lakers': 'Los Angeles L',
    'Memphis Grizzlies': 'Memphis',
    'Miami Heat': 'Miami',
    'Milwaukee Bucks': 'Milwaukee',
    'Minnesota Timberwolves': 'Minnesota',
    'New Orleans Pelicans': 'New Orleans',
    'New York Knicks': 'New York K',
    'Oklahoma City Thunder': 'Oklahoma City',
    'Orlando Magic': 'Orlando',
    'Philadelphia 76ers': 'Philadelphia',
    'Phoenix Suns': 'Phoenix',
    'Portland Trail Blazers': 'Portland',
    'Sacramento Kings': 'Sacramento',
    'San Antonio Spurs': 'San Antonio',
    'Toronto Raptors': 'Toronto',
    'Utah Jazz': 'Utah',
    'Washington Wizards': 'Washington'
}

def filter_kevents(events, filters):
    filtered = []
    for event in events:
        match = True
        for key, value in filters.items():
            if event.get(key) != value:
                match = False
                break
        if match:
            filtered.append(event)
    return filtered

def contstruct_kalshi_dict(event): # can add more things to dict if need be (like team IDs?)
    team1 = event['markets'][0]['yes_sub_title']
    team2 = event['markets'][1]['yes_sub_title']
    team1_odds = float(event['markets'][0]['yes_ask_dollars'])
    team2_odds = float(event['markets'][1]['yes_ask_dollars'])
    
    kalshi_dict = {
        'title': event.get('title'),
        'team1': team1,
        'team2': team2,
        'team1_odds': team1_odds,
        'team2_odds': team2_odds,
        'team1_ticker': event['markets'][0].get('ticker'),
        'team2_ticker': event['markets'][1].get('ticker')
    }

    return kalshi_dict

def fetch_kalshi(): # returns dict keyed by (team1, team2)
    all_events = get_kevents()
    logging.info(f"Fetched {len(all_events)} events from Kalshi")
    event_filters = {
        'category': 'Sports',
        'series_ticker': 'KXNBAGAME' # gets NBA h2h matchups
    }
    filtered_events = filter_kevents(all_events, event_filters)
    logging.info(f"Filtered down to {len(filtered_events)} events after applying filters")

    kalshi_data = {}
    for event in filtered_events:
        event_dict = contstruct_kalshi_dict(event)
        key = tuple(sorted([event_dict['team1'], event_dict['team2']])) # might need to add another identifier in case teams play multiple times
        kalshi_data[key] = event_dict
    # print(kalshi_data.keys())
    return kalshi_data

def construct_pinnacle_dict(event, pinnacle_market): # can add more things to dict if need be (like team IDs?)
    team1_dec, team2_dec = pinnacle_market['odds']['h2h']
    team1_imp = (1/team1_dec)
    team2_imp = (1/team2_dec)
    sum_probs = team1_imp + team2_imp
    team1_timp = team1_imp/sum_probs
    team2_timp = team2_imp/sum_probs

    pinnacle_dict = {
        'team1': pteam_to_klocation.get(event['teams'][0]),
        'team2': pteam_to_klocation.get(event['teams'][1]),
        'team1_odds': team1_timp,
        'team2_odds': team2_timp
    }
    return pinnacle_dict

def fetch_pinnacle(): # returns dict keyed by (team1, team2)
    events = get_pevents()
    logging.info(f"Fetched {len(events)} events from Pinnacle")
    pinnacle_data = {}
    for event in events:
        pinnacle_markets = [
            market for market in event['sites']
            if market['site_key'] == 'pinnacle'
        ]
        if pinnacle_markets:
            event_dict = construct_pinnacle_dict(event, pinnacle_markets[0])
            key = tuple(sorted([event_dict['team1'], event_dict['team2']])) # might need to add another identifier in case teams play multiple times
            pinnacle_data[key] = event_dict
    # print(pinnacle_data.keys())
    # print()
    return pinnacle_data

def find_ev(kalshi_data, pinnacle_data):
    ev_data = []
    for matchup, kdata in kalshi_data.items():
        pdata = pinnacle_data.get(matchup)
        if pdata:
            if pdata['team1'] != kdata['team1']: # if teams stored in different order
                pdata = {
                    'team1': pdata['team2'],
                    'team2': pdata['team1'],
                    'team1_odds': pdata['team2_odds'],
                    'team2_odds': pdata['team1_odds']
                }
            print(f'{kdata["team1"]} odds: Kalshi {kdata["team1_odds"]} vs Pinnacle {pdata["team1_odds"]}')
            print(f'{kdata["team2"]} odds: Kalshi {kdata["team2_odds"]} vs Pinnacle {pdata["team2_odds"]}')
            team1_ev = pdata['team1_odds'] - kdata['team1_odds']
            team2_ev = pdata['team2_odds'] - kdata['team2_odds']
            ev_entry = {
                'team1': kdata['team1'],
                'team2': kdata['team2'],
                'team1_ev': team1_ev,
                'team2_ev': team2_ev,
                'team1_buy': True if (team1_ev > .025 and kdata['team1_odds'] != 0) else False,
                'team2_buy': True if (team2_ev > .025 and kdata['team2_odds'] != 0) else False,
                # 'team1_buy': kdata['team1'] == 'Los Angeles L',
                # 'team2_buy': kdata['team2'] == 'Los Angeles L',
                'team1_buy_price': kdata['team1_odds'],
                'team2_buy_price': kdata['team2_odds'],
                'team1_ticker': kdata['team1_ticker'],
                'team2_ticker': kdata['team2_ticker']
            }
            ev_data.append(ev_entry)
    return ev_data

def execute_trades(ev_data):
    for ev_entry in ev_data:
        payload = {
            'side': 'yes',
            'action': 'buy',
            'count': 50,
            'type': 'market'
        }
        if ev_entry['team1_buy']:
            logging.info(f"Placing buy order for {ev_entry['team1']} in matchup {ev_entry['team1']} vs {ev_entry['team2']} with EV {ev_entry['team1_ev']:.4f}")
            payload['ticker'] = ev_entry['team1_ticker']
            payload['yes_price_dollars'] = f"{ev_entry['team1_buy_price']:.2f}"
        if ev_entry['team2_buy']:
            logging.info(f"Placing buy order for {ev_entry['team2']} in matchup {ev_entry['team1']} vs {ev_entry['team2']} with EV {ev_entry['team2_ev']:.4f}")
            payload['ticker'] = ev_entry['team2_ticker']
            payload['yes_price_dollars'] = f"{ev_entry['team2_buy_price']:.2f}"
        if ev_entry['team1_buy'] or ev_entry['team2_buy']:
            logging.info(f"Order payload: {payload}")
            kalshi_order_url = "https://demo-api.kalshi.co/trade-api/v2/portfolio/orders"
            path = "/trade-api/v2/portfolio/orders"
            headers = get_kalshi_headers('POST', path)
            response = requests.post(kalshi_order_url, headers=headers, json=payload)
            logging.info(f"Order response: {response.text}")
            
            # Send notification if trade was successful
            if response.status_code == 201:
                team = ev_entry['team1'] if ev_entry['team1_buy'] else ev_entry['team2']
                ev = ev_entry['team1_ev'] if ev_entry['team1_buy'] else ev_entry['team2_ev']
                price = payload.get('yes_price_dollars', 'market')
                send_trade_notification(team, ev, price, payload['count'])

def run_cycle():
    logging.info("Starting new cycle")
    kalshi_data = fetch_kalshi()
    pinnacle_data = fetch_pinnacle()
    ev_data = find_ev(kalshi_data, pinnacle_data)
    if ev_data:
        logging.info(f"Found {len(ev_data)} EV opportunities")
        execute_trades(ev_data)
    else:
        logging.info("No EV opportunities found")

def lambda_handler(event, context):
    try:
        run_cycle()
        return {'statusCode': 200, 'body': 'Success'}
    except Exception as e:
        logging.exception("Error in lambda handler")
        return {'statusCode': 500, 'body': str(e)}


# if __name__ == "__main__":
#     try:
#         run_cycle()
#     except Exception as e:
#         logging.exception("Error during cycle")
    # while True:
    #     try:
    #         start = time.time()
    #         run_cycle()
    #     except:
    #         logging.exception("Error during cycle")
        
    #     elapsed = time.time() - start
    #     sleep_for = max(0, 180 - elapsed)
    #     time.sleep(sleep_for)

    # # logging.basicConfig(level=logging.INFO)
    # # kalshi_data = fetch_kalshi()
    # # pinnacle_data = fetch_pinnacle()
    # # ev_data = find_ev(kalshi_data, pinnacle_data)
    # # print()
    # # print(ev_data)
    # # execute_trades(ev_data)