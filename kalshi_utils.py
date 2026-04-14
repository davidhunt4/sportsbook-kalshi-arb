import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

def load_private_key_from_file(file_path):
    with open(file_path, "rb") as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,  # or provide a password if your key is encrypted
            backend=default_backend()
        )
    return private_key

################################################
################################################

import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    message = text.encode('utf-8')
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature).decode('utf-8')
    except InvalidSignature as e:
        raise ValueError("RSA sign PSS failed") from e
    
################################################
################################################

import requests
import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

def get_time():
    current_time = datetime.datetime.now()
    timestamp = current_time.timestamp()
    current_time_milliseconds = int(timestamp * 1000)
    timestampt_str = str(current_time_milliseconds)
    return timestampt_str

def _create_session_with_retries(max_retries=3, backoff_factor=0.5, timeout=10):
    """Create a requests session with automatic retry logic and timeout."""
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.timeout = timeout
    return session

private_key = load_private_key_from_file('demo_private_key.pem')

method = "GET"
# base_url = "https://demo-api.kalshi.co"
base_url = 'https://api.elections.kalshi.com'
path='/trade-api/v2/events'

# Strip query parameters from path before signing
path_without_query = path.split('?')[0]
msg_string = get_time() + method + path_without_query
sig = sign_pss_text(private_key, msg_string)

################################################
################################################

def get_kevents():
    all_events = []
    series_tickers = ['KXNBAGAME', 'KXMLBGAME', 'KXNHLGAME']
    session = _create_session_with_retries(max_retries=3, backoff_factor=0.5, timeout=10)

    for ticker in series_tickers:
        cursor = None
        params = {
            'status': 'open',
            'with_nested_markets': 'true',
            'series_ticker': ticker
        }

        while True:
            headers = {
                'KALSHI-ACCESS-KEY': os.getenv('KALSHI_PROD_API_KEY'),
                'KALSHI-ACCESS-SIGNATURE': sig,
                'KALSHI-ACCESS-TIMESTAMP': get_time(),
            }

            full_url = base_url + path
            if cursor:
                params['cursor'] = cursor
            
            response = session.get(full_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes
            data = response.json()

            all_events.extend(data['events'])

            cursor = data.get('cursor')
            if not cursor:
                break
    
    return all_events