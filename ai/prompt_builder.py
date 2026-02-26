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
   - Columns: ID (int PK), TicketID (varchar), CorporateID (int FK -> company.ID), BranchID (int FK -> branch.ID), BranchAssetID (varchar), PPMDate (varchar), CreatedDate (varchar), CreatedTime (varchar), CloseDate (varchar), CloseTime (varchar), CreatedBy (varchar), DueDate (varchar), AssignedTo (int), Status (varchar), IsActive (int).
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
"""

def build_sql_prompt(user_query: str, state: dict) -> str:
    # Extract intent from state (defaults to detail)
    intent = state.get("intent", "detail")
    
    base_instructions = f"""You are an elite MySQL data analyst. 
Convert the user's natural language request into a highly optimized, read-only SELECT query.

{SCHEMA_DEFINITION}

CRITICAL RULES:
1. STRICT SECURITY BOUNDARY (SUPERSEDES ALL): You do NOT have access to finance, billing, quotation, or payment tables. If requested, DO NOT write SQL. Output exactly: `I do not have access to financial or billing records for security reasons.`
2. OUTPUT FORMAT: Output ONLY raw valid SQL. No markdown formatting, no `sql` tags, and absolutely NO conversational filler.
3. ALWAYS USE ALIASES: Use table aliases for every column (e.g., `pt.TicketID`, NOT `TicketID`).
4. LIMIT RESULTS: Always append `LIMIT 500` to detail queries to prevent massive data dumps.
5. VALID JOINS ONLY: Use LEFT JOINs to prevent data loss. Join on `TicketID`. NOTE: For PPM Service Reports, `TicketID` may be stored as an INT.
6. NO COLUMN HALLUCINATION: Only use exact columns listed in the schema. CRITICAL: Do not ask for `Type`, `Service`, `Subservice`, or `Price` when querying `ppm_tickets`.
7. NEVER USE `*` WITH JOINS: Explicitly select relevant columns from both tables.
8. AMBIGUOUS STATUS: Always alias Status columns when joining (e.g., `pt.Status AS CurrentStatus`).
9. RANKING/SORTING: If asked for "most expensive" or "highest", you MUST use `ORDER BY [ColumnName] DESC`.
10. ZERO ASSUMPTIONS: Do NOT guess. Do not add `WHERE` clauses for Status, Service, or Priority unless explicitly stated in the User Query or Active State.
11. INTELLIGENT TIMEFRAMES: TODAY'S REFERENCE DATE: February 26, 2026. Use `DATE_SUB()` for rolling days (e.g., last 30 days) and `MONTH()/YEAR()` for calendar months.

=== ACTIVE SEARCH STATE (CRITICAL) ===
You MUST apply these filters to your SQL query. Do not ignore them. If a field says "None", do not filter by it.
- Target Domain: {state.get('domain')}
- Company Name: {state.get('company_name')}
- Branch Name: {state.get('branch_name')}
- Timeframe: {state.get('timeframe')}
- Status: {state.get('status')}
- Priority: {state.get('priority')}
- Service Category: {state.get('service_type')}

12. STATE ENFORCEMENT RULES:
    - If Target Domain contains 'ppm', query `ppm_tickets`. Otherwise, query `corporate_tickets`. NEVER JOIN THEM.
    - If Company Name is provided, JOIN `company` -> `corporate` (ON company.CorporateName = corporate.ID) and use `LIKE` with wildcards on BOTH tables: `(corporate.CorporateName LIKE '%[Name]%' OR company.CompanyName LIKE '%[Name]%')`.
    - If Branch Name is provided, JOIN `branch` (ON ticket_table.BranchID = branch.ID). CRITICAL FOREIGN KEY: `branch.CompanyID` maps to `corporate.ID`. Do NOT join `branch.CompanyID` to `company.ID`.
13. READABLE NAMES OVER IDs (CRITICAL): If the user asks for a breakdown, distribution, or grouping by Company or Branch, NEVER group by raw numeric IDs (`CorporateID` or `BranchID`). 
    - For Company breakdowns: You MUST `LEFT JOIN company` (ON ticket_table.CorporateID = company.ID) and `GROUP BY company.CompanyName`.
    - For Branch breakdowns: You MUST `LEFT JOIN branch` (ON ticket_table.BranchID = branch.ID) and `GROUP BY branch.BranchSite`.
"""

    if intent == "summary":
        base_instructions += f"\n14. SUMMARY MODE (STRICT GROUP BY): The user wants counts, charts, or breakdowns. Use aggregations (`COUNT()`) and `GROUP BY`. CRITICAL: Due to ONLY_FULL_GROUP_BY restrictions, your `SELECT` list must ONLY contain the exact column you are grouping by and the `COUNT()` function. Do not select un-grouped columns. Always append `LIMIT 10`."
    else:
        base_instructions += f"\n14. DETAIL MODE: The user wants raw details. Return standard rows and ALWAYS append `LIMIT {settings.MAX_ROWS_LIMIT}`."

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt