import asyncio
import json
import os
import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from typing import Callable, List, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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

private_key = load_private_key_from_file('prod_private_key.pem')

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


################################################
# Kalshi WebSocket Manager
################################################

WS_URI = "wss://api.elections.kalshi.com/trade-api/ws/v2"
WS_PATH = "/trade-api/ws/v2"
_BATCH_SIZE = 400  # max tickers per subscribe message


class KalshiOddsManager:
    """
    Manages a Kalshi WebSocket connection and streams ticker updates for subscribed markets.
    Calls on_update(ticker_msg) whenever a 'ticker' message arrives.
    """

    def __init__(self, api_key_id: str, on_update: Optional[Callable] = None):
        self.api_key_id = api_key_id
        self.on_update = on_update
        self.websocket = None
        self.running = False
        self.tickers: List[str] = []
        self._msg_id = 0

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    def _make_auth_headers(self) -> dict:
        timestamp = get_time()
        sig = sign_pss_text(private_key, timestamp + "GET" + WS_PATH)
        return {
            'KALSHI-ACCESS-KEY': self.api_key_id,
            'KALSHI-ACCESS-SIGNATURE': sig,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
        }

    async def connect(self):
        headers = self._make_auth_headers()
        self.websocket = await websockets.connect(
            WS_URI,
            additional_headers=headers,
            max_size=None,
        )
        print("Connected to Kalshi WebSocket")

    async def subscribe(self, tickers: List[str]):
        if not tickers:
            return
        for i in range(0, len(tickers), _BATCH_SIZE):
            batch = tickers[i:i + _BATCH_SIZE]
            msg = {
                "id": self._next_id(),
                "cmd": "subscribe",
                "params": {
                    "channels": ["ticker"],
                    "market_tickers": batch,
                },
            }
            await self.websocket.send(json.dumps(msg))
        print(f"Subscribed to Kalshi ticker channel for {len(tickers)} markets")

    async def listen(self):
        self.running = True
        while self.running:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                if data.get('type') == 'ticker' and self.on_update:
                    try:
                        await self.on_update(data.get('msg', {}))
                    except Exception as e:
                        print(f"[ERROR] Kalshi on_update callback failed: {e}")
            except websockets.ConnectionClosed as e:
                print(f"Kalshi WebSocket closed: {e}")
                if self.running:
                    print("Reconnecting Kalshi in 5 seconds...")
                    await asyncio.sleep(5)
                    await self.connect()
                    await self.subscribe(self.tickers)
            except Exception as e:
                print(f"[ERROR] Kalshi message error: {e}")

    async def start(self, tickers: List[str]):
        self.tickers = tickers
        await self.connect()
        await self.subscribe(tickers)
        await self.listen()

    async def stop(self):
        self.running = False
        if self.websocket:
            await self.websocket.close()


_kalshi_manager: Optional[KalshiOddsManager] = None


async def start_kalshi_stream(tickers: List[str], on_update: Optional[Callable] = None, api_key_id: Optional[str] = None) -> KalshiOddsManager:
    """
    Start the Kalshi WebSocket stream in the background.

    Args:
        tickers: Market tickers to subscribe to
        on_update: async callback(ticker_msg) called on every ticker update
        api_key_id: Kalshi API key (defaults to KALSHI_PROD_API_KEY env var)
    """
    global _kalshi_manager
    if api_key_id is None:
        api_key_id = os.getenv('KALSHI_PROD_API_KEY')
    _kalshi_manager = KalshiOddsManager(api_key_id, on_update=on_update)
    asyncio.create_task(_kalshi_manager.start(tickers))
    await asyncio.sleep(2)
    return _kalshi_manager


async def stop_kalshi_stream():
    """Stop the Kalshi WebSocket stream."""
    global _kalshi_manager
    if _kalshi_manager:
        await _kalshi_manager.stop()
        _kalshi_manager = None