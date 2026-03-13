from typing import List, Dict, Any, Tuple, Optional
from decimal import Decimal
from core.schemas import ChartData, KPI


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _is_number(val: Any) -> bool:
    return isinstance(val, (int, float, Decimal))


def _looks_like_date(val: Any) -> bool:
    """
    Heuristic: if the string value contains a hyphen or slash it's likely
    a date or month period (e.g. '2025-01', '2025-01-15', '01/2025').
    """
    return any(ch in str(val) for ch in ["-", "/"])


def _make_title(label_col: str, state: Optional[dict]) -> str:
    """
    Builds a human-readable chart title from the grouping column name and
    active state context (e.g. "Tickets by Status — Reliance Jan 2025").
    Falls back to a clean column-name-based title if no state is present.
    """
    base = f"Tickets by {label_col.replace('_', ' ').title()}"
    if not state:
        return base

    context_parts = []
    if state.get("company_name"):
        cn = state["company_name"]
        context_parts.append(cn if isinstance(cn, str) else " + ".join(cn))
    if state.get("branch_name"):
        bn = state["branch_name"]
        context_parts.append(bn if isinstance(bn, str) else " + ".join(bn))
    if state.get("timeframe"):
        context_parts.append(str(state["timeframe"]))

    if context_parts:
        return f"{base} — {', '.join(context_parts)}"
    return base


# ---------------------------------------------------------------------------
# MAIN SELECTOR
# ---------------------------------------------------------------------------

def determine_visuals(
    rows: List[Dict[str, Any]],
    state: Optional[dict] = None
) -> Tuple[List[KPI], List[ChartData]]:
    """
    Analyses the SQL result set shape and determines the appropriate
    chart type(s) and/or KPIs to return to the frontend.

    Scenarios handled:
      1 row,  1 col  → single KPI card
      N rows, 1 col  → multi-value KPI list (e.g. list of statuses)
      N rows, 2 cols → line (date label) / pie (≤5 items) / bar (default)
      N rows, 3 cols → stacked bar signal (pivot done on React side)
      N rows, N cols → raw table fallback (no chart, just data)

    Args:
        rows:  List of dicts from the DB, already capped at MAX_ROWS_LIMIT.
        state: Active search state — used for context-aware chart titles.

    Returns:
        (kpis, charts) — both may be empty if the data shape doesn't fit
        a known visual pattern. The frontend will fall back to a table.
    """
    if not rows:
        return [], []

    kpis: List[KPI] = []
    charts: List[ChartData] = []

    sample = rows[0]
    columns = list(sample.keys())
    num_cols = len(columns)

    # ------------------------------------------------------------------
    # SCENARIO 1: Single number — global KPI card
    # e.g. SELECT COUNT(*) AS Count FROM corporate_tickets
    # ------------------------------------------------------------------
    if len(rows) == 1 and num_cols == 1 and _is_number(sample[columns[0]]):
        col = columns[0]
        kpis.append(KPI(
            label=col.replace("_", " ").title(),
            value=sample[col]
        ))
        return kpis, charts

    # ------------------------------------------------------------------
    # SCENARIO 2: Single column, multiple rows — KPI list
    # e.g. SELECT DISTINCT Status FROM corporate_tickets
    # Unusual but valid — surface as a list of KPI badges.
    # ------------------------------------------------------------------
    if num_cols == 1:
        col = columns[0]
        for row in rows:
            kpis.append(KPI(
                label=col.replace("_", " ").title(),
                value=row[col]
            ))
        return kpis, charts

    # ------------------------------------------------------------------
    # SCENARIO 3: Two columns — categorical or time-series chart
    # e.g. SELECT Status, COUNT(*) AS Count GROUP BY Status
    #      SELECT LEFT(CreatedDate, 7) AS TimePeriod, COUNT(*) GROUP BY TimePeriod
    # ------------------------------------------------------------------
    if num_cols == 2:
        col1, col2 = columns[0], columns[1]

        # Identify label vs value column
        if _is_number(sample[col2]):
            label_col, value_col = col1, col2
        elif _is_number(sample[col1]):
            label_col, value_col = col2, col1
        else:
            # Both columns are strings — can't draw a meaningful chart,
            # fall through to raw table
            return kpis, charts

        labels = [str(row[label_col]) for row in rows]
        values = [row[value_col] for row in rows]
        title = _make_title(label_col, state)

        # Chart type decision
        if _looks_like_date(sample[label_col]):
            chart_type = "line"
        elif len(rows) <= 5:
            chart_type = "pie"
        else:
            chart_type = "bar"

        charts.append(ChartData(
            type=chart_type,
            title=title,
            labels=labels,
            values=values,
            # Pass the raw column names so React knows which axis is which
            # without having to guess from the data.
            x_key=label_col,
            y_key=value_col
        ))
        return kpis, charts

    # ------------------------------------------------------------------
    # SCENARIO 4: Three columns — stacked bar signal
    # e.g. SELECT CompanyName, Status, COUNT(*) AS Count
    #      GROUP BY CompanyName, Status
    #
    # The backend does NOT perform the pivot — React handles that because
    # it already has the logic and the full dataset. We just need to signal
    # the correct chart type and tell React which columns play which role.
    #
    # Convention: col1 = X axis (grouping), col2 = series/stack key,
    # col3 = numeric value.
    # ------------------------------------------------------------------
    if num_cols == 3:
        col1, col2, col3 = columns[0], columns[1], columns[2]

        # Validate the third column is numeric — if not, fall through to table
        if not _is_number(sample[col3]):
            return kpis, charts

        labels = list({str(row[col1]) for row in rows})  # unique X-axis values
        title = _make_title(f"{col1} by {col2}", state)

        charts.append(ChartData(
            type="stacked_bar",
            title=title,
            labels=labels,
            values=[],          # React builds this from raw_data via the pivot
            x_key=col1,         # X axis grouping column
            series_key=col2,    # Stack/series column
            y_key=col3          # Numeric value column
        ))
        return kpis, charts

    # ------------------------------------------------------------------
    # SCENARIO 5: 4+ columns — raw table, no chart
    # The frontend will render a DataTable. Return nothing here so the
    # caller knows not to try forcing a chart type.
    # ------------------------------------------------------------------
    return kpis, charts