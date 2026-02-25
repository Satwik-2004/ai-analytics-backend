from openai import AsyncOpenAI
from config import settings

# Initialize the Async Client to point to Gemini's free API
client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
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
            max_tokens=1500, # Increased from 300 to allow complex JOINs
            top_p=1.0
        )
        
        raw_sql = response.choices[0].message.content.strip()
        clean_sql = raw_sql.replace("```sql", "").replace("```", "").strip()
        
        return clean_sql

    except Exception as e:
        print(f"LLM Generation Error: {e}")
        return ""

async def generate_human_summary(user_query: str, raw_data: list, error_msg: str = None) -> str:
    if error_msg or not raw_data:
        prompt = f"""
        You are a helpful corporate data assistant.
        The user asked: "{user_query}"
        We could not retrieve any data for this specific request.
        Write a polite, 2-sentence conversational response.
        Apologize that you couldn't find exact data for that specific phrasing.
        Suggest they ask about general metrics like 'closed tickets', 'tickets by service category', or 'specific ticket IDs'.
        Do not use markdown formatting.
        """
    else:
        data_sample = raw_data[:5]
        row_count = len(raw_data)
        prompt = f"""
        You are a helpful, professional corporate data assistant. 
        The user asked: "{user_query}"
        The database returned {row_count} rows. Here is a sample of the raw data: {data_sample}
        Write a 2 to 3 sentence conversational summary of this data to answer the user's question. 
        If it is a specific ticket, mention its current status and a brief note about its history.
        Do not use markdown formatting. Do not output the raw JSON.
        """
    
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary Generation Error: {e}")
        return "I could not find data matching that request. Please try asking about a specific ticket ID or category."
