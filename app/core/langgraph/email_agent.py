"""Email ingest/classify/reply-draft pipeline (rules-first LangGraph)."""

from __future__ import annotations

import re
from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from app.core.logging import logger


class EmailState(TypedDict):
    subject: str
    body: str
    from_address: str
    category: str
    confidence: float
    rationale: str
    reply_subject: str
    reply_body: str


_RULES: list[tuple[str, float, re.Pattern[str], str]] = [
    ("support", 0.85, re.compile(r"\b(bug|error|issue|help|support|broken)\b", re.I), "Support keywords"),
    ("sales", 0.8, re.compile(r"\b(pricing|quote|demo|purchase|buy|sales)\b", re.I), "Sales keywords"),
    ("billing", 0.85, re.compile(r"\b(invoice|payment|billing|refund|charge)\b", re.I), "Billing keywords"),
    ("legal", 0.8, re.compile(r"\b(contract|nda|legal|compliance|terms)\b", re.I), "Legal keywords"),
    ("spam", 0.9, re.compile(r"\b(unsubscribe|viagra|lottery|prize winner)\b", re.I), "Spam signals"),
]


def classify_email(subject: str, body: str) -> tuple[str, float, str]:
    text = f"{subject}\n{body}"
    best = ("general", 0.4, "No strong rule match; default general.")
    for category, confidence, pattern, rationale in _RULES:
        if pattern.search(text):
            if confidence > best[1]:
                best = (category, confidence, rationale)
    return best


def generate_reply_draft(category: str, subject: str, body: str, from_address: str) -> tuple[str, str]:
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject or '(no subject)'}"
    templates = {
        "support": (
            f"Hi,\n\nThanks for reporting this. We've logged your request and will investigate.\n\n"
            f"Summary we received:\n{body[:400]}\n\nBest regards,\nSupport"
        ),
        "sales": (
            f"Hi,\n\nThanks for your interest. A teammate will follow up with pricing/demo details shortly.\n\n"
            f"Best regards,\nSales"
        ),
        "billing": (
            f"Hi,\n\nWe've received your billing inquiry and will review the account details.\n\n"
            f"Best regards,\nBilling"
        ),
        "legal": (
            f"Hi,\n\nThanks for reaching out. Our legal team will review and respond.\n\n"
            f"Best regards,\nLegal"
        ),
        "spam": "Thank you.",
        "general": (
            f"Hi,\n\nThanks for your email. We've received it and will get back to you soon.\n\n"
            f"Best regards"
        ),
    }
    return reply_subject, templates.get(category, templates["general"])


def classify_node(state: EmailState) -> EmailState:
    category, confidence, rationale = classify_email(state.get("subject") or "", state.get("body") or "")
    return {**state, "category": category, "confidence": confidence, "rationale": rationale}


def draft_reply_node(state: EmailState) -> EmailState:
    subj, body = generate_reply_draft(
        state.get("category") or "general",
        state.get("subject") or "",
        state.get("body") or "",
        state.get("from_address") or "",
    )
    return {**state, "reply_subject": subj, "reply_body": body}


def build_email_graph():
    g = StateGraph(EmailState)
    g.add_node("classify", classify_node)
    g.add_node("draft_reply", draft_reply_node)
    g.set_entry_point("classify")
    g.add_edge("classify", "draft_reply")
    g.add_edge("draft_reply", END)
    return g.compile()


_GRAPH = None


def get_email_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_email_graph()
    return _GRAPH


def run_email_pipeline(subject: str, body: str, from_address: str = "") -> Dict[str, Any]:
    result = get_email_graph().invoke(
        {
            "subject": subject,
            "body": body,
            "from_address": from_address,
            "category": "",
            "confidence": 0.0,
            "rationale": "",
            "reply_subject": "",
            "reply_body": "",
        }
    )
    logger.info("email_pipeline_completed", category=result.get("category"))
    return dict(result)
