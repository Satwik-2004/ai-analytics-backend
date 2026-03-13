from typing import List, Dict, Any, Optional
from core.schemas import QueryResponse


def build_response(
    intent: str,
    rows: List[Dict[str, Any]],
    summary_text: str,
    kpis: list,
    charts: list,
    state: Optional[dict],
    suggested_actions: List[str],
    sql_error: str = "",
    status: str = "success"
) -> QueryResponse:
    """
    Single assembly point for all QueryResponse objects in the happy path.

    Keeps app.py free of response construction logic — it just passes
    the pieces in and gets a ready-to-return response back.

    Error and edge-case responses (zero data, vague search, security block)
    are still built inline in app.py since they short-circuit before reaching
    the aggregator. This formatter only handles the successful data path.
    """
    if sql_error:
        return QueryResponse(
            status="error",
            summary=f"Failed to retrieve data: {sql_error}",
            suggested_actions=suggested_actions,
            state=state
        )

    if not rows:
        return QueryResponse(
            status="success",
            summary="No tickets found for the selected criteria.",
            insight="Try adjusting your filters or date range.",
            suggested_actions=suggested_actions,
            state=state
        )

    if intent == "summary":
        return QueryResponse(
            status=status,
            summary=summary_text,
            kpis=kpis,
            charts=charts,
            raw_data=rows,
            suggested_actions=suggested_actions,
            state=state
        )

    # detail
    return QueryResponse(
        status=status,
        summary=summary_text,
        kpis=kpis,
        raw_data=rows,
        suggested_actions=suggested_actions,
        state=state
    )