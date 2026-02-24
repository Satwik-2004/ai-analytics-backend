# 🏢 Corporate Tickets AI Analytics (Backend V1)

An enterprise-grade, Natural Language-to-SQL (NL2SQL) AI agent built with FastAPI. This engine allows users to ask questions about corporate ticket data in plain English and returns securely generated, validated database queries formatted for dynamic frontend dashboard rendering.

## ✨ Key Features

* **🧠 Intelligent Intent Routing:** Automatically classifies user queries into `SUMMARY` (aggregations, charts) or `DETAIL` (raw rows) to optimize database load and UI presentation.
* **🛡️ AST SQL Validator (The Shield):** Parses AI-generated SQL using Abstract Syntax Trees (`sqlglot`) before execution. It strictly enforces read-only operations (blocks `DROP`, `DELETE`, `UPDATE`), restricts queries to authorized tables, and enforces `LIMIT` clauses.
* **⚕️ Self-Healing Retry Loop:** If the AI generates malformed SQL, the system catches the error and feeds it back to the LLM for automatic correction before failing.
* **📊 Auto-Dashboard Aggregation:** Transforms raw MySQL rows into structured JSON payloads containing KPIs, Chart Configurations (Bar, Pie, etc.), and Raw Data arrays ready for immediate frontend rendering.

## 🛠️ Tech Stack

* **Framework:** Python 3.x, FastAPI, Uvicorn
* **AI / LLM:** Google Gemini (via OpenAI Python SDK compatibility layer)
* **Database:** MySQL / PyMySQL
* **Security:** SQLGlot (AST Parsing)

## 📁 Architecture & Folder Structure
```text
ai-analytics-backend/
├── app.py                 # The main FastAPI application and retry loop
├── config.py              # Environment variable management
├── requirements.txt       # Python dependencies
├── ai/                    # "The Brain"
│   ├── intent_classifier.py # Routes query as SUMMARY vs DETAIL
│   ├── prompt_builder.py    # Injects database schema and strict rules
│   └── sql_generator.py     # Calls the LLM to generate raw SQL
├── rules/                 # "The Shield"
│   ├── input_validator.py   # Sanitizes user input before AI processing
│   └── sql_validator.py     # Parses AST to ensure secure, read-only SQL
├── db/                    # "The Engine"
│   └── query_executor.py    # Safely executes validated SQL against MySQL
├── aggregator/            # "The Presenter"
│   └── dashboard_aggregator.py # Formats data into charts and KPIs
└── tests/                 # Unit testing suite
```

## 🚀 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/YourUsername/ai-analytics-backend.git
cd ai-analytics-backend
```

### 2. Create and activate a virtual environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# Mac/Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Variables

Create a `.env` file in the root directory. **(Do not commit this file to Git)**:
```env
# AI Configuration
LLM_PROVIDER=gemini
LLM_API_KEY=your_api_key_here
LLM_MODEL=gemini-flash-latest

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=techxpertindia

# Security Limits
ALLOWED_TABLE=corporate_tickets
MAX_ROWS_LIMIT=500
```

## 💻 Running the Application
```bash
python app.py
```

* **API URL:** http://localhost:8000/api/v1/query
* **Swagger UI:** http://localhost:8000/docs

## 📡 API Usage

**Endpoint:** `POST /api/v1/query`

**Request Body:**
```json
{
  "query": "Show me a breakdown of all tickets by their status.",
  "turn_count": 0
}
```

**Successful Response:**
```json
{
  "status": "success",
  "summary": "Here are your results.",
  "kpis": [],
  "charts": [
    {
      "type": "bar",
      "title": "Data Distribution",
      "labels": ["Open", "Closed", "Pending"],
      "values": [45, 120, 15]
    }
  ],
  "raw_data": [],
  "insight": null,
  "options": null
}
```

## 🛣️ Future Roadmap (V2)

* **Multi-Table Support:** Expanding the schema dictionary and updating the AST parser to support secure JOIN operations across 12+ relational tables.
* **Dynamic Charting:** Enhancing the chart selector to support Line charts for time-series data and Pie charts for percentage distributions.
