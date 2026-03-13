import json
from datetime import datetime
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# This defines the structure of our memory
DEFAULT_STATE = {
    "intent": "detail",           # 'summary' or 'detail'
    "domain": "corporate_tickets", # 'corporate_tickets' or 'ppm_tickets'
    "company_name": None,
    "branch_name": None,          # Can now be a list for OR accumulation
    "timeframe": None,
    "status": None,
    "priority": None,
    "service_type": None,
    "dismissed_pills": [],        # Tracks pills user has already seen/dismissed
    "last_updated": None          # ISO timestamp — ready for TTL enforcement later
}

async def update_state(user_query: str, current_state: dict = None) -> dict:
    """
    Takes the user's query and the current JSON state,
    and asks the LLM to intelligently update the state.

    Key improvements over V4.0:
    - branch_name supports a list for additive OR queries ("Delhi and Mumbai")
    - last_updated timestamp is always injected (TTL-ready for session management)
    - dismissed_pills is preserved across turns so Smart Pills don't repeat
    """
    if current_state is None:
        current_state = {**DEFAULT_STATE}

    # Always preserve dismissed_pills across turns — LLM must not wipe it
    existing_dismissed = current_state.get("dismissed_pills") or []

    system_prompt = f"""You are the central State Manager for a database AI.
Your job is to read the User's Request, look at the Current State, and output an updated JSON State.

CRITICAL DOMAIN SWITCHING & MAPPING RULES (SUPERSEDES ALL):
1. If the user mentions "AMC", "R&M", "Supply", "Projects", or "Booking", you MUST forcefully set the `domain` to `corporate_tickets` AND set the `service_type` key to that specific value (e.g., "AMC").
2. If the user mentions "Corporate", you MUST set the `domain` to `corporate_tickets`, but you MUST NOT set `service_type` to "Corporate". Leave `service_type` as null unless a specific trade (like AMC or Plumbing) is also mentioned.
3. If the user mentions "PPM" or "preventive maintenance", you MUST forcefully set the `domain` to `ppm_tickets`.

CRITICAL ENTITY RULES (GEOGRAPHY):
- If a user mentions a known city, state, or geographic location (e.g., Kolkata, Mumbai, Chennai, Delhi, Pune, Noida, Bangalore), you MUST assign it to `branch_name`, NEVER to `company_name`, unless the user explicitly says "Company Kolkata".

CRITICAL RULES FOR UPDATING STATE:
1. INTENT: Set to "summary" if asking for counts/breakdowns. Set to "detail" if asking for raw rows/details.

1b. STATUS EXTRACTION (CRITICAL — DO NOT MISS):
   If the user's query contains a word that maps to a known ticket status, you MUST set the `status` field.
   Known status values and their trigger words:
   - Corporate tickets: "Open", "Closed", "In Progress", "Pending", "Cancelled", "Resolved"
   - PPM tickets:       "Open", "Closed", "Assigned", "In Progress", "Pending", "Cancelled"
   Trigger word examples:
     "assigned tickets"  → status: "Assigned"
     "closed tickets"    → status: "Closed"
     "open tickets"      → status: "Open"
     "in progress"       → status: "In Progress"
     "pending tickets"   → status: "Pending"
   These words are STATUS FILTERS, not generic descriptors. Always extract them into the `status` field.

2. ADDITIVE LOCATION MODE (NEW — CRITICAL):
   - If the user uses additive language for locations (e.g., "and also", "as well as", "along with", "plus", "and Mumbai too"),
     you MUST accumulate locations into a JSON array instead of overwriting.
   - Example: current branch_name is "Delhi", user says "and also Mumbai" → set branch_name to ["Delhi", "Mumbai"].
   - If branch_name is already a list, append the new location to it.
   - If the user mentions only ONE location with no additive language, treat it as a REPLACE (see rule 3).

3. OVERWRITE IT: If the user mentions a new entity of the same type with replacement language
   (e.g., changes "Delhi" to "Mumbai", or "Jan" to "Feb"), overwrite the old value with a plain string (not a list).

4. KEEP IT: If the user asks a follow-up (e.g., "what about closed ones?" or "give me detail about it"),
   KEEP all previous filters and only add the new one.

5. DOMAIN SHIFT: If the user explicitly switches from "PPM" to "Corporate" (or vice versa), change the "domain" field.

6. THE "ALL" COMMAND: If the user says "across all companies", "everywhere", or "clear filters",
   set company_name, branch_name, timeframe, status, priority, and service_type all to null.

7. dismissed_pills: You MUST always copy the existing dismissed_pills array as-is into the output.
   NEVER wipe or modify dismissed_pills. Current value: {json.dumps(existing_dismissed)}

8. last_updated: Always set this to the string "NOW" — the Python layer will replace it with the real timestamp.

Current State:
{json.dumps(current_state, indent=2)}

Output ONLY valid JSON matching this exact structure. Do not output markdown tags like ```json. Do not explain.
The JSON must have these exact keys: intent, domain, company_name, branch_name, timeframe, status, priority, service_type, dismissed_pills, last_updated
"""

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )

        raw_output = response.choices[0].message.content.strip()
        new_state = json.loads(raw_output)

        # --- PYTHON-LAYER HARDENING ---

        # 1. Always stamp real timestamp regardless of what LLM returned
        new_state["last_updated"] = datetime.utcnow().isoformat()

        # 2. Ensure dismissed_pills is never wiped by LLM
        if not isinstance(new_state.get("dismissed_pills"), list):
            new_state["dismissed_pills"] = existing_dismissed
        else:
            # Merge: keep any pills the LLM may have dropped from the existing list
            merged = list(set(existing_dismissed + new_state["dismissed_pills"]))
            new_state["dismissed_pills"] = merged

        # 3. Normalise branch_name: strip whitespace from list entries if it's a list
        bn = new_state.get("branch_name")
        if isinstance(bn, list):
            new_state["branch_name"] = [b.strip() for b in bn if b and b.strip()]
            # Collapse back to a string if only one item ended up in the list
            if len(new_state["branch_name"]) == 1:
                new_state["branch_name"] = new_state["branch_name"][0]

        return new_state

    except Exception as e:
        print(f"State Manager Error: {e}")
        fallback_state = current_state.copy()
        fallback_state["intent"] = "detail"
        fallback_state["last_updated"] = datetime.utcnow().isoformat()
        fallback_state["dismissed_pills"] = existing_dismissed
        return fallback_state