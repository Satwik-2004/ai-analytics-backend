from typing import List, Dict, Any, Optional
from decimal import Decimal
from core.schemas import KPI


def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float, Decimal))


def build_summary_kpis(
    rows: List[Dict[str, Any]],
    intent: str,
    state: Optional[dict] = None,
    limit_reached: bool = False
) -> List[KPI]:
    """
    Produces a small list of summary KPI cards to sit above the main chart
    or table — giving the user instant at-a-glance metrics.

    For summary intent: total grouped rows, sum of numeric column if present.
    For detail intent:  record count, limit-reached flag if capped.

    Args:
        rows:          Result rows, already capped at MAX_ROWS_LIMIT.
        intent:        'summary' or 'detail'.
        state:         Active search state (used for contextual labelling).
        limit_reached: True if row count hit the hard cap — surfaces a warning KPI.

    Returns:
        List of KPI objects. May be empty if nothing meaningful to surface.
    """
    if not rows:
        return []

    kpis: List[KPI] = []
    domain = (state.get("domain", "") if state else "") or "corporate_tickets"
    ticket_label = "PPM Tickets" if "ppm" in domain.lower() else "Tickets"

    if intent == "summary":
        # Total number of grouped rows (e.g. number of distinct statuses/companies)
        kpis.append(KPI(
            label=f"Total {ticket_label}",
            value=_total_count(rows)
        ))

        # If there's a numeric column that isn't already the count,
        # surface its sum as a second KPI (e.g. sum of AvgDaysToClose)
        sample = rows[0]
        columns = list(sample.keys())
        if len(columns) == 2:
            col1, col2 = columns
            value_col = col2 if _is_number(sample[col2]) else (col1 if _is_number(sample[col1]) else None)
            if value_col and value_col.lower() not in ("count", "total"):
                total_val = sum(
                    row[value_col] for row in rows
                    if _is_number(row.get(value_col))
                )
                kpis.append(KPI(
                    label=f"Total {value_col.replace('_', ' ').title()}",
                    value=round(total_val, 1)
                ))

    else:
        # Detail mode — just the record count
        count = len(rows)
        kpis.append(KPI(
            label=f"{ticket_label} Retrieved",
            value=count
        ))

    # Limit warning surfaced as a KPI so it's visible even if the
    # user doesn't read the text summary.
    if limit_reached:
        kpis.append(KPI(
            label="⚠ Display Limit Reached",
            value="Results capped — refine your filters"
        ))

    return kpis


def _total_count(rows: List[Dict[str, Any]]) -> int:
    """
    Attempts to sum any column named 'Count' or 'Total' in the rows.
    Falls back to len(rows) if no such column exists.
    """
    sample = rows[0]
    for col in sample.keys():
        if col.lower() in ("count", "total"):
            try:
                return int(sum(row[col] for row in rows if _is_number(row.get(col))))
            except (TypeError, ValueError):
                pass
    return len(rows)