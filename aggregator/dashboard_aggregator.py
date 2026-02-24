from typing import List, Dict, Any
from core.schemas import QueryResponse
from aggregator.chart_selector import determine_visuals

def format_response(
    intent: str, 
    rows: List[Dict[str, Any]], 
    sql_error: str = "", 
    summary_text: str = "Here are your results."
) -> QueryResponse: # <--- Update type hint
    
    if sql_error:
        return QueryResponse(
            status="error",
            summary=f"Failed to retrieve data: {sql_error}"
        )

    if not rows:
        return QueryResponse(
            status="success",
            summary="No tickets found for the selected criteria.",
            insight="Try adjusting your filters or date range."
        )

    if intent == "summary":
        kpis, charts = determine_visuals(rows, title="Data Distribution")
        return QueryResponse(
            status="success",
            summary=summary_text,
            kpis=kpis,
            charts=charts
        )

    else:
        return QueryResponse(
            status="success",
            summary=f"Retrieved {len(rows)} record(s).",
            raw_data=rows
        )