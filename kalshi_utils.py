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

def get_time():
    current_time = datetime.datetime.now()
    timestamp = current_time.timestamp()
    current_time_milliseconds = int(timestamp * 1000)
    timestampt_str = str(current_time_milliseconds)
    return timestampt_str

private_key = load_private_key_from_file('demo_private_key.pem')

method = "GET"
base_url = "https://demo-api.kalshi.co"
# base_url = 'https://api.elections.kalshi.com'
path='/trade-api/v2/events?status=open&with_nested_markets=true'

# Strip query parameters from path before signing
path_without_query = path.split('?')[0]
msg_string = get_time() + method + path_without_query
sig = sign_pss_text(private_key, msg_string)

################################################
################################################

def get_kevents():
    cursor = None
    all_events = []

    while True:
        headers = {
            'KALSHI-ACCESS-KEY': os.getenv('KALSHI_DEMO_API_KEY'),
            'KALSHI-ACCESS-SIGNATURE': sig,
            'KALSHI-ACCESS-TIMESTAMP': get_time(),
        }

        full_url = base_url + path
        if cursor:
            full_url += f"&cursor={cursor}"
        
        response = requests.get(full_url, headers=headers)
        data = response.json()

        all_events.extend(data['events'])

        # print(response.text)
        # events = data['events']

        cursor = data.get('cursor')
        if not cursor:
            break
    
    return all_events