from typing import List, Dict, Any, Optional
from core.schemas import QueryResponse
from aggregator.chart_selector import determine_visuals
from aggregator.summarizer import build_summary_kpis
from aggregator.response_formatter import build_response


def format_response(
    intent: str,
    rows: List[Dict[str, Any]],
    summary_text: str = "Here are your results.",
    state: Optional[dict] = None,
    suggested_actions: Optional[List[str]] = None,
    limit_reached: bool = False,
    sql_error: str = ""
) -> QueryResponse:
    """
    Main entry point for the aggregator layer. Called by app.py after
    DB execution succeeds and the LLM summary has been generated.

    Orchestration order:
      1. chart_selector  → determine chart type(s) from data shape
      2. summarizer      → build KPI cards (row count, totals, limit warning)
      3. response_formatter → assemble final QueryResponse

    Args:
        intent:            'summary' or 'detail'
        rows:              Result rows from DB, already capped
        summary_text:      LLM-generated insight or fast-pass row count string
        state:             Active search state for context-aware titles/labels
        suggested_actions: Smart Pills from app.py
        limit_reached:     True if row count hit the hard cap
        sql_error:         Non-empty string if DB execution failed
    """
    if suggested_actions is None:
        suggested_actions = []

    # 1. Determine charts (only meaningful for summary intent)
    kpis_from_chart, charts = (
        determine_visuals(rows, state=state)
        if intent == "summary" and rows
        else ([], [])
    )

    # 2. Build summary KPI cards
    kpis_from_summarizer = build_summary_kpis(
        rows,
        intent=intent,
        state=state,
        limit_reached=limit_reached
    )

    # Merge: summarizer KPIs come first (row count context),
    # then any chart-derived KPIs (single-number results, etc.)
    all_kpis = kpis_from_summarizer + kpis_from_chart

    # 3. Assemble and return
    return build_response(
        intent=intent,
        rows=rows,
        summary_text=summary_text,
        kpis=all_kpis,
        charts=charts,
        state=state,
        suggested_actions=suggested_actions,
        sql_error=sql_error
    )