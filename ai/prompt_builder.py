from config import settings

# The Complete V2 Relational Data Dictionary (All 12 Tables)
SCHEMA_DEFINITION = """
1. Table: `corporate_tickets` (The Core Parent Table)
   - Columns: ID (int PK), TicketID (varchar), CorporateID (int), BranchID (int), Type (varchar), Service (varchar - CRITICAL: This column contains the trades/categories like 'CCTV', 'Electrician', 'Painting', 'Carpentry', 'Plumber'), Subservice (varchar), param1, param2, param3, Price, Status, Priority, CreatedDate, CreatedTime, CreatedBy.

2. Table: `corporate_ticket_status_history`
   - Columns: ID (int PK), TicketID (varchar FK), Status (varchar), Remarks (varchar), CreatedDate (date), CreatedTime (time), CreatedBy (varchar).
   - Notes: Tracks every status change a ticket goes through. Connects to `corporate_tickets` via `TicketID`.

3. Table: `corporate_tickets_finance`
   - Columns: ID (int PK), TicketID (varchar FK), T_TotalCost (decimal), C_TotalPrice (decimal), Status (varchar).
   - Notes: Tracks overall financial totals for a ticket. Connects to `corporate_tickets` via `TicketID`.

4. Table: `corporate_ticket_finance_status`
   - Columns: ID (int PK), Status (int), StatusName (varchar).
   - Notes: Lookup table for finance statuses. Connects to `corporate_tickets_finance.Status`.

5. Table: `corporate_tickets_quotation`
   - Columns: ID (int PK), TicketID (varchar FK), Status (int), Q_TotalAmount (decimal), CreatedDate (date).
   - Notes: Stores overall quotation details. Connects to `corporate_tickets` via `TicketID`.

6. Table: `corporate_ticket_quotation_status`
   - Columns: ID (int PK), Status (int), StatusName (varchar).
   - Notes: Lookup table for quotation statuses. Connects to `corporate_tickets_quotation.Status`.

7. Table: `corporate_tickets_quotation_items`
   - Columns: ID (int PK), TicketID (varchar FK), QuotationID (int FK), ItemName (varchar), ItemQty (int), ItemPrice (decimal), ItemTotalPrice (decimal).
   - Notes: Line items for a specific quotation. Connects to `corporate_tickets_quotation` via `QuotationID`.

8. Table: `corporate_ticket_payment_details`
   - Columns: ID (int PK), TicketID (varchar FK), PaymentType (varchar), PaymentAmount (decimal), PaymentDate (date).
   - Notes: Tracks individual payments made against a ticket.

9. Table: `corporate_ticket_general_service_report`
   - Columns: ID (int PK), TicketID (varchar FK), ReportDetails (varchar), CreatedDate (date).
   - Notes: General reports related to the service.

10. Table: `corporate_ticket_general_service_report_items`
    - Columns: ID (int PK), TicketID (varchar FK), GSRID (int FK), ItemDescription (varchar), Quantity (int).
    - Notes: Line items for general service reports.

11. Table: `corporate_tickets_old` (Archive Table)
    - Columns: ID (int PK), TicketID (varchar FK), CorporateID, BranchID, Type, Status, CreatedDate, CloseDate.
    - Notes: Historical archive of older tickets. Similar structure to `corporate_tickets`.

12. Table: `corporate_tickets_uploader` (Bulk Upload / Staging Table)
    - Columns: ID (int PK), ClientTicketID, BranchCode, BranchID, Category, Status, IsParsed, Inserted.
    - Notes: Used for tracking tickets uploaded in bulk before they are fully processed.
"""

def build_sql_prompt(user_query: str, intent: str = "detail") -> str:
    base_instructions = f"""You are an elite MySQL data analyst. 
Convert the user's natural language request into a highly optimized, read-only SELECT query.

{SCHEMA_DEFINITION}
CRITICAL RULES:
1. OUTPUT FORMAT: You must output ONLY the raw SQL query (no markdown, no `sql` tags). EXCEPTION: If the query triggers the Clarification Protocol (Rule 15), you must output ONLY the 'CLARIFY: ' string.
2. ALWAYS USE ALIASES: You must use table aliases for every single column in the query (e.g., `ct.TicketID`, NOT `TicketID`).
3. LIMIT RESULTS: Always append `LIMIT 500` to detail queries to prevent massive data dumps, unless a smaller limit is requested.
4. VALID JOINS ONLY: Only join tables if the user's question specifically requires data from them. Use LEFT JOINs to prevent data loss.
5. NO HALLUCINATION: Only use the exact tables and columns listed in the schema. Do not invent column names.
6. SINGLE QUOTES: Always use single quotes for string literals (e.g., `ct.Type = 'projects'`).
7. CASE INSENSITIVITY: Assume string comparisons might need wildcard matches if exact casing is unknown.
8. NEVER USE `*` WITH JOINS: If joining tables, do not use `SELECT *`. Explicitly select the relevant columns from both tables to avoid ambiguous column errors.
9. DO NOT OVER-JOIN: If the user just asks for general 'ticket details', ONLY query the `corporate_tickets` table unless they ask for history, finance, or quotations.
10. AMBIGUOUS STATUS: Both `corporate_tickets` and `corporate_ticket_status_history` have a `Status` column. Always alias them (e.g., `ct.Status AS CurrentStatus`).
11. SERVICE CATEGORY MATCHING: When a user asks for a specific trade, category, or service (e.g., "CCTV", "Electrician", "Painting", "Plumbing", "Carpentry"), you MUST filter using the `Service` column. Do NOT search the `Type` column for these. Example: `WHERE ct.Service LIKE '%Electrician%'`.
12. MANDATORY TIMEFRAMES FOR COUNTS: If the user asks ONLY for a count (e.g., "How many...", "Total number of..."), you MUST verify they provided a date or timeframe. If NO timeframe is in the query, you MUST abort and output the CLARIFY message from Rule 15. If a timeframe IS provided, use `SELECT COUNT(ct.ID)`. (Note: If the user asks for details AND a count, DO NOT use COUNT(), just select the rows `SELECT ct.*`).
13. RELATIVE DATES: Whenever a user asks for a relative time frame (like "last 1 year", "last month", "today"), NEVER hardcode a date string. You MUST use MySQL's built-in date math. Example for last 1 year: `WHERE CreatedDate >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)`.
14. TICKET HISTORY SEARCH: If a user asks for information, status, or details about a *specific* Ticket ID (e.g., "ticket 16511"), you MUST use a LEFT JOIN to combine the ticket info with its history. 
    Example Format: `SELECT ct.TicketID, ct.Type, ct.Status AS CurrentStatus, ct.Service, csh.Status AS HistoryStatus, csh.Remarks AS HistoryRemarks FROM corporate_tickets ct LEFT JOIN corporate_ticket_status_history csh ON ct.TicketID = csh.TicketID WHERE ct.TicketID LIKE '%16511%'`
15. THE CLARIFICATION PROTOCOL (CRITICAL OVERRIDE): This rule overrides all others. If a query is dangerously vague, or fails the timeframe check in Rule 12, DO NOT WRITE SQL. You MUST output exactly `CLARIFY: ` followed by a polite request for details. Example for missing timeframe: `CLARIFY: Could you please specify a timeframe for these tickets? (e.g., 'in the last 6 months' or 'this year')`. Example for too broad: `CLARIFY: That might return too much data. Could you please narrow it down by a specific Service, Status, or Date?`
16. FOLLOW-UP RESOLUTION: If the User Query contains an `[ORIGINAL REQUEST]` and a `[USER'S REPLY]`, you MUST seamlessly merge them together to write the SQL. For example, if the original request was "total closed tickets" and the reply is "last month", you must write a single query that counts closed tickets AND filters by the last month. Do NOT ask for clarification again.
17. LISTING AVAILABLE OPTIONS: If the user asks what options exist (e.g., "show all the tickets status we have", "what services are there"), do not use fuzzy matching. Use `SELECT DISTINCT Status FROM corporate_tickets` (or the relevant column) to list the unique categories.
"""

    if intent == "summary":
        base_instructions += f"\n18. The user wants a summary or chart. Use aggregations and GROUP BY logic. CRITICAL: If you use GROUP BY, you MUST append LIMIT 10 (or a specific number if the user asks) so we don't return thousands of chart categories."
    else:
        base_instructions += f"\n18. The user wants raw details. Return standard rows and ALWAYS append LIMIT {settings.MAX_ROWS_LIMIT}."

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt