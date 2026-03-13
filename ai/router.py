import json
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# Fields from state that are analytically meaningful to the router.
# Excludes noise like dismissed_pills, last_updated, domain internals.
_ROUTER_STATE_FIELDS = (
    "company_name", "branch_name", "timeframe", "status",
    "priority", "service_type", "domain"
)


def _summarise_state(state: dict) -> str:
    """
    Serialises only the analytically relevant state fields for the router prompt.
    Prevents dismissed_pills / last_updated / domain internals from bloating
    the context and confusing the LLM.
    """
    if not state:
        return "No active filters."
    relevant = {k: state[k] for k in _ROUTER_STATE_FIELDS if state.get(k)}
    if not relevant:
        return "No active filters."
    return json.dumps(relevant)


async def route_user_query(user_prompt: str, active_state: dict = None) -> dict:
    """
    First line of defence. Classifies the user's message into one of four intents
    before any state update or DB work happens.

    Intents:
      DATABASE        — query/filter/summarise tickets, branches, companies, metrics.
      CHITCHAT        — greetings, thanks, goodbye, social pleasantries.
      CONTEXT_QUESTION — question about the currently active filters or visible data
                         (e.g., "Is this from 2025?", "What company is filtered?").
                         Answered directly from state without a DB round-trip.
      UNSUPPORTED     — HR, payroll, coding help, general web knowledge.

    Splitting CHITCHAT and CONTEXT_QUESTION prevents the LLM from writing a
    generic "I can help with tickets!" response when the user is asking a
    legitimate question about their current view.

    Fails open to DATABASE on any exception — a failed router must not block
    a legitimate query.
    """
    state_summary = _summarise_state(active_state)

    system_prompt = f"""You are the Intent Router for the Techxpert ticketing database AI assistant.
The user's current active search filters are: {state_summary}

Classify the user's message into EXACTLY ONE of these four intents:

1. DATABASE — user wants to search, filter, count, or summarise ticket data,
   maintenance records, branches, or companies.

2. CHITCHAT — pure social message: hello, thanks, bye, "great job", etc.
   No data question involved.

3. CONTEXT_QUESTION — user is asking about the data currently on their screen
   or about the active filters shown above (e.g., "Is this data from 2025?",
   "Which company is this?", "How many did you just fetch?").
   Use the active filters to answer directly in response_text.

4. UNSUPPORTED — completely outside the Techxpert ticketing domain: HR,
   payroll, coding help, general web questions, competitor systems.

Output ONLY valid JSON in this exact structure. No extra keys, no markdown:
{{
    "intent": "DATABASE" | "CHITCHAT" | "CONTEXT_QUESTION" | "UNSUPPORTED",
    "response_text": "For CHITCHAT / CONTEXT_QUESTION / UNSUPPORTED: write a polite 1-2 sentence response. For DATABASE: null.",
    "suggested_actions": ["2-3 short button labels to guide the user back to useful queries"]
}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User message: {user_prompt}"}
            ],
            temperature=0.0,
            max_tokens=120,  # Router output is a small JSON object — cap tightly
            response_format={"type": "json_object"}
        )

        raw_content = response.choices[0].message.content
        route_info = json.loads(raw_content)

        intent = route_info.get("intent", "DATABASE")

        # Normalise CONTEXT_QUESTION — the rest of app.py only checks for
        # CHITCHAT and UNSUPPORTED to decide whether to short-circuit.
        # CONTEXT_QUESTION should also short-circuit (it answers from state),
        # so map it to CHITCHAT for the caller's branching logic.
        # The response_text will contain the state-aware answer.
        if intent == "CONTEXT_QUESTION":
            intent = "CHITCHAT"

        return {
            "intent": intent,
            "response_text": route_info.get("response_text"),
            "suggested_actions": route_info.get("suggested_actions", [])
        }

    except Exception as e:
        print(f"Router Exception: {e}")
        return {
            "intent": "DATABASE",
            "response_text": None,
            "suggested_actions": []
        }