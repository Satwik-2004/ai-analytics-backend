from openai import AsyncOpenAI
from config import settings

# Initialize the Async Client to point to Gemini's free API
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

async def generate_sql(prompt: str) -> str:
    """
    Calls the LLM to generate SQL based on the strict prompt.
    Enforces temperature=0 for deterministic outputs.
    """
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": "You are a strict MySQL compiler. Output ONLY raw valid SQL. No markdown, no backticks, no text."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=300,
            top_p=1.0
        )
        
        raw_sql = response.choices[0].message.content.strip()
        clean_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
        
        return clean_sql

    except Exception as e:
        print(f"LLM Generation Error: {e}")
        return ""