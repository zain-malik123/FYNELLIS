import json
import time
import urllib.request
import urllib.error
from urllib.parse import urljoin

BASE = 'http://127.0.0.1:8000/'

def post(path, data, token=None):
    url = urljoin(BASE, path.lstrip('/'))
    b = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=b, headers={'Content-Type':'application/json'})
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8')
            return e.code, json.loads(body)
        except Exception:
            return e.code, {'error': str(e)}
    except Exception as e:
        return None, {'error': str(e)}


def get(path, token=None):
    url = urljoin(BASE, path.lstrip('/'))
    req = urllib.request.Request(url, headers={})
    if token:
        req.add_header('Authorization','Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.getcode(), json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8')
            return e.code, json.loads(body)
        except Exception:
            return e.code, {'error': str(e)}
    except Exception as e:
        return None, {'error': str(e)}

if __name__ == '__main__':
    # wait for server
    print('Waiting for server to start...')
    time.sleep(2)

    email = f'testuser+{int(time.time())}@example.com'
    password = 'TestPass1234'
    phone = f'+1555{int(time.time())%100000}'

    print('Signing up:', email)
    code, res = post('/api/signup', {'email': email, 'password': password, 'phone': phone})
    print('Signup:', code, res)
    if code != 200:
        print('Signup failed, aborting')
        raise SystemExit(1)
    token = res.get('token')
    if not token:
        print('No token returned, aborting')
        raise SystemExit(1)

    print('Fetching profile with token')
    code, res = get('/api/profile', token=token)
    print('Profile:', code, res)

    print('Attempting to create checkout session (expected to fail without Stripe keys)')
    code, res = post('/api/create-checkout-session', {'price_id': 'PRICE_ID_STATER'}, token=token)
    print('Create checkout session:', code, res)

    print('Smoke test finished')
