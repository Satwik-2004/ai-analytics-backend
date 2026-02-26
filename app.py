from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.concurrency import run_in_threadpool

# Import our custom schemas and pipeline layers
from core.schemas import QueryRequest, QueryResponse
from rules.input_validator import validate_user_query
from rules.sql_validator import validate_and_format_sql
from ai.state_manager import update_state  # NEW: Our JSON State Manager
from ai.prompt_builder import build_sql_prompt
from ai.sql_generator import generate_sql, generate_human_summary
from db.query_executor import execute_query
from aggregator.dashboard_aggregator import format_response

# Initialize the FastAPI App
app = FastAPI(
    title="Corporate Tickets AI Analytics",
    description="Stateful V4 NL-to-SQL Engine",
    version="4.0.0"
)

# Configure CORS so your local React app can communicate with it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    The main endpoint. Converts a natural language query into a structured dashboard response using Stateful Memory.
    """
    print(f"\n--- New Request: '{request.query}' ---")

    # 1. THE SHIELD: Input Validation
    validation_result = validate_user_query(request.query, request.turn_count)
    if not validation_result["is_valid"]:
        print("Blocked by Input Validator.")
        return QueryResponse(
            status=validation_result["status"],
            summary=validation_result["message"],
            options=validation_result.get("options"),
            state=request.state # Return existing state unchanged
        )

    # 2. THE BRAIN: State Management
    # Pass the user query and the previous state from the frontend to update it
    new_state = await update_state(request.query, request.state)
    print(f"Active Search State: {new_state}")
    
    # Extract intent for later use in dashboard formatting
    intent = new_state.get("intent", "detail")

    # 3. THE BUILDER: Prompt Building & SQL Generation (With 1 Retry Loop)
    max_retries = 1
    safe_sql = None
    sql_error = None

    for attempt in range(max_retries + 1):
        # Pass the entire new_state dictionary to strictly enforce filters
        prompt = build_sql_prompt(request.query, new_state)
        
        # SELF-HEALING AI: If this is a retry, feed the error back to the AI!
        if attempt > 0 and sql_error:
            print(f"Instructing AI to auto-correct: {sql_error}")
            prompt += f"\n\nCRITICAL FIX REQUIRED: Your previous SQL attempt failed with this error: '{sql_error}'. You MUST write the complete, valid SQL query and ensure all single quotes are closed!"
            
        # Generate raw SQL
        raw_sql = await generate_sql(prompt)
        print(f"Attempt {attempt + 1} Generated SQL: {raw_sql}")
        
        # --- TEXT INTERCEPTOR BYPASS ---
        # 1. Catch missing timeframes / clarification requests
        if raw_sql.strip().upper().startswith("CLARIFY:"):
            clarification_msg = raw_sql.strip()[8:].strip()
            print("Ambiguity Intercepted: Requesting clarification from user.")
            return QueryResponse(
                status="success",
                summary=clarification_msg,
                charts=[],
                raw_data=[],
                insight="Needs clarification",
                state=new_state # Return the updated state
            )
            
        # 2. Catch finance security boundaries
        elif raw_sql.strip().startswith("I do not have access"):
            print("Security Boundary Intercepted: Blocked finance query.")
            return QueryResponse(
                status="success",
                summary=raw_sql.strip(),
                charts=[],
                raw_data=[],
                insight="Security Block",
                state=new_state # Return the updated state
            )
        # ------------------------------------------
        
        # 4. THE SHIELD: SQL Validation & AST Parsing
        validation = validate_and_format_sql(raw_sql)
        
        if validation["is_valid"]:
            safe_sql = validation["safe_sql"]
            print("SQL Validation: PASSED")
            break
        else:
            sql_error = validation["error"]
            print(f"SQL Validation: FAILED - {sql_error}")

    # --- SAFETY NET ---
    if not safe_sql:
        print("All AI attempts failed. Aborting query.")
        return QueryResponse(
            status="error",
            summary="I'm sorry, I couldn't safely translate that into a database query. Could you try rephrasing?",
            insight=sql_error,
            state=new_state # Still return state so the user doesn't lose context on a fail
        )

    # 5. THE ENGINE: Database Execution
    print(f"Executing Safe SQL: {safe_sql}")
    is_success, rows, db_error = await run_in_threadpool(execute_query, safe_sql)

    # 6. THE PRESENTER: Dashboard Aggregation & Human Summary
    print("Generating human-readable summary...")
    
    safe_rows = rows if is_success else []
    
    # NEW: We pass the active state into the summary generator so it knows the domain
    ai_human_text = await generate_human_summary(
        request.query, 
        safe_rows, 
        state=new_state, 
        error_msg=db_error if not is_success else None
    )
    
    # Format the data (charts, KPIs, rows)
    final_payload = format_response(intent, safe_rows)
    
    # Attach the summary and the active state to the final response
    if isinstance(final_payload, dict):
        final_payload["summary"] = ai_human_text
        final_payload["state"] = new_state
    else:
        final_payload.summary = ai_human_text
        final_payload.state = new_state
    
    if not is_success:
        print(f"Handled Database Error gracefully: {db_error}")

    print("--- Request Complete ---\n")
    return final_payload

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)