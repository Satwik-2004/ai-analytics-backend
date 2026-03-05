from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.concurrency import run_in_threadpool

# Import our custom schemas and pipeline layers
from core.schemas import QueryRequest, QueryResponse
from rules.input_validator import validate_user_query
from rules.sql_validator import validate_and_format_sql
from ai.state_manager import update_state  # Our JSON State Manager
from ai.prompt_builder import build_sql_prompt
from ai.sql_generator import generate_sql, generate_human_summary
from db.query_executor import execute_query
from aggregator.dashboard_aggregator import format_response

# Import the Intent Router
from ai.router import route_user_query

# Initialize the FastAPI App
app = FastAPI(
    title="Corporate Tickets AI Analytics",
    description="Stateful V4 NL-to-SQL Engine with Guided Agent",
    version="4.1.0"
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
            suggested_actions=[],
            state=request.state # Return existing state unchanged
        )

    # --- NEW: INCOMPLETE COMMAND INTERCEPTOR ---
    # Catch incomplete phrases so the AI doesn't hallucinate a filter value (like 'open')
    query_lower = request.query.strip().lower()
    incomplete_commands = {
        "filter by status": "Sure! Which specific status are you looking for? (e.g., Closed, Cancel, Pending)",
        "filter by company": "Absolutely. Which company would you like to filter by?",
        "filter by branch": "Which branch location are you looking for?",
        "filter by timeframe": "What timeframe? (e.g., 'this month', '2025', or 'last 30 days')",
        "search by ticket id": "Please provide the exact Ticket ID you want me to look up.",
        "search tickets": "Please provide the exact Ticket ID, Company Name, or timeframe you are looking for."
    }
    
    if query_lower in incomplete_commands:
        print(f"Incomplete command intercepted: '{query_lower}'")
        return QueryResponse(
            status="success",
            summary=incomplete_commands[query_lower],
            suggested_actions=[],
            charts=[],
            raw_data=[],
            insight="Clarification Required",
            state=request.state
        )
    # ------------------------------------------

    # 1.5 THE ROUTER: Chit-chat and Out-of-Scope check
    # Call the router to check if this is even a database question
    route_info = await route_user_query(request.query, request.state)
    
    if route_info.get("intent") in ["CHITCHAT", "UNSUPPORTED"]:
        print(f"Router Intercepted: {route_info['intent']}")
        # Stop the pipeline entirely and return the chatty response with buttons
        return QueryResponse(
            status="success",
            summary=route_info.get("response_text", "How can I help you today?"),
            suggested_actions=route_info.get("suggested_actions", []),
            charts=[],
            raw_data=[],
            insight=route_info.get("intent"),
            state=request.state # Keep state exactly as it was
        )

    # 2. THE BRAIN: State Management
    
    # --- THE MEMORY WIPE INTERCEPTOR ---
    # If the user clicks a Zero-Data Fallback button, forcefully clear their filters 
    # so they don't get trapped in an infinite loop of 0 results!
    fallback_commands = [
        "explore corporate tickets", 
        "explore ppm tickets", 
        "clear my filters and search all"
    ]
    if request.query.strip().lower() in fallback_commands:
        print("Fallback button clicked: Wiping state memory for a fresh search.")
        request.state = None 
    # ----------------------------------------

    # Pass the user query and the (potentially wiped) state to update it
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
            
            # Use the intelligent, context-aware buttons we discussed!
            dynamic_buttons = [
                "PPM tickets this month", 
                "Show me open tickets", 
                "Breakdown by company"
            ] if "ppm" in request.query.lower() else [
                "Tickets this month", 
                "Show me open tickets", 
                "Breakdown by company"
            ]
            
            return QueryResponse(
                status="success",
                summary=clarification_msg,
                suggested_actions=dynamic_buttons,
                charts=[],
                raw_data=[],
                insight="Needs clarification",
                state=new_state
            )
            
        # 2. Catch finance security boundaries
        elif raw_sql.strip().startswith("I do not have access"):
            print("Security Boundary Intercepted: Blocked finance query.")
            return QueryResponse(
                status="success",
                summary=raw_sql.strip(),
                suggested_actions=["Explore Ticket Counts", "Explore Ticket Statuses"],
                charts=[],
                raw_data=[],
                insight="Security Block",
                state=new_state
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
            suggested_actions=["Start over", "Clear my filters"],
            insight=sql_error,
            state=new_state 
        )

    # 5. THE ENGINE: Database Execution
    print(f"Executing Safe SQL: {safe_sql}")
    is_success, rows, db_error = await run_in_threadpool(execute_query, safe_sql)
    
    safe_rows = rows if is_success else []

    # --- 5.5 THE ZERO-DATA FALLBACK ---
    if is_success and len(safe_rows) == 0:
        print("Zero rows returned. Triggering Zero-Data Fallback.")
        return QueryResponse(
            status="success",
            summary="I couldn't find any tickets matching those exact details. To help me narrow it down, what specific area should we look at?",
            suggested_actions=[
                "Explore Corporate Tickets", 
                "Explore PPM Tickets", 
                "Clear my filters and search all"
            ],
            charts=[],
            raw_data=[],
            insight="Zero Data Found",
            state=new_state # Keep the state so they can see what filters caused the zero data
        )

    # 6. THE PRESENTER: Dashboard Aggregation & Human Summary
    print("Generating human-readable summary...")
    
    # We pass the active state into the summary generator so it knows the domain
    ai_human_text = await generate_human_summary(
        request.query, 
        safe_rows, 
        state=new_state, 
        error_msg=db_error if not is_success else None
    )
    
    # Format the data (charts, KPIs, rows)
    # The aggregator (format_response) now correctly injects raw_data!
    final_payload = format_response(intent, safe_rows)
    
    # Attach the summary, state, and default dynamic buttons to the final response
    if isinstance(final_payload, dict):
        final_payload["summary"] = ai_human_text
        final_payload["state"] = new_state
        final_payload["suggested_actions"] = ["Break this down further", "Clear search filters"]
    else:
        final_payload.summary = ai_human_text
        final_payload.state = new_state
        final_payload.suggested_actions = ["Break this down further", "Clear search filters"]
    
    if not is_success:
        print(f"Handled Database Error gracefully: {db_error}")

    print("--- Request Complete ---\n")
    return final_payload

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)