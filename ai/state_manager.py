import json
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# This defines the structure of our memory
DEFAULT_STATE = {
    "intent": "detail", # 'summary' or 'detail'
    "domain": "corporate_tickets", # 'corporate_tickets' or 'ppm_tickets'
    "company_name": None,
    "branch_name": None,
    "timeframe": None,
    "status": None,
    "priority": None,
    "service_type": None
}

async def update_state(user_query: str, current_state: dict = None) -> dict:
    """
    Takes the user's query and the current JSON state, 
    and asks the LLM to intelligently update the state.
    """
    if current_state is None:
        current_state = DEFAULT_STATE

    system_prompt = f"""You are the central State Manager for a database AI.
Your job is to read the User's Request, look at the Current State, and output an updated JSON State.

CRITICAL RULES FOR UPDATING STATE:
1. INTENT: Set to "summary" if asking for counts/breakdowns. Set to "detail" if asking for raw rows/details.
2. KEEP IT: If the user asks a follow-up (e.g., "what about closed ones?"), KEEP all previous filters and add the new one.
3. OVERWRITE IT: If the user mentions a new entity of the same type (e.g., changes "Delhi" to "Mumbai", or "Jan" to "Feb"), overwrite the old value.
4. DOMAIN SHIFT: If the user explicitly switches from "PPM" to "Corporate" (or vice versa), change the "domain" field.
5. THE "ALL" COMMAND: If the user says "across all companies", "everywhere", or "clear filters", change those fields to null.

Current State:
{json.dumps(current_state, indent=2)}

Output ONLY valid JSON matching this exact structure. Do not output markdown tags like ```json. Do not explain.
"""

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL, # Ensure this is your 70B model!
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0,
            response_format={"type": "json_object"} # Forces strict JSON output
        )
        
        raw_output = response.choices[0].message.content.strip()
        new_state = json.loads(raw_output)
        return new_state
        
    except Exception as e:
        print(f"State Manager Error: {e}")
        # Fallback to default state if it fails
        fallback_state = current_state.copy()
        fallback_state["intent"] = "detail" 
        return fallback_state