import json
from openai import AsyncOpenAI
from config import settings

# Initialize the Async Client to point to Groq/Gemini's API
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# NEW: Added 'active_state' as the second argument
async def route_user_query(user_prompt: str, active_state: dict = None) -> dict:
    """
    Acts as the first line of defense. Classifies the user's intent to prevent
    wasting database resources on chit-chat or out-of-scope questions.
    Now state-aware so it can answer context-dependent questions!
    """
    
    # NEW: Format the state so the LLM knows what is currently filtered
    state_context = f"The user's current active search filters are: {active_state}" if active_state else "No active filters."

    system_prompt = f"""
    You are the Intent Router for the Techxpert ticketing database AI assistant.
    {state_context}
    
    Your job is to classify the user's message into exactly ONE of three categories:
    
    1. 'DATABASE': The user is asking to search, filter, or summarize tickets, maintenance, branches, companies, or metrics.
    2. 'CHITCHAT': The user is saying hello, thanks, goodbye, OR they are asking a simple clarification question about their current active filters (e.g., "Is this data from 2025?", "What company is this?").
    3. 'UNSUPPORTED': The user is asking for HR, payroll, marketing, coding help, or general web knowledge completely outside of the Techxpert ticketing system.

    If the user asks a clarification question about the data on their screen, use the active search filters to answer them directly in the 'response_text' and classify as CHITCHAT!

    You MUST output ONLY valid JSON in this exact format:
    {{
        "intent": "DATABASE" | "CHITCHAT" | "UNSUPPORTED",
        "response_text": "If CHITCHAT or UNSUPPORTED, write a polite 1-2 sentence response guiding them back to your database capabilities. If DATABASE, leave as null.",
        "suggested_actions": ["List 2 to 3 short button labels (e.g., 'Search Corporate Tickets') to guide the user"]
    }}
    """

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL, 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User Message: {user_prompt}"}
            ],
            temperature=0, 
            response_format={"type": "json_object"} 
        )
        
        raw_content = response.choices[0].message.content
        route_info = json.loads(raw_content)
        
        return {
            "intent": route_info.get("intent", "DATABASE"),
            "response_text": route_info.get("response_text", None),
            "suggested_actions": route_info.get("suggested_actions", [])
        }
        
    except Exception as e:
        print(f"Router Exception: {e}")
        return {
            "intent": "DATABASE",
            "response_text": None,
            "suggested_actions": []
        }