from config import settings
from datetime import datetime

# The Complete V4 Relational Data Dictionary (Hierarchical Domains)
SCHEMA_DEFINITION = """
=== DOMAIN 1: CORPORATE TICKETS (Reactive/General) ===
1. Table: `corporate_tickets` (Core Table)
   - Columns: ID (int PK), TicketID (varchar), CorporateID (int FK -> company.ID), BranchID (int FK -> branch.ID), Type (varchar), Service (varchar), Subservice (varchar), Price, Status, Priority, CreatedDate, CreatedTime, CreatedBy.

2. Table: `corporate_ticket_status_history`
   - Columns: ID (int PK), TicketID (varchar FK), Status (varchar), Remarks (varchar), CreatedDate (date), CreatedTime (time), CreatedBy (varchar).

3. Table: `corporate_ticket_general_service_report`
   - Columns: ID (int PK), TicketID (int FK), Type (varchar), ProblemReportedByClient (text), Observation (text), ActionTaken (text), Remarks (text), ClientRepresentative (varchar), CreatedDate (varchar), CreatedBy (varchar).

4. Table: `corporate_ticket_general_service_report_items`
   - Columns: ID (int PK), TicketID (varchar FK), GSRID (int FK), ItemDescription (varchar), Quantity (int).

5. Table: `corporate_tickets_old` (Archive)
   - Columns: ID (int PK), TicketID (varchar FK), CorporateID, BranchID, Type, Status, CreatedDate, CloseDate.

6. Table: `corporate_tickets_uploader` (Staging)
   - Columns: ID (int PK), ClientTicketID, BranchCode, BranchID, Category, Status, IsParsed, Inserted.

=== DOMAIN 2: PPM TICKETS (Planned Preventive Maintenance) ===
7. Table: `ppm_tickets` (Core Table)
   - Columns: ID (int PK), TicketID (varchar), CorporateID (int FK -> company.ID), BranchID (int FK -> branch.ID), BranchAssetID (varchar), PPMDate (varchar), CreatedDate (varchar), CreatedTime (varchar), CloseDate (varchar), CloseTime (varchar), CreatedBy (varchar), DueDate (varchar), AssignedTo (int FK -> employees.ID), Status (varchar), IsActive (int).
   - CRITICAL NOTE: This table DOES NOT have `Priority`, `Type`, `Service`, `Subservice`, or `Price` columns. Do not select them. Priority is in `ppm_ticket_status`.
   
8. Table: `ppm_ticket_status` (Lookup/Properties)
   - Columns: ID (int PK), Status (varchar), Color (varchar), Priority (int), AccountBranchManager (int), DisplayPriority (int), IsActive (int).

9. Table: `ppm_ticket_general_service_report`
   - Columns: ID (int PK), TicketID (int FK), ProblemReportedByClient, Observation, ActionTaken, Remarks, EquipmentDetails, SerialNo, Capacity, RefrigerantType, MakeModel, CreatedDate, CreatedBy.

10. Table: `ppm_ep_service_report` (Electrical Panel)
    - Columns: ID (int PK), TicketID (int FK), ServiceReportID (int), AssetCondition (varchar), EarthingResistance, Frequency, Current, PowerFactor, Supply1PhaseVoltage, Supply3PhaseVoltage, CreatedDate.

11. Table: `ppm_fire_extinguisher_service_report`
    - Columns: ID (int PK), TicketID (int FK), ServiceReportID (int), AssetCondition (varchar), CreatedDate.

12. Table: `ppm_hvac_service_report`
    - Columns: ID (int PK), TicketID (int FK), ServiceReportID (int), AssetCondition (varchar), GrillTemperature, AmbientTemperature, RoomTemperature, IndoorFan, ReturnAirTemperature, SupplyAirTemperature, Compressor, Voltage, TotalCurrent, OutdoorFan, CreatedDate.

13. Table: `ppm_ups_service_report`
    - Columns: ID (int PK), TicketID (int FK), ServiceReportID (int), AssetCondition (varchar), IRValue, EarthingVoltage, OutputVoltage, ChargingVoltage, CurrentLoad, CreatedDate.

=== DOMAIN 3: ORGANIZATIONAL HIERARCHY ===
14. Table: `corporate` (Master Entity)
    - Columns: ID (int PK), CorporateName (varchar), CorporateGST, CoporateAddress, CreatedBy, CreatedDate, IsActive (int).

15. Table: `company` (Corporate-to-Ticket Link)
    - Columns: ID (int PK), CorporateName (int FK -> corporate.ID), CompanyName (varchar), CompanyEmail, CompanyPhone, IsActive (int).
    - NOTE: Ticket tables (CorporateID) link to this table's ID.

16. Table: `branch` (Location Link)
    - Columns: ID (int PK), CompanyID (int FK -> corporate.ID), BranchSite (varchar), BranchCode, BranchEmail, BranchCity, BranchState, IsActive (int).
    - NOTE: This links directly to corporate.ID, not company.ID.

17. Table: `branch_assets` (Equipment Link)
    - Columns: ID (int PK), BranchID (int FK -> branch.ID), EquipmentName, Make, Model, SNo, Capacity, Category, SubCategory, IsActive (int).

18. Table: `employees` (Staff Link)
    - Columns: ID (int PK), Name (varchar), Email (varchar), IsActive (int).
    - NOTE: Ticket tables (AssignedTo) link to this table's ID.
"""

# ---------------------------------------------------------------------------
# WILDCARD HELPER
# Centralises the "chop to N chars" logic so the rule is consistent
# between the prompt text and any future Python-side post-processing.
#
# Rules:
#   - Multi-word phrases (contain a space) → use FULL name, no chopping.
#     Reason: "%Uttar%" would also match "Uttarakhand". Exact phrase is safer.
#   - Single-word names with < MIN_WILDCARD_CHARS characters → use FULL name.
#     Reason: Chopping "Goa" to "%Goa" is fine, but chopping to 4 chars gives
#     "%Goa" anyway. The real danger is a 3-letter name like "Goa" being chopped
#     to 3 letters and matching unrelated substrings. We still use it as-is.
#   - Single-word names with >= MIN_WILDCARD_CHARS characters → chop to first
#     MIN_WILDCARD_CHARS letters with wildcards to catch typos.
# ---------------------------------------------------------------------------
MIN_WILDCARD_CHARS = 5  # e.g. "Mumbai" (6) → "%Mumba%", "Pune" (4) → "%Pune%"


def _wildcard_rule_description() -> str:
    """Returns the wildcard rule text injected into the prompt."""
    return f"""
    - ANTI-SPELLING BUG & SMART WILDCARDS (CRITICAL):
      * Multi-word locations (e.g., "Uttar Pradesh", "Tamil Nadu", "West Bengal"):
        ALWAYS use the FULL name in the LIKE clause (e.g., `LIKE '%Uttar Pradesh%'`).
        NEVER chop multi-word names — partial matches cause overlap bugs
        (e.g., `LIKE '%Uttar%'` would also pull Uttarakhand tickets).
      * Single-word names with {MIN_WILDCARD_CHARS} or more characters (e.g., "Mumbai" = 6 chars):
        Chop to the first {MIN_WILDCARD_CHARS} characters with wildcards to catch typos
        (e.g., "Mumbai" → `LIKE '%Mumba%'`, "Chennai" → `LIKE '%Chenn%'`).
      * Single-word names with fewer than {MIN_WILDCARD_CHARS} characters (e.g., "Goa" = 3, "Pune" = 4):
        Use the FULL name with wildcards (e.g., `LIKE '%Goa%'`, `LIKE '%Pune%'`).
        DO NOT chop short names further — they are already short enough to be precise.
"""


def _branch_where_clause_description(ticket_alias: str) -> str:
    """
    Returns the branch/location WHERE clause instruction, now aware that
    branch_name in the state can be either a plain string OR a list of strings
    (for additive OR queries like "Delhi and Mumbai").
    """
    return f"""
    - BRANCH / LOCATION (CRITICAL FIX): If Branch Name is provided in the state
      (which could be a building, city, or state), you MUST `LEFT JOIN branch`
      (ON {ticket_alias}.BranchID = branch.ID).

      IMPORTANT — branch_name can now be a LIST (for multi-location queries):
      * If branch_name is a plain string (e.g., "Delhi"):
        Search across ALL location columns simultaneously:
        `(branch.BranchSite LIKE '%Del%' OR branch.BranchCity LIKE '%Del%' OR branch.BranchState LIKE '%Del%')`
      * If branch_name is a JSON array (e.g., ["Delhi", "Mumbai"]):
        Build a combined OR block that covers ALL location columns for EACH entry:
        ```
        (
          (branch.BranchSite LIKE '%Del%' OR branch.BranchCity LIKE '%Del%' OR branch.BranchState LIKE '%Del%')
          OR
          (branch.BranchSite LIKE '%Mumba%' OR branch.BranchCity LIKE '%Mumba%' OR branch.BranchState LIKE '%Mumba%')
        )
        ```
        Wrap the entire multi-location block in outer parentheses so it doesn't
        break surrounding AND logic.

      Apply the wildcard rules below for each individual location name.
{_wildcard_rule_description()}
"""


def build_sql_prompt(user_query: str, state: dict) -> str:
    # 1. DYNAMIC DATE CALCULATION
    current_date = datetime.now().strftime("%B %d, %Y")
    current_year = datetime.now().strftime("%Y")
    current_month_num = datetime.now().strftime("%m")

    # Extract intent and domain from state
    intent = state.get("intent", "detail")
    target_domain = state.get('domain') or 'corporate_tickets'

    # Dynamically determine the exact base table, alias, and the correct DATE COLUMN
    is_ppm = "ppm" in target_domain.lower()
    base_table = "ppm_tickets pt" if is_ppm else "corporate_tickets ct"
    ticket_alias = "pt" if is_ppm else "ct"
    date_col = "PPMDate" if is_ppm else "CreatedDate"

    # Intent-aware row limits
    # Both intents cap at MAX_ROWS_LIMIT (500) at the DB/SQL level.
    # The 50-row distinction is applied ABOVE the DB (in pipeline.py):
    #   - Summary: all rows returned, every company/status visible in charts.
    #   - Detail:  DB returns up to 500; pipeline.py slices to DETAIL_PREVIEW_LIMIT (50)
    #              for the API response and reports the honest total in summary text.
    # Capping summary SQL at 50 was wrong — it hid real companies from the breakdown.
    SUMMARY_LIMIT = settings.MAX_ROWS_LIMIT  # 500 — full grouped result, never hide rows
    DETAIL_LIMIT  = settings.MAX_ROWS_LIMIT  # 500 — pipeline further slices for display

    base_instructions = f"""You are an elite MySQL data analyst.
Convert the user's natural language request into a highly optimized, read-only SELECT query.

{SCHEMA_DEFINITION}

CRITICAL RULES:
1. STRICT SECURITY BOUNDARY (SUPERSEDES ALL): You do NOT have access to finance, billing, quotation, or payment tables. If requested, DO NOT write SQL. Output exactly: `I do not have access to financial or billing records for security reasons.`
2. OUTPUT FORMAT: Output ONLY raw valid SQL. You MUST start your query with the `SELECT` keyword. Never omit `SELECT`. No markdown formatting, no `sql` tags, and absolutely NO conversational filler.
3. ALWAYS USE ALIASES: Use table aliases for every column (e.g., `{ticket_alias}.TicketID`, NOT `TicketID`).
4. LIMIT RESULTS (INTENT-AWARE — CRITICAL):
   - SUMMARY queries (GROUP BY / COUNT / AVG): Always append `LIMIT {SUMMARY_LIMIT}`.
     Rationale: Return ALL grouped rows so every company/status appears in the chart.
     A company breakdown can have 300+ companies — a low LIMIT silently hides real data.
   - DETAIL queries (raw ticket lists): Always append `LIMIT {DETAIL_LIMIT}`.
     Rationale: Raw lists can legitimately be large — use the full configured cap.
5. MANDATORY BASE TABLE (CRITICAL FIX): You are FORBIDDEN from writing `FROM company`, `FROM corporate`, or `FROM branch`. Your query MUST begin EXACTLY with: `FROM {base_table}`. To get a list of companies or branches, you MUST query `{base_table}` and `LEFT JOIN` the company/branch tables!
6. VALID JOINS ONLY (CRITICAL KEY MAPPINGS):
    - For standard tables, join on the indicated Foreign Keys.
    - PPM SERVICE REPORTS FIX: Tables like `ppm_hvac_service_report`, `ppm_ep_service_report`, etc., have a `TicketID` column that is an INT. This references `ppm_tickets.ID` (the integer primary key). You MUST join them like this: `JOIN ppm_hvac_service_report ON ppm_hvac_service_report.TicketID = ppm_tickets.ID`.
7. NO COLUMN HALLUCINATION: Only use exact columns listed in the schema. CRITICAL: Do not ask for `Type`, `Service`, `Subservice`, or `Price` when querying `ppm_tickets`.
8. NEVER USE `*` WITH JOINS: Explicitly select relevant columns from both tables.
9. AMBIGUOUS STATUS: Always alias Status columns when joining (e.g., `{ticket_alias}.Status AS CurrentStatus`).
10. RANKING/SORTING: If asked for "most expensive" or "highest", you MUST use `ORDER BY [ColumnName] DESC`.
11. ZERO ASSUMPTIONS: Do NOT guess. Do not add `WHERE` clauses for Status, Service, or Priority unless explicitly stated in the User Query or Active Search State.
12. DYNAMIC TIMEFRAMES (VARCHAR DATE FIX): The `{ticket_alias}.{date_col}` column is stored as a VARCHAR string, NOT a strict SQL DATE.
    - CRITICAL: DO NOT USE `MONTH()` or `YEAR()` directly on this column in WHERE clauses.
    - Instead, use `LIKE` with wildcards. For example, for December 2025, use: `WHERE ({ticket_alias}.{date_col} LIKE '%-12-2025' OR {ticket_alias}.{date_col} LIKE '2025-12-%')`.
    - DYNAMIC AWARENESS: Today's exact date is {current_date}. If the user asks for "this month", use the current month number ({current_month_num}) and year ({current_year}) in your LIKE clause!

13. STRICT PARENTHESES ON 'OR' (CRITICAL BUG FIX): Whenever you use an 'OR' operator (especially for checking multiple date formats or multiple locations), you MUST wrap the entire 'OR' condition in parentheses to prevent breaking the 'AND' logic of other filters.
    - FATAL ERROR: `WHERE branch.BranchSite LIKE '%Chen%' AND pt.PPMDate LIKE '%01-2026' OR pt.PPMDate LIKE '2026-01%'`
    - CORRECT: `WHERE branch.BranchSite LIKE '%Chen%' AND (pt.PPMDate LIKE '%01-2026' OR pt.PPMDate LIKE '2026-01%')`

=== ACTIVE SEARCH STATE (CRITICAL) ===
This state represents the ABSOLUTE TRUTH of the current filters. Even if the user's latest text query does not mention a filter, if it has a valid value in this state, YOU MUST APPLY IT using a `WHERE` clause.
MANDATORY: YOU MUST INCLUDE A `WHERE` CONDITION FOR EVERY SINGLE NON-NONE FILTER BELOW. DO NOT DROP ACTIVE FILTERS.
- Target Domain: {target_domain}
- Company Name: {state.get('company_name')}
- Branch Name: {state.get('branch_name')}
- Timeframe: {state.get('timeframe')}
- Status: {state.get('status')}
- Priority: {state.get('priority')}
- Service Category: {state.get('service_type')}

14. STRICT STATE ENFORCEMENT RULES (DO NOT SKIP):
    - ZERO DROPPED FILTERS (CRITICAL): Before outputting the SQL, you MUST mentally check the Active Search State. If a filter is NOT 'None', its specific `WHERE` condition MUST be in your query. No exceptions.
    - FATAL ERROR PREVENTION: Never use a column like `branch.BranchSite` or `company.CompanyName` in your query if you did not explicitly write the `JOIN` command for that table first!
    - TIMEFRAME: If the Timeframe state is a specific period (e.g., '2025', 'Nov', 'this month'), you MUST add a `WHERE` clause using `{ticket_alias}.{date_col}`. *CRITICAL EXCEPTION:* If the Timeframe state is just a generic grouping word (e.g., 'month', 'monthly', 'month wise', 'by month', 'year', 'yearly', 'trend', 'all time'), DO NOT add a `WHERE` clause for the date! Just let it fetch all records and `GROUP BY` the time period.
    - COMPANY: If Company Name is provided, you MUST `LEFT JOIN company` (ON {ticket_alias}.CorporateID = company.ID) AND `LEFT JOIN corporate` (ON company.CorporateName = corporate.ID) BEFORE using them in the WHERE clause. Then filter using: `(corporate.CorporateName LIKE '%[Name]%' OR company.CompanyName LIKE '%[Name]%')`.
    {_branch_where_clause_description(ticket_alias)}
    - PPM SERVICE ROUTING: If Service Category is provided for PPM tickets (e.g., HVAC, Electrical), you MUST `INNER JOIN` the corresponding service report table (e.g., `ppm_hvac_service_report`) ON `report_table.TicketID = ppm_tickets.ID` to filter the results. YOU MUST DO THIS IF IT IS IN THE STATE.
    - CORPORATE TYPE VS SERVICE ROUTING: If the domain is `corporate_tickets` and a Service Category is provided in the state:
        * If the value is 'AMC', 'R&M', 'Supply', 'Projects', or 'Booking', you MUST filter using the `Type` column (e.g., `ct.Type LIKE '%AMC%'`).
        * If the value is a specific trade (e.g., 'Electrician', 'CCTV', 'Interiors', 'Carpentry', 'Plumbing'), you MUST filter using the `Service` column (e.g., `ct.Service LIKE '%Electrician%'`).

15. READABLE NAMES OVER IDs (CRITICAL): NEVER output raw numeric IDs for Company, Branch, or Employees. Always LEFT JOIN the respective tables and select `company.CompanyName`, `branch.BranchSite`, or `employees.Name`.
"""

    if intent == "summary":
        base_instructions += f"""
16. SUMMARY MODE (STRICT COUNTS & GROUP BY): The user wants metrics, counts, averages, or charts.
    - SMART DEFAULTS (THE ANALYST MINDSET - CRITICAL): If the user types a short, vague request (e.g., "tickets in Dec", "Bangalore tickets", "closed tickets") and FORGETS to specify a breakdown (like "by company" or "by status"), YOU MUST ACT LIKE A SENIOR ANALYST. DO NOT just return a single total number or a raw list. You MUST automatically apply a `GROUP BY company.CompanyName` or `GROUP BY pt.Status` so the frontend can draw a beautiful visual chart. Always assume executives want visual breakdowns!
    - CRITICAL FILTER RETENTION (NO SILENT DROPS): Just because you are doing a grouping does NOT mean you can ignore the Active Search State! If the state has filters, your query MUST include the JOINs and WHERE clauses for them. DO NOT DROP STATE FILTERS.

    - ADVANCED METRICS (RESOLUTION TIME / AVERAGES): If the user asks for "average time", "time to close", "slowest", "fastest", or "resolution time":
        * Do NOT use COUNT().
        * Use `ROUND(AVG(GREATEST(DATEDIFF({ticket_alias}.CloseDate, {ticket_alias}.{date_col}), 0)), 1) AS AvgDaysToClose`.
        * (Note: GREATEST(..., 0) ensures that tickets closed earlier than their scheduled date count as 0 days late, preventing negative averages).
        * DATA CLEANSING (CRITICAL): You MUST add `AND {ticket_alias}.CloseDate IS NOT NULL AND {ticket_alias}.CloseDate != ''` to your WHERE clause.
        * Group by the requested category (e.g., Company, Branch) and `ORDER BY AvgDaysToClose DESC`.

    - STANDARD METRIC (COUNTS): If the user asks for "how many", "breakdown", or "total tickets" (and does NOT mention averages/time to close), you MUST ALWAYS use the `COUNT({ticket_alias}.TicketID) AS Count` function.

    - GLOBAL TOTALS: If the user asks for "all tickets" without specifying a breakdown category, return a single global metric (Count or Average).

    - TIME-SERIES / TREND ANALYSIS: If the user asks for a trend over time (e.g., "trend", "month wise", "by month"), you MUST extract the Year and Month from the `{ticket_alias}.{date_col}` string to group by it.
        * The dates in the database are stored as YYYY-MM-DD.
        * You MUST use `LEFT({ticket_alias}.{date_col}, 7)` AS TimePeriod to extract 'YYYY-MM'. Do NOT use RIGHT() or SUBSTRING().
        * Group by `TimePeriod` and order by `TimePeriod ASC`.

    - STRICT SQL FIX: When using `GROUP BY`, you are FORBIDDEN from using `SELECT *`. Your `SELECT` clause MUST ONLY contain the exact columns in the `GROUP BY`, plus the Metric (Count or Avg). Example: `SELECT company.CompanyName, COUNT({ticket_alias}.TicketID) AS Count FROM...`
    - TOP RESULTS LOGIC: Always append `LIMIT {SUMMARY_LIMIT}` to every summary query to ensure all grouped rows are returned.
"""
    else:
        base_instructions += f"""
16. DETAIL MODE (RAW TICKETS): The user wants a raw list of tickets.
    - RELEVANCY FIRST: You MUST order the results to show the most recent tickets first. Always use `ORDER BY {ticket_alias}.{date_col} DESC`.
    - LIMIT: ALWAYS append `LIMIT {DETAIL_LIMIT}` at the very end of the query.
"""

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt