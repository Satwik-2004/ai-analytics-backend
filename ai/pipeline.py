"""
ai/pipeline.py

Encapsulates the two AI execution steps that happen after state management:

  1. sql_pipeline()     — prompt build → SQL generation → AST validation,
                          with one automatic retry on validation failure.
  2. summary_pipeline() — classifies response type, calls LLM for insight
                          (summary intent) or fast-pass string (detail intent).

ROW LIMIT LOGIC (key change from V4.1):
  - Summary / company-breakdown queries:  ALL rows passed to aggregator.
    Showing 50 rows when there are 200 companies makes it look like data
    is hidden. The LLM insight still only sees the first 50 rows (token cap),
    but raw_data in the response is the full set.
  - Detail queries: Return the total count + the 50 most recent rows.
    User sees: "Found 312 tickets. Showing the 50 most recent."
    This is honest and actionable — user can refine filters to narrow down.
"""

from dataclasses import dataclass
from typing import Optional

from ai.prompt_builder import build_sql_prompt
from ai.sql_generator import generate_sql, generate_human_summary, SQL_GENERATION_FAILED
from rules.sql_validator import validate_and_format_sql

# How many rows to surface in detail mode
DETAIL_PREVIEW_LIMIT = 50


@dataclass
class SQLResult:
    safe_sql: Optional[str]
    error: Optional[str]
    special_response: Optional[str] = None


@dataclass
class SummaryResult:
    text: str
    limit_reached: bool
    # For detail queries: the full count before preview truncation
    total_count: Optional[int] = None


# ---------------------------------------------------------------------------
# SQL PIPELINE
# ---------------------------------------------------------------------------

async def sql_pipeline(user_query: str, new_state: dict) -> SQLResult:
    """
    Builds the prompt, calls the LLM for SQL, validates with AST parsing.
    Retries once with the error message appended if validation fails.
    """
    intent = new_state.get("intent", "detail")
    max_retries = 1
    last_error: Optional[str] = None

    for attempt in range(max_retries + 1):
        prompt = build_sql_prompt(user_query, new_state)

        if attempt > 0 and last_error:
            prompt += (
                f"\n\nCRITICAL FIX REQUIRED: Your previous SQL attempt failed with this error: "
                f"'{last_error}'. You MUST write the complete, valid SQL query and ensure "
                f"all single quotes are closed!"
            )

        raw_sql = await generate_sql(prompt)

        if raw_sql == SQL_GENERATION_FAILED:
            last_error = "LLM API call failed during SQL generation."
            continue

        if raw_sql.strip().upper().startswith("CLARIFY:"):
            clarification_msg = raw_sql.strip()[8:].strip()
            return SQLResult(safe_sql=None, error=None, special_response=clarification_msg)

        if raw_sql.strip().startswith("I do not have access"):
            return SQLResult(safe_sql=None, error=None, special_response=raw_sql.strip())

        validation = validate_and_format_sql(raw_sql, intent=intent)

        if validation["is_valid"]:
            return SQLResult(safe_sql=validation["safe_sql"], error=None)
        else:
            last_error = validation["error"]

    return SQLResult(safe_sql=None, error=last_error)


# ---------------------------------------------------------------------------
# SUMMARY PIPELINE
# ---------------------------------------------------------------------------

async def summary_pipeline(
    user_query: str,
    safe_rows: list,
    new_state: dict,
    is_success: bool,
    db_error: Optional[str],
    row_count: int,
) -> SummaryResult:
    """
    Generates the human-readable summary and applies the correct row limit strategy.

    SUMMARY INTENT:
    - All rows are passed to the aggregator (no truncation for display).
    - LLM insight is generated from first 50 rows (token budget).
    - limit_reached warns if rows hit the hard DB cap.

    DETAIL INTENT:
    - Total count is captured before truncation.
    - Only DETAIL_PREVIEW_LIMIT (50) most recent rows go into raw_data.
    - The summary text states the full count honestly:
      "Found 312 tickets. Showing the 50 most recent — refine with filters."
    - No LLM call needed for detail — fast-pass string is sufficient.

    ERROR:
    - LLM generates a polite error message + suggestion.
    """
    from config import settings
    intent = new_state.get("intent", "detail")
    limit_reached = row_count >= settings.MAX_ROWS_LIMIT

    if is_success and row_count > 0:
        if intent == "summary":
            text = await generate_human_summary(
                user_query,
                safe_rows[:50],    # LLM only needs a sample
                state=new_state,
                error_msg=None,
            )
            return SummaryResult(text=text, limit_reached=limit_reached, total_count=row_count)

        else:
            # DETAIL: honest count message, no LLM.
            #
            # When the DB returns exactly MAX_ROWS_LIMIT rows, we hit the hard cap —
            # the real count could be higher. Display "500+" rather than "500" to
            # signal there are more results beyond the cap (same pattern as Gmail / GitHub).
            # When the DB returns fewer rows, the count is exact — show it plainly.
            total = row_count
            shown = min(total, DETAIL_PREVIEW_LIMIT)
            domain = (new_state.get("domain") or "corporate_tickets").lower()
            label = "PPM tickets" if "ppm" in domain else "tickets"

            count_display = f"{total}+" if limit_reached else str(total)

            if total <= DETAIL_PREVIEW_LIMIT:
                text = f"Found **{count_display}** {label}."
            else:
                text = (
                    f"Found **{count_display}** {label} matching your filters. "
                    f"Showing the **{shown} most recent** — add a filter to narrow down."
                )
            return SummaryResult(text=text, limit_reached=limit_reached, total_count=total)

    elif not is_success:
        text = await generate_human_summary(
            user_query,
            safe_rows,
            state=new_state,
            error_msg=db_error,
        )
        return SummaryResult(text=text, limit_reached=False, total_count=0)

    else:
        return SummaryResult(text="No records found.", limit_reached=False, total_count=0)