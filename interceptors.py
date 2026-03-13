"""
interceptors.py

All short-circuit logic that fires before (or just after) the state manager
and returns a QueryResponse directly without touching the database.

Each function returns either:
  - A QueryResponse (caller should return it immediately), or
  - None (no interception, continue the pipeline)
"""

from core.schemas import QueryResponse

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

INCOMPLETE_COMMANDS: dict[str, str] = {
    "filter by status":     "Sure! Which specific status are you looking for? (e.g., Closed, Cancel, Pending)",
    "show me open tickets": "Our system tracks a few types of active tickets. Which specific status are you looking for? (e.g., Pending, In Progress, Unassigned)",
    "filter by company":    "Absolutely. Which company would you like to filter by?",
    "filter by branch":     "Which branch location are you looking for?",
    "filter by timeframe":  "What timeframe? (e.g., 'this month', '2025', or 'last 30 days')",
    "select timeframe":     "What timeframe are you looking for? (e.g., '2025', 'last month', 'Q3')",
    "search by ticket id":  "Please provide the exact Ticket ID you want me to look up.",
    "search tickets":       "Please provide the exact Ticket ID, Company Name, or timeframe you are looking for.",
    "break this down further": "How would you like to break this down? You can narrow the results by applying a specific filter.",
}

# Clicking these resets state entirely before re-querying
MEMORY_WIPE_COMMANDS: set[str] = {
    "explore corporate tickets",
    "explore ppm tickets",
    "clear my filters and search all",
    "clear all filters",
    "show ppm all time",
    "show corporate all time",
    "show all statuses for ppm",
    "show all statuses for corporate",
}

# System pill buttons that should bypass the conversational router
SYSTEM_BUTTONS: set[str] = {
    "break this down further",
    "clear search filters",
    "search ppm tickets",
    "search corporate tickets",
    "filter by status",
    "filter by company",
    "filter by branch",
    "filter by timeframe",
    "explore corporate tickets",
    "explore ppm tickets",
}

ANALYTICAL_PHRASES: tuple[str, ...] = (
    "how many", "what about", "break down",
    "show me", "filter", "count", "tickets",
)


# ---------------------------------------------------------------------------
# INTERCEPTION FUNCTIONS
# ---------------------------------------------------------------------------

def check_incomplete_command(query_lower: str, current_state: dict) -> QueryResponse | None:
    """
    Catches known incomplete button labels that need clarification before
    the pipeline can do anything useful.
    """
    if query_lower not in INCOMPLETE_COMMANDS:
        return None

    nav_buttons = []
    if query_lower == "break this down further":
        nav_buttons = ["Filter by Company", "Filter by Branch", "Filter by Timeframe", "Filter by Status"]

    return QueryResponse(
        status="success",
        summary=INCOMPLETE_COMMANDS[query_lower],
        suggested_actions=nav_buttons,
        charts=[],
        raw_data=[],
        insight="Clarification Required",
        state=current_state,
    )


def should_wipe_state(query_lower: str) -> bool:
    """Returns True if this query should reset the search state before processing."""
    return query_lower in MEMORY_WIPE_COMMANDS


def is_fast_pass(query_lower: str, query: str, current_state: dict | None) -> bool:
    """
    Returns True if the router LLM call should be skipped because the intent
    is obvious from context — analysis mode, system buttons, short queries,
    or analytical phrasing.
    """
    if query_lower in SYSTEM_BUTTONS:
        return True
    if len(query.split()) <= 2:
        return True
    if any(phrase in query_lower for phrase in ANALYTICAL_PHRASES):
        return True
    if current_state and any([
        current_state.get("company_name"),
        current_state.get("branch_name"),
        current_state.get("timeframe"),
        current_state.get("status"),
        current_state.get("service_type"),
    ]):
        return True
    return False


def check_vague_search(intent: str, new_state: dict) -> QueryResponse | None:
    """
    Blocks raw detail queries with no filters — prevents dumping the entire DB.
    Only fires after the state manager has run, so we know the resolved intent.
    """
    if intent != "detail":
        return None

    has_filters = any([
        new_state.get("company_name"),
        new_state.get("branch_name"),
        new_state.get("timeframe"),
        new_state.get("status"),
        new_state.get("priority"),
        new_state.get("service_type"),
    ])

    if has_filters:
        return None

    domain_name = "PPM" if "ppm" in (new_state.get("domain") or "").lower() else "Corporate"
    return QueryResponse(
        status="success",
        summary=(
            f"I can certainly help you explore the {domain_name} tickets! "
            f"Since there are a large number of records, could you help me narrow it down? "
            f"You can filter by a specific Company Name, Timeframe (e.g., 'last month'), "
            f"or Status (e.g., 'Pending')."
        ),
        suggested_actions=[
            f"{domain_name} tickets this month",
            "Filter by Status",
            "Breakdown by company",
        ],
        charts=[],
        raw_data=[],
        insight="Clarification Required",
        state=new_state,
    )


def check_zero_data(safe_rows: list, new_state: dict, safe_sql: str) -> QueryResponse | None:
    """
    Fires when the DB returned 0 rows. Builds a contextual explanation of
    which filters caused the empty result and offers targeted pivots.
    """
    if safe_rows:
        return None

    active_filters = []
    if new_state.get("company_name"):
        active_filters.append(f"Company: {new_state['company_name']}")
    if new_state.get("branch_name"):
        bn = new_state["branch_name"]
        active_filters.append(f"Branch: {' + '.join(bn) if isinstance(bn, list) else bn}")
    if new_state.get("timeframe"):
        active_filters.append(f"Timeframe: {new_state['timeframe']}")
    if new_state.get("status"):
        active_filters.append(f"Status: {new_state['status']}")
    if new_state.get("service_type"):
        active_filters.append(f"Service: {new_state['service_type']}")

    domain_str = "PPM" if "ppm" in (new_state.get("domain") or "").lower() else "Corporate"

    if active_filters:
        filter_str = " + ".join(active_filters)
        summary_msg = (
            f"No {domain_str} tickets found for this exact combination: [{filter_str}]. "
            f"Try broadening your search by dropping one of these filters."
        )
        smart_buttons = []
        if new_state.get("timeframe"):
            smart_buttons.append(f"Show {domain_str} all time")
        if new_state.get("status"):
            smart_buttons.append(f"Show all statuses for {domain_str}")
        smart_buttons.append("Clear all filters")
    else:
        summary_msg = (
            f"I couldn't find any data for that query in the {domain_str} database. "
            f"What specific area should we look at?"
        )
        smart_buttons = [f"Explore {domain_str} Tickets", "Clear all filters"]

    return QueryResponse(
        status="success",
        summary=summary_msg,
        suggested_actions=smart_buttons[:3],
        charts=[],
        raw_data=[],
        insight="Zero Data Found",
        state=new_state,  # Keep state so user can see their active filter chips
    )