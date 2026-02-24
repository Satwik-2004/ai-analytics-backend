from openai import AsyncOpenAI
from config import settings

# Initialize the Async Client to point to Gemini's free API
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

async def classify_intent(user_query: str) -> str:
    """
    Classifies the user's query intent as either 'summary' or 'detail'.
    Optimized to return a single word to prevent JSON parsing errors.
    """
    system_prompt = (
        "You are a routing agent. Read the user's query and reply with EXACTLY ONE WORD.\n"
        "Reply 'SUMMARY' if the user wants counts, totals, charts, or breakdowns (e.g., 'how many', 'by status', 'overview').\n"
        "Reply 'DETAIL' if the user wants raw data rows (e.g., 'show me tickets', 'list the open ones', 'details for 1234').\n\n"
        "DO NOT use markdown. DO NOT explain. JUST ONE WORD: SUMMARY or DETAIL."
    )

    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0, # Zero creativity
            max_tokens=5     # We only need one word!
        )
        
        # Safely extract the single word
        raw_content = response.choices[0].message.content.strip().upper()
        
        # Route based on the word
        if "SUMMARY" in raw_content:
            return "summary"
        else:
            return "detail"
            
    except Exception as e:
        print(f"Intent Classification Error: {e}")
        return "detail"