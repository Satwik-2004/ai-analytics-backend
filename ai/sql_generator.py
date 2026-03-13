import json
from openai import AsyncOpenAI
from config import settings

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# Sentinel returned when the LLM call itself fails (network error, timeout, etc.)
# Distinct from empty string so the caller can skip validation entirely.
SQL_GENERATION_FAILED = "__GENERATION_FAILED__"

# ---------------------------------------------------------------------------
# RESPONSE CLASSIFICATION
# ---------------------------------------------------------------------------
# Before generating a summary, we classify what kind of data came back so
# the prompt is tailored accordingly — instead of one generic "analyst" prompt
# trying to handle 5 different data shapes.
#
# COMPANY_BREAKDOWN  — multi-row, each row is a different company/entity + count
# TIME_TREND         — rows grouped by time period (month, quarter, year)
# STATUS_DIST        — rows grouped by status/priority/type
# SINGLE_KPI         — exactly 1 row, 1-2 columns (a total or single metric)
# DETAIL_LIST        — raw ticket rows (detail intent)
# ---------------------------------------------------------------------------

def _classify_response(rows: list, intent: str) -> str:
    if not rows:
        return "EMPTY"
    if intent == "detail":
        return "DETAIL_LIST"

    if len(rows) == 1:
        return "SINGLE_KPI"

    sample = rows[0]
    keys = [k.lower() for k in sample.keys()]

    # Time trend: first column contains time/date-related key
    time_keys = ("timeperiod", "month", "year", "quarter", "date", "period", "ppmdate", "createddate")
    if any(any(t in k for t in time_keys) for k in keys):
        return "TIME_TREND"

    # Status/priority distribution: first column is a status-like field
    dist_keys = ("status", "currentstatus", "priority", "type", "category", "servicetype")
    if any(any(d in k for d in dist_keys) for k in keys):
        return "STATUS_DIST"

    # Default for multi-row grouped data = company/entity breakdown
    return "COMPANY_BREAKDOWN"


# ---------------------------------------------------------------------------
# SQL GENERATION
# ---------------------------------------------------------------------------

async def generate_sql(prompt: str) -> str:
    """
    Calls the LLM to generate SQL based on the strict prompt.
    Returns raw SQL text, a CLARIFY: message, a security block message,
    or SQL_GENERATION_FAILED if the API call itself errors out.
    """
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict MySQL compiler. "
                        "Output ONLY raw valid SQL. "
                        "No markdown, no backticks, no explanatory text."
                    )
                },
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
        print(f"LLM SQL Generation Error: {e}")
        return SQL_GENERATION_FAILED


# ---------------------------------------------------------------------------
# HUMAN SUMMARY — with No-Overpromising Guardrail
# ---------------------------------------------------------------------------

async def generate_human_summary(
    user_query: str,
    raw_data: list,
    state: dict = None,
    error_msg: str = None
) -> str:
    """
    Generates a conversational summary or executive insight of the data.

    Key improvements:
    - Classifies the response type BEFORE prompting the LLM.
    - Injects a strict NO-OVERPROMISING guardrail to prevent the LLM from
      offering to "investigate factors", "interview staff", or do things
      outside its DB-only scope.
    - Each response type gets a tailored prompt for better quality.
    - All next-step suggestions are constrained to database pivots only,
      which directly aligns with the Smart Pills shown in the UI.
    """
    domain = (state.get("domain", "") if state else "") or "corporate_tickets"
    ticket_label = "PPM tickets" if "ppm" in domain.lower() else "corporate tickets"

    # ── ERROR PATH ────────────────────────────────────────────────────────
    if error_msg or not raw_data:
        prompt = (
            f'You are a helpful data assistant.\n'
            f'The user asked: "{user_query}"\n'
            f'We could not retrieve any data for this specific request.\n'
            f'Write a polite, 2-sentence response.\n'
            f'Suggest they try a different filter combination, a specific company name, '
            f'or a different timeframe.\n'
            f'Do NOT use markdown. Do NOT offer to investigate anything external.'
        )
        max_tokens = 200

    # ── HAPPY PATH — tailored by response type ────────────────────────────
    else:
        response_type = _classify_response(raw_data, state.get("intent", "detail") if state else "detail")

        try:
            data_sample = json.dumps(raw_data[:50])
        except Exception:
            data_sample = str(raw_data[:50])

        # ── SHARED GUARDRAIL — injected into every summary prompt ─────────
        # This is the core fix: hard constraints that prevent the LLM from
        # writing checks the system cannot cash.
        NO_OVERPROMISING_RULES = """
CRITICAL BOUNDARIES — YOU MUST FOLLOW THESE OR YOUR RESPONSE IS WRONG:
1. You only have access to structured database columns: Company, Branch, Timeframe,
   Status, Priority, Service Type, and ticket counts. Nothing else.
2. You CANNOT read emails, interview staff, access external systems, or determine
   real-world root causes.
3. NEVER offer to "investigate the factors", "look into the reasons", "find out why",
   or perform any analysis outside of querying this database.
4. If you suggest a next step, it MUST be a database filter pivot:
   - BAD:  "Would you like me to explore the factors contributing to this?"
   - BAD:  "I can investigate the spike in May further."
   - GOOD: "Would you like to break this down by Branch to isolate the spike?"
   - GOOD: "Filtering by Service Type may reveal which category is driving this."
5. Keep suggestions concrete: mention specific columns like Branch, Status,
   Service Type, Company, or Timeframe — not vague "further analysis"."""

        # ── PROMPT BY RESPONSE TYPE ────────────────────────────────────────

        if response_type == "COMPANY_BREAKDOWN":
            prompt = (
                f'You are a Senior Data Analyst presenting company-level ticket metrics.\n'
                f'The user asked: "{user_query}"\n\n'
                f'Data (all companies shown — complete dataset):\n{data_sample}\n\n'
                f'Write a 2-3 sentence executive summary:\n'
                f'1. Identify the top company by volume and state its count.\n'
                f'2. Note the bottom performer or widest spread if interesting.\n'
                f'3. End with ONE actionable database pivot (e.g., break down by branch '
                f'or filter by a specific status).\n'
                f'{NO_OVERPROMISING_RULES}\n\n'
                f'Output ONLY the insight text. No markdown, no greetings, no headers.'
            )

        elif response_type == "TIME_TREND":
            prompt = (
                f'You are a Senior Data Analyst identifying trends over time.\n'
                f'The user asked: "{user_query}"\n\n'
                f'Time-series data:\n{data_sample}\n\n'
                f'Write a 2-3 sentence insight:\n'
                f'1. Identify the peak period and its value.\n'
                f'2. Note the lowest period OR describe the trend direction '
                f'(rising, falling, or stable).\n'
                f'3. Suggest ONE database pivot to drill deeper '
                f'(e.g., "break down {data_sample[:30]}... by Status or Branch").\n'
                f'{NO_OVERPROMISING_RULES}\n\n'
                f'Output ONLY the insight text. No markdown, no greetings, no headers.'
            )

        elif response_type == "STATUS_DIST":
            prompt = (
                f'You are a Senior Data Analyst presenting a status or category breakdown.\n'
                f'The user asked: "{user_query}"\n\n'
                f'Distribution data:\n{data_sample}\n\n'
                f'Write a 2-3 sentence summary:\n'
                f'1. State the dominant status/category and its count or percentage.\n'
                f'2. Call out any unusually high or low category if present.\n'
                f'3. Suggest ONE follow-up database filter '
                f'(e.g., by Company, Branch, or Timeframe).\n'
                f'{NO_OVERPROMISING_RULES}\n\n'
                f'Output ONLY the insight text. No markdown, no greetings, no headers.'
            )

        elif response_type == "SINGLE_KPI":
            prompt = (
                f'You are a Senior Data Analyst presenting a single metric.\n'
                f'The user asked: "{user_query}"\n\n'
                f'Result: {data_sample}\n\n'
                f'Write 1-2 sentences:\n'
                f'1. State the number clearly in plain English.\n'
                f'2. Suggest ONE way to slice this further using the database '
                f'(e.g., break it down by Status, Company, or Branch).\n'
                f'{NO_OVERPROMISING_RULES}\n\n'
                f'Output ONLY the insight text. No markdown, no greetings, no headers.'
            )

        else:
            # DETAIL_LIST — raw rows, no LLM insight needed, fast-pass handled
            # in pipeline.py. This path is a safety fallback.
            return f"Retrieved {len(raw_data)} {ticket_label}."

        max_tokens = 160

    # ── LLM CALL ──────────────────────────────────────────────────────────
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"Summary Generation Error: {e}")
        if raw_data:
            return (
                f"Here is the requested data for {ticket_label}. "
                f"Please review the results below."
            )
        return (
            "I could not retrieve data matching that request. "
            "Please try a different filter combination."
        )