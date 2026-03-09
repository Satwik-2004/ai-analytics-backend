from config import settings
from datetime import datetime # NEW: Import datetime for dynamic time

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

def build_sql_prompt(user_query: str, state: dict) -> str:
    # 1. DYNAMIC DATE CALCULATION
    current_date = datetime.now().strftime("%B %d, %Y")
    current_year = datetime.now().strftime("%Y")
    current_month_num = datetime.now().strftime("%m")

    # Extract intent and domain from state
    intent = state.get("intent", "detail")
    target_domain = state.get('domain') or 'corporate_tickets'
    
    # Dynamically determine the exact base table, alias, and the correct DATE COLUMN
    base_table = "ppm_tickets pt" if "ppm" in target_domain.lower() else "corporate_tickets ct"
    ticket_alias = "pt" if "ppm" in target_domain.lower() else "ct"
    date_col = "PPMDate" if "ppm" in target_domain.lower() else "CreatedDate"
        
    base_instructions = f"""You are an elite MySQL data analyst. 
Convert the user's natural language request into a highly optimized, read-only SELECT query.

{SCHEMA_DEFINITION}

CRITICAL RULES:
1. STRICT SECURITY BOUNDARY (SUPERSEDES ALL): You do NOT have access to finance, billing, quotation, or payment tables. If requested, DO NOT write SQL. Output exactly: `I do not have access to financial or billing records for security reasons.`
2. OUTPUT FORMAT: Output ONLY raw valid SQL. No markdown formatting, no `sql` tags, and absolutely NO conversational filler.
3. ALWAYS USE ALIASES: Use table aliases for every column (e.g., `{ticket_alias}.TicketID`, NOT `TicketID`).
4. LIMIT RESULTS: Always append `LIMIT 500` to prevent massive data dumps.
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

=== ACTIVE SEARCH STATE (CRITICAL) ===
This state represents the ABSOLUTE TRUTH of the current filters. Even if the user's latest text query does not mention a filter, if it has a value in this state, YOU MUST APPLY IT using a `WHERE` clause. Do not ignore the state.
- Target Domain: {target_domain}
- Company Name: {state.get('company_name')}
- Branch Name: {state.get('branch_name')}
- Timeframe: {state.get('timeframe')}
- Status: {state.get('status')}
- Priority: {state.get('priority')}
- Service Category: {state.get('service_type')}

13. STRICT STATE ENFORCEMENT RULES (DO NOT SKIP):
    - FATAL ERROR PREVENTION: If a filter above is NOT 'None', you MUST write both the `JOIN` and the `WHERE` clause. Never use a column like `branch.BranchSite` or `company.CompanyName` in your query if you did not explicitly write the `JOIN` command for that table first!
    - TIMEFRAME: If the Timeframe state is a specific period (e.g., '2025', 'Nov', 'this month'), you MUST add a `WHERE` clause using `{ticket_alias}.{date_col}`. *CRITICAL EXCEPTION:* If the Timeframe state is just a generic grouping word (e.g., 'month', 'monthly', 'month wise', 'by month', 'year', 'yearly', 'trend', 'all time'), DO NOT add a `WHERE` clause for the date! Just let it fetch all records and `GROUP BY` the time period.
    - COMPANY: If Company Name is provided, you MUST `LEFT JOIN company` (ON {ticket_alias}.CorporateID = company.ID) AND `LEFT JOIN corporate` (ON company.CorporateName = corporate.ID) BEFORE using them in the WHERE clause. Then filter using: `(corporate.CorporateName LIKE '%[Name]%' OR company.CompanyName LIKE '%[Name]%')`.
    - BRANCH: If Branch Name is provided, you MUST `LEFT JOIN branch` (ON {ticket_alias}.BranchID = branch.ID) BEFORE filtering by branch. 
    - ANTI-SPELLING BUG (CRITICAL WILDCARDS): When filtering Branch or Company names with LIKE, use only the first 4 letters of the word, and wrap it in `%` (e.g., `LIKE '%Mumb%'`).
    - PPM SERVICE ROUTING: If Service Category is provided for PPM tickets (e.g., HVAC, Electrical), you MUST `INNER JOIN` the corresponding service report table (e.g., `ppm_hvac_service_report`) ON `report_table.TicketID = ppm_tickets.ID` to filter the results. YOU MUST DO THIS IF IT IS IN THE STATE.
    - CORPORATE TYPE VS SERVICE ROUTING: If the domain is `corporate_tickets` and a Service Category is provided in the state:
        * If the value is 'AMC', 'R&M', 'Supply', 'Projects', or 'Booking', you MUST filter using the `Type` column (e.g., `ct.Type LIKE '%AMC%'`).
        * If the value is a specific trade (e.g., 'Electrician', 'CCTV', 'Interiors', 'Carpentry', 'Plumbing'), you MUST filter using the `Service` column (e.g., `ct.Service LIKE '%Electrician%'`).

14. READABLE NAMES OVER IDs (CRITICAL): NEVER output raw numeric IDs for Company, Branch, or Employees. Always LEFT JOIN the respective tables and select `company.CompanyName`, `branch.BranchSite`, or `employees.Name`.
"""

    if intent == "summary":
        base_instructions += f"""
15. SUMMARY MODE (STRICT COUNTS & GROUP BY): The user wants metrics, counts, averages, or charts.
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
        
    - STRICT SQL FIX: When using `GROUP BY`, your `SELECT` clause MUST ONLY contain the columns in the `GROUP BY`, plus the Metric (Count or Avg). NEVER select `{ticket_alias}.TicketID`.
    - TOP RESULTS LOGIC: For non-time breakdowns, always append `LIMIT 500`.
"""
    else:
        base_instructions += f"\n15. DETAIL MODE: Return standard rows and ALWAYS append `LIMIT {settings.MAX_ROWS_LIMIT}`."

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt