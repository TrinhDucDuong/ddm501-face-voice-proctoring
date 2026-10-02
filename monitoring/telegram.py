"""Telegram transport with verified TLS and no credentials in error messages."""
import json
import socket

import certifi
import requests
import urllib3


def request_telegram(token, method, payload=None):
    if method not in {'getMe', 'sendMessage'}:
        raise ValueError('Unsupported Telegram method')
    path = '/bot' + token + '/' + method
    try:
        try:
            response = requests.post('https://api.telegram.org' + path, json=payload or {}, timeout=10)
            return response.status_code, response.json()
        except requests.exceptions.SSLError:
            raise
        except requests.exceptions.ConnectionError:
            # Some local ISPs reset TLS connections using the domain's SNI.
            # Resolve the official endpoint and verify its certificate against the
            # original domain. Certificate/CA checks remain mandatory.
            address = socket.gethostbyname('api.telegram.org')
            pool = urllib3.HTTPSConnectionPool(address,443,assert_hostname='api.telegram.org',
                server_hostname=address,cert_reqs='CERT_REQUIRED',ca_certs=certifi.where(),
                timeout=urllib3.Timeout(connect=5,read=10))
            try:
                response = pool.request('POST',path,body=json.dumps(payload or {}).encode(),
                    headers={'Host':'api.telegram.org','Content-Type':'application/json'},retries=False)
                return response.status, json.loads(response.data)
            finally:
                pool.close()
    except Exception:
        raise RuntimeError('Telegram transport unavailable; credentials are redacted') from None
