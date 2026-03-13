import sqlglot
from sqlglot import exp
from config import settings
from typing import Dict, Any, Optional

# ---------------------------------------------------------------------------
# INTENT-AWARE LIMITS
# Must stay in sync with prompt_builder.py constants.
# The validator is the last line of defence — it enforces what the prompt
# requested but cannot guarantee the LLM actually wrote.
#
# SUMMARY queries are GROUP BY aggregations (company counts, status breakdowns,
# time trends). These naturally produce far fewer rows than raw ticket dumps,
# but every grouped row matters — capping at 50 hides real companies/statuses.
# Summary queries get the full MAX_ROWS_LIMIT.
#
# DETAIL queries are raw ticket rows. These CAN be huge (10k+ rows). Cap at
# MAX_ROWS_LIMIT (500) to protect the DB and the frontend. pipeline.py then
# further slices to DETAIL_PREVIEW_LIMIT (50) for the API response, while
# reporting the true total count in the summary text.
# ---------------------------------------------------------------------------
SUMMARY_LIMIT = settings.MAX_ROWS_LIMIT  # 500 — full grouped result, never hide companies
DETAIL_LIMIT  = settings.MAX_ROWS_LIMIT  # 500 — DB-level cap; pipeline slices to 50 for display


def validate_and_format_sql(
    sql_query: str,
    intent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Parses the LLM-generated SQL using an Abstract Syntax Tree (AST).
    Enforces strict read-only rules, table restrictions, and limits.

    Args:
        sql_query: Raw SQL string from the LLM.
        intent:    'summary' or 'detail' — used to enforce the correct LIMIT cap.
                   Defaults to 'detail' (more permissive) if not provided.

    Returns a dict:
        {
            "is_valid": bool,
            "error":    str | None,
            "safe_sql": str | None
        }
    """
    # Resolve the correct row cap for this intent so we can enforce it below.
    effective_limit = SUMMARY_LIMIT if intent == "summary" else DETAIL_LIMIT

    # ------------------------------------------------------------------
    # STEP 1 — Parse
    # ------------------------------------------------------------------
    try:
        parsed = sqlglot.parse_one(sql_query, read="mysql")
    except Exception as e:
        return _fail(f"The generated SQL is malformed or incomplete: {str(e)}")

    # ------------------------------------------------------------------
    # STEP 2 — Must be a plain SELECT
    # Blocks DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE at the AST level.
    # ------------------------------------------------------------------
    if not isinstance(parsed, exp.Select):
        return _fail("Security Violation: Only SELECT queries are permitted.")

    # ------------------------------------------------------------------
    # STEP 3 — Block SELECT ... INTO (file/variable exfiltration)
    # `SELECT * INTO OUTFILE '/tmp/dump.csv'` is still an exp.Select but
    # carries an `into` arg. Reject it explicitly.
    # ------------------------------------------------------------------
    if parsed.args.get("into"):
        return _fail(
            "Security Violation: SELECT ... INTO is not permitted. "
            "This prevents filesystem or variable exfiltration."
        )

    # ------------------------------------------------------------------
    # STEP 4 — Block UNION / INTERSECT / EXCEPT
    # These can be used to stitch in results from forbidden tables.
    # ------------------------------------------------------------------
    if parsed.find(exp.Union):
        return _fail("Security Violation: UNION / INTERSECT / EXCEPT queries are not permitted.")

    # ------------------------------------------------------------------
    # STEP 5 — Block CTEs (WITH clauses)
    # A CTE like `WITH secret AS (SELECT * FROM payments)` could alias a
    # forbidden table into scope and bypass the table allowlist below.
    # ------------------------------------------------------------------
    if parsed.find(exp.With):
        return _fail(
            "Security Violation: WITH (CTE) clauses are not permitted. "
            "Rewrite as a subquery if needed."
        )

    # ------------------------------------------------------------------
    # STEP 6 — Block dangerous MySQL functions (DoS / fingerprinting)
    #
    # FIX vs V4.0: We now check BOTH named exp.Func subclasses AND
    # exp.Anonymous nodes (how sqlglot represents functions it doesn't
    # natively know). Using .sql_name() on known types and .name on
    # Anonymous ensures nothing slips through either path.
    # ------------------------------------------------------------------
    FORBIDDEN_FUNCTIONS = {"sleep", "benchmark", "get_lock", "load_file", "rand"}

    for node in parsed.walk():
        func_name = None

        if isinstance(node, exp.Anonymous):
            # Unknown function — name is stored directly as the `this` string
            func_name = node.name.lower() if node.name else None
        elif isinstance(node, exp.Func):
            # Known sqlglot function — use sql_name() for the actual SQL identifier
            try:
                func_name = node.sql_name().lower()
            except AttributeError:
                func_name = type(node).__name__.lower()

        if func_name and func_name in FORBIDDEN_FUNCTIONS:
            return _fail(
                f"Security Violation: The function '{func_name.upper()}' is forbidden."
            )

    # ------------------------------------------------------------------
    # STEP 7 — Table allowlist
    # Walks ALL table references including those inside subqueries.
    # ------------------------------------------------------------------
    tables = list(parsed.find_all(exp.Table))
    if not tables:
        return _fail("Invalid Query: No table was referenced.")

    allowed_lower = {t.lower() for t in settings.ALLOWED_TABLES}

    for table in tables:
        if table.name.lower() not in allowed_lower:
            return _fail(
                f"Security Violation: Querying table '{table.name}' is not permitted."
            )

    # ------------------------------------------------------------------
    # STEP 8 — Block SELECT * on any JOIN query
    # The LLM prompt forbids this (MySQL only_full_group_by / ambiguous cols),
    # but the validator enforces it as a hard gate so it never reaches the DB.
    #
    # We only block it when there are actual JOINs — a bare `SELECT *`
    # from a single table is ugly but not dangerous.
    # ------------------------------------------------------------------
    has_joins = bool(parsed.find(exp.Join))
    if has_joins:
        for col in parsed.find_all(exp.Star):
            return _fail(
                "Invalid Query: SELECT * with JOINs is forbidden. "
                "Explicitly name every column you need."
            )

    # ------------------------------------------------------------------
    # STEP 9 — LIMIT enforcement
    #
    # Both intents cap at MAX_ROWS_LIMIT (500) at the DB level.
    # The distinction between summary and detail is handled ABOVE the DB:
    #   - Summary: all rows returned, full company/status breakdown shown.
    #   - Detail:  pipeline.py slices to DETAIL_PREVIEW_LIMIT (50) for the
    #              API response and reports the true total in summary text.
    # ------------------------------------------------------------------
    limit_clause = parsed.args.get("limit")

    if not limit_clause:
        # LLM forgot the LIMIT entirely — inject the correct cap.
        parsed.set(
            "limit",
            exp.Limit(expression=exp.Literal.number(effective_limit))
        )
    else:
        try:
            limit_val = int(limit_clause.expression.name)
            if limit_val > effective_limit:
                # LLM wrote a LIMIT that's too high — clamp it.
                parsed.set(
                    "limit",
                    exp.Limit(expression=exp.Literal.number(effective_limit))
                )
        except (ValueError, AttributeError):
            # Complex LIMIT expression (e.g. a subquery) — override to be safe.
            parsed.set(
                "limit",
                exp.Limit(expression=exp.Literal.number(effective_limit))
            )

    # ------------------------------------------------------------------
    # All checks passed — return the clean, dialect-correct SQL string.
    # ------------------------------------------------------------------
    return {
        "is_valid": True,
        "error": None,
        "safe_sql": parsed.sql(dialect="mysql")
    }


def _fail(message: str) -> Dict[str, Any]:
    """Convenience constructor for rejection responses."""
    return {
        "is_valid": False,
        "error": message,
        "safe_sql": None
    }