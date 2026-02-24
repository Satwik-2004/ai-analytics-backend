from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.concurrency import run_in_threadpool

# Import our custom schemas and pipeline layers
from core.schemas import QueryRequest, QueryResponse
from rules.input_validator import validate_user_query
from rules.sql_validator import validate_and_format_sql
from ai.intent_classifier import classify_intent
from ai.prompt_builder import build_sql_prompt
from ai.sql_generator import generate_sql
from db.query_executor import execute_query
from aggregator.dashboard_aggregator import format_response

# Initialize the FastAPI App
app = FastAPI(
    title="Corporate Tickets AI Analytics",
    description="Internal V1 NL-to-SQL Engine",
    version="1.0.0"
)

# Configure CORS so your local React app (usually on port 3000 or 5173) can communicate with it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Note: In production, change "*" to your actual React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    The main endpoint. Converts a natural language query into a structured dashboard response.
    """
    print(f"\n--- New Request: '{request.query}' ---")

    # 1. THE SHIELD: Input Validation
    validation_result = validate_user_query(request.query, request.turn_count)
    if not validation_result["is_valid"]:
        print("Blocked by Input Validator.")
        return QueryResponse(
            status=validation_result["status"],
            summary=validation_result["message"],
            options=validation_result.get("options")
        )

    # 2. THE BRAIN: Intent Classification
    intent = await classify_intent(request.query)
    print(f"Detected Intent: {intent.upper()}")

    # 3. THE BRAIN: Prompt Building & SQL Generation (With 1 Retry Loop)
    max_retries = 1
    safe_sql = None
    sql_error = None

    for attempt in range(max_retries + 1):
        # Build prompt
        prompt = build_sql_prompt(request.query, intent)
        
        # SELF-HEALING AI: If this is a retry, feed the error back to the AI!
        if attempt > 0 and sql_error:
            print(f"Instructing AI to auto-correct: {sql_error}")
            prompt += f"\n\nCRITICAL FIX REQUIRED: Your previous SQL attempt failed with this error: '{sql_error}'. You MUST write the complete, valid SQL query and ensure all single quotes are closed!"
            
        # Generate raw SQL
        raw_sql = await generate_sql(prompt)
        print(f"Attempt {attempt + 1} Generated SQL: {raw_sql}")
        
        # 4. THE SHIELD: SQL Validation & AST Parsing
        validation = validate_and_format_sql(raw_sql)
        
        if validation["is_valid"]:
            safe_sql = validation["safe_sql"]
            print("SQL Validation: PASSED")
            break
        else:
            sql_error = validation["error"]
            print(f"SQL Validation: FAILED - {sql_error}")

        # --- ADD THIS NEW SAFETY NET HERE ---
        if not safe_sql:
            print("All AI attempts failed. Aborting query.")
            return QueryResponse(
                status="error",
                summary="I'm sorry, I couldn't safely translate that into a database query. Could you try rephrasing?",
                insight=sql_error
            )
    # ------------------------------------

        

            
    # 5. THE ENGINE: Database Execution
    print(f"Executing Safe SQL: {safe_sql}")
    is_success, rows, db_error = await run_in_threadpool(execute_query, safe_sql)

    if not is_success:
        print(f"Database Execution Error: {db_error}")
        return QueryResponse(
            status="error",
            summary="There was a problem retrieving the data from the database.",
            insight=db_error
        )

    # 6. THE PRESENTER: Dashboard Aggregation
    print(f"Rows returned: {len(rows)}")
    final_payload = format_response(intent, rows)
    
    print("--- Request Complete ---\n")
    return final_payload

# This allows you to run the file directly from the terminal
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)