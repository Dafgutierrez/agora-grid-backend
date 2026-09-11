# Agora Grid — Backend

Approval-gated marketplace backend for an agent-to-agent service economy.
Agents propose completed sales; a human approves each one before any payment
is collected. There is no code path that moves money without that approval.

## Why this isn't "Wise API in, funds out"

Wise does not offer an API where arbitrary third-party buyers push money into
your account on demand — it's built for *you* sending transfers out, not for
accepting ad-hoc payments in. The correct, legal shape for "agents sell
services and I get paid" is:

```
Buyer pays  →  Stripe Checkout  →  Stripe balance  →  Stripe payout  →  your Wise account
                                                        (your local bank
                                                         details from Wise,
                                                         added once in the
                                                         Stripe dashboard)
```

Your Wise account/bank details are configured **once, directly in Stripe's
dashboard**, as your payout destination. They never appear in this codebase,
in an env var, or in any chat with an AI assistant. This backend only ever
holds a `STRIPE_SECRET_KEY`, which can create charges but cannot read or move
funds from your bank account directly.

## Flow

1. An agent calls `POST /api/proposals` with a completed-sale description
   (buyer, service, amount).
2. You open `/dashboard` (token-protected) and see it as **pending**.
3. You **Approve** → the backend creates a real Stripe Checkout Session and
   stores the payment link. You **Reject** → it's marked rejected, nothing
   else happens.
4. The buyer pays via the Stripe Checkout link.
5. Stripe calls the `/webhooks/stripe` endpoint on success; the proposal is
   marked **paid** and appears in `/api/ledger`.
6. Stripe pays out to your bank (Wise) on its normal payout schedule — no
   code here ever touches that step.

Nothing reaches "paid" without step 3 (your explicit approval) and step 4
(a real buyer actually paying).

## Payout path for a Mexico-based seller with a USD Wise account

If your Stripe account is registered in Mexico (using your RFC), Stripe pays
out over local Mexican rails — that settles in **MXN to a Mexican CLABE bank
account**, not directly to a foreign-currency Wise balance. If your Wise
account only shows USD receiving details (no MXN CLABE), there's a mismatch
between where Stripe can pay out and where you want the money to end up. Two
ways to bridge it:

1. **Check whether adding an MXN balance in Wise surfaces a CLABE.** Some
   Wise account types can hold/receive multiple currencies with their own
   local details per currency — open the Wise app, add a MXN balance, and
   see if it offers local receiving details. If it does, use that CLABE as
   the Stripe payout bank account directly — one hop, done.
2. **If not, use a two-hop bridge**: point Stripe's payouts at a Mexican
   bank account you control (a normal MX bank, or a business CLABE from a
   local bank), then periodically use Wise's own **send/convert** feature
   yourself to move MXN from that account into your Wise USD balance
   (Wise does the MXN→USD conversion). This is a manual step on your end,
   not something this backend automates — moving money between your own
   accounts is a decision you make with Wise's own transfer feature, not a
   line of code here.

Either way, this backend never needs your Wise account number: Stripe holds
whatever bank account you designate as payout destination, entered directly
in Stripe's dashboard.

## Setup

1. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. Create a Stripe account (stripe.com) and complete their KYC/verification.
3. In the Stripe dashboard, add your Wise account's local bank details
   (e.g. the USD/EUR/GBP account Wise gives you) as your payout bank
   account. This is a one-time dashboard action, not a code change.
4. Copy `.env.example` to `.env` and fill in:
   - `DASHBOARD_TOKEN` — a long random string, this is what protects `/dashboard`.
   - `STRIPE_SECRET_KEY` — from the Stripe dashboard (start with a **test** key).
   - `STRIPE_WEBHOOK_SECRET` — from the webhook you register in Stripe pointing
     at `https://<your-deployed-host>/webhooks/stripe`.
5. `uvicorn app.main:app --reload`
6. Visit `/dashboard?token=<DASHBOARD_TOKEN>`.

Start with Stripe **test mode** end-to-end (test card `4242 4242 4242 4242`)
before ever switching to live keys.

## What "agents" means here

This backend does not include an LLM-driven agent runtime. It exposes the
`POST /api/proposals` endpoint that any agent process — a script, a Claude
Agent SDK loop, whatever you build next — calls when it has genuinely
completed one of the catalog services below for a real buyer. Wiring up
agents that autonomously *decide* to sell something is a separate, later
step; get one real, human-approved, human-fulfilled transaction working
through this pipeline first.

## Service catalog (edit in `app/catalog.py`)

- Text / content generation
- Research & reports
- Code review / small dev tasks
- Translation

Keep this list to services you can actually stand behind — each one is a
real promise to a paying buyer, made in your name.

## Legal checklist before taking real payments

- [ ] Operate under a registered business entity (sole proprietorship or LLC),
      not a personal side project — this is ordinary taxable business income.
- [ ] Track income for tax reporting; consult an accountant on self-employment
      tax obligations in your jurisdiction.
- [ ] Read Stripe's and Wise's terms of service for the specific use case
      (automated/AI-operated service sales).
- [ ] Disclose to buyers that the service is AI-operated where relevant —
      don't let a human buyer believe they're dealing with a human seller
      if that would be deceptive.
- [ ] If any agent's output is generated by a third-party LLM API, check
      that provider's commercial-use / resale terms.
- [ ] Never let this system route money *between other people's* accounts —
      it's scoped to "you get paid for your own agents' work," which avoids
      money-transmitter licensing questions. Don't extend it into acting as
      a payment intermediary for others.
- [ ] Keep the human-approval step. Don't wire `POST /api/proposals` to
      auto-approve — that removes the one thing making this legally coherent
      (a human decision behind every dollar).

This checklist is a starting point, not legal advice — have an actual
lawyer review this before real money moves at any scale.
