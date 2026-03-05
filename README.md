# Corporate Tickets AI Analytics — Backend V3

> Enterprise-grade, stateful Natural Language-to-SQL (NL2SQL) AI agent built with FastAPI.

Ask questions about corporate and PPM ticket data in plain English. The engine remembers context across turns, enforces strict security boundaries, and returns validated SQL results formatted for dynamic dashboard rendering.

---

## Key Features

- **Stateful Memory** — A deterministic JSON State Tracker replaces raw chat history, remembering domain, company, branch, and timeframe across turns until explicitly cleared.
- **Anti-Hallucination Guardrails** — Strict prompt boundaries prevent the LLM from crossing column definitions between corporate and PPM domains.
- **Readable Data Enforcement** — Automatic JOINs on organizational tables ensure results always return human-readable names instead of raw numeric IDs.
- **Intelligent Domain Routing** — Auto-detects whether the query targets General Corporate Tickets or PPM and scopes SQL accordingly.
- **AST SQL Validator** — Parses AI-generated SQL via Abstract Syntax Trees to enforce read-only operations, block DoS functions, and cap row limits.
- **Self-Healing Retry Loop** — Catches malformed SQL and feeds errors back to the LLM for automatic correction before failing.
- **State-Aware Summary Engine** — Generates conversational, human-readable responses reflecting active filters, with graceful fallback on rate-limit or timeout.
- **Multi-Domain Relational Support** — Full LEFT JOIN support across 17 tables in 3 hierarchical domains: Corporate, PPM, and Organizational.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Python 3.x, FastAPI, Uvicorn |
| AI / LLM | Groq / Google Gemini (OpenAI SDK compatible) |
| Database | MySQL, PyMySQL, Cryptography |
| Security | SQLGlot (AST Parsing) |

---

## Project Structure
```
ai-analytics-backend/
├── app.py                        # Main FastAPI app, state injector, retry loop
├── config.py                     # Environment variables and allowed tables
├── requirements.txt
├── ai/                           # "The Brain"
│   ├── state_manager.py          # Extracts intent, maintains JSON filter state
│   ├── prompt_builder.py         # Injects 17-table schema, enforces active state rules
│   └── sql_generator.py          # LLM calls for SQL and state-aware summaries
├── rules/                        # "The Shield"
│   ├── input_validator.py        # Sanitizes input, blocks malicious prompts
│   └── sql_validator.py          # AST-based read-only SQL enforcement
├── db/
│   └── query_executor.py         # Executes validated SQL against MySQL
├── aggregator/
│   └── dashboard_aggregator.py   # Formats results into charts and KPIs
└── tests/
```

---

## Installation
```bash
git clone <repository-url>
cd ai-analytics-backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory:
```env
# AI
LLM_PROVIDER=your_provider
LLM_API_KEY=your_api_key_here
LLM_MODEL=llama-3.3-70b-versatile

# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_db

# Limits
MAX_ROWS_LIMIT=500
```

### Run
```bash
python app.py
```

- API: `http://localhost:8000/api/v1/query`
- Docs: `http://localhost:8000/docs`

---

## API Reference

**`POST /api/v1/query`**

**Request:**
```json
{
  "query": "What about the Mumbai branch?",
  "turn_count": 0,
  "state": {
    "intent": "summary",
    "domain": "ppm_tickets",
    "company_name": "Maruti Suzuki",
    "branch_name": null,
    "timeframe": "January 2026",
    "status": null,
    "priority": null,
    "service_type": null
  }
}
```

**Response:**
```json
{
  "status": "success",
  "summary": "Here is the breakdown of PPM tickets for Maruti Suzuki in the Mumbai branch...",
  "raw_data": [
    { "CurrentStatus": "Closed", "COUNT(pt.TicketID)": 120 },
    { "CurrentStatus": "Assigned", "COUNT(pt.TicketID)": 3 }
  ],
  "state": {
    "intent": "summary",
    "domain": "ppm_tickets",
    "company_name": "Maruti Suzuki",
    "branch_name": "Mumbai",
    "timeframe": "January 2026",
    "status": null,
    "priority": null,
    "service_type": null
  }
}
```

---

## Roadmap (V4)

- [ ] **RBAC** — Tenant-level isolation restricting data by logged-in user's corporate or branch permissions
- [ ] **Redis Caching** — Query caching for frequent or heavy analytical requests
- [ ] **Proactive Agents** — Background agents for weekly report generation, anomaly detection, and email distribution
