# Local Flask Backend for FYNELLIS Static Pages

This repository contains a minimal Flask backend to support the demo signup/login flows and a placeholder integration for Stripe Customer Portal.

Prerequisites
- Python 3.8+
- (Optional) A Stripe account and `STRIPE_SECRET_KEY` environment variable to enable live portal/invoice functionality.

Setup
1. Create a virtual environment:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```

2. (Optional) Create a `.env` file with your Stripe secret key:

   ```env
   STRIPE_SECRET_KEY=sk_test_...
   ```

Running locally

```bash
python server.py
```

This starts a development server on port 8000. Open `http://localhost:8000` which serves `login.html` by default.

Notes
- For development the server stores user data in `data/db.json`.
- SMS/OTP flows are intentionally omitted; phone numbers are used only to determine trial eligibility in this demo.
- Stripe endpoints are functional only if `stripe` is installed and `STRIPE_SECRET_KEY` is set. Otherwise endpoints return 501 or mock data.

Security
- This demo uses a simplistic token session implementation stored in `data/db.json`. Do not use it in production.
- Secure cookies, HTTPS, CSRF protection, and proper session management are required for production deployment.

Next steps
- Add email verification or password-reset flows.
- Replace simple JSON DB with sqlite or real DB.
- Implement real Stripe Checkout flow for subscriptions.
