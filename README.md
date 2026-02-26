# Corporate Tickets AI Analytics (Backend V2)

* Enterprise-grade, Natural Language-to-SQL (NL2SQL) AI agent built with FastAPI
* Allows users to ask questions about corporate ticket data in plain English
* Returns securely generated, validated database queries formatted for dynamic frontend dashboard rendering

## Key Features

* Intelligent Intent Routing: Automatically classifies user queries into SUMMARY or DETAIL to optimize database load and UI presentation
* AST SQL Validator: Parses AI-generated SQL using Abstract Syntax Trees to strictly enforce read-only operations, block DoS functions, and enforce hard limits
* Self-Healing Retry Loop: Catches malformed SQL errors and feeds them back to the LLM for automatic correction before failing
* Auto-Dashboard Aggregation: Transforms raw MySQL rows into structured JSON payloads containing KPIs, Chart Configurations, and Raw Data arrays
* Two-Pass AI Summary Engine: Dynamically generates conversational, human-readable text explaining the data or gracefully handling database errors
* Clarification Interceptor: Catches ambiguous queries or missing timeframes and prompts the user for context before executing operations
* Short-Term Memory: Handles conversational follow-ups by intelligently merging original requests, clarifications, and user replies
* Multi-Table Relational Support: Fully supports complex JOIN operations across 12 database tables including history, finance, and quotations

## Tech Stack

* Framework: Python 3.x, FastAPI, Uvicorn
* AI / LLM: Google Gemini (via OpenAI Python SDK compatibility layer)
* Database: MySQL, PyMySQL, Cryptography (for MySQL 8.0+ caching_sha2_password)
* Security: SQLGlot (AST Parsing)

## Architecture & Folder Structure

```text
ai-analytics-backend/
├── app.py                 # The main FastAPI application, retry loop, and interceptor
├── config.py              # Environment variable management and allowed tables
├── requirements.txt       # Python dependencies
├── ai/                    # "The Brain"
│   ├── intent_classifier.py # Routes query as SUMMARY vs DETAIL
│   ├── prompt_builder.py    # Injects 12-table database schema and strict rules
│   └── sql_generator.py     # Calls the LLM to generate SQL and human summaries
├── rules/                 # "The Shield"
│   ├── input_validator.py   # Sanitizes user input and manages conversation turn limits
│   └── sql_validator.py     # Parses AST to ensure secure, read-only SQL
├── db/                    # "The Engine"
│   └── query_executor.py    # Safely executes validated SQL against MySQL
├── aggregator/            # "The Presenter"
│   └── dashboard_aggregator.py # Formats data into charts and KPIs
└── tests/                 # Unit testing suite

```

## Installation & Setup

* Clone the repository using git clone
* Create and activate a Python virtual environment
* Install dependencies using pip install -r requirements.txt
* Create a .env file in the root directory for configuration variables

## Environment Variables

```env
# AI Configuration
LLM_PROVIDER=your_provider
LLM_API_KEY=your_api_key_here
LLM_MODEL=your_model

# Database Configuration
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_db

# Security Limits
MAX_ROWS_LIMIT=500

```

## Running the Application

* Start the application by running python app.py
* Access the API endpoint at http://localhost:8000/api/v1/query
* Access the Swagger UI documentation at http://localhost:8000/docs

## API Usage

* Endpoint: POST /api/v1/query
* Request Body:

```json
{
  "query": "What is the total number of closed tickets last month?",
  "turn_count": 0
}

```

* Successful Response:

```json
{
  "status": "success",
  "summary": "There were 189 closed tickets in the last month across various service categories.",
  "kpis": [],
  "charts": [
    {
      "type": "bar",
      "title": "Data Distribution",
      "labels": ["Closed"],
      "values": [189]
    }
  ],
  "raw_data": [],
  "insight": null,
  "options": null
}

```

## Future Roadmap (V3)

* Implement Role-Based Access Control to restrict data retrieval based on specific user permissions
* Add a caching layer using Redis to serve frequent analytical queries instantly
* Develop agentic workflows for automated weekly report generation and email distribution
