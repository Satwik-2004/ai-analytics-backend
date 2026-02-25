import sqlglot
from sqlglot import exp
from config import settings
from typing import Dict, Any

def validate_and_format_sql(sql_query: str) -> Dict[str, Any]:
    """
    Parses the LLM-generated SQL using an Abstract Syntax Tree (AST).
    Enforces strict read-only rules, table restrictions, and limits.
    Returns the validated/fixed SQL or an error.
    """
    try:
        # 1. Parse the SQL specifically for MySQL dialect
        parsed = sqlglot.parse_one(sql_query, read="mysql")
        
    except Exception as e:
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

    # 3.5 NEW: Block Dangerous MySQL Functions (Denial of Service protection)
    dangerous_functions = ["sleep", "benchmark"]
    for func in parsed.find_all(exp.Func):
        if func.name.lower() in dangerous_functions:
            return {
                "is_valid": False,
                "error": f"Security Violation: The function '{func.name.upper()}' is forbidden.",
                "safe_sql": None
            }

    # 4. Restrict Table Access (V2: Multi-Table Support)
    tables = list(parsed.find_all(exp.Table))
    if not tables:
        return {
            "is_valid": False,
            "error": "Invalid Query: No table was specified.",
            "safe_sql": None
        }
        
    allowed_lower = [t.lower() for t in settings.ALLOWED_TABLES]
    
    for table in tables:
        if table.name.lower() not in allowed_lower:
            return {
                "is_valid": False,
                "error": f"Security Violation: Querying table '{table.name}' is forbidden.",
                "safe_sql": None
            }

    # 5. HARD ENFORCE LIMIT: Every query must have a limit to prevent DB overload
    limit_clause = parsed.args.get("limit")
    
    if not limit_clause:
        # Auto-inject a LIMIT if the LLM forgot it
        parsed.set("limit", exp.Limit(expression=exp.Literal.number(settings.MAX_ROWS_LIMIT)))
    else:
        # If a limit exists, ensure it doesn't exceed our MAX_ROWS_LIMIT
        try:
            limit_val = int(limit_clause.expression.name)
            if limit_val > settings.MAX_ROWS_LIMIT:
                parsed.set("limit", exp.Limit(expression=exp.Literal.number(settings.MAX_ROWS_LIMIT)))
        except (ValueError, AttributeError):
            # If the limit is a complex expression, override it to be safe
            parsed.set("limit", exp.Limit(expression=exp.Literal.number(settings.MAX_ROWS_LIMIT)))

    # Return the clean, safely compiled MySQL string
    return {
        "is_valid": True,
        "error": None,
        "safe_sql": parsed.sql(dialect="mysql")
    }