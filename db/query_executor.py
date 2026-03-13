from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from typing import Dict, Any, Tuple, List
from db.connection import engine
from config import settings

# MySQL error code for MAX_EXECUTION_TIME exceeded.
# More reliable than string-matching the error message across MySQL versions.
MYSQL_TIMEOUT_ERROR_CODE = 3024

# Python-side hard cap — last-resort guard independent of the SQL LIMIT clause.
# Should match settings.MAX_ROWS_LIMIT but is intentionally explicit here.
MAX_ROWS_HARD_CAP = settings.MAX_ROWS_LIMIT


def execute_query(sql_query: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Executes a validated read-only SQL query against the database.

    Defence layers applied at the connection level (on top of AST validation):
      - Session is set to READ ONLY before any query runs.
      - Per-session MAX_EXECUTION_TIME is enforced in milliseconds.
      - A Python-side row cap is applied after fetch as a final guard.

    Returns:
        (is_success, rows_as_dicts, error_message)
        On success: (True, [...], "")
        On failure: (False, [], "human-readable error")
    """
    if engine is None:
        return False, [], "Critical Error: Database engine is not initialized."

    try:
        with engine.connect() as connection:

            # --- 1. READ-ONLY SESSION GUARD ---
            # Even if a write query somehow passed the AST validator, the DB
            # engine itself will reject it at this connection level.
            connection.execute(text("SET SESSION TRANSACTION READ ONLY"))

            # --- 2. PER-SESSION EXECUTION TIMEOUT ---
            # Cast to int defensively — if QUERY_TIMEOUT_SECONDS is sourced
            # from an env var and misconfigured, this surfaces a clean error
            # rather than silently producing malformed SQL.
            timeout_ms = int(settings.QUERY_TIMEOUT_SECONDS) * 1000
            connection.execute(text(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}"))

            # --- 3. EXECUTE THE VALIDATED QUERY ---
            result = connection.execute(text(sql_query))

            # --- 4. FETCH AND MAP TO DICTS ---
            # fetchall() is acceptable at the current 500-row cap.
            # The Python-side hard cap below is an independent safety net.
            keys = list(result.keys())
            rows = [dict(zip(keys, row)) for row in result.fetchall()]

            # --- 5. PYTHON-SIDE ROW CAP ---
            # Final guard that holds true regardless of what LIMIT the SQL
            # contained. Makes the invariant "rows <= MAX_ROWS_HARD_CAP"
            # something the rest of the pipeline can rely on unconditionally.
            if len(rows) > MAX_ROWS_HARD_CAP:
                rows = rows[:MAX_ROWS_HARD_CAP]

            return True, rows, ""

    except OperationalError as e:
        # --- TIMEOUT: check by MySQL error code, not string matching ---
        try:
            mysql_code = e.orig.args[0]
        except (AttributeError, IndexError):
            mysql_code = None

        if mysql_code == MYSQL_TIMEOUT_ERROR_CODE:
            return False, [], (
                "Query timed out. The request was too large or complex. "
                "Try narrowing your search with a company, branch, or timeframe filter."
            )

        return False, [], f"Database operational error: {str(e.orig)}"

    except SQLAlchemyError as e:
        return False, [], f"Database error: {str(e)}"

    except Exception as e:
        return False, [], f"Unexpected execution error: {str(e)}"