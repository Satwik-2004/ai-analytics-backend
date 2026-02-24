import sqlglot
from sqlglot import exp
from config import settings
from typing import Dict, Any, Optional

def validate_and_format_sql(sql_query: str) -> Dict[str, Any]:
    """
    Parses the LLM-generated SQL using an Abstract Syntax Tree (AST).
    Enforces strict read-only rules, table restrictions, and limits.
    Returns the validated/fixed SQL or an error.
    """
    try:
        # 1. Parse the SQL specifically for MySQL dialect
        parsed = sqlglot.parse_one(sql_query, read="mysql")
        
    except Exception as e: # <--- CRITICAL FIX: Now catches ALL parsing and tokenizing errors cleanly
        return {
            "is_valid": False,
            "error": f"The generated SQL is malformed or incomplete: {str(e)}",
            "safe_sql": None
        }

    # 2. CRITICAL: Must be a SELECT statement
    # This automatically blocks DELETE, UPDATE, INSERT, DROP, ALTER, TRUNCATE
    if not isinstance(parsed, exp.Select):
        return {
            "is_valid": False,
            "error": "Security Violation: Only SELECT queries are permitted.",
            "safe_sql": None
        }

    # 3. Block UNION queries (V1 Scope Constraint)
    if parsed.find(exp.Union):
        return {
            "is_valid": False,
            "error": "Security Violation: UNION queries are not allowed.",
            "safe_sql": None
        }

    # 4. Restrict Table Access
    # Find every table referenced in the query and ensure it is the ALLOWED_TABLE
    tables = list(parsed.find_all(exp.Table))
    if not tables:
        return {
            "is_valid": False,
            "error": "Invalid Query: No table was specified.",
            "safe_sql": None
        }
        
    for table in tables:
        if table.name.lower() != settings.ALLOWED_TABLE.lower():
            return {
                "is_valid": False,
                "error": f"Security Violation: Querying table '{table.name}' is forbidden. Only '{settings.ALLOWED_TABLE}' is allowed.",
                "safe_sql": None
            }

    # 5. Enforce LIMIT for Detail Queries
    # If the query does not contain aggregation (COUNT, SUM) or GROUP BY, it's a detail query
    has_aggregation = bool(list(parsed.find_all(exp.AggFunc)))
    has_group_by = bool(parsed.args.get("group"))
    
    if not has_aggregation and not has_group_by:
        limit_clause = parsed.args.get("limit")
        
        if not limit_clause:
            # Auto-inject a LIMIT if the LLM forgot it
            parsed = parsed.limit(settings.MAX_ROWS_LIMIT)
        else:
            # If a limit exists, ensure it doesn't exceed our MAX_ROWS_LIMIT
            try:
                # Extract the numeric value of the limit
                limit_val = int(limit_clause.expression.name)
                if limit_val > settings.MAX_ROWS_LIMIT:
                    # Override the limit safely in the AST
                    parsed.set("limit", exp.Limit(expression=exp.Literal.number(settings.MAX_ROWS_LIMIT)))
            except (ValueError, AttributeError):
                # If the limit is a complex expression, we override it to be safe
                parsed.set("limit", exp.Limit(expression=exp.Literal.number(settings.MAX_ROWS_LIMIT)))

    # Return the clean, safely compiled MySQL string
    return {
        "is_valid": True,
        "error": None,
        "safe_sql": parsed.sql(dialect="mysql")
    }