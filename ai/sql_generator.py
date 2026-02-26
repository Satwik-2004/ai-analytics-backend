import json
from openai import AsyncOpenAI
from config import settings

# Initialize the Async Client to point to Groq/Gemini's API
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

async def generate_human_summary(user_query: str, raw_data: list, state: dict = None, error_msg: str = None) -> str:
    """
    Generates a conversational summary of the data. 
    Now strictly aware of the active JSON State to prevent mislabeling ticket types.
    """
    # 1. STATE-AWARE NAMING: Check the memory to know exactly what we are looking at.
    domain = state.get("domain", "") if state else ""
    ticket_type = "PPM tickets" if "ppm" in domain.lower() else "corporate tickets"

    if error_msg or not raw_data:
        prompt = f"""
        You are a helpful data assistant.
        The user asked: "{user_query}"
        We could not retrieve any data for this specific request.
        Write a polite, 2-sentence conversational response apologizing.
        Suggest they ask about general metrics like 'closed tickets', 'tickets by service category', or 'specific ticket IDs'.
        Do not use markdown formatting.
        """
    else:
        # Convert safely to string to prevent JSON parsing crashes
        data_sample = str(raw_data[:5])
        row_count = len(raw_data)
        
        prompt = f"""
        You are a helpful, professional corporate data assistant. 
        The user asked: "{user_query}"
        The database returned {row_count} rows of {ticket_type}. 
        Here is a sample of the raw data: {data_sample}
        
        Write a 2 to 3 sentence conversational summary of this data to answer the user's question. 
        If it is a specific ticket, mention its current status and a brief note about its history.
        
        CRITICAL NAMING RULES (DO NOT IGNORE):
        1. You MUST refer to the data explicitly as "{ticket_type}". NEVER guess the ticket type.
        2. If the user filtered by a specific Branch or Company name, you MUST explicitly mention that exact name in your summary.
        3. THE DRILL-DOWN INVITE: If the data is a summary/breakdown (like a count by company, status, or branch), end your response by inviting the user to zoom in. (e.g., "If you'd like to see the specific details or zoom in on a particular company, just let me know!")
        
        Do not use markdown formatting. Do not output the raw JSON.
        """
    
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2, 
            max_tokens=200
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary Generation Error: {e}")
        # 2. GRACEFUL FALLBACK: If the LLM times out but we HAVE data, don't lie to the user!
        if raw_data:
            return f"Here is the requested data regarding {ticket_type}. Please see the table below for details."
        else:
            return "I could not find data matching that request. Please try asking about a specific ticket ID or category."