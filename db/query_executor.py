from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from typing import Dict, Any, Tuple, List
from db.connection import engine
from config import settings

def execute_query(sql_query: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Executes a validated read-only SQL query against the database.
    Returns: (is_success, rows_as_dicts, error_message)
    """
    if engine is None:
        return False, [], "Critical Error: Database engine is not initialized."

    try:
        with engine.connect() as connection:
            # 1. Enforce MySQL Session Timeout (converted to milliseconds)
            timeout_ms = settings.QUERY_TIMEOUT_SECONDS * 1000
            connection.execute(text(f"SET SESSION MAX_EXECUTION_TIME={timeout_ms}"))
            
            # 2. Execute the validated AI query
            result = connection.execute(text(sql_query))
            
            # 3. Extract column names
            keys = result.keys()
            
            # 4. Map the raw tuples into clean Python dictionaries
            rows = [dict(zip(keys, row)) for row in result.fetchall()]
            
            return True, rows, ""

    except OperationalError as e:
        # Catches timeouts and connection drops
        error_msg = str(e.orig)
        if "MAX_EXECUTION_TIME" in error_msg:
            return False, [], "Query timed out. The request was too large or complex."
        return False, [], f"Database operational error: {error_msg}"
        
    except SQLAlchemyError as e:
        # Catches general database execution errors
        return False, [], f"Database error: {str(e)}"
        
    except Exception as e:
        return False, [], f"Unexpected execution error: {str(e)}"