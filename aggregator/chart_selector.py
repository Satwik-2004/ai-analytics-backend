from typing import List, Dict, Any, Tuple
from core.schemas import ChartData, KPI
from decimal import Decimal

def is_number(val: Any) -> bool:
    return isinstance(val, (int, float, Decimal))

def determine_visuals(rows: List[Dict[str, Any]], title: str = "Query Results") -> Tuple[List[KPI], List[ChartData]]:
    """
    Analyzes the SQL result set and determines the appropriate charts or KPIs.
    Returns a tuple of (kpis, charts).
    """
    if not rows:
        return [], []

    kpis = []
    charts = []
    
    # Get column names and a sample row to check data types
    sample_row = rows[0]
    columns = list(sample_row.keys())
    
    # ---------------------------------------------------------
    # SCENARIO 1: Single Number (KPI)
    # e.g., SELECT COUNT(*) FROM corporate_tickets
    # ---------------------------------------------------------
    if len(rows) == 1 and len(columns) == 1 and is_number(sample_row[columns[0]]):
        kpis.append(KPI(label=columns[0].replace("_", " ").title(), value=sample_row[columns[0]]))
        return kpis, charts

    # ---------------------------------------------------------
    # SCENARIO 2: Two Columns (Categories/Dates + Numbers) -> CHARTS
    # e.g., SELECT Status, COUNT(*) FROM corporate_tickets GROUP BY Status
    # ---------------------------------------------------------
    if len(columns) == 2:
        col1, col2 = columns[0], columns[1]
        
        # Identify which column is the label and which is the value
        label_col, value_col = None, None
        
        if is_number(sample_row[col2]):
            label_col, value_col = col1, col2
        elif is_number(sample_row[col1]):
            label_col, value_col = col2, col1
            
        if label_col and value_col:
            labels = [str(row[label_col]) for row in rows]
            values = [row[value_col] for row in rows]
            
            # Decide Chart Type
            chart_type = "bar" # Default
            
            # If the label looks like a date/time (contains hyphens or slashes)
            if any(char in str(sample_row[label_col]) for char in ['-', '/']):
                chart_type = "line"
            # If it's categorical and has 5 or fewer items, Pie chart looks better
            elif len(rows) <= 5:
                chart_type = "pie"
                
            charts.append(ChartData(
                type=chart_type,
                title=title,
                labels=labels,
                values=values
            ))
            
    return kpis, charts