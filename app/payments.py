import os

import stripe

from . import catalog

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")


def create_checkout_session(proposal: dict):
    """Create a real Stripe Checkout Session for an approved proposal.

    Raises RuntimeError if STRIPE_SECRET_KEY isn't configured, so an
    approval can never silently succeed without a real payment link.
    """
    if not stripe.api_key:
        raise RuntimeError(
            "STRIPE_SECRET_KEY is not set — configure it before approving proposals."
        )

    amount_cents = int(round(proposal["amount_usd"] * 100))
    label = f"{catalog.service_label(proposal['service'])} — by {proposal['agent_name']}"

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": label,
                        "description": proposal["description"][:500],
                    },
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        success_url=os.environ.get("CHECKOUT_SUCCESS_URL", "https://example.com/success"),
        cancel_url=os.environ.get("CHECKOUT_CANCEL_URL", "https://example.com/cancel"),
        metadata={"proposal_id": str(proposal["id"])},
    )
    return session


def verify_webhook(payload: bytes, sig_header: str):
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set.")
    return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
