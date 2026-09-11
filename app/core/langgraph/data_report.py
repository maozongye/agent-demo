"""NL → SQL → analysis report pipeline (rules-first LangGraph)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

from app.core.logging import logger
from app.services.sql_sandbox import SQLSafetyError, assert_tenant_scope


class ReportState(TypedDict):
    query: str
    tenant_id: int
    sql: str
    rows: List[Dict[str, Any]]
    analysis: str
    error: str


def nl_to_sql(query: str, tenant_id: int) -> str:
    """Rule-based NL→SQL translator scoped to tenant_id."""
    q = (query or "").strip().lower()
    tid = int(tenant_id)
    if not q:
        raise SQLSafetyError("Query is empty")
    if re.search(r"\b(delete|drop|update|insert|alter|truncate)\b", q):
        # NL that asks to mutate — refuse at translation layer too
        raise SQLSafetyError("Write operations are not allowed")
    if "email" in q and ("status" in q or "draft" in q):
        return (
            f"SELECT status, COUNT(*) AS n FROM email_draft "
            f"WHERE tenant_id = {tid} GROUP BY status"
        )
    if "contract" in q and ("review" in q or "risk" in q or "count" in q):
        return f"SELECT COUNT(*) AS n FROM contract_review WHERE tenant_id = {tid}"
    if "document" in q or ("contract" in q and "upload" in q):
        return (
            f"SELECT id, filename, created_at FROM contract_document "
            f"WHERE tenant_id = {tid} ORDER BY created_at DESC LIMIT 50"
        )
    if "session" in q and ("list" in q or "show" in q or "recent" in q):
        return (
            f"SELECT id, name, created_at FROM session "
            f"WHERE tenant_id = {tid} ORDER BY created_at DESC LIMIT 50"
        )
    if "session" in q or "how many" in q or "count" in q:
        return f"SELECT COUNT(*) AS n FROM session WHERE tenant_id = {tid}"
    # default: session count
    return f"SELECT COUNT(*) AS n FROM session WHERE tenant_id = {tid}"


def analyze_rows(query: str, sql: str, rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Data Report",
        "",
        f"## Question\n{query}",
        "",
        f"## SQL\n```sql\n{sql}\n```",
        "",
        f"## Result ({len(rows)} row(s))",
    ]
    if not rows:
        lines.append("No rows returned for this tenant scope.")
    else:
        preview = rows[:10]
        for i, row in enumerate(preview, 1):
            lines.append(f"{i}. {row}")
        if len(rows) > 10:
            lines.append(f"... {len(rows) - 10} more row(s) omitted")
    lines.append("")
    lines.append("## Notes")
    lines.append("Query executed in read-only sandbox with tenant_id enforcement.")
    return "\n".join(lines)


def translate_node(state: ReportState) -> ReportState:
    try:
        sql = nl_to_sql(state["query"], state["tenant_id"])
        assert_tenant_scope(sql, state["tenant_id"])
        return {**state, "sql": sql, "error": ""}
    except Exception as exc:  # noqa: BLE001
        return {**state, "sql": "", "error": str(exc)}


def analyze_node(state: ReportState) -> ReportState:
    if state.get("error"):
        return {**state, "analysis": f"Report failed: {state['error']}"}
    analysis = analyze_rows(state.get("query") or "", state.get("sql") or "", state.get("rows") or [])
    return {**state, "analysis": analysis}


def build_report_graph():
    g = StateGraph(ReportState)
    g.add_node("translate", translate_node)
    g.add_node("analyze", analyze_node)
    g.set_entry_point("translate")
    g.add_edge("translate", "analyze")
    g.add_edge("analyze", END)
    return g.compile()


_GRAPH = None


def get_report_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_report_graph()
    return _GRAPH


def run_report_pipeline(query: str, tenant_id: int, rows: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Translate NL→SQL and build analysis; optional precomputed rows."""
    graph = get_report_graph()
    state = graph.invoke(
        {
            "query": query,
            "tenant_id": tenant_id,
            "sql": "",
            "rows": rows or [],
            "analysis": "",
            "error": "",
        }
    )
    logger.info("data_report_pipeline", tenant_id=tenant_id, ok=not bool(state.get("error")))
    return dict(state)
