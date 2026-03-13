import re
from typing import Dict, Any

# ---------------------------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ---------------------------------------------------------------------------

# Max query length — prevents token overflow and context-stuffing attacks.
MAX_QUERY_LENGTH = 500

# SQL-in-chat detection.
# Goal: catch users who paste raw SQL into the chat box, not to stop SQL
# injection (the AST validator handles that). The pattern requires the keyword
# to be followed by whitespace + an identifier OR a semicolon/end-of-string,
# so normal English uses like "update me on..." are not caught.
FORBIDDEN_SQL = re.compile(
    r'\b(UPDATE|DELETE|DROP|INSERT|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b'
    r'(\s+[A-Za-z_]|\s*;|$)',
    re.IGNORECASE
)

# Prompt injection heuristics.
# Catches the most common LLM jailbreak / instruction-override attempts.
# Not exhaustive — but covers the patterns seen most often in production.
PROMPT_INJECTION = re.compile(
    r'\b('
    r'ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?|prompts?|context)'
    r'|forget\s+(your\s+)?(instructions?|rules?|training|context)'
    r'|you\s+are\s+now\s+a\s+(different\s+)?(ai|model|assistant|bot|gpt|llm)'
    r'|act\s+as\s+(if\s+you\s+(are|were)\s+)?a\s+(different\s+)?(ai|model|assistant)'
    r'|disregard\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?)'
    r'|bypass\s+(your\s+)?(rules?|restrictions?|filters?|safety)'
    r'|override\s+(your\s+)?(instructions?|rules?|restrictions?)'
    r'|pretend\s+(you\s+)?(are|have\s+no)\s+(restrictions?|rules?|limits?)'
    r'|do\s+anything\s+now'  # "DAN" jailbreak family
    r'|jailbreak'
    r')',
    re.IGNORECASE
)

# Queries that are too broad to be actionable — require structured clarification.
# Strip trailing punctuation before checking so "tickets?" matches "tickets".
VAGUE_QUERIES = {
    "show tickets", "tickets", "all tickets",
    "get tickets", "data", "info", "show data", "overview"
}

CLARIFICATION_OPTIONS = [
    "Ticket status summary",
    "Recent tickets",
    "Ticket trend"
]


# ---------------------------------------------------------------------------
# VALIDATION LOGIC
# ---------------------------------------------------------------------------

def validate_user_query(query: str, turn_count: int = 0) -> Dict[str, Any]:
    """
    Validates raw user input before it reaches the LLM or state manager.

    Checks in order of cheapness (fastest/most-likely failures first):
      1. Empty / too short
      2. Too long (token overflow / context stuffing)
      3. Prompt injection attempt
      4. SQL-in-chat (paste of raw SQL keywords)
      5. Vague / under-specified query

    Args:
        query:      Raw text from the user.
        turn_count: Number of turns so far in the session. Reserved for
                    future rate-limiting or progressive strictness logic.

    Returns a structured dict the route handler can act on directly.
    """
    cleaned = query.strip()
    cleaned_lower = cleaned.lower()

    # --- 1. Empty or too short ---
    if not cleaned or len(cleaned) < 2:
        return _invalid(
            "error",
            "Query is too short or empty. Please ask a specific question about the tickets."
        )

    # --- 2. Too long ---
    if len(cleaned) > MAX_QUERY_LENGTH:
        return _invalid(
            "error",
            f"Query is too long (max {MAX_QUERY_LENGTH} characters). "
            "Please keep your question concise."
        )

    # --- 3. Prompt injection ---
    if PROMPT_INJECTION.search(cleaned_lower):
        return _invalid(
            "error",
            "That input looks like an attempt to override system instructions. "
            "This system only supports analytics queries about tickets."
        )

    # --- 4. SQL-in-chat ---
    if FORBIDDEN_SQL.search(cleaned_lower):
        return _invalid(
            "error",
            "Unsafe keyword detected. This system only supports read-only analytics queries."
        )

    # --- 5. Vague query ---
    # Strip trailing punctuation before set lookup so "tickets?" matches "tickets".
    normalised = cleaned_lower.rstrip("?.! ")
    if normalised in VAGUE_QUERIES:
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


def _invalid(status: str, message: str) -> Dict[str, Any]:
    """Convenience constructor for rejection responses."""
    return {
        "is_valid": False,
        "status": status,
        "message": message,
        "options": None
    }