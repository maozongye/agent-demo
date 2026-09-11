"""Contract risk review pipeline (rules-first, LangGraph-shaped)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from app.core.logging import logger


class ReviewState(TypedDict):
    text: str
    findings: List[Dict[str, Any]]
    report: str


# Rules: (severity, clause label, pattern, summary)
_RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "high",
        "§ liability",
        re.compile(r"unlimited\s+liability|liability\s+shall\s+be\s+unlimited", re.I),
        "Unlimited liability language detected.",
    ),
    (
        "high",
        "§ indemnity",
        re.compile(r"indemnif(y|ication)|hold\s+harmless", re.I),
        "Broad indemnity / hold-harmless clause detected.",
    ),
    (
        "medium",
        "§ auto-renewal",
        re.compile(r"auto[- ]?renew(al|s)?|automatically\s+renew", re.I),
        "Automatic renewal terms should be reviewed.",
    ),
    (
        "medium",
        "§ termination",
        re.compile(r"terminat(e|ion)\s+for\s+convenience|may\s+terminate\s+at\s+any\s+time", re.I),
        "Termination-for-convenience language detected.",
    ),
    (
        "medium",
        "§ intellectual property",
        re.compile(r"assign(s|ment)?\s+all\s+(intellectual\s+property|ip\s+rights)|work\s+made\s+for\s+hire", re.I),
        "Broad IP assignment language detected.",
    ),
    (
        "low",
        "§ governing law",
        re.compile(r"governing\s+law|laws\s+of\s+the\s+state\s+of", re.I),
        "Governing law clause present — confirm jurisdiction fit.",
    ),
    (
        "medium",
        "§ non-compete",
        re.compile(r"non[- ]?compete|not\s+compete\s+with", re.I),
        "Non-compete restriction detected.",
    ),
    (
        "low",
        "§ confidentiality",
        re.compile(r"confidential(\s+information)?|non[- ]?disclosure", re.I),
        "Confidentiality / NDA language detected.",
    ),
]


def _detect_risks(text: str) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for severity, clause, pattern, summary in _RULES:
        match = pattern.search(text or "")
        if not match:
            continue
        start = max(0, match.start() - 40)
        end = min(len(text), match.end() + 40)
        findings.append(
            {
                "severity": severity,
                "clause": clause,
                "summary": summary,
                "excerpt": text[start:end].replace("\n", " ").strip(),
            }
        )
    return findings


def _build_report(text: str, findings: List[Dict[str, Any]]) -> str:
    lines = [
        "# Contract Review Report",
        "",
        f"Source length: {len(text or '')} characters.",
        f"Findings: {len(findings)}.",
        "",
    ]
    if not findings:
        lines.append("No rule-based risk patterns matched. Manual legal review still recommended.")
    else:
        lines.append("## Findings")
        for i, f in enumerate(findings, 1):
            lines.append(f"{i}. **{f['severity'].upper()}** {f['clause']}: {f['summary']}")
            if f.get("excerpt"):
                lines.append(f"   - Excerpt: {f['excerpt']}")
        lines.append("")
        lines.append("## Recommendation")
        highs = sum(1 for f in findings if f["severity"] == "high")
        if highs:
            lines.append(f"{highs} high-severity item(s) require counsel review before signing.")
        else:
            lines.append("No high-severity hits; review medium items and confirm business terms.")
    return "\n".join(lines)


def detect_node(state: ReviewState) -> ReviewState:
    findings = _detect_risks(state.get("text") or "")
    return {**state, "findings": findings}


def report_node(state: ReviewState) -> ReviewState:
    report = _build_report(state.get("text") or "", state.get("findings") or [])
    return {**state, "report": report}


def build_contract_review_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("detect", detect_node)
    graph.add_node("build_report", report_node)
    graph.set_entry_point("detect")
    graph.add_edge("detect", "build_report")
    graph.add_edge("build_report", END)
    return graph.compile()


_GRAPH = None


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_contract_review_graph()
    return _GRAPH


def run_contract_review(text: str) -> tuple[list[dict[str, Any]], str]:
    """Run the contract review graph; returns (findings, report)."""
    if not (text or "").strip():
        raise ValueError("Contract text is empty")
    result = get_graph().invoke({"text": text, "findings": [], "report": ""})
    findings = list(result.get("findings") or [])
    report = str(result.get("report") or "")
    logger.info("contract_review_completed", findings=len(findings))
    return findings, report
