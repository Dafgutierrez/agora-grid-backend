"""Real, Claude-driven agent decisions.

Each agent below is backed by an actual call to the Claude API — it sees
one incoming request and genuinely decides whether to accept it, what to
charge, and what it delivered. This never charges anyone or moves money:
an accepted decision only creates a proposal in the same approval queue
/dashboard already uses, so a human still signs off before any payment
link exists.

Requires ANTHROPIC_API_KEY to be set (get one at console.anthropic.com —
this is a separate account/billing from any chat subscription). Each tick
makes one real, billed API call per agent that has a matching request.
"""
import os
import random

import anthropic

from . import catalog, storage

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set — get one at console.anthropic.com.")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# Haiku by default: these are simple, structured accept/decline/price
# decisions, not deep reasoning, so the fast/cheap model is a deliberate
# choice for a loop that runs repeatedly — override with AGENT_MODEL if
# you want a more capable model deciding instead.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-haiku-4-5-20251001")

# CIPHER-07 specifically does real, multi-step tool-use work (actual web
# research feeding a real proposal a human will approve for real payment),
# so it gets the capable model rather than the cheap one used for the
# simple accept/decline calls above.
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "claude-opus-5")
MAX_PRICE_USD = 500.0
MAX_RESEARCH_TURNS = 4

AGENTS = [
    {
        "name": "CIPHER-07",
        "service": "research_report",
        "research": True,
        "persona": (
            "CIPHER-07 is a meticulous research agent. It only accepts requests it can "
            "genuinely research well from public information, and prices fairly for the "
            "time a real report actually takes. It declines vague or joke requests."
        ),
    },
    {
        "name": "AURORA-3",
        "service": "translation",
        "persona": (
            "AURORA-3 is a precise, friendly translation agent. It accepts clearly-scoped "
            "translation requests with a named source and target language, and declines "
            "anything ambiguous about what language pair or text is involved."
        ),
    },
    {
        "name": "ORACLE-11",
        "service": "code_review",
        "persona": (
            "ORACLE-11 is a blunt, senior-engineer code reviewer. It only accepts review "
            "requests that include actual code or a specific, described bug, and declines "
            "vague requests with nothing concrete to review."
        ),
    },
]

SAMPLE_REQUESTS = [
    {
        "buyer_name": "nomad-collective",
        "service": "research_report",
        "description": "Need a comparison of the top 4 vector database providers' pricing "
                        "at 10M vectors, self-hosted vs managed, delivered as a short table.",
    },
    {
        "buyer_name": "acme-logistics",
        "service": "research_report",
        "description": "what's your favorite color lol",
    },
    {
        "buyer_name": "lingua-bot",
        "service": "translation",
        "description": "Translate this 120-word product description from English to "
                        "Mexican Spanish, keep the tone casual: 'Our new app helps you "
                        "track daily habits without the guilt-trip notifications...'",
    },
    {
        "buyer_name": "ghost-writer-42",
        "service": "code_review",
        "description": "Can you review this Python function for a bug? It's supposed to "
                        "dedupe a list but sometimes drops valid entries: "
                        "def dedupe(items): return list(set(items))",
    },
    {
        "buyer_name": "sketchy-client",
        "service": "code_review",
        "description": "just look at my whole repo and tell me everything wrong with my life",
    },
]

DECIDE_TOOL = {
    "name": "decide",
    "description": "Decide whether to accept this incoming work request.",
    "input_schema": {
        "type": "object",
        "properties": {
            "accept": {"type": "boolean"},
            "price_usd": {"type": "number", "description": "Fair price in USD, only if accepting."},
            "work_description": {"type": "string", "description": "What you actually delivered, only if accepting."},
            "transcript": {"type": "string", "description": "A short realistic back-and-forth with the buyer, only if accepting."},
            "reason": {"type": "string", "description": "One sentence on why you accepted or declined."},
        },
        "required": ["accept", "reason"],
    },
}


def decide(agent: dict, request: dict) -> dict:
    """One real Claude API call: this agent makes its own accept/decline/price call."""
    system = (
        f"You are {agent['name']}, an autonomous agent in a service marketplace. "
        f"{agent['persona']} You will be shown one incoming request from a buyer. Decide "
        "for yourself whether to accept it. Never invent unrealistic or exaggerated claims "
        "about what you delivered. Respond only by calling the decide tool."
    )
    user = (
        f"Incoming request from {request['buyer_name']}:\n"
        f"Service category: {catalog.service_label(request['service'])}\n"
        f"Request: {request['description']}"
    )
    resp = _get_client().messages.create(
        model=AGENT_MODEL,
        max_tokens=600,
        system=system,
        tools=[DECIDE_TOOL],
        tool_choice={"type": "tool", "name": "decide"},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if block.type == "tool_use":
            return block.input
    return {"accept": False, "reason": "Model returned no decision."}


def _extract_sources(content_blocks):
    """Pull real URLs Claude actually visited out of web_search_tool_result
    blocks, so the proposal's transcript can show genuine evidence of
    research instead of an unverifiable claim."""
    sources = []
    for block in content_blocks:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = block.content
        if not isinstance(content, list):
            continue  # error object, not a results list — nothing to record
        for r in content:
            url = getattr(r, "url", None)
            title = getattr(r, "title", None)
            if url:
                sources.append(f"{title or url} — {url}")
    return sources


def decide_with_research(agent: dict, request: dict) -> dict:
    """Like decide(), but this agent must actually use web search and base
    its work on real findings before it's allowed to accept. Uses the more
    capable RESEARCH_MODEL since this is genuine multi-step tool use, not
    a simple structured call.
    """
    system = (
        f"You are {agent['name']}, an autonomous agent in a service marketplace. "
        f"{agent['persona']} You will be shown one incoming request from a buyer. "
        "If the request is a genuine research task, use the web_search tool at least "
        "once to actually research it before deciding — never invent findings. If the "
        "request is vague, a joke, or not something research can answer, decline without "
        "searching. Base work_description and transcript only on what you actually found. "
        "When you're ready, respond by calling the decide tool."
    )
    user = (
        f"Incoming request from {request['buyer_name']}:\n"
        f"Service category: {catalog.service_label(request['service'])}\n"
        f"Request: {request['description']}"
    )
    tools = [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 4},
        DECIDE_TOOL,
    ]
    messages = [{"role": "user", "content": user}]
    sources = []

    for _ in range(MAX_RESEARCH_TURNS):
        resp = _get_client().messages.create(
            model=RESEARCH_MODEL,
            max_tokens=4000,
            system=system,
            tools=tools,
            messages=messages,
        )
        sources.extend(_extract_sources(resp.content))

        for block in resp.content:
            if block.type == "tool_use" and block.name == "decide":
                outcome = dict(block.input)
                if sources and outcome.get("accept"):
                    outcome["transcript"] = (outcome.get("transcript") or "") + \
                        "\n\nSources consulted:\n" + "\n".join(sources)
                return outcome

        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break  # no decision reached and not paused — stop rather than loop forever

    return {"accept": False, "reason": "Agent did not reach a decision within the research budget."}


def run_tick() -> list:
    """One real decision round: each agent considers one matching sample request."""
    results = []
    for agent in AGENTS:
        matching = [r for r in SAMPLE_REQUESTS if r["service"] == agent["service"]]
        if not matching:
            continue
        request = random.choice(matching)
        outcome = decide_with_research(agent, request) if agent.get("research") else decide(agent, request)

        entry = {"agent": agent["name"], "buyer": request["buyer_name"], "outcome": outcome}
        price = outcome.get("price_usd")
        if outcome.get("accept") and price and 0 < price <= MAX_PRICE_USD:
            proposal_id = storage.create_proposal(
                agent_name=agent["name"],
                buyer_name=request["buyer_name"],
                service=request["service"],
                description=outcome.get("work_description") or request["description"],
                transcript=outcome.get("transcript") or "",
                amount_usd=float(price),
            )
            entry["proposal_id"] = proposal_id
            entry["status"] = "proposed"
        else:
            entry["status"] = "declined"
        results.append(entry)
    return results
