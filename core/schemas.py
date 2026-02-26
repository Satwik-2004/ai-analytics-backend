from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union

# -------------------------------------------------------------------
# REQUEST SCHEMAS (What React sends to the backend)
# -------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="The natural language query from the user")
    turn_count: int = Field(default=0, description="Tracks clarification loops to enforce the max 1 turn limit")
    # NEW: Accepts the current search state from React
    state: Optional[Dict[str, Any]] = Field(default=None, description="The current active JSON search state")

# -------------------------------------------------------------------
# RESPONSE SCHEMAS (What the backend sends to React)
# -------------------------------------------------------------------
class ChartData(BaseModel):
    type: str = Field(..., description="'pie', 'bar', or 'line'")
    title: str
    labels: List[str]
    values: List[Union[int, float]]

class KPI(BaseModel):
    label: str
    value: Union[int, float, str]

class QueryResponse(BaseModel):
    status: str = Field(..., description="'success', 'error', or 'clarification_required'")
    summary: str = Field(..., description="Executive summary or error/clarification message")
    kpis: List[KPI] = []
    charts: List[ChartData] = []
    raw_data: List[Dict[str, Any]] = []  # Array of row dictionaries
    insight: Optional[str] = None
    
    # Used ONLY if status is 'clarification_required'
    options: Optional[List[str]] = None
    
    # NEW: Returns the updated search state to React
    state: Optional[Dict[str, Any]] = Field(default=None, description="The newly updated JSON search state")