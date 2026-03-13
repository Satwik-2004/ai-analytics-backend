"""
aggregator/smart_pills.py

Generates context-aware navigation pill suggestions.

Key improvements in V4.2:
- Pills now mirror exactly what the LLM's NO-OVERPROMISING guardrail will suggest,
  creating the closed-loop Copilot experience: LLM says "break down by Branch"
  and the pill [Show branches for X] appears right below it.
- Detail mode with high counts gets a targeted "refine your search" pill set.
- Summary mode gets drill-down pills matched to what the analyst would suggest next.
"""

MAX_PILLS = 4

# Pill templates that mirror NO_OVERPROMISING_RULES database pivot suggestions.
# When the LLM says "Would you like to break this down by Branch?", the pill
# "Show branches for {company}" is already visible below the response.
# This is the closed-loop experience.

def generate_smart_pills(
    intent: str,
    new_state: dict,
    query_lower: str,
    total_count: int = 0,
) -> list[str]:
    """
    Returns at most MAX_PILLS non-duplicate, non-dismissed pill suggestions.

    Args:
        intent:      'summary' or 'detail'
        new_state:   Active search state
        query_lower: Lowercased query string (for dedup)
        total_count: Actual row count (for detail mode messaging)
    """
    dismissed = {p.lower().strip() for p in (new_state.get("dismissed_pills") or [])}
    company   = new_state.get("company_name")
    branch    = new_state.get("branch_name")
    status    = new_state.get("status")
    timeframe = new_state.get("timeframe")
    domain    = (new_state.get("domain") or "corporate_tickets").lower()
    domain_label = "PPM" if "ppm" in domain else "Corporate"

    candidates: list[str] = []

    # ── DETAIL MODE: high count → push user to summarize or refine ─────────
    if intent == "detail" and total_count > 50:
        # Primary suggestion: summarize this data instead of browsing raw rows
        candidates.append("Summarize this as a chart")

        # Drill-down suggestions — mirror what LLM guardrail would suggest
        if company and not branch:
            candidates.append(f"Show branches for {company}")
        if not status:
            candidates.append("Filter by Status")
        if not timeframe:
            candidates.append("Filter to this month")
        # Domain switch as last resort
        if "ppm" not in query_lower and "ppm" not in domain:
            candidates.append("Explore PPM tickets")
        elif "corporate" not in query_lower and "corporate" not in domain:
            candidates.append("Explore Corporate tickets")

    # ── SUMMARY MODE: analyst drill-down pivots ────────────────────────────
    elif intent == "summary":
        # 1. Raw list toggle — always offer opposite view
        candidates.append("Show the raw ticket list")

        # 2. BRANCH DRILL-DOWN — mirrors "break this down by Branch" suggestion
        #    This is the #1 pivot the LLM guardrail will suggest for company breakdowns
        if company and not branch:
            candidates.append(f"Show branches for {company}")

        # 3. STATUS DRILL-DOWN — mirrors "filter by Status" LLM suggestion
        if not status and "status" not in query_lower:
            candidates.append("Breakdown by Status")

        # 4. COMPANY BREAKDOWN — if no company yet
        if not company and "company" not in query_lower:
            candidates.append("Show company-wise breakdown")

        # 5. TIME TREND — mirrors "filter by Timeframe" LLM suggestion
        if not timeframe:
            candidates.append("Filter to this month")
        elif "trend" not in query_lower and "month" not in query_lower:
            candidates.append("Show month-wise trend")

        # 6. MULTI-LOCATION hint
        if isinstance(branch, list) and len(branch) >= 2:
            candidates.append("Add another location")

        # 7. DOMAIN SWITCH
        if "ppm" not in query_lower and "ppm" not in domain:
            candidates.append("Explore PPM tickets")
        elif "corporate" not in query_lower and "corporate" not in domain:
            candidates.append("Explore Corporate tickets")

    # ── DEFAULT (fallback for edge cases) ──────────────────────────────────
    else:
        candidates.extend([
            "Show company-wise breakdown",
            "Filter to this month",
            "Explore PPM tickets" if "ppm" not in domain else "Explore Corporate tickets",
        ])

    # ── DEDUP + DISMISSED FILTER ───────────────────────────────────────────
    seen: set[str] = set()
    final_pills: list[str] = []

    for pill in candidates:
        normalised = pill.lower().strip()
        if normalised in dismissed or normalised in seen:
            continue
        seen.add(normalised)
        final_pills.append(pill)
        if len(final_pills) >= MAX_PILLS:
            break

    return final_pills