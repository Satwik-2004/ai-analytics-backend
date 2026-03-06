import time
from fastapi import FastAPI, BackgroundTasks
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

# Import the Intent Router and the new Audit Logger
from ai.router import route_user_query
from db.audit_logger import log_query_event

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
async def process_query(request: QueryRequest, background_tasks: BackgroundTasks):
    """
    The main endpoint. Converts a natural language query into a structured dashboard response using Stateful Memory.
    """
    start_time = time.time()
    print(f"\n--- New Request: '{request.query}' ---")

    # --- HELPER: BACKGROUND AUDIT LOGGER ---
    def dispatch_log(status: str, safe_state: dict, sql: str = "", rows: int = 0, error: str = ""):
        """Helper to fire off the background log right before we return a response."""
        exec_time_ms = int((time.time() - start_time) * 1000)
        background_tasks.add_task(
            log_query_event,
            session_id=None, # Ready for later!
            user_id=None,    # Ready for later!
            user_query=request.query,
            turn_count=request.turn_count,
            intent=safe_state.get("intent", "unknown") if safe_state else "unknown",
            active_domain=safe_state.get("domain", "") if safe_state else "",
            generated_sql=sql,
            execution_status=status,
            rows_returned=rows,
            error_message=error,
            execution_time_ms=exec_time_ms
        )
    # ---------------------------------------

    # 1. THE SHIELD: Input Validation
    validation_result = validate_user_query(request.query, request.turn_count)
    if not validation_result["is_valid"]:
        print("Blocked by Input Validator.")
        dispatch_log("Blocked_InputValidator", request.state, error=validation_result["message"])
        return QueryResponse(
            status=validation_result["status"],
            summary=validation_result["message"],
            options=validation_result.get("options"),
            suggested_actions=[],
            state=request.state # Return existing state unchanged
        )

    # --- INCOMPLETE COMMAND INTERCEPTOR ---
    query_lower = request.query.strip().lower()
    incomplete_commands = {
        "filter by status": "Sure! Which specific status are you looking for? (e.g., Closed, Cancel, Pending)",
        "show me open tickets": "Our system tracks a few types of active tickets. Which specific status are you looking for? (e.g., Pending, In Progress, Unassigned)",
        "filter by company": "Absolutely. Which company would you like to filter by?",
        "filter by branch": "Which branch location are you looking for?",
        "filter by timeframe": "What timeframe? (e.g., 'this month', '2025', or 'last 30 days')",
        "select timeframe": "What timeframe are you looking for? (e.g., '2025', 'last month', 'Q3')",
        "search by ticket id": "Please provide the exact Ticket ID you want me to look up.",
        "search tickets": "Please provide the exact Ticket ID, Company Name, or timeframe you are looking for.",
        "break this down further": "How would you like to break this down? You can narrow the results by applying a specific filter."
    }
    
    if query_lower in incomplete_commands:
        print(f"Incomplete command intercepted: '{query_lower}'")
        dispatch_log("Blocked_IncompleteCommand", request.state)

        # Explicitly inject the navigation buttons!
        nav_buttons = []
        if query_lower == 'break this down further':
            nav_buttons = ["Filter by Company", "Filter by Branch", "Filter by Timeframe", "Filter by Status"]
            
        return QueryResponse(
            status="success",
            summary=incomplete_commands[query_lower],
            suggested_actions=nav_buttons,
            charts=[],
            raw_data=[],
            insight="Clarification Required",
            state=request.state
        )
    # ------------------------------------------

    # 1.5 THE ROUTER (WITH ANALYSIS MODE BYPASS)
    system_buttons = [
        "break this down further",
        "clear search filters",
        "search ppm tickets",
        "search corporate tickets",
        "filter by status",
        "filter by company",
        "filter by branch",
        "filter by timeframe",
        "explore corporate tickets",
        "explore ppm tickets"
    ]
    
    # 1. ANALYSIS MODE: If the user already has active filters, they are actively drilling down. 
    # Do NOT let the Chatty Router interrupt them.
    is_in_analysis_mode = False
    if request.state:
        is_in_analysis_mode = any([
            request.state.get('company_name'),
            request.state.get('branch_name'),
            request.state.get('timeframe'),
            request.state.get('status'),
            request.state.get('service_type')
        ])

    # 2. DATA INTENT: If they use analytical phrases, skip the Router.
    analytical_phrases = ["how many", "what about", "break down", "show me", "filter", "count", "tickets"]
    is_analytical_query = any(phrase in query_lower for phrase in analytical_phrases)
    
    is_short_answer = len(request.query.split()) <= 2
    
    # THE ULTIMATE FAST PASS
    is_fast_pass = (query_lower in system_buttons) or is_short_answer or is_in_analysis_mode or is_analytical_query
    
    if not is_fast_pass:
        route_info = await route_user_query(request.query, request.state)
        
        if route_info.get("intent") in ["CHITCHAT", "UNSUPPORTED"]:
            print(f"Router Intercepted: {route_info['intent']}")
            dispatch_log(f"Router_{route_info.get('intent')}", request.state)
            return QueryResponse(
                status="success",
                summary=route_info.get("response_text", "How can I help you today?"),
                suggested_actions=route_info.get("suggested_actions", []),
                charts=[],
                raw_data=[],
                insight=route_info.get("intent"),
                state=request.state 
            )
    else:
        print(f"Fast-Pass Activated: Bypassing Router for '{request.query}'")

    # 2. THE BRAIN: State Management
    
    # --- THE MEMORY WIPE INTERCEPTOR ---
    fallback_commands = [
        "explore corporate tickets", 
        "explore ppm tickets", 
        "clear my filters and search all",
        "clear all filters",
        "show ppm all time",
        "show corporate all time",
        "show all statuses for ppm",
        "show all statuses for corporate"
    ]
    if query_lower in fallback_commands:
        print("Fallback button clicked: Wiping state memory for a fresh search.")
        request.state = None 
    # ----------------------------------------

    # Pass the user query and the (potentially wiped) state to update it
    new_state = await update_state(request.query, request.state)
    print(f"Active Search State: {new_state}")
    
    # Extract intent for later use in dashboard formatting
    intent = new_state.get("intent", "detail")

    # =====================================================================
    # --- THE ULTIMATE PYTHON-LEVEL VAGUE SEARCH INTERCEPTOR ---
    # =====================================================================
    has_filters = any([
        new_state.get('company_name'),
        new_state.get('branch_name'),
        new_state.get('timeframe'),
        new_state.get('status'),
        new_state.get('priority'),
        new_state.get('service_type')
    ])

    if intent == "detail" and not has_filters:
        print("Python-Level Vague Search Intercepted! Blocking DB dump.")
        domain_name = "PPM" if "ppm" in (new_state.get('domain') or '').lower() else "Corporate"
        
        dispatch_log("Blocked_VagueSearch", new_state)
        return QueryResponse(
            status="success",
            summary=f"I can certainly help you explore the {domain_name} tickets! Since there are a large number of records, could you help me narrow it down? You can filter by a specific Company Name, Timeframe (e.g., 'last month'), or Status (e.g., 'Pending').",
            suggested_actions=[
                f"{domain_name} tickets this month", 
                "Filter by Status", 
                "Breakdown by company"
            ],
            charts=[],
            raw_data=[],
            insight="Clarification Required",
            state=new_state
        )
    # =====================================================================

    # 3. THE BUILDER: Prompt Building & SQL Generation
    max_retries = 1
    safe_sql = None
    sql_error = None

    for attempt in range(max_retries + 1):
        prompt = build_sql_prompt(request.query, new_state)
        
        if attempt > 0 and sql_error:
            print(f"Instructing AI to auto-correct: {sql_error}")
            prompt += f"\n\nCRITICAL FIX REQUIRED: Your previous SQL attempt failed with this error: '{sql_error}'. You MUST write the complete, valid SQL query and ensure all single quotes are closed!"
            
        raw_sql = await generate_sql(prompt)
        print(f"Attempt {attempt + 1} Generated SQL: {raw_sql}")
        
        # --- TEXT INTERCEPTOR BYPASS ---
        if raw_sql.strip().upper().startswith("CLARIFY:"):
            clarification_msg = raw_sql.strip()[8:].strip()
            print("Ambiguity Intercepted: Requesting clarification from user.")
            
            dynamic_buttons = [
                "PPM tickets this month", 
                "Filter by Status", 
                "Breakdown by company"
            ] if "ppm" in request.query.lower() else [
                "Tickets this month", 
                "Filter by Status", 
                "Breakdown by company"
            ]
            
            dispatch_log("Clarification_Requested", new_state, sql=raw_sql)
            return QueryResponse(
                status="success",
                summary=clarification_msg,
                suggested_actions=dynamic_buttons,
                charts=[],
                raw_data=[],
                insight="Needs clarification",
                state=new_state
            )
            
        elif raw_sql.strip().startswith("I do not have access"):
            print("Security Boundary Intercepted: Blocked finance query.")
            dispatch_log("Blocked_Security", new_state, sql=raw_sql)
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
        dispatch_log("Error_SQLGeneration", new_state, error=sql_error)
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

    # --- 5.5 THE SUPERIOR ZERO-DATA FALLBACK ---
    if is_success and len(safe_rows) == 0:
        print("Zero rows returned. Triggering Smart Zero-Data Fallback.")
        
        # 1. Dynamically read active filters to explain WHY it failed
        active_filters = []
        if new_state.get('company_name'): active_filters.append(f"Company: {new_state['company_name']}")
        if new_state.get('branch_name'): active_filters.append(f"Branch: {new_state['branch_name']}")
        if new_state.get('timeframe'): active_filters.append(f"Timeframe: {new_state['timeframe']}")
        if new_state.get('status'): active_filters.append(f"Status: {new_state['status']}")
        if new_state.get('service_type'): active_filters.append(f"Service: {new_state['service_type']}")
        
        domain_str = "PPM" if "ppm" in (new_state.get('domain') or '').lower() else "Corporate"
        
        if active_filters:
            filter_str = " + ".join(active_filters)
            summary_msg = f"No {domain_str} tickets found for this exact combination: [{filter_str}]. Try broadening your search by dropping one of these filters."
            
            # 2. Build contextual pivot buttons
            smart_buttons = []
            if new_state.get('timeframe'): 
                smart_buttons.append(f"Show {domain_str} all time")
            if new_state.get('status'):
                smart_buttons.append(f"Show all statuses for {domain_str}")
                
            smart_buttons.append("Clear all filters")
        else:
            summary_msg = f"I couldn't find any data for that query in the {domain_str} database. What specific area should we look at?"
            smart_buttons = [f"Explore {domain_str} Tickets", "Clear all filters"]

        dispatch_log("Zero_Data_SmartFallback", new_state, sql=safe_sql)
        return QueryResponse(
            status="success",
            summary=summary_msg,
            suggested_actions=smart_buttons[:3], # Ensure we max out at 3 clean buttons
            charts=[],
            raw_data=[],
            insight="Zero Data Found",
            state=new_state # CRITICAL: We DO NOT wipe the state here. The user can see their pills.
        )
    # -----------------------------------------------------------

    # 6. THE PRESENTER: Dashboard Aggregation & Human Summary
    print("Formatting payload...")
    final_payload = format_response(intent, safe_rows)
    
    # SMART OUTPUT BYPASS (If it's a Fast-Pass, skip the chatty AI paragraph)
    if is_fast_pass and is_success and len(safe_rows) > 0:
        print("Fast-Pass Output: Skipping LLM summary. Using professional BI text.")
        limit_msg = " (Maximum display limit reached)" if len(safe_rows) >= 500 else ""
        
        if intent == "summary" and len(safe_rows) == 1 and len(safe_rows[0]) == 1:
            val = list(safe_rows[0].values())[0]
            ai_human_text = f"Metric calculated: {val}"
        else:
            ai_human_text = f"Data retrieved: {len(safe_rows)} records{limit_msg}."
    else:
        print("Generating human-readable summary via LLM...")
        ai_human_text = await generate_human_summary(
            request.query, 
            safe_rows, 
            state=new_state, 
            error_msg=db_error if not is_success else None
        )
    
    # Attach data to the payload
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
        dispatch_log("DB_Error", new_state, sql=safe_sql, error=str(db_error))
    else:
        dispatch_log("Success", new_state, sql=safe_sql, rows=len(safe_rows))

    print("--- Request Complete ---\n")
    return final_payload

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)