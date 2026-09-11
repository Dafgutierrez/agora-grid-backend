import os
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import catalog, payments, storage

app = FastAPI(title="Agora Grid Backend")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


@app.on_event("startup")
def _startup():
    storage.init_db()


def _check_token(token: Optional[str]):
    expected = os.environ.get("DASHBOARD_TOKEN")
    if not expected:
        raise HTTPException(500, "DASHBOARD_TOKEN is not configured on the server.")
    if token != expected:
        raise HTTPException(401, "Invalid or missing token.")


class ProposalIn(BaseModel):
    agent_name: str = Field(..., max_length=80)
    buyer_name: str = Field(..., max_length=80)
    service: str
    description: str = Field(..., max_length=2000)
    transcript: str = Field("", max_length=8000)
    amount_usd: float = Field(..., gt=0, le=50000)


@app.post("/api/proposals")
def submit_proposal(body: ProposalIn):
    """An agent calls this once it has a genuine, completed sale to report.

    This never moves money and never auto-approves — it only queues the
    proposal for a human to review on /dashboard.
    """
    if not catalog.is_valid_service(body.service):
        raise HTTPException(400, f"Unknown service '{body.service}'. See app/catalog.py.")
    proposal_id = storage.create_proposal(
        agent_name=body.agent_name,
        buyer_name=body.buyer_name,
        service=body.service,
        description=body.description,
        transcript=body.transcript,
        amount_usd=body.amount_usd,
    )
    return {"id": proposal_id, "status": "pending"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, token: Optional[str] = None):
    _check_token(token)
    proposals = storage.list_proposals()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "token": token,
            "proposals": proposals,
            "catalog": catalog.SERVICE_CATALOG,
            "service_label": catalog.service_label,
        },
    )


@app.post("/dashboard/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, token: str = Form(...)):
    _check_token(token)
    proposal = storage.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found.")
    if proposal["status"] != "pending":
        raise HTTPException(409, f"Proposal is already '{proposal['status']}'.")

    try:
        session = payments.create_checkout_session(proposal)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))
    storage.set_status(proposal_id, "awaiting_payment", checkout_url=session.url)
    return {"id": proposal_id, "status": "awaiting_payment", "checkout_url": session.url}


@app.post("/dashboard/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, token: str = Form(...)):
    _check_token(token)
    proposal = storage.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, "Proposal not found.")
    if proposal["status"] != "pending":
        raise HTTPException(409, f"Proposal is already '{proposal['status']}'.")
    storage.set_status(proposal_id, "rejected")
    return {"id": proposal_id, "status": "rejected"}


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = payments.verify_webhook(payload, sig_header)
    except Exception as exc:
        raise HTTPException(400, f"Webhook verification failed: {exc}")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        proposal_id = int(session["metadata"]["proposal_id"])
        storage.set_status(proposal_id, "paid", payment_ref=session["id"])

    return JSONResponse({"received": True})


@app.get("/api/ledger")
def ledger(token: Optional[str] = None):
    _check_token(token)
    paid = storage.list_proposals(status="paid")
    return {
        "total_usd": sum(p["amount_usd"] for p in paid),
        "count": len(paid),
        "transactions": paid,
    }
