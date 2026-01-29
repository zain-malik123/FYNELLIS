import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash

# Optional: stripe if configured
try:
    import stripe
    STRIPE_AVAILABLE = True
except Exception:
    stripe = None
    STRIPE_AVAILABLE = False

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(APP_ROOT, 'data', 'db.json')
if not os.path.exists(os.path.dirname(DATA_FILE)):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

# Initialize DB if missing
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': {}, 'sessions': {}, 'used_phones': []}, f)

def load_db():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_db(db):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, default=str)

app = Flask(__name__, static_folder=APP_ROOT, static_url_path='')

# Helper: token-based auth (simple)
def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
            db = load_db()
            sessions = db.get('sessions', {})
            sess = sessions.get(token)
            if sess:
                try:
                    expires = datetime.fromisoformat(sess.get('expires'))
                except Exception:
                    return jsonify({'error': 'Unauthorized'}), 401
                if expires > datetime.utcnow():
                    request.user_email = sess.get('email')
                    return fn(*args, **kwargs)
                # expired: remove it
                sessions.pop(token, None)
                save_db(db)
        return jsonify({'error': 'Unauthorized'}), 401
    return wrapper

# Serve static files (HTML/CSS/JS)
@app.route('/')
def index():
    return send_from_directory(APP_ROOT, 'login.html')

@app.route('/<path:filename>')
def static_files(filename):
    # allow serving the local static HTML pages and assets directory
    safe = os.path.join(APP_ROOT, filename)
    if os.path.exists(safe):
        return send_from_directory(APP_ROOT, filename)
    # fallback to assets
    assets_path = os.path.join(APP_ROOT, 'assets', filename)
    if os.path.exists(assets_path):
        return send_from_directory(os.path.join(APP_ROOT, 'assets'), filename)
    abort(404)

# Signup: expects JSON {email, password, phone}
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    phone = data.get('phone')
    if not email or not password or not phone:
        return jsonify({'error': 'email,password,phone required'}), 400

    db = load_db()
    users = db.setdefault('users', {})
    used_phones = db.setdefault('used_phones', [])

    if email in users:
        return jsonify({'error': 'email already exists'}), 400

    # Determine free trial eligibility: phone not in used_phones
    eligible = phone not in used_phones
    trial_expires = None
    if eligible:
        trial_expires = (datetime.utcnow() + timedelta(days=7)).isoformat()

    # create user
    users[email] = {
        'email': email,
        'password_hash': generate_password_hash(password),
        'phone': phone,
        'trial_expires': trial_expires,
        'stripe_customer_id': None,
        'subscription': None,
        'profile': {}
    }

    # mark phone used to prevent subsequent trials
    if phone not in used_phones:
        used_phones.append(phone)

    save_db(db)

    return jsonify({'ok': True, 'free_trial': bool(trial_expires), 'trial_expires': trial_expires})

# Login: JSON {email,password} -> returns token
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'email,password required'}), 400

    db = load_db()
    users = db.get('users', {})
    u = users.get(email)
    if not u:
        return jsonify({'error': 'invalid credentials'}), 401
    if not check_password_hash(u.get('password_hash', ''), password):
        return jsonify({'error': 'invalid credentials'}), 401

    token = str(uuid.uuid4())
    sessions = db.setdefault('sessions', {})
    sessions[token] = {'email': email, 'expires': (datetime.utcnow() + timedelta(days=7)).isoformat()}
    save_db(db)
    return jsonify({'ok': True, 'token': token, 'email': email})

# Profile GET/POST
@app.route('/api/profile', methods=['GET'])
@require_auth
def api_profile_get():
    db = load_db()
    users = db.get('users', {})
    u = users.get(request.user_email)
    if not u:
        return jsonify({'error': 'not found'}), 404
    # return safe profile fields
    payload = {k: v for k, v in u.items() if k not in ('password_hash',)}
    return jsonify({'ok': True, 'profile': payload})

@app.route('/api/profile', methods=['POST'])
@require_auth
def api_profile_update():
    data = request.json or {}
    db = load_db()
    users = db.get('users', {})
    u = users.get(request.user_email)
    if not u:
        return jsonify({'error': 'not found'}), 404
    # Accept name, billing_address, vat, password
    profile = u.setdefault('profile', {})
    for field in ('name', 'billing_address', 'vat'):
        if field in data:
            profile[field] = data[field]
    if 'password' in data and data['password']:
        u['password_hash'] = generate_password_hash(data['password'])
    save_db(db)
    return jsonify({'ok': True})


@app.route('/api/request-password-reset', methods=['POST'])
def api_request_password_reset():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'email required'}), 400
    db = load_db()
    u = db.get('users', {}).get(email)
    if not u:
        return jsonify({'ok': True})
    token = str(uuid.uuid4())
    resets = db.setdefault('password_resets', {})
    resets[token] = {'email': email, 'expires': (datetime.utcnow() + timedelta(hours=1)).isoformat()}
    save_db(db)
    # For demo only: return token so the user can test reset without email
    return jsonify({'ok': True, 'reset_token': token})


@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data = request.json or {}
    token = data.get('token')
    password = data.get('password')
    if not token or not password:
        return jsonify({'error': 'token and password required'}), 400
    db = load_db()
    resets = db.get('password_resets', {})
    entry = resets.get(token)
    if not entry:
        return jsonify({'error': 'invalid token'}), 400
    try:
        expires = datetime.fromisoformat(entry.get('expires'))
    except Exception:
        return jsonify({'error': 'invalid token'}), 400
    if expires < datetime.utcnow():
        resets.pop(token, None)
        save_db(db)
        return jsonify({'error': 'token expired'}), 400
    email = entry.get('email')
    user = db.get('users', {}).get(email)
    if not user:
        return jsonify({'error': 'user not found'}), 404
    user['password_hash'] = generate_password_hash(password)
    resets.pop(token, None)
    save_db(db)
    return jsonify({'ok': True})

# Create Stripe Customer Portal session (server must have STRIPE_SECRET_KEY env set)
@app.route('/api/create-portal-session', methods=['POST'])
@require_auth
def api_create_portal():
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured on server. Set STRIPE_SECRET_KEY environment variable.'}), 501
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = load_db()
    user = db['users'].get(request.user_email)
    if not user:
        return jsonify({'error': 'user not found'}), 404
    customer = user.get('stripe_customer_id')
    if not customer:
        # Create customer
        cust = stripe.Customer.create(email=user['email'])
        customer = cust['id']
        user['stripe_customer_id'] = customer
        save_db(db)

    session = stripe.billing_portal.Session.create(customer=customer, return_url=request.json.get('return_url') or request.host_url)
    return jsonify({'url': session.url})

# List invoices (requires Stripe configured)
@app.route('/api/invoices', methods=['GET'])
@require_auth
def api_invoices():
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured on server. Return mock data or set STRIPE_SECRET_KEY.'}), 501
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = load_db()
    user = db['users'].get(request.user_email)
    if not user:
        return jsonify({'error': 'user not found'}), 404
    customer = user.get('stripe_customer_id')
    if not customer:
        return jsonify({'invoices': []})
    invoices = stripe.Invoice.list(customer=customer)
    # return minimal invoice info
    res = []
    for inv in invoices.auto_paging_iter():
        res.append({'id': inv.id, 'amount_due': inv.amount_due, 'status': inv.status, 'pdf': inv.invoice_pdf})
    return jsonify({'invoices': res})

# Create subscription / checkout session (simplified stub)
@app.route('/api/subscribe', methods=['POST'])
@require_auth
def api_subscribe():
    plan = request.json.get('plan', 'starter')
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        # For now create a mock subscription entry in DB
        db = load_db()
        user = db['users'].get(request.user_email)
        user['subscription'] = {'plan': plan, 'status': 'active', 'started': datetime.utcnow().isoformat()}
        save_db(db)
        return jsonify({'ok': True, 'subscription': user['subscription']})
    # Minimal real Stripe Checkout flow (requires configured products/prices)
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = load_db()
    user = db['users'].get(request.user_email)
    if not user:
        return jsonify({'error': 'user not found'}), 404
    # create customer if missing
    if not user.get('stripe_customer_id'):
        cust = stripe.Customer.create(email=user['email'])
        user['stripe_customer_id'] = cust['id']
        save_db(db)
    # In a real integration you'd create a Checkout Session with a price id
    return jsonify({'error': 'Real Stripe Checkout not configured. Provide PRICE_ID and STRIPE_SECRET_KEY.'}), 501

# Logout
@app.route('/api/logout', methods=['POST'])
@require_auth
def api_logout():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    token = auth.split(' ', 1)[1]
    db = load_db()
    sessions = db.get('sessions', {})
    sessions.pop(token, None)
    save_db(db)
    return jsonify({'ok': True})

if __name__ == '__main__':
    # Optional: expose stripe availability info
    if STRIPE_AVAILABLE:
        print('Stripe library is installed; check STRIPE_SECRET_KEY env variable to enable live flows.')
    else:
        print('Stripe library not installed or import failed. Endpoints will return mock responses.')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=True)
