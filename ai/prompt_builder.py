from config import settings

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
    # Extract intent and domain from state
    intent = state.get("intent", "detail")
    target_domain = state.get('domain') or 'corporate_tickets'
    
    # Check if there are ANY specific filters applied in the current state
    has_filters = any([
        state.get('company_name'),
        state.get('branch_name'),
        state.get('timeframe'),
        state.get('status'),
        state.get('priority'),
        state.get('service_type')
    ])
    
    # Dynamically determine the exact base table, alias, and the correct DATE COLUMN
    base_table = "ppm_tickets pt" if "ppm" in target_domain.lower() else "corporate_tickets ct"
    ticket_alias = "pt" if "ppm" in target_domain.lower() else "ct"
    date_col = "CreatedDate" # Based on your previous business logic decision
    
    # NEW: The highly professional Dynamic Vague Search Interceptor
    if intent == "detail" and not has_filters:
        vague_rule = "2. THE \"VAGUE SEARCH\" INTERCEPTOR (TRIGGERED): The user is asking for ticket details, but there are NO active filters in the state. Querying without filters will dump the entire database. You are STRICTLY FORBIDDEN from writing SQL. You MUST reply EXACTLY with this string: `CLARIFY: I can certainly help you explore those tickets! Since there are a large number of records, could you help me narrow it down? You can filter by a specific Company Name, Timeframe (e.g., 'last month'), or Status (e.g., 'open').`"
    else:
        vague_rule = "2. THE \"VAGUE SEARCH\" INTERCEPTOR: If the user explicitly asks to search but provides no filter criteria, DO NOT write SQL. Instead, reply EXACTLY with this string: `CLARIFY: I can certainly help you explore those tickets! Since there are a large number of records, could you help me narrow it down? You can filter by a specific Company Name, Timeframe (e.g., 'last month'), or Status (e.g., 'open').`"
        
    base_instructions = f"""You are an elite MySQL data analyst. 
Convert the user's natural language request into a highly optimized, read-only SELECT query.

{SCHEMA_DEFINITION}

CRITICAL RULES:
1. STRICT SECURITY BOUNDARY (SUPERSEDES ALL): You do NOT have access to finance, billing, quotation, or payment tables. If requested, DO NOT write SQL. Output exactly: `I do not have access to financial or billing records for security reasons.`
{vague_rule}
3. OUTPUT FORMAT: Output ONLY raw valid SQL. No markdown formatting, no `sql` tags, and absolutely NO conversational filler.
4. ALWAYS USE ALIASES: Use table aliases for every column (e.g., `{ticket_alias}.TicketID`, NOT `TicketID`).
5. LIMIT RESULTS: Always append `LIMIT 500` to prevent massive data dumps.
6. MANDATORY BASE TABLE (CRITICAL FIX): You are FORBIDDEN from writing `FROM company`, `FROM corporate`, or `FROM branch`. Your query MUST begin EXACTLY with: `FROM {base_table}`. To get a list of companies or branches, you MUST query `{base_table}` and `LEFT JOIN` the company/branch tables!
7. VALID JOINS ONLY (CRITICAL KEY MAPPINGS): 
    - For standard tables, join on the indicated Foreign Keys.
    - PPM SERVICE REPORTS FIX: Tables like `ppm_hvac_service_report`, `ppm_ep_service_report`, etc., have a `TicketID` column that is an INT. This references `ppm_tickets.ID` (the integer primary key). You MUST join them like this: `JOIN ppm_hvac_service_report ON ppm_hvac_service_report.TicketID = ppm_tickets.ID`.
8. NO COLUMN HALLUCINATION: Only use exact columns listed in the schema. CRITICAL: Do not ask for `Type`, `Service`, `Subservice`, or `Price` when querying `ppm_tickets`.
9. NEVER USE `*` WITH JOINS: Explicitly select relevant columns from both tables.
10. AMBIGUOUS STATUS: Always alias Status columns when joining (e.g., `{ticket_alias}.Status AS CurrentStatus`).
11. RANKING/SORTING: If asked for "most expensive" or "highest", you MUST use `ORDER BY [ColumnName] DESC`.
12. ZERO ASSUMPTIONS: Do NOT guess. Do not add `WHERE` clauses for Status, Service, or Priority unless explicitly stated in the User Query or Active Search State.
13. INTELLIGENT TIMEFRAMES: The primary date column for this domain is `{ticket_alias}.{date_col}`. TODAY'S REFERENCE DATE: March 5, 2026. Use `DATE_SUB()` for rolling days and `MONTH()/YEAR()` for calendar months on the `{ticket_alias}.{date_col}` column.

=== ACTIVE SEARCH STATE (CRITICAL) ===
This state represents the ABSOLUTE TRUTH of the current filters. Even if the user's latest text query does not mention a filter, if it has a value in this state, YOU MUST APPLY IT using a `WHERE` clause. Do not ignore the state.
- Target Domain: {target_domain}
- Company Name: {state.get('company_name')}
- Branch Name: {state.get('branch_name')}
- Timeframe: {state.get('timeframe')}
- Status: {state.get('status')}
- Priority: {state.get('priority')}
- Service Category: {state.get('service_type')}

14. STATE ENFORCEMENT RULES:
    - TIMEFRAME (CRITICAL): If the Timeframe state is not None, you MUST add a `WHERE` clause using `{ticket_alias}.{date_col}` (e.g., `WHERE YEAR({ticket_alias}.{date_col}) = 2025`).
    - COMPANY: If Company Name is provided, you MUST `LEFT JOIN company` (ON {ticket_alias}.CorporateID = company.ID) AND `LEFT JOIN corporate` (ON company.CorporateName = corporate.ID) BEFORE using them in the WHERE clause. Then filter using: `(corporate.CorporateName LIKE '%[Name]%' OR company.CompanyName LIKE '%[Name]%')`.
    - BRANCH: If Branch Name is provided, JOIN `branch` (ON {ticket_alias}.BranchID = branch.ID). 
    - ANTI-SPELLING BUG (CRITICAL WILDCARDS): When filtering Branch or Company names with LIKE, use only the first 4 letters of the word, and wrap it in `%` (e.g., `LIKE '%Mumb%'`).
    - PPM SERVICE ROUTING: If Service Category is provided for PPM tickets (e.g., HVAC, Electrical), you MUST `INNER JOIN` the corresponding service report table (e.g., `ppm_hvac_service_report`) ON `report_table.TicketID = ppm_tickets.ID` to filter the results. YOU MUST DO THIS IF IT IS IN THE STATE.
    - CORPORATE TYPE VS SERVICE ROUTING: If the domain is `corporate_tickets` and a Service Category is provided in the state:
        * If the value is 'AMC', 'R&M', 'Supply', 'Projects', or 'Booking', you MUST filter using the `Type` column (e.g., `ct.Type LIKE '%AMC%'`).
        * If the value is a specific trade (e.g., 'Electrician', 'CCTV', 'Interiors', 'Carpentry', 'Plumbing'), you MUST filter using the `Service` column (e.g., `ct.Service LIKE '%Electrician%'`).

15. READABLE NAMES OVER IDs (CRITICAL): NEVER output raw numeric IDs for Company, Branch, or Employees. 
    - Always LEFT JOIN the respective tables and select `company.CompanyName`, `branch.BranchSite`, or `employees.Name`.
"""

    if intent == "summary":
        base_instructions += f"""
16. SUMMARY MODE (STRICT COUNTS & GROUP BY): The user wants metrics, counts, or charts.
    - MANDATORY METRIC: You MUST ALWAYS use the `COUNT()` function. NEVER return raw ticket rows in summary mode.
    - GLOBAL TOTALS: If the user asks for "all tickets", "total tickets", or asks "how many" without specifying a breakdown category, you MUST return a single global count: `SELECT COUNT({ticket_alias}.TicketID) AS TotalTickets FROM {base_table}`. (Apply WHERE clauses if the state has filters).
    - BREAKDOWNS: If the user asks for a list of names or a breakdown (e.g., "by company", "branch wise"), you MUST `GROUP BY` that column and use `COUNT({ticket_alias}.TicketID) AS Count`.
    - STRICT SQL FIX: When using `GROUP BY`, your `SELECT` clause MUST ONLY contain the columns in the `GROUP BY`, plus the `COUNT()`. NEVER select `{ticket_alias}.TicketID`.
    - TOP RESULTS LOGIC: For breakdowns, always append `ORDER BY Count DESC LIMIT 500`.
"""
    else:
        base_instructions += f"\n16. DETAIL MODE: Return standard rows and ALWAYS append `LIMIT {settings.MAX_ROWS_LIMIT}`."

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt