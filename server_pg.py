import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy import (create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Optional: stripe if configured
try:
    import stripe
    STRIPE_AVAILABLE = True
except Exception:
    stripe = None
    STRIPE_AVAILABLE = False

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    # Fallback to sqlite for local testing if DATABASE_URL not provided
    DATABASE_URL = 'sqlite:///data/dev.sqlite'

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(256), unique=True, index=True, nullable=False)
    password_hash = Column(String(512), nullable=False)
    phone = Column(String(64), nullable=True, index=True)
    trial_expires = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String(128), nullable=True)
    profile = Column(Text, nullable=True)  # JSON string
    subscription = Column(Text, nullable=True)  # JSON string

class SessionToken(Base):
    __tablename__ = 'sessions'
    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    expires = Column(DateTime, nullable=False)
    user = relationship('User')

class PasswordReset(Base):
    __tablename__ = 'password_resets'
    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    expires = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    user = relationship('User')

class UsedPhone(Base):
    __tablename__ = 'used_phones'
    phone = Column(String(64), primary_key=True)

# Create tables if not exist
Base.metadata.create_all(bind=engine)

app = Flask(__name__, static_folder=os.path.dirname(os.path.abspath(__file__)), static_url_path='')

# Auth decorator
def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth.split(' ', 1)[1]
            db = SessionLocal()
            try:
                sess = db.query(SessionToken).filter_by(token=token).one_or_none()
                if sess and sess.expires > datetime.utcnow():
                    request.user = db.query(User).get(sess.user_id)
                    return fn(*args, **kwargs)
                # expired -> remove
                if sess:
                    db.delete(sess)
                    db.commit()
            finally:
                db.close()
        return jsonify({'error': 'Unauthorized'}), 401
    return wrapper

# Serve static files
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'login.html')

@app.route('/<path:filename>')
def static_files(filename):
    safe = os.path.join(app.static_folder, filename)
    if os.path.exists(safe):
        return send_from_directory(app.static_folder, filename)
    assets_path = os.path.join(app.static_folder, 'assets', filename)
    if os.path.exists(assets_path):
        return send_from_directory(os.path.join(app.static_folder, 'assets'), filename)
    abort(404)

# Signup
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    phone = data.get('phone')
    if not email or not password or not phone:
        return jsonify({'error': 'email,password,phone required'}), 400

    db = SessionLocal()
    try:
        existing = db.query(User).filter_by(email=email).one_or_none()
        if existing:
            return jsonify({'error': 'email already exists'}), 400
        used = db.query(UsedPhone).filter_by(phone=phone).one_or_none()
        eligible = used is None
        trial_expires = None
        if eligible:
            trial_expires = datetime.utcnow() + timedelta(days=7)
        u = User(
            email=email,
            password_hash=generate_password_hash(password),
            phone=phone,
            trial_expires=trial_expires
        )
        db.add(u)
        if eligible:
            db.add(UsedPhone(phone=phone))
        db.commit()
        # create a session token for the new user so frontend can continue
        token = str(uuid.uuid4())
        sess = SessionToken(token=token, user_id=u.id, expires=(datetime.utcnow() + timedelta(days=7)))
        db.add(sess)
        db.commit()
        return jsonify({'ok': True, 'token': token, 'free_trial': bool(trial_expires), 'trial_expires': trial_expires.isoformat() if trial_expires else None})
    finally:
        db.close()

# Login
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password')
    if not email or not password:
        return jsonify({'error': 'email,password required'}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).one_or_none()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'error': 'invalid credentials'}), 401
        token = str(uuid.uuid4())
        sess = SessionToken(token=token, user_id=user.id, expires=(datetime.utcnow() + timedelta(days=7)))
        db.add(sess)
        db.commit()
        return jsonify({'ok': True, 'token': token, 'email': email})
    finally:
        db.close()

# Profile
@app.route('/api/profile', methods=['GET'])
@require_auth
def api_profile_get():
    user = request.user
    # safe fields
    payload = {
        'email': user.email,
        'phone': user.phone,
        'trial_expires': user.trial_expires.isoformat() if user.trial_expires else None,
        'stripe_customer_id': user.stripe_customer_id,
        'profile': json.loads(user.profile) if user.profile else {}
    }
    return jsonify({'ok': True, 'profile': payload})

@app.route('/api/profile', methods=['POST'])
@require_auth
def api_profile_update():
    data = request.json or {}
    db = SessionLocal()
    try:
        user = db.query(User).get(request.user.id)
        profile = json.loads(user.profile) if user.profile else {}
        for field in ('name', 'billing_address', 'vat'):
            if field in data:
                profile[field] = data[field]
        if 'password' in data and data['password']:
            user.password_hash = generate_password_hash(data['password'])
        user.profile = json.dumps(profile)
        db.add(user)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

# Password reset
@app.route('/api/request-password-reset', methods=['POST'])
def api_request_password_reset():
    data = request.json or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'email required'}), 400
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(email=email).one_or_none()
        if not user:
            return jsonify({'ok': True})
        token = str(uuid.uuid4())
        pr = PasswordReset(token=token, user_id=user.id, expires=(datetime.utcnow() + timedelta(hours=1)))
        db.add(pr)
        db.commit()
        # For demo return token (in production email it)
        return jsonify({'ok': True, 'reset_token': token})
    finally:
        db.close()

@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data = request.json or {}
    token = data.get('token')
    password = data.get('password')
    if not token or not password:
        return jsonify({'error': 'token and password required'}), 400
    db = SessionLocal()
    try:
        pr = db.query(PasswordReset).filter_by(token=token, used=False).one_or_none()
        if not pr:
            return jsonify({'error': 'invalid token'}), 400
        if pr.expires < datetime.utcnow():
            db.delete(pr)
            db.commit()
            return jsonify({'error': 'token expired'}), 400
        user = db.query(User).get(pr.user_id)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        user.password_hash = generate_password_hash(password)
        pr.used = True
        db.add(user)
        db.add(pr)
        db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

# Stripe portal/invoices/subscribe
@app.route('/api/create-portal-session', methods=['POST'])
@require_auth
def api_create_portal():
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured on server. Set STRIPE_SECRET_KEY environment variable.'}), 501
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = SessionLocal()
    try:
        user = db.query(User).get(request.user.id)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        customer = user.stripe_customer_id
        if not customer:
            cust = stripe.Customer.create(email=user.email)
            user.stripe_customer_id = cust['id']
            db.add(user)
            db.commit()
            customer = user.stripe_customer_id
        session = stripe.billing_portal.Session.create(customer=customer, return_url=request.json.get('return_url') or request.host_url)
        return jsonify({'url': session.url})
    finally:
        db.close()

@app.route('/api/invoices', methods=['GET'])
@require_auth
def api_invoices():
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured on server. Return mock data or set STRIPE_SECRET_KEY.'}), 501
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = SessionLocal()
    try:
        user = db.query(User).get(request.user.id)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        customer = user.stripe_customer_id
        if not customer:
            return jsonify({'invoices': []})
        invoices = stripe.Invoice.list(customer=customer)
        res = []
        for inv in invoices.auto_paging_iter():
            res.append({'id': inv.id, 'amount_due': inv.amount_due, 'status': inv.status, 'pdf': inv.invoice_pdf})
        return jsonify({'invoices': res})
    finally:
        db.close()

@app.route('/api/subscribe', methods=['POST'])
@require_auth
def api_subscribe():
    plan = request.json.get('plan', 'starter')
    db = SessionLocal()
    try:
        user = db.query(User).get(request.user.id)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
            # mock subscription
            user.subscription = json.dumps({'plan': plan, 'status': 'active', 'started': datetime.utcnow().isoformat()})
            db.add(user)
            db.commit()
            return jsonify({'ok': True, 'subscription': json.loads(user.subscription)})
        stripe.api_key = os.environ['STRIPE_SECRET_KEY']
        if not user.stripe_customer_id:
            cust = stripe.Customer.create(email=user.email)
            user.stripe_customer_id = cust['id']
            db.add(user)
            db.commit()
        return jsonify({'error': 'Use /api/create-checkout-session to start Checkout with a PRICE_ID.'}), 501
    finally:
        db.close()


@app.route('/api/create-checkout-session', methods=['POST'])
@require_auth
def api_create_checkout_session():
    data = request.json or {}
    price_id = data.get('price_id') or os.environ.get('DEFAULT_PRICE_ID')
    if not price_id:
        return jsonify({'error': 'price_id required (or set DEFAULT_PRICE_ID)'}), 400
    if not STRIPE_AVAILABLE or not os.environ.get('STRIPE_SECRET_KEY'):
        return jsonify({'error': 'Stripe not configured on server.'}), 501
    stripe.api_key = os.environ['STRIPE_SECRET_KEY']
    db = SessionLocal()
    try:
        user = db.query(User).get(request.user.id)
        if not user:
            return jsonify({'error': 'user not found'}), 404
        # ensure customer
        if not user.stripe_customer_id:
            cust = stripe.Customer.create(email=user.email)
            user.stripe_customer_id = cust['id']
            db.add(user)
            db.commit()
        # create checkout session
        success_url = data.get('success_url') or (request.host_url.rstrip('/') + '/dashboard.html')
        cancel_url = data.get('cancel_url') or (request.host_url.rstrip('/') + '/signup.html')
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            customer=user.stripe_customer_id,
            line_items=[{'price': price_id, 'quantity': 1}],
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
        )
        return jsonify({'ok': True, 'id': session.id, 'url': session.url})
    finally:
        db.close()


@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    event = None
    try:
        if webhook_secret and STRIPE_AVAILABLE:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            # Best-effort parsing (unsafe) when webhook secret not provided
            event = json.loads(payload.decode('utf-8'))
    except Exception as e:
        return jsonify({'error': 'invalid webhook'}), 400

    # Handle relevant events
    typ = event.get('type') if isinstance(event, dict) else getattr(event, 'type', None)
    data = event.get('data', {}) if isinstance(event, dict) else event.data
    obj = data.get('object') if isinstance(data, dict) else data.object

    db = SessionLocal()
    try:
        if typ == 'checkout.session.completed':
            session = obj
            customer = session.get('customer')
            subscription = session.get('subscription')
            # find user by customer id and store subscription
            user = db.query(User).filter_by(stripe_customer_id=customer).one_or_none()
            if user:
                user.subscription = json.dumps({'subscription_id': subscription, 'status': 'active', 'updated': datetime.utcnow().isoformat()})
                db.add(user)
                db.commit()
        elif typ == 'invoice.payment_succeeded':
            invoice = obj
            customer = invoice.get('customer')
            user = db.query(User).filter_by(stripe_customer_id=customer).one_or_none()
            if user:
                # append invoice record or mark paid
                sub = json.loads(user.subscription) if user.subscription else {}
                sub['last_invoice'] = invoice.get('id')
                user.subscription = json.dumps(sub)
                db.add(user)
                db.commit()
    finally:
        db.close()
    return jsonify({'ok': True})

@app.route('/api/logout', methods=['POST'])
@require_auth
def api_logout():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'error': 'Unauthorized'}), 401
    token = auth.split(' ', 1)[1]
    db = SessionLocal()
    try:
        sess = db.query(SessionToken).filter_by(token=token).one_or_none()
        if sess:
            db.delete(sess)
            db.commit()
        return jsonify({'ok': True})
    finally:
        db.close()

if __name__ == '__main__':
    print(f'Using DATABASE_URL={DATABASE_URL}')
    if STRIPE_AVAILABLE:
        print('Stripe library is installed; check STRIPE_SECRET_KEY env variable to enable live flows.')
    else:
        print('Stripe library not installed or import failed. Endpoints will return mock responses.')
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8000)), debug=True)
