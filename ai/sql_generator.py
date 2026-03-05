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
    Generates a conversational summary of the data. 
    Now strictly aware of the active JSON State and the dynamic shape of the data.
    """
    # 1. STATE-AWARE NAMING: Check the memory to know exactly what we are looking at.
    domain = state.get("domain", "") if state else ""
    # Fallback to corporate_tickets if domain is completely None/Empty
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
        # Convert safely to string to prevent JSON parsing crashes
        data_sample = str(raw_data[:5])
        row_count = len(raw_data)
        
        prompt = f"""
        You are a helpful, professional corporate data assistant. 
        The user asked: "{user_query}"
        The database returned a result set containing {row_count} rows. 
        Here is a sample of the top records in the data: {data_sample}
        
        Write a 2 to 3 sentence conversational summary of this data. 
        
        CRITICAL NAMING RULES:
        1. DYNAMIC CONTEXT (Total Count vs Top Results): 
           - IF the data sample contains a column like `TotalTickets` or `TotalCount` and NO grouping names, this is a GRAND TOTAL. State the exact number from the sample (e.g., "There are a total of X {ticket_type} matching your search.").
           - IF the data contains `TicketID`, say "We fetched {row_count} individual {ticket_type} records..."
           - IF the data contains grouped columns (like CompanyName or BranchSite), say "We found {row_count} unique branches/companies..." and highlight the top 1 or 2 results from the sample data.
        2. THE LIMIT WARNING (CRITICAL):
           - If {row_count} is exactly {settings.MAX_ROWS_LIMIT} (or exactly 500), explicitly tell the user: "Note: We fetched the maximum display limit of {settings.MAX_ROWS_LIMIT} results, but there may be more in the database."
        3. NO MATH ALLOWED: NEVER attempt to add, sum, or calculate totals from the data yourself. 
        4. TOP RESULTS: State the highest/top result factually based ONLY on the numbers provided.
        
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