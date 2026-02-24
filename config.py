import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

class Settings:
    # Database
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "")

    # Construct the SQLAlchemy Database URL
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    # AI
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-flash")

    # System Constraints
    MAX_ROWS_LIMIT = int(os.getenv("MAX_ROWS_LIMIT", 500))
    QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", 15))
    MAX_CLARIFICATION_TURNS = int(os.getenv("MAX_CLARIFICATION_TURNS", 1))
    ALLOWED_TABLE = os.getenv("ALLOWED_TABLE", "corporate_tickets")

settings = Settings()