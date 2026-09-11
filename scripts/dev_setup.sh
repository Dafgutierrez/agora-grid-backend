#!/usr/bin/env bash
# One-shot local dev setup. Run this from the repo root on YOUR machine
# (this needs real internet access to Stripe, which a Claude Code cloud
# sandbox may not have):
#
#   git clone https://github.com/Dafgutierrez/agora-grid-backend
#   cd agora-grid-backend
#   bash scripts/dev_setup.sh
#
# It creates a venv, installs dependencies, and scaffolds .env — it does
# NOT fill in your Stripe keys or start the server. You still need to:
#   1. Edit .env and set STRIPE_SECRET_KEY (sk_test_...) and DASHBOARD_TOKEN.
#   2. Run: source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
#   3. In another terminal: stripe listen --forward-to localhost:8000/webhooks/stripe
#      then copy the printed whsec_... into .env as STRIPE_WEBHOOK_SECRET
#      and restart the server from step 2.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv

echo "==> Installing dependencies"
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  # generate a real random dashboard token instead of leaving the placeholder
  TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  python3 - "$TOKEN" <<'PY'
import sys, pathlib
token = sys.argv[1]
p = pathlib.Path(".env")
text = p.read_text()
text = text.replace("DASHBOARD_TOKEN=replace-with-a-long-random-string", f"DASHBOARD_TOKEN={token}")
p.write_text(text)
PY
  echo "    Generated a random DASHBOARD_TOKEN for you."
else
  echo "==> .env already exists, leaving it alone"
fi

echo ""
echo "Setup done. Still needed before running:"
echo "  1. Open .env and set STRIPE_SECRET_KEY to your sk_test_... key."
echo "  2. Get a webhook secret: stripe listen --forward-to localhost:8000/webhooks/stripe"
echo "     (install the Stripe CLI first if you don't have it: https://stripe.com/docs/stripe-cli)"
echo "     Copy the printed whsec_... into .env as STRIPE_WEBHOOK_SECRET."
echo "  3. Start the server:"
echo "       source .venv/bin/activate && uvicorn app.main:app --reload --port 8000"
echo "  4. In another terminal, submit a test proposal:"
echo "       source .venv/bin/activate && python3 examples/example_agent.py --base-url http://localhost:8000"
echo "  5. Open http://localhost:8000/dashboard?token=<the DASHBOARD_TOKEN from .env>"
