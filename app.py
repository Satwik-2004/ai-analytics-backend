import time
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
import uvicorn

from core.schemas import QueryRequest, QueryResponse
from rules.input_validator import validate_user_query
from ai.state_manager import update_state
from ai.pipeline import sql_pipeline, summary_pipeline, DETAIL_PREVIEW_LIMIT
from db.query_executor import execute_query
from aggregator.dashboard_aggregator import format_response
from ai.router import route_user_query
from db.audit_logger import log_query_event
from interceptors import (
    check_incomplete_command,
    check_vague_search,
    check_zero_data,
    should_wipe_state,
    is_fast_pass,
)
from aggregator.smart_pills import generate_smart_pills

app = FastAPI(
    title="Corporate Tickets AI Analytics",
    description="Stateful V4 NL-to-SQL Engine with Guided Agent",
    version="4.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(request: QueryRequest, background_tasks: BackgroundTasks):
    start_time = time.time()
    print(f"\n--- New Request: '{request.query}' ---")
    query_lower = request.query.strip().lower()

    # ── AUDIT HELPER ────────────────────────────────────────────────────────
    def dispatch_log(status: str, state: dict, sql: str = "", rows: int = 0, error: str = ""):
        exec_time_ms = int((time.time() - start_time) * 1000)
        background_tasks.add_task(
            log_query_event,
            session_id=None,
            user_id=None,
            user_query=request.query,
            turn_count=request.turn_count,
            intent=state.get("intent", "unknown") if state else "unknown",
            active_domain=state.get("domain", "") if state else "",
            generated_sql=sql,
            execution_status=status,
            rows_returned=rows,
            error_message=error,
            execution_time_ms=exec_time_ms,
        )
    # ────────────────────────────────────────────────────────────────────────

    # 1. INPUT VALIDATION
    validation_result = validate_user_query(request.query, request.turn_count)
    if not validation_result["is_valid"]:
        dispatch_log("Blocked_InputValidator", request.state or {}, error=validation_result["message"])
        return QueryResponse(
            status=validation_result["status"],
            summary=validation_result["message"],
            options=validation_result.get("options"),
            suggested_actions=[],
            state=request.state,
        )

    # 2. INCOMPLETE COMMAND INTERCEPT
    intercept = check_incomplete_command(query_lower, request.state or {})
    if intercept:
        dispatch_log("Blocked_IncompleteCommand", request.state or {})
        return intercept

    # 3. ROUTER (skipped on fast-pass)
    if not is_fast_pass(query_lower, request.query, request.state):
        route_info = await route_user_query(request.query, request.state)
        if route_info.get("intent") in ["CHITCHAT", "UNSUPPORTED"]:
            dispatch_log(f"Router_{route_info['intent']}", request.state or {})
            return QueryResponse(
                status="success",
                summary=route_info.get("response_text", "How can I help you today?"),
                suggested_actions=route_info.get("suggested_actions", []),
                charts=[],
                raw_data=[],
                insight=route_info.get("intent"),
                state=request.state,
            )
    else:
        print(f"Fast-Pass Activated for '{request.query}'")

    # 4. STATE MANAGEMENT
    if should_wipe_state(query_lower):
        print("Memory wipe: resetting state for fresh search.")
        request.state = None

    new_state = await update_state(request.query, request.state)
    print(f"Active State: {new_state}")
    intent = new_state.get("intent", "detail")

    # 5. VAGUE SEARCH INTERCEPT (needs resolved state/intent)
    intercept = check_vague_search(intent, new_state)
    if intercept:
        dispatch_log("Blocked_VagueSearch", new_state)
        return intercept

    # 6. SQL PIPELINE (prompt -> generate -> validate, with retry)
    sql_result = await sql_pipeline(request.query, new_state)

    if sql_result.special_response:
        is_security = sql_result.special_response.startswith("I do not have access")
        dispatch_log(
            "Blocked_Security" if is_security else "Clarification_Requested",
            new_state,
            sql=sql_result.special_response,
        )
        domain_lower = request.query.lower()
        return QueryResponse(
            status="success",
            summary=sql_result.special_response,
            suggested_actions=(
                ["Explore Ticket Counts", "Explore Ticket Statuses"]
                if is_security else
                ["PPM tickets this month", "Filter by Status", "Breakdown by company"]
                if "ppm" in domain_lower else
                ["Tickets this month", "Filter by Status", "Breakdown by company"]
            ),
            charts=[],
            raw_data=[],
            insight="Security Block" if is_security else "Needs clarification",
            state=new_state,
        )

    if not sql_result.safe_sql:
        dispatch_log("Error_SQLGeneration", new_state, error=sql_result.error or "")
        return QueryResponse(
            status="error",
            summary="I'm sorry, I couldn't safely translate that into a database query. Could you try rephrasing?",
            suggested_actions=["Start over", "Clear my filters"],
            insight=sql_result.error,
            state=new_state,
        )

    # 7. DATABASE EXECUTION
    print(f"Executing SQL: {sql_result.safe_sql}")
    is_success, rows, db_error = await run_in_threadpool(execute_query, sql_result.safe_sql)
    safe_rows = rows if is_success else []

    # 8. ZERO DATA INTERCEPT
    if is_success and len(safe_rows) == 0:
        intercept = check_zero_data(safe_rows, new_state, sql_result.safe_sql)
        dispatch_log("Zero_Data_SmartFallback", new_state, sql=sql_result.safe_sql)
        return intercept

    # 9. SUMMARY / INSIGHT GENERATION
    # pipeline.py handles:
    #   - response type classification (COMPANY_BREAKDOWN / TIME_TREND / STATUS_DIST / etc.)
    #   - no-overpromising guardrail enforcement
    #   - honest count messaging for detail queries
    #   - total_count capture before any row slicing
    summary = await summary_pipeline(
        user_query=request.query,
        safe_rows=safe_rows,
        new_state=new_state,
        is_success=is_success,
        db_error=db_error,
        row_count=len(safe_rows),
    )

    # 10. ROW LIMIT STRATEGY
    #
    # SUMMARY intent → send ALL rows to the aggregator.
    #   Every company/status must appear in the chart/table.
    #   Showing only 50 of 200 companies = hiding data. Not acceptable.
    #
    # DETAIL intent → send only the 50 most recent rows to the frontend.
    #   The summary text already tells the user the full count honestly:
    #   "Found 312 tickets. Showing the 50 most recent — add a filter to narrow down."
    #   The smart pills will push the user to refine rather than scroll 312 rows.
    if intent == "detail" and len(safe_rows) > DETAIL_PREVIEW_LIMIT:
        display_rows = safe_rows[:DETAIL_PREVIEW_LIMIT]
        print(f"Detail preview: showing {DETAIL_PREVIEW_LIMIT} of {len(safe_rows)} rows.")
    else:
        display_rows = safe_rows

    # 11. SMART PILLS
    # total_count enables context-aware pills for detail mode:
    # if count > 50, primary pill is "Summarize this as a chart" rather than a drill-down.
    final_pills = generate_smart_pills(
        intent,
        new_state,
        query_lower,
        total_count=summary.total_count or len(safe_rows),
    )

    # 12. FORMAT & RETURN
    final_payload = format_response(
        intent=intent,
        rows=display_rows,          # correctly sliced: all rows for summary, 50 for detail
        summary_text=summary.text,
        state=new_state,
        suggested_actions=final_pills,
        limit_reached=summary.limit_reached,
    )

    if not is_success:
        dispatch_log("DB_Error", new_state, sql=sql_result.safe_sql, error=str(db_error))
    else:
        dispatch_log("Success", new_state, sql=sql_result.safe_sql, rows=len(safe_rows))

    print("--- Request Complete ---\n")
    return final_payload


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)