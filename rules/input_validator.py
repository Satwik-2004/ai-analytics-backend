import re
from typing import Dict, Any

# -------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------------------

# First line of defense against prompt injection and SQL injection
# Now uses Regex to look for SQL syntax (e.g., "UPDATE table" or "DROP database")
# This prevents blocking normal English words like "update"
FORBIDDEN_SQL = re.compile(
    r'\b(UPDATE|DELETE|DROP|INSERT|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\s+[A-Za-z_]+\b', 
    re.IGNORECASE
)

# Queries that are too broad and require the V1 structured clarification
VAGUE_QUERIES = {
    "show tickets", "tickets", "all tickets", 
    "get tickets", "data", "info", "show data", "overview"
}

# The strict options we return when a query is too vague (from your V1 spec)
CLARIFICATION_OPTIONS = [
    "Ticket status summary",
    "Recent tickets",
    "Ticket trend"
]

# -------------------------------------------------------------------
# VALIDATION LOGIC
# -------------------------------------------------------------------

def validate_user_query(query: str, turn_count: int = 0) -> Dict[str, Any]:
    """
    Validates the raw text input from the user before it reaches the AI.
    """
    cleaned_query = query.strip().lower()

    # 1. Check for empty or excessively short queries
    if not cleaned_query or len(cleaned_query) < 2:
        return {
            "is_valid": False,
            "status": "error",
            "message": "Query is too short or empty. Please ask a specific question about the tickets.",
            "options": None
        }

    # 3. Check for Dangerous Keywords (Prompt/SQL Injection Prevention)
    if FORBIDDEN_SQL.search(cleaned_query):
        return {
            "is_valid": False,
            "status": "error",
            "message": "Unsafe keyword detected. This system only supports read-only analytics queries.",
            "options": None
        }

    # 4. Check for excessively vague queries
    if cleaned_query in VAGUE_QUERIES:
        return {
            "is_valid": False,
            "status": "clarification_required",
            "message": "Your query is a bit too broad. Please choose one of the options below:",
            "options": CLARIFICATION_OPTIONS
        }

    return {
        "is_valid": True,
        "status": "success",
        "message": "Valid input",
        "options": None
    }