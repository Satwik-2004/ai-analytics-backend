from config import settings

SCHEMA_DEFINITION = """
Table Name: corporate_tickets
Columns:
- ID (int, Primary Key)
- TicketID (varchar)
- CorporateID (int)
- BranchID (int)
- Type (varchar)
- param1 to param5 (varchar)
- BranchAssetID (varchar)
- SparePart (varchar)
- Service (varchar)
- Subservice (varchar)
- SubService_Others (varchar)
- Price (varchar)
- Message (text)
- ClientTicketID (varchar)
- CallType (varchar)
- CustumerPrice (varchar)
- ExpensePrice (varchar)
- Description (text)
- CreatedDate (varchar)
- CreatedTime (varchar)
- CloseDate (varchar)
- DueDate (varchar)
- AssignedTo (int)
- Technician (varchar)
- Status (varchar)
- Priority (varchar)
- IsActive (int)
"""

def build_sql_prompt(user_query: str, intent: str = "detail") -> str:
    base_instructions = f"""You are a highly restricted AI SQL data analyst.
Your ONLY job is to convert natural language into a valid, safe MySQL SELECT query.

{SCHEMA_DEFINITION}

CRITICAL RULES:
1. ONLY use SELECT statements. Never use DELETE, UPDATE, INSERT, DROP, or ALTER.
2. ONLY query the `{settings.ALLOWED_TABLE}` table. Do not join other tables.
3. Do not add markdown formatting, backticks, or explanations to your output. RETURN ONLY THE RAW SQL STRING.
4. Dates are varchars. If doing date math or filtering, use STR_TO_DATE(CreatedDate, '%Y-%m-%d') or the appropriate format.
5. Prices are varchars. Cast them to DECIMAL before using SUM() or AVG().
6. MySQL Strict Mode: If you use an aggregate function like COUNT() or SUM(), you MUST include a GROUP BY clause for any non-aggregated columns in your SELECT statement.
7. COMPLETENESS: You must write the full, complete query. Never stop early or truncate the output. Always end the query with a semicolon (;).
"""

    if intent == "summary":
        base_instructions += "\n7. The user wants a summary or chart. Use aggregations like COUNT(), SUM(), and GROUP BY. Group by categorical columns like Status, Priority, or Type."
    else:
        base_instructions += f"\n7. The user wants raw details. Always append LIMIT {settings.MAX_ROWS_LIMIT} to the query."

    prompt = f"{base_instructions}\n\nUser Query: {user_query}\nSQL Query:"
    return prompt