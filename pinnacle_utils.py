import json
import requests
import os

# An api key is emailed to you when you sign up to a plan
api_key = os.getenv('PINNACLE_API_KEY')

def get_pevents():
    sport_key = 'basketball_nba'

    odds_response = requests.get('https://api.the-odds-api.com/v3/odds', params={
        'api_key': api_key,
        'sport': sport_key,
        'region': 'eu', # uk | us | eu | au
        'mkt': 'h2h' # h2h | spreads | totals
    })

    odds_json = json.loads(odds_response.text)
    return odds_json.get('data', [])

## Get events of specified sport and region and market

# sport_key = 'basketball_nba'

# odds_response = requests.get('https://api.the-odds-api.com/v3/odds', params={
#     'api_key': api_key,
#     'sport': sport_key,
#     'region': 'eu', # uk | us | eu | au
#     'mkt': 'h2h' # h2h | spreads | totals
# })

# odds_json = json.loads(odds_response.text)
# if not odds_json['success']:
#     print(
#         'There was a problem with the odds request:',
#         odds_json['msg']
#     )

# else:
#     # odds_json['data'] contains a list of live and 
#     #   upcoming events and odds for different bookmakers.
#     # Events are ordered by start time (live events are first)
#     print()
#     print(
#         'Successfully got {} events'.format(len(odds_json['data'])),
#         'Here\'s all of the events:'
#     )
#     print(odds_json['data'])

#     # Check your usage
#     print()
#     print('Remaining requests', odds_response.headers['x-requests-remaining'])
#     print('Used requests', odds_response.headers['x-requests-used'])

