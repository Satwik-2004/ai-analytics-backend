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
            max_tokens=1500, 
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
    Generates a conversational summary or executive insight of the data. 
    Acts as a Senior Data Analyst providing agentic insights on dashboard charts.
    """
    # 1. STATE-AWARE NAMING
    domain = state.get("domain", "") if state else ""
    safe_domain = domain or "corporate_tickets" 
    ticket_type = "PPM tickets" if "ppm" in safe_domain.lower() else "corporate tickets"
    
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
        # Convert to clean JSON string (app.py already sliced this to top 50 rows)
        import json
        try:
            data_sample = json.dumps(raw_data)
        except Exception:
            data_sample = str(raw_data)
            
        prompt = f"""
        You are an elite Senior Data Analyst. 
        The user asked: "{user_query}"
        
        Here is the raw JSON data returned from the database for the visual chart:
        {data_sample}
        
        Your Task: Provide a sharp, executive-level insight based ONLY on this data.
        
        Strict Rules:
        1. Do not narrate the data: Never say "Here is a breakdown..." or list out the rows. The user can already see the visual chart!
        2. Find the Anomaly/Leader: Identify the highest performer, the lowest performer, or a distinct trend. If it's just a single total number, give a quick thought on it.
        3. Be Concise: Maximum 2 to 3 sentences. Get straight to the point.
        4. Suggest a Next Step: Always end with one logical follow-up question the user could ask to drill deeper (e.g., "Would you like me to break this down by branch?").
        5. Format: Output ONLY the insight text. No markdown, no code blocks, no robotic greetings.
        """
    
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, # Slightly adjusted for analytical reasoning
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Summary Generation Error: {e}")
        # 2. GRACEFUL FALLBACK: If the LLM times out but we HAVE data, don't lie to the user!
        if raw_data:
            return f"Here is the requested data regarding {ticket_type}. Please see the chart below for details."
        else:
            return "I could not find data matching that request. Please try asking about a specific ticket ID or category."