import re
from typing import Dict, Any

# -------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------------------

# First line of defense against prompt injection and SQL injection
DANGEROUS_KEYWORDS = {
    "delete", "drop", "update", "insert", "alter", 
    "truncate", "grant", "revoke", "exec", "execute"
}

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
    Returns a dictionary that maps perfectly to our QueryResponse schema.
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

    # 2. Relaxed the Clarification Limit for Multi-Turn Context
    if turn_count >= 10:
        return {
            "is_valid": False,
            "status": "error",
            "message": "Conversation limit exceeded. Please start a new query with more specific details.",
            "options": None
        }

    # 3. Check for Dangerous Keywords (Prompt/SQL Injection Prevention)
    # We use regex word boundaries (\b) so we don't accidentally block words like "drop-down"
    for word in DANGEROUS_KEYWORDS:
        if re.search(rf"\b{word}\b", cleaned_query):
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

    # If it passes all checks, it is clear to proceed to the AI layer
    return {
        "is_valid": True,
        "status": "success",
        "message": "Valid input",
        "options": None
    }