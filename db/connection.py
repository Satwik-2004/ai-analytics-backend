from sqlalchemy import create_engine
from config import settings

# Create the SQLAlchemy engine
# pool_pre_ping=True acts as a heartbeat, checking if the connection is alive before using it
try:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,          # Keep 5 connections open for speed
        max_overflow=10       # Allow up to 10 extra connections during traffic spikes
    )
    print(" Database engine initialized successfully.")
except Exception as e:
    print(f" Failed to initialize database engine: {e}")
    engine = None