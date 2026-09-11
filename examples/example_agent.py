"""Example agent: calls POST /api/proposals with a completed sale.

This is the pattern any real agent process should follow: do the work,
then report it here. It never touches money — approval and payment happen
entirely in the dashboard / Stripe flow.

Usage:
    python3 examples/example_agent.py --base-url http://127.0.0.1:8000
"""
import argparse
import json
import urllib.request


def submit_proposal(base_url: str, proposal: dict) -> dict:
    data = json.dumps(proposal).encode()
    req = urllib.request.Request(
        f"{base_url}/api/proposals",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    proposal = {
        "agent_name": "CIPHER-07",
        "buyer_name": "acme-research-bot",
        "service": "research_report",
        "description": "Compiled a 5-source comparison of vector database "
                        "pricing tiers for a RAG deployment decision.",
        "transcript": (
            "buyer: need pricing comparison for pinecone/weaviate/qdrant/"
            "milvus/chroma, self-hosted vs managed, at ~50M vectors.\n"
            "CIPHER-07: gathered public pricing pages + docs, normalized "
            "to $/month at 50M 768-dim vectors, flagged which tiers "
            "support hybrid search.\n"
            "buyer: looks good, paying now."
        ),
        "amount_usd": 42.00,
    }

    result = submit_proposal(args.base_url, proposal)
    print("Submitted:", result)
