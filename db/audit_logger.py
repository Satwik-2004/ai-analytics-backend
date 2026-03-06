import pymysql
from config import settings

def log_query_event(
    session_id: str,
    user_id: str,
    user_query: str,
    turn_count: int,
    intent: str,
    active_domain: str,
    generated_sql: str,
    execution_status: str,
    rows_returned: int,
    error_message: str,
    execution_time_ms: int
):
    """
    Inserts a comprehensive audit log into the database.
    Designed to be run as a FastAPI BackgroundTask so it doesn't block the UI.
    """
    try:
        # Connect to the database (Adjust to match your existing DB connection logic if needed)
        connection = pymysql.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            cursorclass=pymysql.cursors.DictCursor
        )
        
        with connection.cursor() as cursor:
            sql = """
                INSERT INTO ai_audit_logs 
                (SessionID, UserID, UserQuery, TurnCount, Intent, ActiveDomain, GeneratedSQL, ExecutionStatus, RowsReturned, ErrorMessage, ExecutionTimeMs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (
                session_id, user_id, user_query, turn_count, intent, active_domain, 
                generated_sql, execution_status, rows_returned, error_message, execution_time_ms
            ))
            
        connection.commit()
        connection.close()
        print(f" Audit Log Saved: [{execution_status}] ({execution_time_ms}ms)")
        
    except Exception as e:
        print(f" Failed to write audit log: {e}")